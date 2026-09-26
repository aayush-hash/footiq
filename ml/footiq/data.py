"""Day 2: download and clean match results from football-data.co.uk.

football-data.co.uk publishes one CSV per league per season, for free.
URL pattern: https://www.football-data.co.uk/mmz4281/<season>/<league>.csv
  season "2324" means the 2023/24 season
  league codes: E0 = Premier League, SP1 = La Liga, D1 = Bundesliga,
                I1 = Serie A, F1 = Ligue 1
"""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path

import pandas as pd

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"

LEAGUES = {
    "E0": "Premier League",
    "SP1": "La Liga",
    "D1": "Bundesliga",
    "I1": "Serie A",
    "F1": "Ligue 1",
}

# The raw CSV columns we need, and the clean names we give them.
COLUMNS = {
    "Date": "date",
    "HomeTeam": "home_team",
    "AwayTeam": "away_team",
    "FTHG": "home_goals",  # full-time home goals
    "FTAG": "away_goals",  # full-time away goals
}


def season_code(start_year: int) -> str:
    """2023 -> '2324' (the 2023/24 season)."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def last_n_seasons(n: int = 10, last_start_year: int = 2025) -> list[str]:
    """The last n season codes, oldest first. Default: 2016/17 ... 2025/26."""
    return [season_code(y) for y in range(last_start_year - n + 1, last_start_year + 1)]


def download_all(
    raw_dir: str | Path = "data/raw",
    leagues: list[str] | None = None,
    seasons: list[str] | None = None,
    overwrite: bool = False,
) -> list[Path]:
    """Download every league/season CSV into raw_dir. Skips files you already have."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    leagues = leagues or list(LEAGUES)
    seasons = seasons or last_n_seasons()

    saved = []
    for league in leagues:
        for season in seasons:
            path = raw_dir / f"{league}_{season}.csv"
            if path.exists() and not overwrite:
                saved.append(path)
                continue
            url = BASE_URL.format(season=season, league=league)
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    path.write_bytes(response.read())
                saved.append(path)
                print(f"  downloaded {path.name}")
            except Exception as error:  # keep going if one file fails
                print(f"  FAILED {url}: {error}")
            time.sleep(1)  # be polite to a free website
    return saved


def load_raw(raw_dir: str | Path = "data/raw") -> pd.DataFrame:
    """Read every CSV in raw_dir into one table, adding league and season columns."""
    frames = []
    for path in sorted(Path(raw_dir).glob("*.csv")):
        league, season = path.stem.split("_")
        # Some older files use latin-1 encoding and have broken trailing lines.
        df = pd.read_csv(path, encoding="latin-1", on_bad_lines="skip")
        missing = [c for c in COLUMNS if c not in df.columns]
        if missing:
            print(f"  skipping {path.name}: missing columns {missing}")
            continue
        df = df[list(COLUMNS)].rename(columns=COLUMNS)
        df["league"] = league
        df["season"] = season
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No usable CSV files found in {raw_dir}")
    return pd.concat(frames, ignore_index=True)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Fix types, drop empty or broken rows, and add a result column (H/D/A)."""
    df = df.copy()
    df = df.dropna(subset=["date", "home_team", "away_team", "home_goals", "away_goals"])

    # Dates appear as 15/08/2023 or 15/08/23 depending on the season.
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, format="mixed", errors="coerce")
    df = df.dropna(subset=["date"])

    df["home_goals"] = pd.to_numeric(df["home_goals"], errors="coerce")
    df["away_goals"] = pd.to_numeric(df["away_goals"], errors="coerce")
    df = df.dropna(subset=["home_goals", "away_goals"])
    df["home_goals"] = df["home_goals"].astype(int)
    df["away_goals"] = df["away_goals"].astype(int)

    df["home_team"] = df["home_team"].str.strip()
    df["away_team"] = df["away_team"].str.strip()

    df["result"] = "D"
    df.loc[df["home_goals"] > df["away_goals"], "result"] = "H"
    df.loc[df["home_goals"] < df["away_goals"], "result"] = "A"

    df = df.drop_duplicates(subset=["league", "date", "home_team", "away_team"])
    df = df.sort_values(["date", "league", "home_team"]).reset_index(drop=True)
    return df[["date", "league", "season", "home_team", "away_team", "home_goals", "away_goals", "result"]]


def load_matches(path: str | Path = "data/processed/matches.csv") -> pd.DataFrame:
    """Load the cleaned file that scripts/day2_download_data.py creates."""
    return pd.read_csv(path, parse_dates=["date"], dtype={"season": str})
