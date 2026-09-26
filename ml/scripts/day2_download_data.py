"""Day 2: download 10 seasons of the top 5 leagues and save one clean CSV.

Run from the ml folder:
    python scripts/day2_download_data.py
"""

from pathlib import Path

from footiq.data import LEAGUES, clean, download_all, last_n_seasons, load_raw

RAW = Path("data/raw")
OUT = Path("data/processed/matches.csv")

seasons = last_n_seasons(10)
print(f"Downloading {len(LEAGUES)} leagues x {len(seasons)} seasons ({seasons[0]} to {seasons[-1]})...")
download_all(RAW, seasons=seasons)

print("Cleaning...")
raw = load_raw(RAW)
matches = clean(raw)
OUT.parent.mkdir(parents=True, exist_ok=True)
matches.to_csv(OUT, index=False)

print(f"\nRaw rows: {len(raw):,}   clean rows: {len(matches):,}   dropped: {len(raw) - len(matches):,}")
print(matches.groupby(["league", "season"]).size().unstack("league").to_string())
print(f"\nSaved to {OUT}")
