"""Fake league data with KNOWN team strengths.

Used by the tests: if the model can recover strengths we chose ourselves,
we know the maths is right before trusting it on real data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from footiq.simulate import score_matrix


def make_league(n_teams=20, n_seasons=3, home_adv=0.25, rho=-0.1, seed=0, start_year=2021):
    rng = np.random.default_rng(seed)
    teams = [f"Team {chr(65 + i)}" for i in range(n_teams)]
    attack = rng.normal(0, 0.3, n_teams)
    attack -= attack.mean()
    defence = rng.normal(0.1, 0.3, n_teams)

    rows = []
    for s in range(n_seasons):
        season_start = pd.Timestamp(f"{start_year + s}-08-10")
        fixtures = [(h, a) for h in range(n_teams) for a in range(n_teams) if h != a]
        rng.shuffle(fixtures)
        for k, (h, a) in enumerate(fixtures):
            lam_h = np.exp(home_adv + attack[h] - defence[a])
            lam_a = np.exp(attack[a] - defence[h])
            m = score_matrix(lam_h, lam_a, rho)
            pick = rng.choice(m.size, p=m.ravel())
            x, y = np.unravel_index(pick, m.shape)
            rows.append({
                "date": season_start + pd.Timedelta(days=int(k * 280 / len(fixtures))),
                "league": "XX", "season": f"{(start_year + s) % 100:02d}{(start_year + s + 1) % 100:02d}",
                "home_team": teams[h], "away_team": teams[a], "home_goals": int(x), "away_goals": int(y),
                "result": "H" if x > y else ("A" if x < y else "D"),
            })
    truth = pd.DataFrame({"team": teams, "attack": attack, "defence": defence})
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True), truth
