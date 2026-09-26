"""Provider parsing, tested with fake HTTP responses shaped like the real APIs.
No real network calls and no API quota used."""

import httpx
import pytest

from app.competitions import by_code
from app.services.providers import ApiFootballProvider, FootballDataOrgProvider, ProviderError

API_FOOTBALL_SAMPLE = {
    "errors": [],
    "response": [
        {"fixture": {"id": 1001, "date": "2026-09-27T14:00:00+00:00", "venue": {"name": "Etihad Stadium"},
                     "status": {"short": "NS", "elapsed": None}},
         "league": {"id": 39, "round": "Regular Season - 6"},
         "teams": {"home": {"id": 50, "name": "Manchester City"}, "away": {"id": 42, "name": "Arsenal"}},
         "goals": {"home": None, "away": None},
         "score": {"fulltime": {"home": None, "away": None}}},
        {"fixture": {"id": 1002, "date": "2026-09-20T16:30:00+00:00", "venue": {"name": "Anfield"},
                     "status": {"short": "AET", "elapsed": 120}},
         "league": {"id": 39, "round": "Regular Season - 5"},
         "teams": {"home": {"id": 40, "name": "Liverpool"}, "away": {"id": 49, "name": "Chelsea"}},
         "goals": {"home": 2, "away": 1},
         "score": {"fulltime": {"home": 1, "away": 1}}},
        {"fixture": {"id": 1003, "date": "2026-09-26T19:00:00+00:00", "venue": {},
                     "status": {"short": "2H", "elapsed": 67}},
         "league": {"id": 39, "round": "Regular Season - 6"},
         "teams": {"home": {"id": 33, "name": "Manchester United"}, "away": {"id": 39, "name": "Wolves"}},
         "goals": {"home": 0, "away": 1},
         "score": {"fulltime": {"home": None, "away": None}}},
    ],
}


def client_returning(payload, status=200, check=None):
    def handler(request):
        if check:
            check(request)
        return httpx.Response(status, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_api_football_parsing():
    def check(request):
        assert request.headers["x-apisports-key"] == "KEY"
        assert request.url.params["league"] == "39" and request.url.params["season"] == "2026"
    provider = ApiFootballProvider("KEY", client_returning(API_FOOTBALL_SAMPLE, check=check))
    upcoming, extra_time, live = provider.fixtures(by_code("E0"), 2026)

    assert upcoming.status == "scheduled" and upcoming.home_goals is None
    assert upcoming.external_id == "api_football:1001" and upcoming.home_id == "api_football:50"
    assert upcoming.kickoff.utcoffset().total_seconds() == 0
    assert extra_time.status == "finished"
    assert (extra_time.home_goals, extra_time.away_goals) == (1, 1)  # score after 90 minutes, not after extra time
    assert live.status == "live" and live.minute == 67 and live.away_goals == 1


def test_api_football_plan_error_is_clear():
    payload = {"errors": {"plan": "Free plans do not have access to this season, try from 2022 to 2024."}, "response": []}
    provider = ApiFootballProvider("KEY", client_returning(payload))
    with pytest.raises(ProviderError, match="Free plans"):
        provider.fixtures(by_code("E0"), 2026)


def test_missing_key_is_clear():
    with pytest.raises(ProviderError, match="API_FOOTBALL_KEY"):
        ApiFootballProvider("")


FOOTBALL_DATA_SAMPLE = {"matches": [
    {"id": 555, "utcDate": "2026-09-27T14:00:00Z", "status": "TIMED", "matchday": 6,
     "homeTeam": {"id": 65, "name": "Manchester City FC"}, "awayTeam": {"id": 57, "name": "Arsenal FC"},
     "score": {"fullTime": {"home": None, "away": None}}},
    {"id": 556, "utcDate": "2026-09-20T14:00:00Z", "status": "FINISHED", "matchday": 5,
     "homeTeam": {"id": 64, "name": "Liverpool FC"}, "awayTeam": {"id": 61, "name": "Chelsea FC"},
     "score": {"fullTime": {"home": 3, "away": 0}}},
]}


def test_football_data_org_parsing():
    def check(request):
        assert request.headers["X-Auth-Token"] == "KEY" and request.url.path.endswith("/competitions/PL/matches")
    provider = FootballDataOrgProvider("KEY", client_returning(FOOTBALL_DATA_SAMPLE, check=check))
    upcoming, finished = provider.fixtures(by_code("E0"), 2026)
    assert upcoming.status == "scheduled" and upcoming.round == "Matchday 6"
    assert finished.status == "finished" and (finished.home_goals, finished.away_goals) == (3, 0)


def test_football_data_org_has_no_nations_league():
    provider = FootballDataOrgProvider("KEY", client_returning({}))
    with pytest.raises(ProviderError, match="doesn't cover"):
        provider.fixtures(by_code("UNL"), 2026)
