"""Days 22 and 24: fans' predictions, leaderboard, and Fan vs AI.

Locking works on the server, not in the app: even if someone edits the app,
the server refuses a prediction once the match has kicked off.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import League, Match, User, UserPrediction
from app.routers.auth import get_current_user, get_optional_user
from app.schemas import (FanVsAIOut, LeaderboardOut, LeaderboardRow, MyStatsOut, UserPredictionIn,
                         UserPredictionOut)
from app.services.scoring import streaks

router = APIRouter(tags=["predictions"])


def _open_match(db: Session, match_id: int) -> Match:
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.status != "scheduled" or match.kickoff <= datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="Predictions are locked: this match has already started")
    return match


def _mine(db: Session, user: User, match_id: int) -> UserPrediction | None:
    return db.scalar(select(UserPrediction).where(UserPrediction.user_id == user.id, UserPrediction.match_id == match_id))


# ---------- Day 22: make, change, see, delete your prediction ----------

@router.put("/matches/{match_id}/my-prediction", response_model=UserPredictionOut)
def save_prediction(match_id: int, body: UserPredictionIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Create or change your predicted score. Allowed until kickoff."""
    _open_match(db, match_id)
    pred = _mine(db, user, match_id)
    if pred is None:
        pred = UserPrediction(user_id=user.id, match_id=match_id)
        db.add(pred)
    pred.home_goals, pred.away_goals = body.home_goals, body.away_goals
    db.commit()
    db.refresh(pred)
    return pred


@router.get("/matches/{match_id}/my-prediction", response_model=UserPredictionOut)
def get_my_prediction(match_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pred = _mine(db, user, match_id)
    if pred is None:
        raise HTTPException(status_code=404, detail="You haven't predicted this match")
    return pred


@router.delete("/matches/{match_id}/my-prediction", status_code=204)
def delete_my_prediction(match_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _open_match(db, match_id)
    pred = _mine(db, user, match_id)
    if pred:
        db.delete(pred)
        db.commit()
    return Response(status_code=204)


@router.get("/me/predictions", response_model=list[UserPredictionOut])
def my_predictions(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                   status: str = Query("all", pattern="^(all|pending|scored)$"),
                   limit: int = Query(50, ge=1, le=200)):
    query = select(UserPrediction).where(UserPrediction.user_id == user.id)
    if status == "pending":
        query = query.where(UserPrediction.scored_at.is_(None))
    elif status == "scored":
        query = query.where(UserPrediction.scored_at.is_not(None))
    return db.scalars(query.order_by(UserPrediction.created_at.desc()).limit(limit)).all()


# ---------- Day 24: stats, leaderboard, Fan vs AI ----------

def fan_vs_ai(db: Session, user_id: int | None = None) -> FanVsAIOut:
    """Compare fans and FOOTIQ on the same matches. user_id=None means all fans together."""
    query = select(UserPrediction).where(UserPrediction.scored_at.is_not(None), UserPrediction.ai_points.is_not(None))
    if user_id is not None:
        query = query.where(UserPrediction.user_id == user_id)
    rows = db.scalars(query).all()
    fan_wins = sum(r.points > r.ai_points for r in rows)
    ai_wins = sum(r.points < r.ai_points for r in rows)
    return FanVsAIOut(
        matches=len(rows), fan_points=sum(r.points for r in rows), ai_points=sum(r.ai_points for r in rows),
        fan_wins=fan_wins, ai_wins=ai_wins, ties=len(rows) - fan_wins - ai_wins,
    )


def my_rank(db: Session, user_id: int) -> int | None:
    totals = (select(UserPrediction.user_id, func.sum(UserPrediction.points).label("pts"))
              .where(UserPrediction.scored_at.is_not(None)).group_by(UserPrediction.user_id).subquery())
    mine = db.scalar(select(totals.c.pts).where(totals.c.user_id == user_id))
    if mine is None:
        return None
    return db.scalar(select(func.count()).select_from(totals).where(totals.c.pts > mine)) + 1


def user_stats(db: Session, user: User) -> MyStatsOut:
    scored = db.scalars(select(UserPrediction).join(Match).where(
        UserPrediction.user_id == user.id, UserPrediction.scored_at.is_not(None)).order_by(Match.kickoff)).all()
    pending = db.scalar(select(func.count()).select_from(UserPrediction).where(
        UserPrediction.user_id == user.id, UserPrediction.scored_at.is_(None)))
    return MyStatsOut(
        username=user.username, points=sum(p.points for p in scored), predictions_scored=len(scored),
        predictions_pending=pending,
        correct_results=sum(1 for p in scored if p.breakdown and ("result" in p.breakdown or "draw" in p.breakdown)),
        exact_scores=sum(1 for p in scored if p.breakdown and "exact_score" in p.breakdown),
        streak=streaks(scored), rank=my_rank(db, user.id), fan_vs_ai=fan_vs_ai(db, user.id),
    )


@router.get("/me/stats", response_model=MyStatsOut)
def my_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return user_stats(db, user)


@router.get("/me/fan-vs-ai", response_model=FanVsAIOut)
def my_fan_vs_ai(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return fan_vs_ai(db, user.id)


@router.get("/fan-vs-ai", response_model=FanVsAIOut)
def everyone_vs_ai(db: Session = Depends(get_db)):
    """All fans together against FOOTIQ."""
    return fan_vs_ai(db)


@router.get("/leaderboard", response_model=LeaderboardOut)
def leaderboard(db: Session = Depends(get_db), user: User | None = Depends(get_optional_user),
                period: str = Query("all", pattern="^(week|month|all)$"),
                league: str | None = Query(None, description="league code, e.g. E0"),
                limit: int = Query(50, ge=1, le=200)):
    """Ranking by points. Ties: more exact scores first, then fewer predictions (more efficient)."""
    exact = func.sum(case((UserPrediction.breakdown["exact_score"].as_string().is_not(None), 1), else_=0))
    query = (select(User.id, User.username, func.sum(UserPrediction.points).label("points"),
                    func.count(UserPrediction.id).label("predictions"), exact.label("exact_scores"))
             .join(UserPrediction, UserPrediction.user_id == User.id).join(Match, Match.id == UserPrediction.match_id)
             .where(UserPrediction.scored_at.is_not(None)))
    if period != "all":
        days = 7 if period == "week" else 30
        query = query.where(Match.kickoff >= datetime.now(timezone.utc) - timedelta(days=days))
    if league:
        query = query.join(League, League.id == Match.league_id).where(League.code == league)
    query = query.group_by(User.id, User.username).order_by(
        func.sum(UserPrediction.points).desc(), exact.desc(), func.count(UserPrediction.id), User.username)

    rows, rank, previous = [], 0, None
    for i, r in enumerate(db.execute(query).all(), start=1):
        key = (r.points, r.exact_scores)
        rank = rank if key == previous else i  # equal points and exact scores share a rank
        previous = key
        rows.append(LeaderboardRow(rank=rank, user_id=r.id, username=r.username, points=r.points,
                                   predictions=r.predictions, exact_scores=r.exact_scores))
    me = next((row for row in rows if user and row.user_id == user.id), None)
    return LeaderboardOut(period=period, league=league, rows=rows[:limit], me=me)
