"""Day 19: the what-if engine over HTTP.

POST /matches/{id}/simulate   a real match from the database
POST /simulate                any two teams the models know
Both use footiq.simulate.what_if - the same code you tested in Week 1.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from footiq.simulate import MatchState, what_if

from app.database import get_db
from app.routers.matches import _load_match
from app.schemas import FreeSimulationIn, MatchStateIn, SimulationOut
from app.services.predictor import get_model, kinds_for, known_team_names

router = APIRouter(tags=["simulate"])


def _run(model, model_key: str, kind: str, home: str, away: str, neutral: bool, body: MatchStateIn) -> SimulationOut:
    lam_h, lam_a = model.expected_goals(home, away, neutral=neutral)
    state = MatchState(body.minute, body.home_goals, body.away_goals, body.home_red_cards, body.away_red_cards)
    result = what_if(lam_h, lam_a, state, rho=getattr(model, "rho", 0.0))
    return SimulationOut(
        home_team=home, away_team=away, model=kind, state=body,
        expected_goals_remaining=result["remaining_xg"],
        probabilities=result["probabilities"],
        top_scorelines=result["top_scorelines"],
    )


def _get_model_or_error(model_key: str, kind: str):
    if kind not in kinds_for(model_key):
        raise HTTPException(status_code=400, detail=f"Model must be one of {kinds_for(model_key)}")
    try:
        return get_model(model_key, kind)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail=f"Model {model_key}/{kind} isn't trained yet")


@router.post("/matches/{match_id}/simulate", response_model=SimulationOut)
def simulate_match(match_id: int, body: MatchStateIn, db: Session = Depends(get_db)):
    match = _load_match(db, match_id)
    key = match.league.model_key
    kind = "elo" if key == "international" else body.model
    model = _get_model_or_error(key, kind)
    home, away = match.home_team.model_name, match.away_team.model_name
    if not home or not away:
        raise HTTPException(status_code=422, detail="The model doesn't know one of these teams yet")
    neutral = match.neutral if body.neutral is None else body.neutral
    return _run(model, key, kind, home, away, neutral, body)


@router.post("/simulate", response_model=SimulationOut)
def simulate_any(body: FreeSimulationIn):
    key = body.competition
    kind = "elo" if key == "international" else body.model
    model = _get_model_or_error(key, kind)
    known = set(known_team_names(key))
    for team in (body.home_team, body.away_team):
        if team not in known:
            raise HTTPException(status_code=422, detail=f"Unknown team '{team}' for {key}")
    return _run(model, key, kind, body.home_team, body.away_team, bool(body.neutral), body)
