"""The bridge between the backend and the ML models from the ml folder.

Models are loaded from disk once and kept in memory (loading a file on every
request would be slow). After retraining, restart the server or call
reload_models().
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

import footiq.config as ml_config
from footiq.elo import EloGoalsModel, international_k
from footiq.registry import load_model, model_path

from app.config import get_settings
from app.models import League, Match, Prediction

CLUB_MODEL_KINDS = ["dixon_coles", "elo"]
_applied_results: set[int] = set()  # international results already added to the in-memory Elo


def _point_ml_at_models() -> None:
    ml_config.MODELS_DIR = get_settings().models_dir


@lru_cache(maxsize=32)
def get_model(model_key: str, kind: str = "dixon_coles"):
    _point_ml_at_models()
    return load_model(model_key, "elo" if model_key == "international" else kind)


def reload_models() -> None:
    get_model.cache_clear()
    _applied_results.clear()


def kinds_for(model_key: str) -> list[str]:
    return ["elo"] if model_key == "international" else CLUB_MODEL_KINDS


def available_models() -> list[str]:
    _point_ml_at_models()
    found = []
    for key in ["E0", "SP1", "D1", "I1", "F1"]:
        found += [f"{key}_{k}" for k in CLUB_MODEL_KINDS if model_path(key, k).exists()]
    if model_path("international").exists():
        found.append("international_elo")
    return found


def model_version() -> str | None:
    manifest = get_settings().models_dir / "manifest.json"
    if manifest.exists():
        return json.loads(manifest.read_text())["trained_at"][:19]
    return None


def known_team_names(model_key: str) -> list[str]:
    try:
        model = get_model(model_key)
    except FileNotFoundError:
        return []
    return sorted(model.ratings.ratings) if isinstance(model, EloGoalsModel) else list(model.teams)


def expected_goals(match: Match, kind: str) -> tuple[float, float]:
    model = get_model(match.league.model_key, kind)
    home, away = match.home_team.model_name, match.away_team.model_name
    if not home or not away:
        raise LookupError(f"No model name for {match.home_team.name if not home else match.away_team.name}")
    return model.expected_goals(home, away, neutral=match.neutral)


def apply_new_international_results(db: Session) -> int:
    """Finished international matches newer than the model's data move the Elo
    ratings (in memory), exactly like Day 11 did with the fixtures file."""
    try:
        model = get_model("international")
    except FileNotFoundError:
        return 0
    last = model.ratings.last_date
    query = (select(Match).join(League).options(joinedload(Match.home_team), joinedload(Match.away_team))
             .where(League.is_international, Match.status == "finished").order_by(Match.kickoff))
    applied = 0
    for m in db.scalars(query).unique():
        if m.id in _applied_results or (last is not None and m.kickoff.date() <= last.date()):
            continue
        if m.home_team.model_name and m.away_team.model_name and m.home_goals is not None:
            model.ratings.update(m.home_team.model_name, m.away_team.model_name, m.home_goals, m.away_goals,
                                 neutral=m.neutral, k=international_k(m.league.name))
            _applied_results.add(m.id)
            applied += 1
    return applied


def predict_match(db: Session, match: Match) -> list[Prediction]:
    """Create or refresh this match's predictions. Never touches a match that has kicked off."""
    if match.status != "scheduled":
        return []
    saved = []
    for kind in kinds_for(match.league.model_key):
        try:
            model = get_model(match.league.model_key, kind)
            result = model.predict(match.home_team.model_name, match.away_team.model_name, neutral=match.neutral)
        except (FileNotFoundError, LookupError, TypeError):
            continue
        pred = db.scalar(select(Prediction).where(Prediction.match_id == match.id, Prediction.model == kind))
        if pred is None:
            pred = Prediction(match_id=match.id, model=kind)
            db.add(pred)
        p, xg = result["probabilities"], result["expected_goals"]
        pred.home_win, pred.draw, pred.away_win = p["home_win"], p["draw"], p["away_win"]
        pred.expected_home_goals, pred.expected_away_goals = xg["home"], xg["away"]
        pred.top_scorelines = result["top_scorelines"]
        pred.model_version = model_version()
        saved.append(pred)
    return saved


def generate_predictions(db: Session, days_ahead: int = 14) -> dict:
    """Predict every scheduled match in the next `days_ahead` days."""
    applied = apply_new_international_results(db)
    now = datetime.now(timezone.utc)
    query = (select(Match).options(joinedload(Match.league), joinedload(Match.home_team), joinedload(Match.away_team))
             .where(Match.status == "scheduled", Match.kickoff >= now, Match.kickoff <= now + timedelta(days=days_ahead)))
    matches = list(db.scalars(query).unique())
    predicted = skipped = 0
    for match in matches:
        if match.home_team.model_name and match.away_team.model_name and predict_match(db, match):
            predicted += 1
        else:
            skipped += 1
    db.commit()
    return {"matches": len(matches), "predicted": predicted, "skipped_unknown_teams": skipped,
            "new_international_results": applied}
