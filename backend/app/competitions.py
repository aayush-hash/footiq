"""The competitions FOOTIQ follows, and their IDs in each data provider.

To add a competition later (Champions League, World Cup qualifiers...),
add one entry here. model_key must be a model trained in the ml folder.
"""

COMPETITIONS = [
    {"code": "E0", "name": "Premier League", "country": "England", "model_key": "E0",
     "api_football_id": 39, "football_data_code": "PL", "international": False},
    {"code": "SP1", "name": "La Liga", "country": "Spain", "model_key": "SP1",
     "api_football_id": 140, "football_data_code": "PD", "international": False},
    {"code": "D1", "name": "Bundesliga", "country": "Germany", "model_key": "D1",
     "api_football_id": 78, "football_data_code": "BL1", "international": False},
    {"code": "I1", "name": "Serie A", "country": "Italy", "model_key": "I1",
     "api_football_id": 135, "football_data_code": "SA", "international": False},
    {"code": "F1", "name": "Ligue 1", "country": "France", "model_key": "F1",
     "api_football_id": 61, "football_data_code": "FL1", "international": False},
    # football-data.org's free tier doesn't include the Nations League, so it's API-Football only.
    {"code": "UNL", "name": "UEFA Nations League", "country": None, "model_key": "international",
     "api_football_id": 5, "football_data_code": None, "international": True},
]

CURRENT_SEASON = 2026  # 2026/27. Change once a year, in July.


def by_code(code: str) -> dict:
    for c in COMPETITIONS:
        if c["code"] == code:
            return c
    raise KeyError(code)
