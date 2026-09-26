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
import time
from datetime import date, datetime

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


@dataclass
class PlayerData:
    """Day 28"""
    external_id: str
    name: str
    position: str | None = None
    birth_date: date | None = None
    nationality: str | None = None
    shirt_number: int | None = None


@dataclass
class ScorerData:
    """Day 28: one row of a competition's top-scorer list."""
    player: PlayerData
    team_external_id: str
    team_name: str
    appearances: int | None
    goals: int
    assists: int | None
    penalties: int | None


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


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
        """Your account and today's usage. Costs no request quota."""
        response = self.client.get(f"{self.base_url}/status", headers=self.headers)
        response.raise_for_status()
        return response.json()["response"]

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


    def squad(self, team_external_id: str) -> list[PlayerData]:
        raise ProviderError("Player data uses football-data.org. Set DATA_PROVIDER=football_data_org")

    def scorers(self, competition: dict, season: int, limit: int = 50) -> list[ScorerData]:
        raise ProviderError("Player data uses football-data.org. Set DATA_PROVIDER=football_data_org")


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

    def __init__(self, api_key: str, client: httpx.Client | None = None, min_interval: float = 6.5):
        if not api_key:
            raise ProviderError("FOOTBALL_DATA_ORG_KEY is empty. Add your key to backend/.env")
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"X-Auth-Token": api_key}
        # Free tier: 10 requests a minute. Waiting 6.5 s between requests keeps us under it.
        self.min_interval = min_interval
        self._last_request = 0.0

    def _get(self, path: str, params: dict | None = None) -> dict:
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        response = self.client.get(f"{self.base_url}{path}", params=params, headers=self.headers)
        self._last_request = time.monotonic()
        if response.status_code in (400, 403, 429):
            try:
                message = response.json().get("message", response.text)
            except ValueError:
                message = response.text
            raise ProviderError(f"football-data.org: {message}")
        response.raise_for_status()
        return response.json()

    def status(self) -> dict:
        return {"ok": True, "competition": self._get("/competitions/PL").get("name")}

    def squad(self, team_external_id: str) -> list[PlayerData]:
        """Day 28: every player in a team's current squad."""
        team_id = team_external_id.split(":")[-1]
        data = self._get(f"/teams/{team_id}")
        return [self._player(p) for p in data.get("squad", [])]

    def scorers(self, competition: dict, season: int, limit: int = 50) -> list[ScorerData]:
        """Day 28: the competition's top scorers, with goals, assists and penalties."""
        code = competition.get("football_data_code")
        if not code:
            raise ProviderError(f"football-data.org doesn't cover {competition['name']}")
        data = self._get(f"/competitions/{code}/scorers", {"season": season, "limit": limit})
        return [ScorerData(
            player=self._player(s["player"]),
            team_external_id=f"football_data_org:{s['team']['id']}", team_name=s["team"]["name"],
            appearances=s.get("playedMatches"), goals=s.get("goals") or 0,
            assists=s.get("assists"), penalties=s.get("penalties"),
        ) for s in data.get("scorers", [])]

    @staticmethod
    def _player(p: dict) -> PlayerData:
        return PlayerData(external_id=f"football_data_org:{p['id']}", name=p["name"],
                          position=p.get("position") or p.get("section"), birth_date=_parse_date(p.get("dateOfBirth")),
                          nationality=p.get("nationality"), shirt_number=p.get("shirtNumber"))

    def fixtures(self, competition: dict, season: int) -> list[FixtureData]:
        code = competition.get("football_data_code")
        if not code:
            raise ProviderError(f"football-data.org doesn't cover {competition['name']}")
        out = []
        for m in self._get(f"/competitions/{code}/matches", {"season": season})["matches"]:
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
