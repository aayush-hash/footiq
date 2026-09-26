"""Day 28: save players and their current-season stats.

Two jobs, because they cost very different amounts of API requests:
  sync_scorers  - top scorers of each league: 1 request per league (5 total).
                  Gives goals, assists, penalties, appearances. Cheap: runs daily.
  sync_squads   - every player of every team: 1 request per team (about 96).
                  Gives the full player list. At 10 requests a minute that takes
                  about 11 minutes, so run it weekly or by hand.

What this does NOT give yet: full careers, older seasons, or players outside
the top 5 leagues (Messi plays in MLS). Those come in Phase 2.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.competitions import COMPETITIONS, CURRENT_SEASON
from app.models import League, Match, Player, PlayerSeasonStats, Team
from app.services.providers import PlayerData
from app.text import fold


def search_key(name: str) -> str:
    """'Kylian Mbappé' -> 'kylian mbappe', so searches ignore accents and capitals."""
    return fold(name)


def upsert_player(db: Session, data: PlayerData, team: Team | None) -> Player:
    player = db.scalar(select(Player).where(Player.external_id == data.external_id))
    if player is None:
        player = Player(external_id=data.external_id, name=data.name)
        db.add(player)
    player.name, player.search_name = data.name, search_key(data.name)
    player.position = data.position or player.position
    player.birth_date = data.birth_date or player.birth_date
    player.nationality = data.nationality or player.nationality
    player.shirt_number = data.shirt_number or player.shirt_number
    if team is not None:
        player.team_id = team.id
    return player


def _league_teams(db: Session, league: League) -> list[Team]:
    ids = (select(Match.home_team_id).where(Match.league_id == league.id)
           .union(select(Match.away_team_id).where(Match.league_id == league.id)))
    return list(db.scalars(select(Team).where(Team.id.in_(ids)).order_by(Team.name)))


def sync_squads(db: Session, provider, codes: list[str] | None = None, progress=print) -> dict:
    saved = teams_done = 0
    errors = []
    for league in db.scalars(select(League).where(League.is_international.is_(False))):
        if codes and league.code not in codes:
            continue
        for team in _league_teams(db, league):
            if not team.external_id.startswith("football_data_org:"):
                continue  # squads need the team's football-data.org id
            try:
                for p in provider.squad(team.external_id):
                    upsert_player(db, p, team)
                    saved += 1
                db.commit()
                teams_done += 1
                progress(f"  {league.code} {team.name}: done")
            except Exception as error:
                db.rollback()
                errors.append(f"{team.name}: {error}")
    return {"teams": teams_done, "players_saved": saved, "errors": errors}


def sync_scorers(db: Session, provider, codes: list[str] | None = None, season: int = CURRENT_SEASON) -> list[dict]:
    results = []
    for c in COMPETITIONS:
        if c["international"] or (codes and c["code"] not in codes):
            continue
        league = db.scalar(select(League).where(League.code == c["code"]))
        if league is None:
            continue
        try:
            rows = provider.scorers(c, season)
        except Exception as error:
            db.rollback()
            results.append({"league": c["code"], "error": str(error)})
            continue
        for row in rows:
            team = db.scalar(select(Team).where(Team.external_id == row.team_external_id))
            player = upsert_player(db, row.player, team)
            db.flush()
            stats = db.scalar(select(PlayerSeasonStats).where(
                PlayerSeasonStats.player_id == player.id, PlayerSeasonStats.league_id == league.id,
                PlayerSeasonStats.season == season))
            if stats is None:
                stats = PlayerSeasonStats(player_id=player.id, league_id=league.id, season=season)
                db.add(stats)
            stats.team_id = team.id if team else None
            stats.appearances, stats.goals = row.appearances, row.goals
            stats.assists, stats.penalties = row.assists, row.penalties
        db.commit()
        results.append({"league": c["code"], "scorers": len(rows)})
    return results
