"""Day 28: player search, player page, and top scorers."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.competitions import CURRENT_SEASON
from app.database import get_db
from app.models import League, Player, PlayerSeasonStats
from app.schemas import PlayerDetail, PlayerOut, PlayerStatsOut, TopScorerOut
from app.services.players import search_key

router = APIRouter(tags=["players"])


def age(birth: date | None) -> int | None:
    if birth is None:
        return None
    today = date.today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def _out(p: Player) -> PlayerOut:
    return PlayerOut(id=p.id, name=p.name, position=p.position, nationality=p.nationality,
                     birth_date=p.birth_date, age=age(p.birth_date), shirt_number=p.shirt_number, team=p.team)


def _detail(p: Player) -> PlayerDetail:
    stats = [PlayerStatsOut(league_code=s.league.code, league=s.league.name, season=s.season,
                            team=s.team.name if s.team else None, appearances=s.appearances,
                            goals=s.goals, assists=s.assists, penalties=s.penalties)
             for s in sorted(p.stats, key=lambda s: (-s.season, s.league.code))]
    return PlayerDetail(**_out(p).model_dump(), stats=stats)


@router.get("/players", response_model=list[PlayerOut])
def search_players(db: Session = Depends(get_db),
                   search: str = Query(..., min_length=2, description="any part of the name, accents optional"),
                   team_id: int | None = None, limit: int = Query(20, ge=1, le=100)):
    """Search 'mbappe', 'Mbappé' or 'kylian': all find the same player.
    Players with goals this season come first."""
    goals = (select(PlayerSeasonStats.player_id, func.sum(PlayerSeasonStats.goals).label("goals"))
             .group_by(PlayerSeasonStats.player_id).subquery())
    query = (select(Player).options(joinedload(Player.team)).outerjoin(goals, goals.c.player_id == Player.id)
             .where(Player.search_name.contains(search_key(search))))
    if team_id:
        query = query.where(Player.team_id == team_id)
    query = query.order_by(func.coalesce(goals.c.goals, 0).desc(), Player.name).limit(limit)
    return [_out(p) for p in db.scalars(query).unique()]


@router.get("/players/{player_id}", response_model=PlayerDetail)
def get_player(player_id: int, db: Session = Depends(get_db)):
    player = db.scalar(select(Player).options(
        joinedload(Player.team), selectinload(Player.stats).joinedload(PlayerSeasonStats.league),
        selectinload(Player.stats).joinedload(PlayerSeasonStats.team)).where(Player.id == player_id))
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return _detail(player)


@router.get("/leagues/{code}/top-scorers", response_model=list[TopScorerOut])
def top_scorers(code: str, db: Session = Depends(get_db), season: int = CURRENT_SEASON,
                limit: int = Query(20, ge=1, le=100)):
    league = db.scalar(select(League).where(League.code == code))
    if league is None:
        raise HTTPException(status_code=404, detail=f"Unknown league '{code}'")
    rows = db.scalars(select(PlayerSeasonStats).options(joinedload(PlayerSeasonStats.player), joinedload(PlayerSeasonStats.team))
                      .where(PlayerSeasonStats.league_id == league.id, PlayerSeasonStats.season == season)
                      .order_by(PlayerSeasonStats.goals.desc(), PlayerSeasonStats.assists.desc().nulls_last(),
                                PlayerSeasonStats.appearances.nulls_last())
                      .limit(limit)).all()
    return [TopScorerOut(rank=i, player_id=r.player.id, name=r.player.name, team=r.team.name if r.team else None,
                         appearances=r.appearances, goals=r.goals, assists=r.assists, penalties=r.penalties)
            for i, r in enumerate(rows, start=1)]
