"""Day 9: international results (martj42 dataset) and international Elo.

The dataset: every men's international match since 1872, kept up to date by
Mart Jürisoo. It's on Kaggle, and the same files are on GitHub, which is
easier to download from a script:
https://github.com/martj42/international_results
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pandas as pd

from footiq.elo import EloRatings, international_k

RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
INTERNATIONAL_HOME_ADVANTAGE = 100  # World Football Elo uses 100 rating points

# Names people type -> names used in the dataset
TEAM_ALIASES = {
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Turkiye": "Turkey",
    "USA": "United States",
    "Korea Republic": "South Korea",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde",
}


def canonical_name(team: str) -> str:
    return TEAM_ALIASES.get(team, team)


def download_results(path: str | Path = "data/international/results.csv") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(RESULTS_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        path.write_bytes(response.read())
    return path


def load_results(path: str | Path = "data/international/results.csv") -> pd.DataFrame:
    """Load and tidy: rename score columns to match our club data, drop unplayed rows."""
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.rename(columns={"home_score": "home_goals", "away_score": "away_goals"})
    df = df.dropna(subset=["home_goals", "away_goals"])
    df["home_goals"] = df["home_goals"].astype(int)
    df["away_goals"] = df["away_goals"].astype(int)
    df["neutral"] = df["neutral"].astype(str).str.upper().eq("TRUE")
    df["k"] = df["tournament"].map(international_k)
    df["result"] = "D"
    df.loc[df["home_goals"] > df["away_goals"], "result"] = "H"
    df.loc[df["home_goals"] < df["away_goals"], "result"] = "A"
    return df.sort_values("date", kind="stable").reset_index(drop=True)


def build_international_elo(results: pd.DataFrame) -> tuple[EloRatings, pd.DataFrame]:
    """Rate every national team from 1872 until the latest match.
    Returns the ratings and the matches with their pre-match gaps."""
    elo = EloRatings(home_advantage=INTERNATIONAL_HOME_ADVANTAGE, new_team="start")
    rated = elo.run(results, k_column="k", neutral_column="neutral")
    return elo, rated
