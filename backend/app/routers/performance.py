"""Day 25: how good is FOOTIQ really? The numbers behind the transparency page.

Two sources, clearly separated:
  live     - predictions this app actually made before kickoff, checked against
             real results. The most honest number, but it needs time to build up.
  backtest - your Day 6 walk-forward test from the ml folder
             (ml/reports/evaluation.csv), so the page isn't empty on day one.
"""

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from footiq.evaluate import all_metrics, calibration_table, one_hot

from app.config import get_settings
from app.database import get_db
from app.models import League, Match, Prediction

router = APIRouter(tags=["transparency"])
MIN_RELIABLE = 30  # fewer matches than this and the numbers are mostly luck


def _live_rows(db: Session, model: str, league: str | None, last: int) -> list[dict]:
    query = (select(Prediction, Match).join(Match, Match.id == Prediction.match_id)
             .options(joinedload(Match.league))
             .where(Prediction.model == model, Match.status == "finished", Match.home_goals.is_not(None))
             .order_by(Match.kickoff.desc()).limit(last))
    if league:
        query = query.join(League, League.id == Match.league_id).where(League.code == league)
    rows = []
    for pred, match in db.execute(query).all():
        result = "H" if match.home_goals > match.away_goals else ("A" if match.home_goals < match.away_goals else "D")
        top = pred.top_scorelines[0]["score"] if pred.top_scorelines else None
        rows.append({"league": match.league.code, "result": result,
                     "p_home": pred.home_win, "p_draw": pred.draw, "p_away": pred.away_win,
                     "exact": top == f"{match.home_goals}-{match.away_goals}"})
    return rows


def _summary(df: pd.DataFrame) -> dict:
    probs = df[["p_home", "p_draw", "p_away"]].to_numpy()
    actual = one_hot(df["result"])
    m = all_metrics(probs, actual)
    m["exact_score_rate"] = float(df["exact"].mean())
    # Baseline: always predict how often home wins, draws and away wins happened in these matches.
    rates = actual.mean(axis=0)
    m["baseline"] = all_metrics(np.tile(rates, (len(df), 1)), actual)
    return m


def _backtest() -> list[dict] | None:
    path = get_settings().models_dir.parent / "reports" / "evaluation.csv"
    if not path.exists():
        return None
    return pd.read_csv(path).round(4).to_dict(orient="records")


@router.get("/model-performance")
def model_performance(db: Session = Depends(get_db),
                      model: str = Query("dixon_coles", pattern="^(dixon_coles|elo)$"),
                      league: str | None = Query(None, description="league code, e.g. E0"),
                      last: int = Query(500, ge=10, le=5000, description="use the most recent N finished matches")):
    rows = _live_rows(db, model, league, last)
    live: dict = {"matches": len(rows), "reliable": len(rows) >= MIN_RELIABLE}
    if rows:
        df = pd.DataFrame(rows)
        live.update(_summary(df))
        live["by_league"] = {code: _summary(g) for code, g in df.groupby("league")}
        calib = calibration_table(df[["p_home", "p_draw", "p_away"]].to_numpy(), one_hot(df["result"]), bins=5)
        live["calibration"] = calib.round(4).to_dict(orient="records")
    if not live["reliable"]:
        live["note"] = f"Only {len(rows)} finished matches so far. Numbers become meaningful after about {MIN_RELIABLE}."
    return {
        "model": model,
        "live": live,
        "backtest": _backtest(),
        "how_to_read": {
            "accuracy": "share of matches where the most likely result happened (higher is better)",
            "brier": "error of the three probabilities, 0 = perfect (lower is better)",
            "log_loss": "punishes confident mistakes (lower is better)",
            "calibration": "when FOOTIQ says 60%, it should happen about 60% of the time",
        },
    }
