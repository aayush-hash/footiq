"""Day 10: turn Elo gaps into expected goals, test it honestly, and save the model.

    python scripts/day10_elo_to_goals.py
"""

import numpy as np

from footiq.elo import EloGoalsModel
from footiq.evaluate import all_metrics, one_hot
from footiq.international import build_international_elo, load_results
from footiq.simulate import MatchState, outcome_probs, score_matrix, what_if

results = load_results()
elo, rated = build_international_elo(results)

# 1) Fit the goals conversion on 2000-2021 only, then test on 2022 onwards.
train = rated[(rated["date"] >= "2000-01-01") & (rated["date"] < "2022-01-01")]
test = rated[rated["date"] >= "2022-01-01"]
goals = EloGoalsModel(elo).fit(train)
print(f"Learned: expected goals = exp({goals.a:.3f} + {goals.b:.3f} x gap/400)")
for gap in [0, 100, 200, 400]:
    h, a = goals.goals_from_gap(gap)
    print(f"  gap {gap:>3}: {h:.2f} - {a:.2f}")

probs = np.array([list(outcome_probs(score_matrix(*goals.goals_from_gap(g))).values()) for g in test["elo_gap"]])
actual = one_hot(test["result"])
rates = train["result"].value_counts(normalize=True)
baseline = np.tile([rates["H"], rates["D"], rates["A"]], (len(test), 1))
print(f"\nTest on {len(test):,} international matches since 2022:")
for name, p in [("baseline", baseline), ("elo goals", probs)]:
    m = all_metrics(p, actual)
    print(f"  {name:10s} accuracy {m['accuracy']:.3f}  brier {m['brier']:.4f}  log loss {m['log_loss']:.4f}")

competitive = test["tournament"] != "Friendly"
m = all_metrics(probs[competitive.to_numpy()], actual[competitive.to_numpy()])
print(f"  competitive matches only: accuracy {m['accuracy']:.3f}  log loss {m['log_loss']:.4f}")

# 2) Refit on everything since 2000 and save for the app.
final = EloGoalsModel(elo).fit(rated[rated["date"] >= "2000-01-01"])
final.save("models/international_elo.json")
print("\nSaved models/international_elo.json")

# 3) The same simulation engine from Week 1 now works for countries.
for home, away, neutral in [("Spain", "England", False), ("England", "Spain", False), ("Spain", "England", True)]:
    p = final.predict(home, away, neutral=neutral)
    pr = p["probabilities"]
    where = "neutral" if neutral else f"at {home}"
    print(f"\n{home} vs {away} ({where}): {pr['home_win']:.1%} / {pr['draw']:.1%} / {pr['away_win']:.1%}")
    print("  likely:", ", ".join(f"{s['score']} {s['probability']:.0%}" for s in p["top_scorelines"][:4]))

lam_h, lam_a = final.expected_goals("England", "Spain")
r = what_if(lam_h, lam_a, MatchState(minute=30, away_goals=1))
pr = r["probabilities"]
print(f"\nWhat if Spain lead 1-0 at Wembley after 30'? England {pr['home_win']:.1%} / draw {pr['draw']:.1%} / Spain {pr['away_win']:.1%}")
