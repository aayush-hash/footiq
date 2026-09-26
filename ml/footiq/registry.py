"""Day 12: train every model in one go, save them, and load them by name.

This is the single entry point the FastAPI backend will use in Week 3:

    from footiq.registry import load_model
    model = load_model("E0")                    # Premier League, Dixon-Coles
    model = load_model("E0", kind="elo")        # Premier League, Elo
    model = load_model("international")         # national teams
    model.predict("Arsenal", "Chelsea")

Every model has the same two methods, expected_goals() and predict(),
so the rest of the app never needs to know which one it's using.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from footiq import config
from footiq.data import LEAGUES, load_matches
from footiq.elo import EloGoalsModel, EloRatings
from footiq.international import build_international_elo, load_results
from footiq.models import DixonColesModel


def model_path(name: str, kind: str = "dixon_coles") -> Path:
    if name == "international":
        return config.MODELS_DIR / "international_elo.json"
    return config.MODELS_DIR / f"{name}_{kind}.json"


def train_club_models(league: str, matches) -> dict:
    data = matches[matches["league"] == league]
    seasons = sorted(data["season"].unique())

    recent = data[data["season"].isin(seasons[-config.DC_TRAIN_SEASONS:])]
    dc = DixonColesModel(xi=config.DC_XI).fit(recent)
    dc.save(model_path(league, "dixon_coles"))

    elo = EloRatings(k=config.CLUB_ELO_K, home_advantage=config.CLUB_ELO_HOME_ADVANTAGE, new_team="weak")
    rated = elo.run(data)
    goals = EloGoalsModel(elo).fit(rated[rated["season"] != seasons[0]])  # first season is warm-up
    goals.save(model_path(league, "elo"))

    return {"matches": len(data), "last_match": str(data["date"].max().date()),
            "dixon_coles": {"home_adv": dc.home_adv, "rho": dc.rho}, "elo": {"a": goals.a, "b": goals.b}}


def train_international_model(results) -> dict:
    elo, rated = build_international_elo(results)
    goals = EloGoalsModel(elo).fit(rated[rated["date"] >= config.INTERNATIONAL_GOALS_FROM])
    goals.save(model_path("international"))
    return {"matches": len(results), "last_match": str(results["date"].max().date()), "a": goals.a, "b": goals.b}


def train_all(leagues: list[str] | None = None) -> dict:
    manifest = {"trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "settings": {k: str(v) for k, v in vars(config).items() if k.isupper()}, "models": {}}
    matches = load_matches(config.CLUB_DATA)
    for league in leagues or list(LEAGUES):
        manifest["models"][league] = train_club_models(league, matches)
        print(f"  trained {league} ({LEAGUES.get(league, league)})")
    if Path(config.INTERNATIONAL_DATA).exists():
        manifest["models"]["international"] = train_international_model(load_results(config.INTERNATIONAL_DATA))
        print("  trained international")
    else:
        print(f"  skipped international: {config.INTERNATIONAL_DATA} not found (run Day 9 first)")
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    (config.MODELS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def load_model(name: str, kind: str = "dixon_coles"):
    """name: a league code like 'E0', or 'international'. kind: 'dixon_coles' or 'elo' (clubs only)."""
    path = model_path(name, kind)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run: python scripts/day12_train_all.py")
    if name == "international" or kind == "elo":
        return EloGoalsModel.load(path)
    return DixonColesModel.load(path)
