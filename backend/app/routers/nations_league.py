"""Day 27: Nations League endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import GroupOut, GroupSummary
from app.services.nations_league import group_view, groups

router = APIRouter(prefix="/nations-league", tags=["nations league"])


@router.get("/groups", response_model=list[GroupSummary])
def list_groups(db: Session = Depends(get_db)):
    return [GroupSummary(group=g, teams=t) for g, t in groups(db).items()]


@router.get("/groups/{group}", response_model=GroupOut)
def get_group(group: str, db: Session = Depends(get_db),
              simulations: int = Query(10_000, ge=1_000, le=50_000)):
    """Current table, 10,000-season odds (quarter-finals, play-off, relegation) and fixtures."""
    view = group_view(db, group.upper(), simulations)
    if view is None:
        raise HTTPException(status_code=404, detail=f"No group '{group}'. Try /nations-league/groups")
    return view
