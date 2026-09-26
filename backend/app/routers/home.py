"""Day 26: favorite teams and leagues, and the personalised home screen."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import get_db
from app.models import FavoriteLeague, FavoriteTeam, League, Match, Team, User, UserPrediction
from app.routers.auth import get_current_user
from app.routers.predictions import user_stats
from app.schemas import FavoritesIn, FavoritesOut, HomeOut, TeamOut, UserPredictionOut

router = APIRouter(tags=["home"])
MAX_FAVORITES = 20


def _zone(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=400, detail=f"Unknown timezone '{tz}'")


@router.get("/teams", response_model=list[TeamOut])
def list_teams(db: Session = Depends(get_db), search: str | None = None,
               league: str | None = Query(None, description="league code, e.g. E0"),
               limit: int = Query(50, ge=1, le=200)):
    """For the 'pick your teams' screen."""
    query = select(Team)
    if search:
        query = query.where(Team.name.ilike(f"%{search}%"))
    if league:
        in_league = (select(Match.home_team_id).join(League).where(League.code == league)
                     .union(select(Match.away_team_id).join(League).where(League.code == league)))
        query = query.where(Team.id.in_(in_league))
    return db.scalars(query.order_by(Team.name).limit(limit)).all()


def _favorites(db: Session, user: User) -> FavoritesOut:
    teams = db.scalars(select(Team).join(FavoriteTeam, FavoriteTeam.team_id == Team.id)
                       .where(FavoriteTeam.user_id == user.id).order_by(Team.name)).all()
    leagues = db.scalars(select(League).join(FavoriteLeague, FavoriteLeague.league_id == League.id)
                         .where(FavoriteLeague.user_id == user.id).order_by(League.id)).all()
    return FavoritesOut(teams=teams, leagues=leagues)


@router.get("/me/favorites", response_model=FavoritesOut)
def get_favorites(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _favorites(db, user)


@router.put("/me/favorites", response_model=FavoritesOut)
def set_favorites(body: FavoritesIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Replace your favorites with this list (send everything you want to keep)."""
    team_ids, codes = set(body.team_ids), set(body.league_codes)
    if len(team_ids) > MAX_FAVORITES or len(codes) > MAX_FAVORITES:
        raise HTTPException(status_code=400, detail=f"At most {MAX_FAVORITES} teams and {MAX_FAVORITES} leagues")
    teams = db.scalars(select(Team).where(Team.id.in_(team_ids))).all() if team_ids else []
    leagues = db.scalars(select(League).where(League.code.in_(codes))).all() if codes else []
    if len(teams) != len(team_ids):
        raise HTTPException(status_code=400, detail=f"Unknown team ids: {sorted(team_ids - {t.id for t in teams})}")
    if len(leagues) != len(codes):
        raise HTTPException(status_code=400, detail=f"Unknown leagues: {sorted(codes - {lg.code for lg in leagues})}")
    db.execute(delete(FavoriteTeam).where(FavoriteTeam.user_id == user.id))
    db.execute(delete(FavoriteLeague).where(FavoriteLeague.user_id == user.id))
    db.add_all([FavoriteTeam(user_id=user.id, team_id=t.id) for t in teams])
    db.add_all([FavoriteLeague(user_id=user.id, league_id=lg.id) for lg in leagues])
    db.commit()
    return _favorites(db, user)


@router.get("/me/home", response_model=HomeOut)
def home(db: Session = Depends(get_db), user: User = Depends(get_current_user),
         tz: str = Query("UTC", description="your timezone, e.g. Asia/Kathmandu")):
    """Everything the home screen needs, in one request."""
    zone = _zone(tz)
    now = datetime.now(zone)
    start_today = datetime.combine(now.date(), time.min, tzinfo=zone)
    today = (Match.kickoff >= start_today, Match.kickoff < start_today + timedelta(days=1))

    fav_team_ids = select(FavoriteTeam.team_id).where(FavoriteTeam.user_id == user.id)
    fav_league_ids = select(FavoriteLeague.league_id).where(FavoriteLeague.user_id == user.id)
    is_favorite = or_(Match.home_team_id.in_(fav_team_ids), Match.away_team_id.in_(fav_team_ids),
                      Match.league_id.in_(fav_league_ids))
    my_match_ids = select(UserPrediction.match_id).where(UserPrediction.user_id == user.id)
    loaded = (joinedload(Match.league), joinedload(Match.home_team), joinedload(Match.away_team),
              selectinload(Match.predictions))

    upcoming = db.scalars(select(Match).options(*loaded).where(
        is_favorite, Match.status.in_(["scheduled", "live"]), Match.kickoff >= now - timedelta(hours=3),
        Match.kickoff <= now + timedelta(days=7)).order_by(Match.kickoff).limit(10)).unique().all()
    to_predict = db.scalars(select(Match).options(*loaded).where(
        is_favorite, Match.status == "scheduled", Match.kickoff > now, Match.kickoff <= now + timedelta(days=7),
        Match.id.not_in(my_match_ids)).order_by(Match.kickoff).limit(5)).unique().all()
    recent = db.scalars(select(UserPrediction).where(
        UserPrediction.user_id == user.id, UserPrediction.scored_at.is_not(None))
        .order_by(UserPrediction.scored_at.desc()).limit(5)).all()

    count = lambda *where: db.scalar(select(func.count()).select_from(Match).where(*where))
    return HomeOut(
        username=user.username,
        local_time=now.isoformat(timespec="minutes"),
        today={"matches": count(*today), "live": count(Match.status == "live"),
               "your_predictions": db.scalar(select(func.count()).select_from(UserPrediction).join(Match).where(
                   UserPrediction.user_id == user.id, *today))},
        stats=user_stats(db, user),
        favorite_matches=upcoming,
        needs_your_prediction=to_predict,
        recent_results=[UserPredictionOut.model_validate(r) for r in recent],
        has_favorites=bool(db.scalar(select(func.count()).select_from(FavoriteTeam).where(FavoriteTeam.user_id == user.id))
                           or db.scalar(select(func.count()).select_from(FavoriteLeague).where(FavoriteLeague.user_id == user.id))),
    )
