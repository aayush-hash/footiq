"""Days 4-5: the prediction models.

Day 4 - PoissonModel
    Each team gets two numbers:
      attack  - how good they are at scoring (higher = better)
      defence - how good they are at stopping goals (higher = better)
    Plus one number for the whole league: home advantage.

    Expected goals for the home team:
        lambda_home = exp(home_adv + attack[home] - defence[away])
    Expected goals for the away team:
        lambda_away = exp(attack[away] - defence[home])

    The model "learns" by finding the numbers that make the real results
    most likely (maximum likelihood), using scipy's optimiser.

Day 5 - DixonColesModel
    Same model, plus two upgrades from Dixon and Coles (1997):
      rho - fixes the probability of 0-0, 1-0, 0-1 and 1-1
      xi  - time decay: a match from 2 years ago counts less than last week's
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln

from footiq.simulate import outcome_probs, score_matrix, top_scorelines


class PoissonModel:
    uses_rho = False

    def __init__(self, xi: float = 0.0, l2: float = 0.0):
        self.xi = xi  # time decay per day (0 = every match counts the same)
        self.l2 = l2  # small penalty that keeps team numbers near 0 when data is thin
        self.teams: list[str] = []
        self.attack = self.defence = None
        self.home_adv = 0.0
        self.rho = 0.0
        self.trained_until = None

    # ----- training -------------------------------------------------------

    def fit(self, matches: pd.DataFrame, as_of: pd.Timestamp | None = None) -> "PoissonModel":
        """Learn team strengths from matches (columns: date, home_team, away_team, home_goals, away_goals)."""
        as_of = pd.Timestamp(as_of) if as_of is not None else matches["date"].max()
        self.trained_until = as_of
        self.teams = sorted(set(matches["home_team"]) | set(matches["away_team"]))
        index = {team: i for i, team in enumerate(self.teams)}

        self._h = matches["home_team"].map(index).to_numpy()
        self._a = matches["away_team"].map(index).to_numpy()
        self._x = matches["home_goals"].to_numpy()
        self._y = matches["away_goals"].to_numpy()
        days_ago = (as_of - matches["date"]).dt.days.to_numpy().clip(min=0)
        self._w = np.exp(-self.xi * days_ago)  # weight of each match

        n = len(self.teams)
        start = np.zeros(2 * n + 1 + (1 if self.uses_rho else 0))
        start[2 * n] = 0.25  # home advantage starting guess
        bounds = [(None, None)] * (2 * n + 1) + ([(-0.2, 0.2)] if self.uses_rho else [])

        result = minimize(self._loss, start, jac=True, method="L-BFGS-B", bounds=bounds)
        if not result.success:
            print(f"  warning: optimiser says: {result.message}")
        self._unpack(result.x, store=True)
        return self

    def _unpack(self, params, store=False):
        n = len(self.teams)
        attack = params[:n] - params[:n].mean()  # average attack is fixed at 0
        defence = params[n : 2 * n]
        home_adv = params[2 * n]
        rho = params[2 * n + 1] if self.uses_rho else 0.0
        if store:
            self.attack, self.defence, self.home_adv, self.rho = attack, defence, float(home_adv), float(rho)
        return attack, defence, home_adv, rho

    def _loss(self, params):
        """Negative log-likelihood (lower = the numbers explain the results better) and its gradient."""
        n = len(self.teams)
        attack, defence, home_adv, rho = self._unpack(params)
        h, a, x, y, w = self._h, self._a, self._x, self._y, self._w

        lam_h = np.exp(home_adv + attack[h] - defence[a])
        lam_a = np.exp(attack[a] - defence[h])

        # Poisson log-probability of each real score
        loglik = w * (x * np.log(lam_h) - lam_h - gammaln(x + 1) + y * np.log(lam_a) - lam_a - gammaln(y + 1))
        # derivative of loglik with respect to log(lambda)
        d_log_lam_h = w * (x - lam_h)
        d_log_lam_a = w * (y - lam_a)

        d_rho = 0.0
        if self.uses_rho:
            extra, dh, da, d_rho = self._tau_terms(x, y, lam_h, lam_a, rho, w)
            loglik = loglik + extra
            d_log_lam_h += dh
            d_log_lam_a += da

        # turn per-match derivatives into per-parameter derivatives
        g_attack = np.bincount(h, d_log_lam_h, n) + np.bincount(a, d_log_lam_a, n)
        g_defence = -np.bincount(a, d_log_lam_h, n) - np.bincount(h, d_log_lam_a, n)
        g_attack = g_attack - g_attack.mean()  # because of the "average attack = 0" rule
        g_home = d_log_lam_h.sum()

        loss = -loglik.sum() + self.l2 * (np.sum(attack**2) + np.sum(defence**2))
        grad = -np.concatenate([g_attack, g_defence, [g_home], [d_rho] if self.uses_rho else []])
        grad[:n] += 2 * self.l2 * (attack - 0)  # attack is already centred
        grad[n : 2 * n] += 2 * self.l2 * defence
        return loss, grad

    def _tau_terms(self, x, y, lam_h, lam_a, rho, w):
        return 0.0, 0.0, 0.0, 0.0

    # ----- predicting -----------------------------------------------------

    def _team(self, team: str) -> tuple[float, float]:
        """(attack, defence) for a team. Unknown teams (usually just promoted)
        get the average of the three weakest teams."""
        if team in self.teams:
            i = self.teams.index(team)
            return float(self.attack[i]), float(self.defence[i])
        return float(np.sort(self.attack)[:3].mean()), float(np.sort(self.defence)[:3].mean())

    def expected_goals(self, home: str, away: str, neutral: bool = False) -> tuple[float, float]:
        att_h, def_h = self._team(home)
        att_a, def_a = self._team(away)
        home_adv = 0.0 if neutral else self.home_adv
        return float(np.exp(home_adv + att_h - def_a)), float(np.exp(att_a - def_h))

    def predict(self, home: str, away: str, neutral: bool = False) -> dict:
        lam_h, lam_a = self.expected_goals(home, away, neutral)
        matrix = score_matrix(lam_h, lam_a, self.rho)
        return {
            "home_team": home,
            "away_team": away,
            "expected_goals": {"home": lam_h, "away": lam_a},
            "probabilities": outcome_probs(matrix),
            "top_scorelines": top_scorelines(matrix),
        }

    def ratings(self) -> pd.DataFrame:
        """Team strength table, best overall first."""
        df = pd.DataFrame({"team": self.teams, "attack": self.attack, "defence": self.defence})
        df["overall"] = df["attack"] + df["defence"]
        return df.sort_values("overall", ascending=False).reset_index(drop=True)

    # ----- saving ---------------------------------------------------------

    def save(self, path: str | Path) -> None:
        data = {
            "model": type(self).__name__,
            "xi": self.xi,
            "teams": self.teams,
            "attack": list(map(float, self.attack)),
            "defence": list(map(float, self.defence)),
            "home_adv": self.home_adv,
            "rho": self.rho,
            "trained_until": str(self.trained_until.date()) if self.trained_until is not None else None,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "PoissonModel":
        data = json.loads(Path(path).read_text())
        model_cls = DixonColesModel if data["model"] == "DixonColesModel" else PoissonModel
        model = model_cls(xi=data["xi"])
        model.teams = data["teams"]
        model.attack = np.array(data["attack"])
        model.defence = np.array(data["defence"])
        model.home_adv, model.rho = data["home_adv"], data["rho"]
        model.trained_until = pd.Timestamp(data["trained_until"]) if data["trained_until"] else None
        return model


class DixonColesModel(PoissonModel):
    """Poisson model + low-score correction (rho) + time decay (xi).

    xi = 0.0018 per day means a match from one year ago counts about half
    as much as one played today (exp(-0.0018 * 365) = 0.52).
    """

    uses_rho = True

    def __init__(self, xi: float = 0.0018, l2: float = 0.0):
        super().__init__(xi=xi, l2=l2)

    def _tau_terms(self, x, y, lam_h, lam_a, rho, w):
        """Log of the Dixon-Coles correction, and its derivatives."""
        extra = np.zeros_like(lam_h)
        dh = np.zeros_like(lam_h)  # derivative w.r.t. log(lambda_home)
        da = np.zeros_like(lam_h)  # derivative w.r.t. log(lambda_away)
        drho = np.zeros_like(lam_h)

        m = (x == 0) & (y == 0)
        tau = 1 - lam_h[m] * lam_a[m] * rho
        extra[m] = np.log(tau)
        dh[m] = da[m] = -lam_h[m] * lam_a[m] * rho / tau
        drho[m] = -lam_h[m] * lam_a[m] / tau

        m = (x == 0) & (y == 1)
        tau = 1 + lam_h[m] * rho
        extra[m] = np.log(tau)
        dh[m] = lam_h[m] * rho / tau
        drho[m] = lam_h[m] / tau

        m = (x == 1) & (y == 0)
        tau = 1 + lam_a[m] * rho
        extra[m] = np.log(tau)
        da[m] = lam_a[m] * rho / tau
        drho[m] = lam_a[m] / tau

        m = (x == 1) & (y == 1)
        extra[m] = np.log(1 - rho)
        drho[m] = -1 / (1 - rho)

        return w * extra, w * dh, w * da, float((w * drho).sum())
