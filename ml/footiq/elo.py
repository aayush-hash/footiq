"""Days 8-10: Elo ratings, and turning them into expected goals.

Elo in one paragraph
--------------------
Every team has a rating number (everyone starts at 1500). Before a match,
the rating gap tells you how likely each side is to win. After the match,
points move from the loser to the winner. A surprise (a weak team beating a
strong one) moves many points; an expected result moves only a few. That's
the whole idea. It was invented for chess and works well for football.

    expected score for home = 1 / (1 + 10 ** (-gap / 400))
    gap = home rating + home advantage - away rating
    new rating = old rating + K * margin_multiplier * (actual score - expected score)

    actual score: win = 1, draw = 0.5, loss = 0

Elo only gives an "expected score", not goals or draw chances. Day 10's
EloGoalsModel converts the rating gap into expected goals, so the same
simulation engine from Week 1 works for Elo too.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from footiq.simulate import outcome_probs, score_matrix, top_scorelines

START_RATING = 1500.0


def goal_margin_multiplier(margin: int) -> float:
    """Winning by more moves more points (World Football Elo formula)."""
    margin = abs(int(margin))
    if margin <= 1:
        return 1.0
    if margin == 2:
        return 1.5
    return (11 + margin) / 8


def international_k(tournament: str) -> float:
    """How much a match counts, by tournament (World Football Elo style).
    A World Cup match moves ratings three times as much as a friendly."""
    t = str(tournament).lower()
    if t == "fifa world cup":
        return 60
    if "qualification" in t or "nations league" in t:
        return 40
    if t in {"uefa euro", "copa américa", "copa america", "african cup of nations",
             "afc asian cup", "gold cup", "confederations cup"}:
        return 50
    if t == "friendly":
        return 20
    return 30


class EloRatings:
    """Elo ratings that update one match at a time."""

    def __init__(self, k: float = 20, home_advantage: float = 65, new_team: str = "start"):
        """
        k:              how fast ratings move (clubs ~20, internationals use international_k)
        home_advantage: rating points added to the home side (clubs ~65, countries ~100)
        new_team:       "start" = new teams begin at 1500
                        "weak"  = new teams begin at the average of the 3 lowest ratings
                                  (right for club leagues, where new teams are promoted sides)
        """
        self.k = k
        self.home_advantage = home_advantage
        self.new_team = new_team
        self.ratings: dict[str, float] = {}
        self.last_date: pd.Timestamp | None = None

    def rating(self, team: str) -> float:
        if team not in self.ratings:
            if self.new_team == "weak" and len(self.ratings) >= 3:
                self.ratings[team] = float(np.mean(sorted(self.ratings.values())[:3]))
            else:
                self.ratings[team] = START_RATING
        return self.ratings[team]

    def gap(self, home: str, away: str, neutral: bool = False) -> float:
        """Rating gap from the home side's point of view, including home advantage."""
        return self.rating(home) + (0 if neutral else self.home_advantage) - self.rating(away)

    def expected_score(self, home: str, away: str, neutral: bool = False) -> float:
        return 1 / (1 + 10 ** (-self.gap(home, away, neutral) / 400))

    def update(self, home, away, home_goals, away_goals, neutral=False, k=None, date=None) -> float:
        """Apply one result. Returns the gap BEFORE the match (useful for training)."""
        gap = self.gap(home, away, neutral)
        expected = 1 / (1 + 10 ** (-gap / 400))
        actual = 1.0 if home_goals > away_goals else (0.5 if home_goals == away_goals else 0.0)
        change = (k or self.k) * goal_margin_multiplier(home_goals - away_goals) * (actual - expected)
        self.ratings[home] += change
        self.ratings[away] -= change
        if date is not None:
            self.last_date = pd.Timestamp(date)
        return gap

    def run(self, matches: pd.DataFrame, k_column: str | None = None, neutral_column: str | None = None) -> pd.DataFrame:
        """Play through matches in date order. Returns a copy with the pre-match
        rating gap in a new 'elo_gap' column. Because each gap is recorded
        before the match updates the ratings, there is no future data leakage."""
        matches = matches.sort_values("date", kind="stable")
        gaps = []
        for m in matches.itertuples(index=False):
            m = m._asdict()
            gaps.append(self.update(
                m["home_team"], m["away_team"], m["home_goals"], m["away_goals"],
                neutral=bool(m[neutral_column]) if neutral_column else False,
                k=m[k_column] if k_column else None,
                date=m["date"],
            ))
        out = matches.copy()
        out["elo_gap"] = gaps
        return out

    def table(self) -> pd.DataFrame:
        df = pd.DataFrame(sorted(self.ratings.items(), key=lambda kv: -kv[1]), columns=["team", "elo"])
        df.index += 1
        return df

    def to_dict(self) -> dict:
        return {"k": self.k, "home_advantage": self.home_advantage, "new_team": self.new_team,
                "last_date": str(self.last_date.date()) if self.last_date is not None else None,
                "ratings": self.ratings}

    @classmethod
    def from_dict(cls, data: dict) -> "EloRatings":
        elo = cls(k=data["k"], home_advantage=data["home_advantage"], new_team=data["new_team"])
        elo.ratings = dict(data["ratings"])
        elo.last_date = pd.Timestamp(data["last_date"]) if data["last_date"] else None
        return elo


