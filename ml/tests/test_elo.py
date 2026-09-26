import numpy as np
import pandas as pd
import pytest

from footiq.elo import EloGoalsModel, EloRatings, goal_margin_multiplier, international_k
from footiq.synthetic import make_league


def test_equal_teams_on_neutral_ground_are_50_50():
    elo = EloRatings()
    assert elo.expected_score("A", "B", neutral=True) == pytest.approx(0.5)


def test_home_advantage_helps_home_team():
    elo = EloRatings(home_advantage=100)
    assert elo.expected_score("A", "B") > 0.6


def test_400_point_gap_means_about_91_percent():
    elo = EloRatings()
    elo.ratings = {"A": 1900.0, "B": 1500.0}
    assert elo.expected_score("A", "B", neutral=True) == pytest.approx(10 / 11, abs=1e-6)


def test_points_move_from_loser_to_winner():
    elo = EloRatings()
    elo.update("A", "B", 2, 0, neutral=True)
    assert elo.ratings["A"] > 1500 > elo.ratings["B"]
    assert elo.ratings["A"] + elo.ratings["B"] == pytest.approx(3000)  # nothing created or destroyed


def test_upset_moves_more_points_than_expected_win():
    fav_wins = EloRatings(); fav_wins.ratings = {"Fav": 1800.0, "Dog": 1400.0}
    dog_wins = EloRatings(); dog_wins.ratings = {"Fav": 1800.0, "Dog": 1400.0}
    fav_wins.update("Fav", "Dog", 1, 0, neutral=True)
    dog_wins.update("Fav", "Dog", 0, 1, neutral=True)
    assert abs(dog_wins.ratings["Dog"] - 1400) > abs(fav_wins.ratings["Dog"] - 1400)


def test_bigger_wins_move_more():
    assert goal_margin_multiplier(1) < goal_margin_multiplier(2) < goal_margin_multiplier(4)


def test_world_cup_counts_more_than_friendly():
    assert international_k("FIFA World Cup") > international_k("UEFA Nations League") > international_k("Friendly")


def test_run_records_gap_before_each_match():
    matches = pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-01-08"]),
                            "home_team": ["A", "A"], "away_team": ["B", "B"],
                            "home_goals": [3, 0], "away_goals": [0, 0]})
    rated = EloRatings(home_advantage=0).run(matches)
    assert rated["elo_gap"].iloc[0] == 0          # nobody had played yet
    assert rated["elo_gap"].iloc[1] > 0           # A's first win already counts


def test_elo_ranks_synthetic_teams_correctly():
    matches, truth = make_league(n_teams=16, n_seasons=4, seed=3)
    elo = EloRatings(k=20, home_advantage=65)
    elo.run(matches)
    true_strength = (truth["attack"] + truth["defence"]).to_numpy()
    learned = np.array([elo.ratings[t] for t in truth["team"]])
    assert np.corrcoef(true_strength, learned)[0, 1] > 0.85


def test_goals_model_learns_sensible_numbers_and_saves():
    matches, _ = make_league(n_teams=16, n_seasons=4, seed=5)
    elo = EloRatings(k=20, home_advantage=65)
    rated = elo.run(matches)
    model = EloGoalsModel(elo).fit(rated)
    assert model.b > 0                             # higher rating -> more goals
    h, a = model.goals_from_gap(200)
    assert h > a
    assert sum(model.predict("Team A", "Team B")["probabilities"].values()) == pytest.approx(1)


def test_save_and_load_roundtrip(tmp_path):
    elo = EloRatings(); elo.update("A", "B", 1, 0, date="2024-05-01")
    model = EloGoalsModel(elo)
    model.save(tmp_path / "m.json")
    loaded = EloGoalsModel.load(tmp_path / "m.json")
    assert loaded.predict("A", "B") == model.predict("A", "B")
    assert loaded.ratings.last_date == pd.Timestamp("2024-05-01")
