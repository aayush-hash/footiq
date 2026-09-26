"""Run backend jobs by hand, without starting the server.

    python -m app.cli check-provider              is my API key working? (uses no quota on API-Football)
    python -m app.cli sync                        fetch all competitions
    python -m app.cli sync --league E0            fetch one competition
    python -m app.cli predict                     predictions for the next 14 days
    python -m app.cli daily                       sync + predict (what the scheduler runs)
    python -m app.cli teams --unmatched           teams the models don't recognise yet
    python -m app.cli set-team-name "Manchester City" "Man City"

Week 4:
    python -m app.cli score                       award points for finished matches
    python -m app.cli import-nations-league       load the Nations League CSV (run again after adding scores)
    python -m app.cli sync-scorers                top scorers of each league (5 requests)
    python -m app.cli sync-squads --league E0     every player of every team (1 request per team, slow)
"""

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import League, Match, Team
from app.services.ingest import sync_all
from app.services.predictor import generate_predictions, known_team_names
from app.services.providers import ProviderError, get_provider
from app.services.nations_league import DEFAULT_CSV, import_fixtures
from app.services.players import sync_scorers, sync_squads
from app.services.scheduler import run_daily_update
from app.services.scoring import score_finished_matches


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-provider")
    s = sub.add_parser("sync"); s.add_argument("--league", action="append")
    sub.add_parser("predict")
    sub.add_parser("daily")
    t = sub.add_parser("teams"); t.add_argument("--unmatched", action="store_true")
    n = sub.add_parser("set-team-name"); n.add_argument("api_name"); n.add_argument("model_name")
    sub.add_parser("score")
    nl = sub.add_parser("import-nations-league"); nl.add_argument("path", nargs="?", default=str(DEFAULT_CSV))
    sc = sub.add_parser("sync-scorers"); sc.add_argument("--league", action="append")
    sq = sub.add_parser("sync-squads"); sq.add_argument("--league", action="append")
    args = parser.parse_args(argv)

    settings = get_settings()
    db = SessionLocal()
    try:
        _run(args, settings, db)
    except ProviderError as error:
        raise SystemExit(f"Problem with the data provider: {error}")
    finally:
        db.close()


def _run(args, settings, db):
    """Do the chosen command."""
    if args.command == "check-provider":
        print(f"Provider: {settings.data_provider}")
        print(json.dumps(get_provider(settings).status(), indent=2))
    elif args.command == "sync":
        for row in sync_all(db, get_provider(settings), args.league):
            print(row)
    elif args.command == "predict":
        print(generate_predictions(db))
    elif args.command == "daily":
        print(json.dumps(run_daily_update(), indent=2, default=str))
    elif args.command == "teams":
        query = select(Team).order_by(Team.name)
        if args.unmatched:
            query = query.where(Team.model_name.is_(None))
        teams = list(db.scalars(query))
        for team in teams:
            print(f"{team.name:35s} -> {team.model_name or '??? (add to app/team_aliases.json)'}")
        if args.unmatched and teams:
            # help: show the names the model does know, for each league with unmatched teams
            league_ids = {m.league_id for m in db.scalars(select(Match).where(
                (Match.home_team_id.in_([t.id for t in teams])) | (Match.away_team_id.in_([t.id for t in teams]))))}
            for league in db.scalars(select(League).where(League.id.in_(league_ids))):
                names = known_team_names(league.model_key)
                if league.model_key != "international":
                    print(f"\nNames the {league.name} model knows:\n  " + ", ".join(names))
        print(f"\n{len(teams)} team(s)")
    elif args.command == "set-team-name":
        team = db.scalar(select(Team).where(Team.name == args.api_name))
        if team is None:
            print(f"No team called '{args.api_name}' in the database")
        else:
            team.model_name = args.model_name
            db.commit()
            print(f"{team.name} -> {team.model_name}")
    elif args.command == "score":
        print(score_finished_matches(db))
    elif args.command == "import-nations-league":
        print(import_fixtures(db, Path(args.path)))
        print(generate_predictions(db))
    elif args.command == "sync-scorers":
        for row in sync_scorers(db, get_provider(settings), args.league):
            print(row)
    elif args.command == "sync-squads":
        print("About 7 seconds per team (free API limit). Press Ctrl+C to stop; saved teams are kept.")
        result = sync_squads(db, get_provider(settings), args.league)
        print({k: v for k, v in result.items() if k != "errors"})
        for error in result["errors"]:
            print("  error:", error)


if __name__ == "__main__":
    main()
