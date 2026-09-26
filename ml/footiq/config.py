"""Day 12: every setting in one place. Change a number here, retrain, done.

After your Day 6 tuning, put your best xi here.
"""

from pathlib import Path

MODELS_DIR = Path("models")
CLUB_DATA = Path("data/processed/matches.csv")
INTERNATIONAL_DATA = Path("data/international/results.csv")

# Dixon-Coles (clubs)
DC_XI = 0.0018          # time decay per day - replace with your tuned value
DC_TRAIN_SEASONS = 4    # how many recent seasons to train on

# Club Elo
CLUB_ELO_K = 20
CLUB_ELO_HOME_ADVANTAGE = 65

# International Elo -> goals conversion is fitted on matches from this date on
INTERNATIONAL_GOALS_FROM = "2000-01-01"