class EloGoalsModel:
    """Day 10: turn an Elo gap into expected goals.

        expected goals for a side = exp(a + b * (that side's gap / 400))

    The home side's gap is +gap, the away side's is -gap. a sets the average
    number of goals; b says how much a stronger rating turns into goals.
    Both are learned from past matches with the same maximum-likelihood idea
    as the Poisson model on Day 4.
    """

    def __init__(self, ratings: EloRatings):
        self.ratings = ratings
        self.a = 0.3
        self.b = 0.7

    def fit(self, history: pd.DataFrame) -> "EloGoalsModel":
        """history needs columns elo_gap, home_goals, away_goals (from EloRatings.run)."""
        x = np.concatenate([history["elo_gap"], -history["elo_gap"]]) / 400
        goals = np.concatenate([history["home_goals"], history["away_goals"]]).astype(float)

        def loss(p):
            lam = np.exp(p[0] + p[1] * x)
            return (lam - goals * np.log(lam)).sum(), np.array([(lam - goals).sum(), ((lam - goals) * x).sum()])

        result = minimize(loss, [0.3, 0.7], jac=True, method="L-BFGS-B")
        self.a, self.b = map(float, result.x)
        return self

    def goals_from_gap(self, gap: float) -> tuple[float, float]:
        return float(np.exp(self.a + self.b * gap / 400)), float(np.exp(self.a - self.b * gap / 400))

    def expected_goals(self, home: str, away: str, neutral: bool = False) -> tuple[float, float]:
        return self.goals_from_gap(self.ratings.gap(home, away, neutral))

    def predict(self, home: str, away: str, neutral: bool = False) -> dict:
        lam_h, lam_a = self.expected_goals(home, away, neutral)
        matrix = score_matrix(lam_h, lam_a)
        return {
            "home_team": home, "away_team": away,
            "elo": {"home": self.ratings.rating(home), "away": self.ratings.rating(away)},
            "expected_goals": {"home": lam_h, "away": lam_a},
            "probabilities": outcome_probs(matrix),
            "top_scorelines": top_scorelines(matrix),
        }

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({"model": "EloGoalsModel", "a": self.a, "b": self.b,
                                          "elo": self.ratings.to_dict()}, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "EloGoalsModel":
        data = json.loads(Path(path).read_text())
        model = cls(EloRatings.from_dict(data["elo"]))
        model.a, model.b = data["a"], data["b"]
        return model


def elo_walk_forward(matches: pd.DataFrame, test_season: str, k: float = 20, home_advantage: float = 65) -> pd.DataFrame:
    """Day 8: club Elo predictions for a test season, in the same format as
    evaluate.walk_forward, so the scores can be compared with Dixon-Coles.

    Ratings only ever use earlier matches (they update after each match), and
    the goals conversion (a, b) is fitted only on seasons before the test season.
    """
    rated = EloRatings(k=k, home_advantage=home_advantage, new_team="weak").run(matches)
    test = rated[rated["season"] == test_season]
    history = rated[(rated["date"] < test["date"].min()) & (rated["season"] != rated["season"].min())]  # skip warm-up season
    goals = EloGoalsModel(EloRatings()).fit(history)

    rows = []
    for m in test.itertuples():
        p = outcome_probs(score_matrix(*goals.goals_from_gap(m.elo_gap)))
        rows.append({"date": m.date, "home_team": m.home_team, "away_team": m.away_team, "result": m.result,
                     "p_home": p["home_win"], "p_draw": p["draw"], "p_away": p["away_win"]})
    return pd.DataFrame(rows)
