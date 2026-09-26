"""Day 5: train Dixon-Coles (with time decay) for every league and save the models.

    python scripts/day5_train_dixon_coles.py
"""

from pathlib import Path

from footiq.data import LEAGUES, load_matches
from footiq.models import DixonColesModel, PoissonModel

matches = load_matches()
Path("models").mkdir(exist_ok=True)

for league, name in LEAGUES.items():
    data = matches[matches["league"] == league]
    # With time decay we can give it more history: old matches count less automatically.
    recent_seasons = sorted(data["season"].unique())[-4:]
    train = data[data["season"].isin(recent_seasons)]

    dc = DixonColesModel(xi=0.0018).fit(train)
    plain = PoissonModel().fit(train)
    dc.save(f"models/{league}_dixon_coles.json")

    best = dc.ratings()["team"]
    home, away = best[0], best[1]
    p_dc = dc.predict(home, away)["probabilities"]
    p_plain = plain.predict(home, away)["probabilities"]

    print(f"\n=== {name} ({len(train):,} matches) ===")
    print(f"home advantage {dc.home_adv:.3f}   rho {dc.rho:.3f}   (negative rho = more 0-0 and 1-1 than plain Poisson expects)")
    print("top 5:", ", ".join(dc.ratings()["team"].head(5)))
    print(f"{home} vs {away}:")
    print(f"  Poisson       H {p_plain['home_win']:.1%}  D {p_plain['draw']:.1%}  A {p_plain['away_win']:.1%}")
    print(f"  Dixon-Coles   H {p_dc['home_win']:.1%}  D {p_dc['draw']:.1%}  A {p_dc['away_win']:.1%}")

print("\nSaved models to the models/ folder")
