"""Built-in directory of Russian cities (backend/data/ru_cities.txt).

Used for director suggestions when a school is registered; pupils only see
cities that have active schools (``service.search_cities`` without scope).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

CITIES_FILE = Path(__file__).parent / "data" / "ru_cities.txt"


def fold(text: str) -> str:
    """Case-insensitive key; "ё" equals "е", runs of spaces collapse."""
    return " ".join(text.casefold().replace("ё", "е").split())


@lru_cache(maxsize=1)
def directory() -> tuple[str, ...]:
    try:
        lines = CITIES_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    return tuple(dict.fromkeys(line.strip() for line in lines if line.strip()))


@lru_cache(maxsize=1)
def _by_key() -> dict[str, str]:
    return {fold(name): name for name in directory()}


def canonical_city(name: str) -> str | None:
    """Spelling from the directory when ``name`` matches it ignoring case."""
    return _by_key().get(fold(name))


def search_directory(query: str, limit: int = 10) -> list[str]:
    needle = fold(query)[:60]
    starts: list[str] = []
    inside: list[str] = []
    for name in directory():
        key = fold(name)
        if not needle or key.startswith(needle):
            starts.append(name)
        elif needle in key:
            inside.append(name)
    return (starts + inside)[:limit]
