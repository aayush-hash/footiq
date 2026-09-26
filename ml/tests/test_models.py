import numpy as np
import pandas as pd
import pytest
from scipy.optimize import check_grad

from footiq.data import clean
from footiq.evaluate import (
    baseline_predictions, brier_score, log_loss, one_hot, score_predictions, walk_forward,
)
from footiq.models import DixonColesModel, PoissonModel
from footiq.synthetic import make_league


@pytest.fixture(scope="module")
def league():
    return make_league(n_teams=20, n_seasons=4, seed=42)


@pytest.mark.parametrize("model_cls", [PoissonModel, DixonColesModel])
def test_gradient_is_correct(league, model_cls):
    matches, _ = league
    model = model_cls().fit(matches.head(300))  # sets up internal arrays
    n = len(model.teams)
    x0 = np.random.default_rng(0).normal(0, 0.1, 2 * n + 1 + (1 if model.uses_rho else 0))
    err = check_grad(lambda p: model._loss(p)[0], lambda p: model._loss(p)[1], x0)
    assert err < 1e-3 * np.sqrt(len(x0)) * 10


def test_poisson_recovers_true_strengths(league):
    matches, truth = league
    model = PoissonModel().fit(matches)
    learned = model.ratings().set_index("team").loc[truth["team"]]
    assert np.corrcoef(learned["attack"], truth["attack"])[0, 1] > 0.9
    assert np.corrcoef(learned["defence"], truth["defence"])[0, 1] > 0.9
    assert model.home_adv == pytest.approx(0.25, abs=0.06)


def test_dixon_coles_finds_negative_rho(league):
    matches, _ = league
    model = DixonColesModel(xi=0.0).fit(matches)
    assert -0.25 < model.rho < 0.02


def test_unknown_team_gets_weak_ratings(league):
    matches, _ = league
    model = PoissonModel().fit(matches)
    p = model.predict(model.ratings()["team"][0], "Brand New FC")["probabilities"]
    assert p["home_win"] > 0.5


def test_save_and_load(tmp_path, league):
    matches, _ = league
    model = DixonColesModel().fit(matches)
    model.save(tmp_path / "m.json")
    loaded = DixonColesModel.load(tmp_path / "m.json")
    assert loaded.predict("Team A", "Team B") == model.predict("Team A", "Team B")


def test_metrics_on_perfect_and_uniform_predictions():
    actual = one_hot(pd.Series(["H", "D", "A"]))
    assert brier_score(actual, actual) == 0
    uniform = np.full((3, 3), 1 / 3)
    assert brier_score(uniform, actual) == pytest.approx(2 / 3)
    assert log_loss(uniform, actual) == pytest.approx(np.log(3))


def test_model_beats_baseline_on_unseen_season(league):
    matches, _ = league
    test_season = matches["season"].iloc[-1]
    model = score_predictions(walk_forward(lambda: DixonColesModel(), matches, test_season, refit_every_days=28))
    base = score_predictions(baseline_predictions(matches, test_season))
    assert model["brier"] < base["brier"]


def test_clean_handles_messy_rows():
    raw = pd.DataFrame({
        "date": ["15/08/2023", "16/08/23", None, "20/08/2023"],
        "home_team": [" Arsenal", "Chelsea", "Spurs", "Leeds"],
        "away_team": ["Forest", "Liverpool", "Brentford", "Burnley"],
        "home_goals": [2, 1, 0, "x"],
        "away_goals": [1, 1, 2, 0],
        "league": "E0", "season": "2324",
    })
    df = clean(raw)
    assert len(df) == 2
    assert list(df["result"]) == ["H", "D"]
    assert df["home_team"].iloc[0] == "Arsenal"
    assert df["date"].iloc[1] == pd.Timestamp("2023-08-16")
