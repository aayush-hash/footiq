"""Day 7: the what-if engine, using a saved model.

    python scripts/day7_what_if_demo.py
    python scripts/day7_what_if_demo.py SP1 "Barcelona" "Real Madrid"
"""

import sys

from footiq.models import DixonColesModel
from footiq.simulate import MatchState, outcome_probs, score_matrix, simulate_matches, what_if

league = sys.argv[1] if len(sys.argv) > 1 else "SP1"
model = DixonColesModel.load(f"models/{league}_dixon_coles.json")
home = sys.argv[2] if len(sys.argv) > 2 else model.ratings()["team"][0]
away = sys.argv[3] if len(sys.argv) > 3 else model.ratings()["team"][1]
for team in (home, away):
    if team not in model.teams:
        print(f"'{team}' not found. Teams: {', '.join(model.teams)}")
        sys.exit(1)

lam_h, lam_a = model.expected_goals(home, away)
print(f"{home} vs {away}   expected goals {lam_h:.2f} - {lam_a:.2f}\n")

# 1) Play the match 10,000 times
matrix = score_matrix(lam_h, lam_a, model.rho)
sims = simulate_matches(matrix, n=10_000, seed=7)
print("10,000 simulated matches:")
print(f"  {home} win {(sims[:, 0] > sims[:, 1]).mean():6.1%}   (exact maths: {outcome_probs(matrix)['home_win']:.1%})")
print(f"  draw        {(sims[:, 0] == sims[:, 1]).mean():6.1%}")
print(f"  {away} win {(sims[:, 0] < sims[:, 1]).mean():6.1%}\n")


def show(title, state):
    r = what_if(lam_h, lam_a, state, rho=model.rho, n_top=4)
    p = r["probabilities"]
    scores = ", ".join(f"{s['score']} {s['probability']:.0%}" for s in r["top_scorelines"])
    print(f"{title}")
    print(f"  {home} {p['home_win']:6.1%} | draw {p['draw']:6.1%} | {away} {p['away_win']:6.1%}   likely: {scores}")


show("Kick-off", MatchState())
show(f"{away} score at 17'", MatchState(minute=17, away_goals=1))
show(f"...then {home} get a red card at 63'", MatchState(minute=63, away_goals=1, home_red_cards=1))
show(f"...but {home} equalise at 80' anyway", MatchState(minute=80, home_goals=1, away_goals=1, home_red_cards=1))

# Home or away switch: same teams at a neutral ground, then with the venue swapped
lam_hn, lam_an = model.expected_goals(home, away, neutral=True)
p = what_if(lam_hn, lam_an, MatchState(), rho=model.rho)["probabilities"]
print(f"\nNeutral venue:  {home} {p['home_win']:.1%} | draw {p['draw']:.1%} | {away} {p['away_win']:.1%}")
lam_sh, lam_sa = model.expected_goals(away, home)
p = what_if(lam_sh, lam_sa, MatchState(), rho=model.rho)["probabilities"]
print(f"At {away}'s ground: {home} {p['away_win']:.1%} | draw {p['draw']:.1%} | {away} {p['home_win']:.1%}")
