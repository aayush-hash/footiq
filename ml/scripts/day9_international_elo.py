"""Day 9: download every international match since 1872 and rate every national team.

    python scripts/day9_international_elo.py
    python scripts/day9_international_elo.py Japan Morocco    (look up any countries)
"""

import sys
from pathlib import Path

from footiq.international import build_international_elo, download_results, load_results

path = Path("data/international/results.csv")
print("Downloading international results...")
download_results(path)

results = load_results(path)
print(f"{len(results):,} matches from {results['date'].min().date()} to {results['date'].max().date()}")
print("\nMost common tournaments:")
print(results["tournament"].value_counts().head(8).to_string())

elo, rated = build_international_elo(results)
table = elo.table()
print("\nWorld top 25 (national team Elo):")
print(table.head(25).round(0).to_string())

for team in sys.argv[1:]:
    if team in elo.ratings:
        rank = int(table.index[table["team"] == team][0])
        print(f"\n{team}: {elo.ratings[team]:.0f} (rank {rank} of {len(table)})")
    else:
        print(f"\n{team}: not found. Check the spelling (the dataset uses names like 'Czech Republic', 'Turkey').")

Path("reports").mkdir(exist_ok=True)
table.to_csv("reports/international_elo.csv")
print("\nSaved reports/international_elo.csv")
