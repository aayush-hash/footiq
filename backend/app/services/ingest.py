"""Day 16: save fixtures and results from the provider into the database.

"Upsert" = update the row if it exists, insert it if it doesn't. Running a
sync twice never creates duplicates, because every match and team has a
unique external_id from the provider.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.competitions import COMPETITIONS, CURRENT_SEASON
from app.models import League, Match, Team
from app.services.predictor import known_team_names
from app.services.team_names import resolve


def ensure_leagues(db: Session) -> dict[str, League]:
    """Create the leagues from competitions.py if they don't exist yet."""
    leagues = {}
    for c in COMPETITIONS:
        league = db.scalar(select(League).where(League.code == c["code"]))
        if league is None:
            league = League(code=c["code"])
            db.add(league)
        league.name, league.country = c["name"], c["country"]
        league.model_key, league.is_international = c["model_key"], c["international"]
        league.current_season = CURRENT_SEASON
        leagues[c["code"]] = league
    db.commit()
    return leagues


def upsert_team(db: Session, external_id: str, name: str, league: League, known: list[str]) -> Team:
    team = db.scalar(select(Team).where(Team.external_id == external_id))
    if team is None:
        team = Team(external_id=external_id, name=name, is_national=league.is_international,
                    country=None if league.is_international else league.country)
        db.add(team)
    team.name = name
    if not team.model_name:  # keep a name you fixed by hand
        team.model_name = resolve(name, known)
    return team


def sync_competition(db: Session, provider, code: str, season: int = CURRENT_SEASON) -> dict:
    competition = next(c for c in COMPETITIONS if c["code"] == code)
    league = ensure_leagues(db)[code]
    fixtures = provider.fixtures(competition, season)
    known = known_team_names(league.model_key)

    created = updated = 0
    for f in fixtures:
        home = upsert_team(db, f.home_id, f.home_name, league, known)
        away = upsert_team(db, f.away_id, f.away_name, league, known)
        db.flush()  # gives the new teams their id
        match = db.scalar(select(Match).where(Match.external_id == f.external_id))
        if match is None:
            match = Match(external_id=f.external_id)
            db.add(match)
            created += 1
        else:
            updated += 1
        match.league_id, match.season, match.round = league.id, season, f.round
        match.kickoff, match.status, match.minute = f.kickoff, f.status, f.minute
        match.home_team_id, match.away_team_id = home.id, away.id
        match.home_goals, match.away_goals = f.home_goals, f.away_goals
        match.neutral, match.venue = f.neutral, f.venue
    db.commit()
    return {"league": code, "fixtures": len(fixtures), "created": created, "updated": updated}


def sync_all(db: Session, provider, codes: list[str] | None = None) -> list[dict]:
    """Sync every competition. One provider request per competition."""
    results = []
    for c in COMPETITIONS:
        if codes and c["code"] not in codes:
            continue
        try:
            results.append(sync_competition(db, provider, c["code"]))
        except Exception as error:  # one failing league shouldn't stop the others
            db.rollback()
            results.append({"league": c["code"], "error": str(error)})
    return results
