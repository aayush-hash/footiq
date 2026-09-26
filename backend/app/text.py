"""Shared text helper: turn any name into plain lowercase letters for matching and search."""

import unicodedata

# Letters that aren't "a plain letter + an accent", so plain accent-stripping
# would delete them instead of simplifying them (Ødegaard would become "degaard").
SPECIAL_LETTERS = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ß": "ss",
                                 "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ð": "d", "Ð": "D", "þ": "th",
                                 "Þ": "Th", "ı": "i"})


def fold(name: str) -> str:
    """'Martin Ødegaard' -> 'martin odegaard', 'Kylian Mbappé' -> 'kylian mbappe'."""
    name = name.translate(SPECIAL_LETTERS)
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()
