"""Match API team names to the names our ML models were trained with.

APIs say "Manchester City", football-data.co.uk says "Man City". Without
this step the models wouldn't recognise half the teams.

Order of attempts:
  1. your own fixes in team_aliases.json (always wins)
  2. exact match
  3. match after simplifying (lowercase, no accents, no "FC", "AFC"...)
  4. close spelling (difflib), only if very similar

Run `python -m app.cli teams --unmatched` to see teams that still need an
entry in team_aliases.json.
"""

from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache
from pathlib import Path

from footiq.international import TEAM_ALIASES

from app.text import fold

ALIASES_FILE = Path(__file__).resolve().parent.parent / "team_aliases.json"
_DROP_WORDS = {"fc", "afc", "cf", "sc", "ac", "as", "ssc", "sv", "vfb", "vfl", "tsg", "fsv", "rc", "ogc",
               "cd", "ud", "rcd", "sd", "club", "calcio", "1899", "1846", "1848", "1904", "1909", "04", "05", "29", "de", "the", "1"}


@lru_cache
def load_aliases() -> dict:
    if ALIASES_FILE.exists():
        data = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if not k.startswith("_")}
    return {}


def simplify(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", fold(name)).split()
    kept = [w for w in words if w not in _DROP_WORDS]
    return " ".join(kept or words)


def resolve(api_name: str, known: list[str]) -> str | None:
    """Return the model's name for this team, or None if we can't be sure."""
    if not known:
        return None
    aliases = {**TEAM_ALIASES, **load_aliases()}  # country aliases from the ml package + yours
    if api_name in aliases and aliases[api_name] in known:
        return aliases[api_name]
    if api_name in known:
        return api_name
    simple = {simplify(k): k for k in known}
    target = simplify(api_name)
    if target in simple:
        return simple[target]
    close = difflib.get_close_matches(target, list(simple), n=1, cutoff=0.85)
    return simple[close[0]] if close else None
