"""Day 6: honest test on the most recent full season the models have never seen.

    python scripts/day6_evaluate.py              (all 5 leagues, takes a few minutes)
    python scripts/day6_evaluate.py E0           (one league)

Good real-world numbers for 1X2 (home/draw/away) predictions are roughly:
    accuracy 0.50 - 0.55,  Brier 0.57 - 0.60,  log loss 0.97 - 1.01
If you see much better than that, suspect a bug (usually future data leaking in).
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from footiq.data import LEAGUES, load_matches
from footiq.evaluate import baseline_predictions, calibration_table, one_hot, score_predictions, walk_forward
from footiq.models import DixonColesModel, PoissonModel

matches = load_matches()
leagues = sys.argv[1:] or list(LEAGUES)
test_season = sorted(matches["season"].unique())[-1]
print(f"Test season: {test_season} (models only ever see matches played before each prediction)\n")

results, all_dc = [], []
for league in leagues:
    data = matches[matches["league"] == league]
    contenders = {
        "baseline": None,
        "poisson": lambda: PoissonModel(),
        "dixon_coles": lambda: DixonColesModel(xi=0.0018),
    }
    for name, make_model in contenders.items():
        if make_model is None:
            preds = baseline_predictions(data, test_season)
        else:
            preds = walk_forward(make_model, data, test_season, train_years=4, refit_every_days=7)
        if name == "dixon_coles":
            all_dc.append(preds)
        results.append({"league": league, "model": name, **score_predictions(preds)})
        print(f"  {league} {name:12s} done")

table = pd.DataFrame(results)
print("\n" + table.round(4).to_string(index=False))
print("\nAverage over leagues:")
print(table.groupby("model")[["accuracy", "brier", "log_loss"]].mean().round(4).to_string())

# Calibration plot: points close to the diagonal = trustworthy probabilities
dc = pd.concat(all_dc)
calib = calibration_table(dc[["p_home", "p_draw", "p_away"]].to_numpy(), one_hot(dc["result"]))
print("\nCalibration (Dixon-Coles):")
print(calib.round(3).to_string(index=False))

Path("reports").mkdir(exist_ok=True)
fig, ax = plt.subplots(figsize=(5, 5))
ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="perfect")
ax.plot(calib["predicted"], calib["actual"], marker="o", label="Dixon-Coles")
ax.set_xlabel("Predicted probability")
ax.set_ylabel("How often it actually happened")
ax.set_title(f"Calibration, season {test_season}")
ax.legend()
fig.tight_layout()
fig.savefig("reports/calibration.png", dpi=150)
table.to_csv("reports/evaluation.csv", index=False)
print("\nSaved reports/evaluation.csv and reports/calibration.png")
