"""Day 4: train the simple Poisson model on the Premier League.

    python scripts/day4_train_poisson.py
    python scripts/day4_train_poisson.py SP1        (La Liga instead)
"""

import sys

from footiq.data import load_matches
from footiq.models import PoissonModel

league = sys.argv[1] if len(sys.argv) > 1 else "E0"
matches = load_matches()
matches = matches[matches["league"] == league]

# Train on the last 3 seasons only: team quality changes over time.
recent_seasons = sorted(matches["season"].unique())[-3:]
train = matches[matches["season"].isin(recent_seasons)]
print(f"Training on {len(train):,} {league} matches from seasons {recent_seasons}")

model = PoissonModel().fit(train)

print(f"\nHome advantage: {model.home_adv:.3f}  (home teams score about {100 * (2.718 ** model.home_adv - 1):.0f}% more)")
print("\nTeam ratings (higher = better):")
print(model.ratings().round(3).to_string())

# Try a prediction with the two best teams
top = model.ratings()["team"]
home, away = top[0], top[1]
p = model.predict(home, away)
print(f"\n{home} vs {away}")
print(f"  expected goals  {p['expected_goals']['home']:.2f} - {p['expected_goals']['away']:.2f}")
for k, v in p["probabilities"].items():
    print(f"  {k:9s} {v:6.1%}")
print("  likely scores:", ", ".join(f"{s['score']} ({s['probability']:.1%})" for s in p["top_scorelines"]))
