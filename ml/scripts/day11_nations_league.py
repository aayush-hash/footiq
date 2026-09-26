"""Day 11: Nations League 2026/27 League A - simulate every group 10,000 times.

    python scripts/day11_nations_league.py
    python scripts/day11_nations_league.py A3        (one group)

Keep fixtures/nations_league_2026_27_league_a.csv up to date: after each
matchday, type the real scores into home_goals and away_goals, then run again.
"""

import sys

import pandas as pd

from footiq.elo import EloGoalsModel, international_k
from footiq.tournament import LEAGUE_A_OUTCOMES, current_table, simulate_group

FIXTURES = "fixtures/nations_league_2026_27_league_a.csv"

model = EloGoalsModel.load("models/international_elo.json")
fixtures = pd.read_csv(FIXTURES, parse_dates=["date"])

# Results newer than the downloaded dataset haven't moved the ratings yet: apply them now.
played = fixtures.dropna(subset=["home_goals", "away_goals"]).sort_values("date")
last = model.ratings.last_date
new = played[played["date"] > last] if last is not None else played
for m in new.itertuples():
    model.ratings.update(m.home_team, m.away_team, int(m.home_goals), int(m.away_goals),
                         k=international_k("UEFA Nations League"), date=m.date)
print(f"Ratings include matches up to {last.date() if last is not None else '?'}, plus {len(new)} newer Nations League results.\n")

groups = sys.argv[1:] or sorted(fixtures["group"].unique())
summary = []
for group in groups:
    g = fixtures[fixtures["group"] == group]
    left = g["home_goals"].isna().sum()
    print(f"=== Group {group}  ({len(g) - left} played, {left} to play) ===")
    print(current_table(g).to_string(index=False))

    odds = simulate_group(g, model, n=10_000, seed=11, outcomes=LEAGUE_A_OUTCOMES)
    odds["elo"] = odds["team"].map(model.ratings.rating)
    show = odds[["team", "elo", "avg_points", "p1", "quarter_finals", "playoff", "relegated"]]
    print("\nAfter 10,000 simulations:")
    print(show.to_string(index=False, formatters={
        "elo": "{:.0f}".format, "avg_points": "{:.1f}".format,
        **{c: "{:.1%}".format for c in ["p1", "quarter_finals", "playoff", "relegated"]}}))
    print()
    summary.append(odds.assign(group=group))

all_odds = pd.concat(summary)
print("Most likely to top their group:")
print(all_odds.sort_values("p1", ascending=False).head(5)[["group", "team", "p1"]].to_string(
    index=False, formatters={"p1": "{:.1%}".format}))
