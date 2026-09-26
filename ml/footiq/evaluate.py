"""Day 6: test the models honestly on matches they have never seen.

The golden rule: when predicting a match, the model may only use matches
played BEFORE it. Otherwise you are cheating and the numbers look too good.

We use "walk-forward" testing: every week of the test season, retrain on
everything before that week, then predict that week's matches.

Metrics (for probabilities in the order home, draw, away):
  accuracy  - how often the most likely outcome happened (higher = better)
  brier     - squared error of the probabilities, 0 = perfect, lower = better
  log_loss  - punishes confident wrong predictions hard, lower = better
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

OUTCOMES = ["H", "D", "A"]


def one_hot(results: pd.Series) -> np.ndarray:
    return np.column_stack([(results == o).to_numpy() for o in OUTCOMES]).astype(float)


def accuracy(probs: np.ndarray, actual: np.ndarray) -> float:
    return float((probs.argmax(axis=1) == actual.argmax(axis=1)).mean())


def brier_score(probs: np.ndarray, actual: np.ndarray) -> float:
    return float(((probs - actual) ** 2).sum(axis=1).mean())


def log_loss(probs: np.ndarray, actual: np.ndarray) -> float:
    p_true = (probs * actual).sum(axis=1).clip(1e-12, 1)
    return float(-np.log(p_true).mean())


def all_metrics(probs: np.ndarray, actual: np.ndarray) -> dict:
    return {
        "matches": len(probs),
        "accuracy": accuracy(probs, actual),
        "brier": brier_score(probs, actual),
        "log_loss": log_loss(probs, actual),
    }


def calibration_table(probs: np.ndarray, actual: np.ndarray, bins: int = 10) -> pd.DataFrame:
    """When the model says 60%, does it happen about 60% of the time?"""
    p, hit = probs.ravel(), actual.ravel()
    edges = np.linspace(0, 1, bins + 1)
    which = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    rows = []
    for b in range(bins):
        m = which == b
        if m.sum():
            rows.append({"bin": f"{edges[b]:.1f}-{edges[b + 1]:.1f}", "predicted": p[m].mean(), "actual": hit[m].mean(), "count": int(m.sum())})
    return pd.DataFrame(rows)


def walk_forward(
    make_model: Callable,
    matches: pd.DataFrame,
    test_season: str,
    train_years: float = 4.0,
    refit_every_days: int = 7,
) -> pd.DataFrame:
    """Predict every match of test_season using only earlier matches.

    make_model: a function that returns a fresh, untrained model,
                e.g. lambda: DixonColesModel(xi=0.0018)
    Returns one row per test match with the predicted probabilities.
    """
    test = matches[matches["season"] == test_season].sort_values("date")
    if test.empty:
        raise ValueError(f"No matches for season {test_season}")

    rows = []
    period_start = test["date"].min()
    while period_start <= test["date"].max():
        period_end = period_start + pd.Timedelta(days=refit_every_days)
        batch = test[(test["date"] >= period_start) & (test["date"] < period_end)]
        if not batch.empty:
            train = matches[
                (matches["date"] < period_start)
                & (matches["date"] >= period_start - pd.Timedelta(days=int(365 * train_years)))
            ]
            model = make_model().fit(train, as_of=period_start)
            for match in batch.itertuples():
                p = model.predict(match.home_team, match.away_team)["probabilities"]
                rows.append({
                    "date": match.date, "home_team": match.home_team, "away_team": match.away_team,
                    "result": match.result, "p_home": p["home_win"], "p_draw": p["draw"], "p_away": p["away_win"],
                })
        period_start = period_end
    return pd.DataFrame(rows)


def baseline_predictions(matches: pd.DataFrame, test_season: str) -> pd.DataFrame:
    """The 'dumb' benchmark: always predict last seasons' average H/D/A rates.
    A real model must beat this, or it has learned nothing."""
    test = matches[matches["season"] == test_season]
    history = matches[matches["date"] < test["date"].min()]
    rates = history["result"].value_counts(normalize=True)
    out = test[["date", "home_team", "away_team", "result"]].copy()
    out["p_home"], out["p_draw"], out["p_away"] = rates.get("H", 0), rates.get("D", 0), rates.get("A", 0)
    return out


def score_predictions(preds: pd.DataFrame) -> dict:
    probs = preds[["p_home", "p_draw", "p_away"]].to_numpy()
    return all_metrics(probs, one_hot(preds["result"]))
