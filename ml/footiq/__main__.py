"""Day 12: a small command-line tool, so you can use FOOTIQ without writing code.

Examples (run from the ml folder, after scripts/day12_train_all.py):
    python -m footiq predict E0 "Arsenal" "Chelsea"
    python -m footiq predict E0 "Arsenal" "Chelsea" --model elo
    python -m footiq predict international "Spain" "England" --neutral
    python -m footiq whatif SP1 "Barcelona" "Real Madrid" --minute 63 --score 0-1 --reds 1-0
    python -m footiq ratings international --top 20
    python -m footiq teams E0
"""

import argparse
import difflib
import sys

from footiq.elo import EloGoalsModel
from footiq.international import canonical_name
from footiq.registry import load_model
from footiq.simulate import MatchState, what_if


def _load(args):
    kind = "elo" if getattr(args, "model", "dc") == "elo" else "dixon_coles"
    return load_model(args.competition, kind)


def _teams(model):
    return sorted(model.ratings.ratings) if isinstance(model, EloGoalsModel) else model.teams


def _check(model, *teams):
    known = _teams(model)
    for t in teams:
        if t not in known:
            close = difflib.get_close_matches(t, known, n=3, cutoff=0.5)
            hint = f" Did you mean: {', '.join(close)}?" if close else " Use the 'teams' command to list names."
            sys.exit(f"Unknown team '{t}'.{hint}")


def _pct(p):
    return f"{p['home_win']:.1%} / {p['draw']:.1%} / {p['away_win']:.1%}"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m footiq", description="FOOTIQ predictions")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("predict", help="win/draw/loss chances for one match")
    p.add_argument("competition", help="league code (E0, SP1, D1, I1, F1) or 'international'")
    p.add_argument("home"); p.add_argument("away")
    p.add_argument("--model", choices=["dc", "elo"], default="dc")
    p.add_argument("--neutral", action="store_true")

    w = sub.add_parser("whatif", help="chances from a match situation")
    w.add_argument("competition"); w.add_argument("home"); w.add_argument("away")
    w.add_argument("--model", choices=["dc", "elo"], default="dc")
    w.add_argument("--minute", type=int, default=0)
    w.add_argument("--score", default="0-0", help="current score, like 1-0")
    w.add_argument("--reds", default="0-0", help="red cards, like 1-0")
    w.add_argument("--neutral", action="store_true")

    r = sub.add_parser("ratings", help="strongest teams")
    r.add_argument("competition"); r.add_argument("--model", choices=["dc", "elo"], default="dc")
    r.add_argument("--top", type=int, default=20)

    t = sub.add_parser("teams", help="list team names exactly as the model knows them")
    t.add_argument("competition"); t.add_argument("--model", choices=["dc", "elo"], default="dc")

    args = parser.parse_args(argv)
    model = _load(args)
    if args.competition == "international" and hasattr(args, "home"):
        args.home, args.away = canonical_name(args.home), canonical_name(args.away)

    if args.command == "predict":
        _check(model, args.home, args.away)
        res = model.predict(args.home, args.away, neutral=args.neutral)
        xg = res["expected_goals"]
        print(f"{args.home} vs {args.away}{' (neutral)' if args.neutral else ''}")
        print(f"  expected goals {xg['home']:.2f} - {xg['away']:.2f}")
        print(f"  home / draw / away: {_pct(res['probabilities'])}")
        print("  likely scores:", ", ".join(f"{s['score']} ({s['probability']:.0%})" for s in res["top_scorelines"]))

    elif args.command == "whatif":
        _check(model, args.home, args.away)
        hg, ag = map(int, args.score.split("-"))
        hr, ar = map(int, args.reds.split("-"))
        lam_h, lam_a = model.expected_goals(args.home, args.away, neutral=args.neutral)
        res = what_if(lam_h, lam_a, MatchState(args.minute, hg, ag, hr, ar), rho=getattr(model, "rho", 0.0))
        print(f"{args.home} {hg}-{ag} {args.away}, {args.minute}', red cards {hr}-{ar}")
        print(f"  home / draw / away: {_pct(res['probabilities'])}")
        print("  likely finals:", ", ".join(f"{s['score']} ({s['probability']:.0%})" for s in res["top_scorelines"]))

    elif args.command == "ratings":
        table = model.ratings.table() if isinstance(model, EloGoalsModel) else model.ratings()
        print(table.head(args.top).round(3).to_string())

    elif args.command == "teams":
        print("\n".join(_teams(model)))


if __name__ == "__main__":
    main()
