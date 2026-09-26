import numpy as np
import pytest
from scipy.stats import poisson

from footiq.simulate import (
    MatchState, outcome_probs, score_matrix, simulate_matches, top_scorelines, what_if,
)


def test_score_matrix_adds_up_to_one():
    assert score_matrix(1.7, 1.2).sum() == pytest.approx(1.0)
    assert score_matrix(1.7, 1.2, rho=-0.1).sum() == pytest.approx(1.0)


def test_plain_poisson_matches_scipy():
    m = score_matrix(1.5, 1.0)
    assert m[2, 1] == pytest.approx(poisson.pmf(2, 1.5) * poisson.pmf(1, 1.0), rel=1e-3)


def test_negative_rho_adds_draws_at_0_0_and_1_1():
    plain, dc = score_matrix(1.4, 1.1), score_matrix(1.4, 1.1, rho=-0.1)
    assert dc[0, 0] > plain[0, 0] and dc[1, 1] > plain[1, 1]


def test_outcomes_sum_to_one_and_stronger_team_wins_more():
    p = outcome_probs(score_matrix(2.2, 0.8))
    assert sum(p.values()) == pytest.approx(1.0)
    assert p["home_win"] > p["away_win"]


def test_equal_teams_are_symmetric():
    p = outcome_probs(score_matrix(1.3, 1.3))
    assert p["home_win"] == pytest.approx(p["away_win"])


def test_top_scorelines_sorted():
    top = top_scorelines(score_matrix(1.7, 1.4), n=4)
    probs = [t["probability"] for t in top]
    assert probs == sorted(probs, reverse=True)


def test_10000_simulations_agree_with_exact_maths():
    m = score_matrix(1.72, 1.43)
    sims = simulate_matches(m, n=10_000, seed=1)
    home_win_share = (sims[:, 0] > sims[:, 1]).mean()
    assert home_win_share == pytest.approx(outcome_probs(m)["home_win"], abs=0.02)


def test_full_time_result_is_certain():
    r = what_if(1.7, 1.4, MatchState(minute=90, home_goals=2, away_goals=1))
    assert r["probabilities"]["home_win"] == pytest.approx(1.0)


def test_early_goal_changes_the_odds():
    before = what_if(1.7, 1.4, MatchState())["probabilities"]
    after = what_if(1.7, 1.4, MatchState(minute=17, away_goals=1))["probabilities"]
    assert after["away_win"] > before["away_win"] + 0.15


def test_red_card_hurts_that_team():
    base = what_if(1.7, 1.4, MatchState(minute=63, home_goals=1, away_goals=1))["probabilities"]
    red = what_if(1.7, 1.4, MatchState(minute=63, home_goals=1, away_goals=1, home_red_cards=1))["probabilities"]
    assert red["home_win"] < base["home_win"]
    assert red["away_win"] > base["away_win"]


def test_scorelines_include_goals_already_scored():
    r = what_if(1.7, 1.4, MatchState(minute=80, home_goals=3, away_goals=0))
    assert r["top_scorelines"][0]["score"] == "3-0"
