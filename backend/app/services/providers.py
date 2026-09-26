"""Day 16: fetch fixtures and results from a football data API.

Two providers with the same interface, so you can switch with one setting
(DATA_PROVIDER in .env) if one of them stops working for you:
  - API-Football  (api-football.com, free: 100 requests/day)
  - football-data.org (free: 10 requests/minute, top leagues only)

Both return a list of FixtureData, so the rest of the app never cares
which one is in use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx


class ProviderError(Exception):
    """The API said no: bad key, plan limit, or no access to that season."""


@dataclass
class FixtureData:
    external_id: str
    kickoff: datetime
    status: str            # scheduled / live / finished / postponed / cancelled
    home_id: str
    home_name: str
    away_id: str
    away_name: str
    home_goals: int | None = None
    away_goals: int | None = None
    minute: int | None = None
    round: str | None = None
    venue: str | None = None
    neutral: bool = False


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ApiFootballProvider:
    name = "api_football"
    base_url = "https://v3.football.api-sports.io"

    STATUS = {
        "TBD": "scheduled", "NS": "scheduled",
        "1H": "live", "HT": "live", "2H": "live", "ET": "live", "BT": "live", "P": "live",
        "LIVE": "live", "INT": "live", "SUSP": "live",
        "FT": "finished", "AET": "finished", "PEN": "finished",
        "PST": "postponed",
        "CANC": "cancelled", "ABD": "cancelled", "AWD": "cancelled", "WO": "cancelled",
    }

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        if not api_key:
            raise ProviderError("API_FOOTBALL_KEY is empty. Add your key to backend/.env")
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"x-apisports-key": api_key}

    def _get(self, path: str, params: dict) -> list:
        response = self.client.get(f"{self.base_url}{path}", params=params, headers=self.headers)
        response.raise_for_status()
        data = response.json()
        if data.get("errors"):  # API-Football reports problems here, with status 200
            raise ProviderError(f"API-Football: {data['errors']}")
        return data["response"]

    def status(self) -> dict:
        response = self.client.get(f"{self.base_url}/competitions/PL", headers=self.headers)
        if response.status_code in (400, 403):
            raise ProviderError(f"football-data.org: {response.json().get('message', response.text)}")
        response.raise_for_status()
        return {"ok": True, "competition": response.json().get("name")}

    def fixtures(self, competition: dict, season: int) -> list[FixtureData]:
        """Every fixture of a competition's season, in ONE request."""
        items = self._get("/fixtures", {"league": competition["api_football_id"], "season": season})
        out = []
        for item in items:
            fx, teams = item["fixture"], item["teams"]
            status = self.STATUS.get(fx["status"]["short"], "scheduled")
            # For our 90-minute models we want the score after normal time,
            # not after extra time or penalties.
            fulltime = (item.get("score") or {}).get("fulltime") or {}
            goals = fulltime if fulltime.get("home") is not None else item["goals"]
            out.append(FixtureData(
                external_id=f"api_football:{fx['id']}",
                kickoff=_parse_time(fx["date"]),
                status=status,
                minute=fx["status"].get("elapsed") if status == "live" else None,
                home_id=f"api_football:{teams['home']['id']}", home_name=teams["home"]["name"],
                away_id=f"api_football:{teams['away']['id']}", away_name=teams["away"]["name"],
                home_goals=goals.get("home"), away_goals=goals.get("away"),
                round=item["league"].get("round"),
                venue=(fx.get("venue") or {}).get("name"),
            ))
        return out


class FootballDataOrgProvider:
    name = "football_data_org"
    base_url = "https://api.football-data.org/v4"

    STATUS = {
        "SCHEDULED": "scheduled", "TIMED": "scheduled",
        "IN_PLAY": "live", "PAUSED": "live", "LIVE": "live",
        "FINISHED": "finished", "AWARDED": "finished",
        "POSTPONED": "postponed", "SUSPENDED": "postponed",
        "CANCELLED": "cancelled",
    }

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        if not api_key:
            raise ProviderError("FOOTBALL_DATA_ORG_KEY is empty. Add your key to backend/.env")
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"X-Auth-Token": api_key}

    def status(self) -> dict:
        response = self.client.get(f"{self.base_url}/competitions/PL", headers=self.headers)
        response.raise_for_status()
        return {"ok": True, "competition": response.json().get("name")}

    def fixtures(self, competition: dict, season: int) -> list[FixtureData]:
        code = competition.get("football_data_code")
        if not code:
            raise ProviderError(f"football-data.org doesn't cover {competition['name']}")
        response = self.client.get(f"{self.base_url}/competitions/{code}/matches",
                                   params={"season": season}, headers=self.headers)
        if response.status_code in (400, 403):
            raise ProviderError(f"football-data.org: {response.json().get('message', response.text)}")
        response.raise_for_status()
        out = []
        for m in response.json()["matches"]:
            score = m.get("score") or {}
            goals = score.get("regularTime") or score.get("fullTime") or {}
            out.append(FixtureData(
                external_id=f"football_data_org:{m['id']}",
                kickoff=_parse_time(m["utcDate"]),
                status=self.STATUS.get(m["status"], "scheduled"),
                home_id=f"football_data_org:{m['homeTeam']['id']}", home_name=m["homeTeam"]["name"],
                away_id=f"football_data_org:{m['awayTeam']['id']}", away_name=m["awayTeam"]["name"],
                home_goals=goals.get("home"), away_goals=goals.get("away"),
                round=f"Matchday {m['matchday']}" if m.get("matchday") else m.get("stage"),
            ))
        return out


def get_provider(settings):
    if settings.data_provider == "api_football":
        return ApiFootballProvider(settings.api_football_key)
    if settings.data_provider == "football_data_org":
        return FootballDataOrgProvider(settings.football_data_org_key)
    raise ProviderError(f"Unknown DATA_PROVIDER '{settings.data_provider}'")
