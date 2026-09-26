import numpy as np
import pandas as pd
import pytest

from footiq.tournament import LEAGUE_A_OUTCOMES, current_table, rank_teams, simulate_group


class FixedModel:
    """A fake model with known strengths, so tests don't depend on real data."""

    def __init__(self, strength):
        self.strength = strength

    def expected_goals(self, home, away, neutral=False):
        return 1.3 * np.exp(self.strength[home] - self.strength[away]), 1.1 * np.exp(self.strength[away] - self.strength[home])


def group_fixtures(results=None):
    teams = ["A", "B", "C", "D"]
    rows = [{"home_team": h, "away_team": a, "home_goals": np.nan, "away_goals": np.nan}
            for h in teams for a in teams if h != a]
    df = pd.DataFrame(rows)
    for (h, a), (hg, ag) in (results or {}).items():
        m = (df["home_team"] == h) & (df["away_team"] == a)
        df.loc[m, ["home_goals", "away_goals"]] = [hg, ag]
    return df


def test_points_decide_first():
    matches = [("A", "B", 1, 0), ("C", "D", 0, 0)]
    assert rank_teams(["A", "B", "C", "D"], matches)[0] == "A"


def test_head_to_head_beats_goal_difference():
    # Three-way tie on 3 points: the head-to-head table between all three decides
    # (A: GD 0, B: GD +4, C: GD -4).
    matches = [("A", "B", 1, 0), ("B", "C", 5, 0), ("C", "A", 1, 0)]
    assert rank_teams(["A", "B", "C"], matches) == ["B", "A", "C"]
    # Two-way tie: A and B on 3 points. B has the far better goal difference,
    # but A beat B, so A must finish above B.
    two_way = [("A", "B", 1, 0), ("B", "C", 5, 0), ("D", "A", 1, 0), ("C", "D", 0, 0)]
    order = rank_teams(["A", "B", "C", "D"], two_way)
    assert order.index("A") < order.index("B")  # A and B on 3 points; A won the head-to-head


def test_finished_group_is_certain():
    results = {("A", "B"): (2, 0), ("A", "C"): (2, 0), ("A", "D"): (2, 0), ("B", "A"): (0, 1), ("C", "A"): (0, 1),
               ("D", "A"): (0, 1), ("B", "C"): (1, 0), ("B", "D"): (1, 0), ("C", "B"): (0, 1), ("D", "B"): (0, 1),
               ("C", "D"): (1, 0), ("D", "C"): (0, 1)}
    odds = simulate_group(group_fixtures(results), FixedModel(dict.fromkeys("ABCD", 0.0)), n=200, seed=1)
    assert odds.set_index("team").loc["A", "p1"] == 1.0
    assert odds.set_index("team").loc["D", "p4"] == 1.0


def test_probabilities_add_up_and_strong_team_leads():
    model = FixedModel({"A": 0.6, "B": 0.2, "C": 0.0, "D": -0.5})
    odds = simulate_group(group_fixtures(), model, n=3000, seed=2, outcomes=LEAGUE_A_OUTCOMES).set_index("team")
    for pos in ["p1", "p2", "p3", "p4"]:
        assert odds[pos].sum() == pytest.approx(1.0)
    for team in "ABCD":
        assert odds.loc[team, ["p1", "p2", "p3", "p4"]].sum() == pytest.approx(1.0)
    assert odds["p1"].idxmax() == "A"
    assert odds["relegated"].idxmax() == "D"
    assert odds.loc["A", "quarter_finals"] == pytest.approx(odds.loc["A", "p1"] + odds.loc["A", "p2"])


def test_current_table_counts_played_matches():
    table = current_table(group_fixtures({("A", "B"): (3, 1)})).set_index("team")
    assert table.loc["A", "points"] == 3 and table.loc["A", "gd"] == 2
    assert table.loc["B", "played"] == 1 and table.loc["C", "played"] == 0
