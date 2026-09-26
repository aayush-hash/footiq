"""Day 7: turn expected goals into probabilities, scorelines and what-if scenarios.

Everything here only needs two numbers: how many goals each team is expected
to score (lambda). The models from Days 4-5 produce those numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import poisson

MAX_GOALS = 10  # we ignore scorelines above 10 goals per team (almost never happen)

# What-if assumptions. These are sensible starting values, not facts.
# Later you can estimate them from data and replace them.
RED_CARD_OWN_FACTOR = 0.70       # a team with one red card scores at 70% of its rate
RED_CARD_OPPONENT_FACTOR = 1.20  # ... and its opponent scores 20% more
MATCH_MINUTES = 90


def dixon_coles_tau(home_goals, away_goals, lam_home, lam_away, rho):
    """Dixon-Coles correction for low scores (0-0, 1-0, 0-1, 1-1).

    Plain Poisson slightly gets these four scores wrong (real football has
    a few more 0-0s and 1-1s). rho nudges them. rho = 0 means no change.
    """
    tau = np.ones(np.broadcast(home_goals, away_goals).shape)
    tau = np.where((home_goals == 0) & (away_goals == 0), 1 - lam_home * lam_away * rho, tau)
    tau = np.where((home_goals == 0) & (away_goals == 1), 1 + lam_home * rho, tau)
    tau = np.where((home_goals == 1) & (away_goals == 0), 1 + lam_away * rho, tau)
    tau = np.where((home_goals == 1) & (away_goals == 1), 1 - rho, tau)
    return tau


def score_matrix(lam_home: float, lam_away: float, rho: float = 0.0, max_goals: int = MAX_GOALS) -> np.ndarray:
    """Probability of every scoreline. matrix[i, j] = P(home scores i, away scores j)."""
    goals = np.arange(max_goals + 1)
    home_pmf = poisson.pmf(goals, lam_home)
    away_pmf = poisson.pmf(goals, lam_away)
    matrix = np.outer(home_pmf, away_pmf)
    if rho != 0.0:
        i, j = np.meshgrid(goals, goals, indexing="ij")
        matrix = matrix * dixon_coles_tau(i, j, lam_home, lam_away, rho)
    return matrix / matrix.sum()  # renormalise so everything adds to exactly 1


def outcome_probs(matrix: np.ndarray, offset_home: int = 0, offset_away: int = 0) -> dict:
    """Home win / draw / away win from a score matrix.

    offset_* = goals already scored (used by the what-if engine).
    """
    goals = np.arange(matrix.shape[0])
    final_home = goals[:, None] + offset_home
    final_away = goals[None, :] + offset_away
    return {
        "home_win": float(matrix[final_home > final_away].sum()),
        "draw": float(matrix[final_home == final_away].sum()),
        "away_win": float(matrix[final_home < final_away].sum()),
    }


def top_scorelines(matrix: np.ndarray, n: int = 5, offset_home: int = 0, offset_away: int = 0) -> list[dict]:
    """The n most likely final scores."""
    flat = np.argsort(matrix, axis=None)[::-1][:n]
    rows, cols = np.unravel_index(flat, matrix.shape)
    return [
        {"score": f"{r + offset_home}-{c + offset_away}", "probability": float(matrix[r, c])}
        for r, c in zip(rows, cols)
    ]


def simulate_matches(matrix: np.ndarray, n: int = 10_000, seed: int | None = None) -> np.ndarray:
    """Actually 'play' the match n times by sampling from the score matrix.

    Returns an array of shape (n, 2): home goals and away goals for each run.
    The exact probabilities above are more precise; this is useful for
    features that need individual simulated matches (like season simulations).
    """
    rng = np.random.default_rng(seed)
    picks = rng.choice(matrix.size, size=n, p=matrix.ravel())
    home, away = np.unravel_index(picks, matrix.shape)
    return np.column_stack([home, away])


@dataclass
class MatchState:
    """Where the match is right now."""

    minute: int = 0
    home_goals: int = 0
    away_goals: int = 0
    home_red_cards: int = 0
    away_red_cards: int = 0


def remaining_rates(lam_home: float, lam_away: float, state: MatchState) -> tuple[float, float]:
    """Expected goals for the rest of the match, given the current state."""
    minutes_left = max(MATCH_MINUTES - state.minute, 0)
    time_left = minutes_left / MATCH_MINUTES
    home = lam_home * time_left
    away = lam_away * time_left
    home *= RED_CARD_OWN_FACTOR ** state.home_red_cards * RED_CARD_OPPONENT_FACTOR ** state.away_red_cards
    away *= RED_CARD_OWN_FACTOR ** state.away_red_cards * RED_CARD_OPPONENT_FACTOR ** state.home_red_cards
    return home, away


def what_if(lam_home: float, lam_away: float, state: MatchState, rho: float = 0.0, n_top: int = 5) -> dict:
    """The what-if engine: probabilities from the current state to full time.

    Example: 1-0 to Madrid at 17', Barcelona red card at 63' ->
        what_if(1.72, 1.43, MatchState(minute=63, away_goals=1, home_red_cards=1))
    """
    rest_home, rest_away = remaining_rates(lam_home, lam_away, state)
    # The low-score correction only makes sense for a whole match from 0-0.
    use_rho = rho if (state.minute == 0 and state.home_goals == 0 and state.away_goals == 0) else 0.0
    matrix = score_matrix(rest_home, rest_away, rho=use_rho)
    return {
        "state": state,
        "remaining_xg": {"home": rest_home, "away": rest_away},
        "probabilities": outcome_probs(matrix, state.home_goals, state.away_goals),
        "top_scorelines": top_scorelines(matrix, n_top, state.home_goals, state.away_goals),
    }
