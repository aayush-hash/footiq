"""Day 11: simulate the rest of a group (like a Nations League group) 10,000 times.

For every simulation, each unplayed match gets a random score drawn from the
model's expected goals. Then we build the final table with the official-style
tiebreakers and record where each team finished. Counting the finishes over
10,000 runs gives the probabilities.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# What each final position means in UEFA Nations League 2026/27, League A.
# Check the official regulations if you use other leagues.
LEAGUE_A_OUTCOMES = {1: "quarter_finals", 2: "quarter_finals", 3: "playoff", 4: "relegated"}


def _team_stats(teams, matches):
    """matches: list of (home, away, home_goals, away_goals). Returns dict team -> stats."""
    s = {t: {"pts": 0, "gf": 0, "ga": 0, "away_gf": 0, "wins": 0, "away_wins": 0} for t in teams}
    for h, a, hg, ag in matches:
        if h not in s or a not in s:
            continue
        s[h]["gf"] += hg; s[h]["ga"] += ag
        s[a]["gf"] += ag; s[a]["ga"] += hg; s[a]["away_gf"] += ag
        if hg > ag:
            s[h]["pts"] += 3; s[h]["wins"] += 1
        elif hg < ag:
            s[a]["pts"] += 3; s[a]["wins"] += 1; s[a]["away_wins"] += 1
        else:
            s[h]["pts"] += 1; s[a]["pts"] += 1
    return s


def rank_teams(teams, matches, rng=None) -> list[str]:
    """Order teams using Nations League-style tiebreakers:
    1. points
    2. head-to-head between the tied teams: points, goal difference, goals scored
       (applied again to any teams still tied)
    3. overall goal difference, goals scored, away goals, wins, away wins
    4. random (stands in for disciplinary points and the UEFA coefficient)
    """
    rng = rng or np.random.default_rng()
    overall = _team_stats(teams, matches)
    by_points = {}
    for t in teams:
        by_points.setdefault(overall[t]["pts"], []).append(t)
    order = []
    for pts in sorted(by_points, reverse=True):
        order += _break_tie(by_points[pts], matches, overall, rng)
    return order


def _break_tie(tied, matches, overall, rng):
    if len(tied) == 1:
        return tied
    h2h = _team_stats(tied, [m for m in matches if m[0] in tied and m[1] in tied])
    key = lambda t: (h2h[t]["pts"], h2h[t]["gf"] - h2h[t]["ga"], h2h[t]["gf"])
    groups = {}
    for t in tied:
        groups.setdefault(key(t), []).append(t)
    if len(groups) > 1:  # head-to-head separated at least some teams: re-apply to each still-tied subgroup
        return [t for k in sorted(groups, reverse=True) for t in _break_tie(groups[k], matches, overall, rng)]
    # head-to-head couldn't separate them: use overall record, then random
    return sorted(tied, key=lambda t: (
        overall[t]["gf"] - overall[t]["ga"], overall[t]["gf"], overall[t]["away_gf"],
        overall[t]["wins"], overall[t]["away_wins"], rng.random(),
    ), reverse=True)


def current_table(fixtures: pd.DataFrame) -> pd.DataFrame:
    """The real table right now, from the matches already played."""
    teams = sorted(set(fixtures["home_team"]) | set(fixtures["away_team"]))
    played = fixtures.dropna(subset=["home_goals", "away_goals"])
    matches = [(r.home_team, r.away_team, int(r.home_goals), int(r.away_goals)) for r in played.itertuples()]
    stats = _team_stats(teams, matches)
    order = rank_teams(teams, matches, np.random.default_rng(0))
    rows = []
    for pos, t in enumerate(order, 1):
        played_n = sum(t in (m[0], m[1]) for m in matches)
        rows.append({"pos": pos, "team": t, "played": played_n, "points": stats[t]["pts"],
                     "gf": stats[t]["gf"], "ga": stats[t]["ga"], "gd": stats[t]["gf"] - stats[t]["ga"]})
    return pd.DataFrame(rows)


def simulate_group(fixtures: pd.DataFrame, model, n: int = 10_000, seed: int | None = None,
                   outcomes: dict | None = None) -> pd.DataFrame:
    """Simulate the unplayed matches n times.

    fixtures: columns home_team, away_team, home_goals, away_goals
              (goals empty/NaN for matches not played yet)
    model:    anything with expected_goals(home, away, neutral) - Dixon-Coles or Elo
    Returns one row per team: chance of each final position, average points,
    and (if outcomes is given) the chance of each outcome, like "relegated".
    """
    rng = np.random.default_rng(seed)
    teams = sorted(set(fixtures["home_team"]) | set(fixtures["away_team"]))
    played = fixtures.dropna(subset=["home_goals", "away_goals"])
    remaining = fixtures[fixtures["home_goals"].isna() | fixtures["away_goals"].isna()]
    fixed = [(r.home_team, r.away_team, int(r.home_goals), int(r.away_goals)) for r in played.itertuples()]

    # Draw all random scores at once: shape (n, number of remaining matches)
    rates = [model.expected_goals(r.home_team, r.away_team, neutral=False) for r in remaining.itertuples()]
    home_goals = np.column_stack([rng.poisson(lh, n) for lh, _ in rates]) if rates else np.zeros((n, 0), int)
    away_goals = np.column_stack([rng.poisson(la, n) for _, la in rates]) if rates else np.zeros((n, 0), int)
    pairs = list(zip(remaining["home_team"], remaining["away_team"]))

    position_counts = {t: np.zeros(len(teams)) for t in teams}
    points_total = {t: 0.0 for t in teams}
    for s in range(n):
        sim = fixed + [(h, a, int(home_goals[s, j]), int(away_goals[s, j])) for j, (h, a) in enumerate(pairs)]
        order = rank_teams(teams, sim, rng)
        stats = _team_stats(teams, sim)
        for pos, t in enumerate(order):
            position_counts[t][pos] += 1
            points_total[t] += stats[t]["pts"]

    rows = []
    for t in teams:
        row = {"team": t, "avg_points": points_total[t] / n}
        for pos in range(len(teams)):
            row[f"p{pos + 1}"] = position_counts[t][pos] / n
        if outcomes:
            for pos, label in outcomes.items():
                row[label] = row.get(label, 0) + row[f"p{pos}"]
        rows.append(row)
    return pd.DataFrame(rows).sort_values("avg_points", ascending=False).reset_index(drop=True)
