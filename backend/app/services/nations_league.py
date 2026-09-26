"""Day 27: Nations League groups, live tables and simulated odds.

Neither free data provider covers the 2026/27 Nations League, so the fixtures
come from your Week 2 CSV (ml/fixtures/...). After each matchday, type the
scores into the CSV and run `python -m app.cli import-nations-league` again.

The table and odds reuse footiq.tournament from Day 11. Simulating 10,000
seasons takes about half a second per group, so results are cached until a
result in that group changes.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from footiq.tournament import LEAGUE_A_OUTCOMES, current_table, simulate_group

from app.models import League, Match, Team
from app.services.ingest import ensure_leagues
from app.services.predictor import apply_new_international_results, get_model, known_team_names
from app.services.team_names import resolve

DEFAULT_CSV = Path("../ml/fixtures/nations_league_2026_27_league_a.csv")
KICKOFF_UTC = "18:45"   # most Nations League matches start 20:45 CET; the CSV has dates only
_cache: dict[tuple, pd.DataFrame] = {}


def import_fixtures(db: Session, path: Path = DEFAULT_CSV, season: int = 2026) -> dict:
    """Upsert every row of the CSV as a match. Safe to run again after adding scores."""
    league = ensure_leagues(db)["UNL"]
    known = known_team_names("international")
    df = pd.read_csv(path)
    created = updated = 0
    teams: dict[str, Team] = {}
    for name in sorted(set(df["home_team"]) | set(df["away_team"])):
        ext = f"csv:{name}"
        team = db.scalar(select(Team).where(Team.external_id == ext))
        if team is None:
            team = Team(external_id=ext, name=name, is_national=True)
            db.add(team)
        team.model_name = team.model_name or resolve(name, known) or name
        teams[name] = team
    db.flush()
    for row in df.itertuples():
        ext = f"csv:unl:{season}:{row.home_team}:{row.away_team}"
        match = db.scalar(select(Match).where(Match.external_id == ext))
        if match is None:
            match = Match(external_id=ext)
            db.add(match)
            created += 1
        else:
            updated += 1
        played = pd.notna(row.home_goals) and pd.notna(row.away_goals)
        match.league_id, match.season, match.group_name = league.id, season, row.group
        match.round = f"Group {row.group}"
        match.kickoff = datetime.fromisoformat(f"{row.date}T{KICKOFF_UTC}").replace(tzinfo=timezone.utc)
        match.home_team_id, match.away_team_id = teams[row.home_team].id, teams[row.away_team].id
        match.status = "finished" if played else "scheduled"
        match.home_goals = int(row.home_goals) if played else None
        match.away_goals = int(row.away_goals) if played else None
    db.commit()
    return {"rows": len(df), "created": created, "updated": updated}


def _group_matches(db: Session, group: str) -> list[Match]:
    return list(db.scalars(select(Match).join(League).options(joinedload(Match.home_team), joinedload(Match.away_team))
                           .where(League.code == "UNL", Match.group_name == group).order_by(Match.kickoff, Match.id)).unique())


def groups(db: Session) -> dict[str, list[str]]:
    out: dict[str, set] = {}
    query = (select(Match).join(League).options(joinedload(Match.home_team), joinedload(Match.away_team))
             .where(League.code == "UNL", Match.group_name.is_not(None)))
    for m in db.scalars(query).unique():
        out.setdefault(m.group_name, set()).update([m.home_team.name, m.away_team.name])
    return {g: sorted(t) for g, t in sorted(out.items())}


def _frame(matches: list[Match]) -> pd.DataFrame:
    """The shape footiq.tournament expects, using the names the model knows."""
    return pd.DataFrame([{
        "home_team": m.home_team.model_name or m.home_team.name, "away_team": m.away_team.model_name or m.away_team.name,
        "home_goals": m.home_goals if m.status == "finished" else None,
        "away_goals": m.away_goals if m.status == "finished" else None,
    } for m in matches])


def group_view(db: Session, group: str, simulations: int = 10_000) -> dict | None:
    matches = _group_matches(db, group)
    if not matches:
        return None
    apply_new_international_results(db)  # latest results move the Elo ratings first
    frame = _frame(matches)
    display = {(m.home_team.model_name or m.home_team.name): m.home_team.name for m in matches}
    display.update({(m.away_team.model_name or m.away_team.name): m.away_team.name for m in matches})

    fingerprint = hashlib.md5(frame.to_json().encode()).hexdigest()
    key = (group, fingerprint, simulations)
    if key not in _cache:
        _cache[key] = simulate_group(frame, get_model("international"), n=simulations, seed=27,
                                     outcomes=LEAGUE_A_OUTCOMES)
    odds = _cache[key].copy()
    table = current_table(frame)
    for df in (odds, table):
        df["team"] = df["team"].map(lambda t: display.get(t, t))
    played = sum(m.status == "finished" for m in matches)
    return {"group": group, "played": played, "remaining": len(matches) - played, "simulations": simulations,
            "table": table.to_dict(orient="records"), "odds": odds.round(4).to_dict(orient="records"),
            "matches": matches}
