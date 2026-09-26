"""Day 18: leagues, matches and predictions."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import get_db
from app.models import League, Match, Prediction
from app.schemas import LeagueOut, MatchDetail, MatchOut, PredictionOut

router = APIRouter(tags=["matches"])


def _load_match(db: Session, match_id: int) -> Match:
    match = db.scalar(select(Match).options(
        joinedload(Match.league), joinedload(Match.home_team), joinedload(Match.away_team),
        selectinload(Match.predictions)).where(Match.id == match_id))
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


@router.get("/leagues", response_model=list[LeagueOut])
def list_leagues(db: Session = Depends(get_db)):
    return db.scalars(select(League).order_by(League.id)).all()


@router.get("/matches", response_model=list[MatchOut])
def list_matches(
    db: Session = Depends(get_db),
    day: date | None = Query(None, alias="date", description="YYYY-MM-DD, in the tz timezone"),
    tz: str = Query("UTC", description="timezone for 'date', e.g. Asia/Kathmandu"),
    league: str | None = Query(None, description="league code, e.g. E0"),
    status: str | None = Query(None, pattern="^(scheduled|live|finished|postponed|cancelled)$"),
    team_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    query = select(Match).options(joinedload(Match.league), joinedload(Match.home_team), joinedload(Match.away_team))
    if day is not None:
        try:
            zone = ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(status_code=400, detail=f"Unknown timezone '{tz}'")
        start = datetime.combine(day, time.min, tzinfo=zone)
        query = query.where(Match.kickoff >= start, Match.kickoff < start + timedelta(days=1))
    if league:
        query = query.join(League).where(League.code == league)
    if status:
        query = query.where(Match.status == status)
    if team_id:
        query = query.where((Match.home_team_id == team_id) | (Match.away_team_id == team_id))
    query = query.order_by(Match.kickoff, Match.id).limit(limit).offset(offset)
    return db.scalars(query).unique().all()


@router.get("/matches/{match_id}", response_model=MatchDetail)
def get_match(match_id: int, db: Session = Depends(get_db)):
    return _load_match(db, match_id)


@router.get("/matches/{match_id}/prediction", response_model=PredictionOut)
def get_prediction(match_id: int, model: str = "dixon_coles", db: Session = Depends(get_db)):
    match = _load_match(db, match_id)
    pred = db.scalar(select(Prediction).where(Prediction.match_id == match.id, Prediction.model == model))
    if pred is None:
        raise HTTPException(status_code=404, detail=f"No {model} prediction for this match yet")
    return pred
