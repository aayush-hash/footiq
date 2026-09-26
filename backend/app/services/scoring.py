"""Day 23: scoring. Award points once a match finishes, to fans and to the AI.

Points for a predicted score (change them here; nothing else needs to change):
  correct result (home win or away win)   +5
  correct draw (draws are harder)         +7
  correct goal difference (wins only)     +8    e.g. said 2-0, it ended 3-1
  exact score                             +15
  over/under 2.5 goals correct            +5    e.g. said 2-1 (3 goals), it ended 3-2 (5 goals): both "over"

The AI plays by the same rules. Its pick is FOOTIQ's most likely result, with
the most likely score for that result, taken from the prediction frozen at
kickoff. That makes Fan vs AI a fair fight.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Match, Prediction, UserPrediction

POINTS = {"result": 5, "draw": 7, "goal_difference": 8, "exact_score": 15, "over_under": 5}
AI_MODEL_PREFERENCE = ["dixon_coles", "elo"]


def outcome(home: int, away: int) -> str:
    return "H" if home > away else ("A" if home < away else "D")


def score_prediction(pred_home: int, pred_away: int, real_home: int, real_away: int) -> tuple[int, dict]:
    """Points for one prediction, and where they came from."""
    breakdown = {}
    predicted, actual = outcome(pred_home, pred_away), outcome(real_home, real_away)
    if predicted == actual:
        if actual == "D":
            breakdown["draw"] = POINTS["draw"]
        else:
            breakdown["result"] = POINTS["result"]
            if pred_home - pred_away == real_home - real_away:
                breakdown["goal_difference"] = POINTS["goal_difference"]
    if (pred_home, pred_away) == (real_home, real_away):
        breakdown["exact_score"] = POINTS["exact_score"]
    if (pred_home + pred_away > 2.5) == (real_home + real_away > 2.5):
        breakdown["over_under"] = POINTS["over_under"]
    return sum(breakdown.values()), breakdown


def ai_pick(match: Match) -> tuple[int, int] | None:
    """FOOTIQ's own predicted score for a match, from its frozen prediction."""
    by_model = {p.model: p for p in match.predictions}
    pred = next((by_model[m] for m in AI_MODEL_PREFERENCE if m in by_model), None)
    if pred is None:
        return None
    probs = {"H": pred.home_win, "D": pred.draw, "A": pred.away_win}
    best = max(probs, key=probs.get)
    for line in pred.top_scorelines:
        h, a = map(int, line["score"].split("-"))
        if outcome(h, a) == best:
            return h, a
    return {"H": (1, 0), "D": (1, 1), "A": (0, 1)}[best]


def score_finished_matches(db: Session) -> dict:
    """Score every unscored prediction on a finished match. Safe to run any time:
    each prediction is scored once."""
    query = (select(UserPrediction).join(Match)
             .options(joinedload(UserPrediction.match).selectinload(Match.predictions))
             .where(Match.status == "finished", Match.home_goals.is_not(None), UserPrediction.scored_at.is_(None)))
    now = datetime.now(timezone.utc)
    scored = 0
    for up in db.scalars(query).unique():
        m = up.match
        up.points, up.breakdown = score_prediction(up.home_goals, up.away_goals, m.home_goals, m.away_goals)
        pick = ai_pick(m)
        if pick:
            up.ai_score = f"{pick[0]}-{pick[1]}"
            up.ai_points, _ = score_prediction(*pick, m.home_goals, m.away_goals)
        up.scored_at = now
        scored += 1
    db.commit()
    return {"scored": scored}


def got_result_right(breakdown: dict | None) -> bool:
    return bool(breakdown) and ("result" in breakdown or "draw" in breakdown)


def streaks(scored_in_order: list[UserPrediction]) -> dict:
    """Current and best run of correct results (oldest first in the list)."""
    current = best = 0
    for up in scored_in_order:
        current = current + 1 if got_result_right(up.breakdown) else 0
        best = max(best, current)
    return {"current": current, "best": best}


def latest_prediction(db: Session, match_id: int) -> Prediction | None:
    preds = {p.model: p for p in db.scalars(select(Prediction).where(Prediction.match_id == match_id))}
    return next((preds[m] for m in AI_MODEL_PREFERENCE if m in preds), None)
