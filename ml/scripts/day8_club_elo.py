"""Day 8: club Elo ratings, compared with Dixon-Coles on the same unseen season.

    python scripts/day8_club_elo.py          (all leagues)
    python scripts/day8_club_elo.py E0       (one league)
"""

import sys
from pathlib import Path

import pandas as pd

from footiq.data import LEAGUES, load_matches
from footiq.elo import EloRatings, elo_walk_forward
from footiq.evaluate import score_predictions, walk_forward
from footiq.models import DixonColesModel

matches = load_matches()
leagues = sys.argv[1:] or list(LEAGUES)
test_season = sorted(matches["season"].unique())[-1]

# 1) Current Elo table for the first league, just to look at
first = matches[matches["league"] == leagues[0]]
elo = EloRatings(k=20, home_advantage=65, new_team="weak")
elo.run(first)
print(f"Current Elo ratings, {LEAGUES.get(leagues[0], leagues[0])}:")
print(elo.table().head(10).round(0).to_string())

# 2) Try a few K values: how fast should ratings react?
print(f"\nTuning K on season {test_season} (lower log loss = better):")
tuning = []
for k in [10, 15, 20, 30, 40]:
    scores = [score_predictions(elo_walk_forward(matches[matches["league"] == lg], test_season, k=k)) for lg in leagues]
    ll = sum(s["log_loss"] for s in scores) / len(scores)
    tuning.append((k, ll))
    print(f"  K={k:<3} log loss {ll:.4f}")
best_k = min(tuning, key=lambda t: t[1])[0]
print(f"Best K: {best_k}")

# 3) Elo vs Dixon-Coles, league by league
rows = []
dc_saved = Path("reports/evaluation.csv")
dc_table = pd.read_csv(dc_saved) if dc_saved.exists() else None
for lg in leagues:
    data = matches[matches["league"] == lg]
    rows.append({"league": lg, "model": f"elo (K={best_k})", **score_predictions(elo_walk_forward(data, test_season, k=best_k))})
    if dc_table is not None and ((dc_table["league"] == lg) & (dc_table["model"] == "dixon_coles")).any():
        rows.append(dc_table[(dc_table["league"] == lg) & (dc_table["model"] == "dixon_coles")].iloc[0].to_dict())
    else:  # no Day 6 results saved: compute them now (slower)
        rows.append({"league": lg, "model": "dixon_coles", **score_predictions(walk_forward(lambda: DixonColesModel(), data, test_season))})

table = pd.DataFrame(rows)[["league", "model", "matches", "accuracy", "brier", "log_loss"]]
print("\n" + table.round(4).to_string(index=False))
print("\nAverage:")
print(table.assign(model=table["model"].str.split(" ").str[0]).groupby("model")[["accuracy", "brier", "log_loss"]].mean().round(4).to_string())
