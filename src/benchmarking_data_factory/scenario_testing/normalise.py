"""Normalise pay table rows to weekly rates for scenario comparison."""
from __future__ import annotations

import re
from typing import Optional

STANDARD_BAND_MIN = 1
STANDARD_BAND_MAX = 10
STANDARD_LEVELS = {"A", "B", "C", "D", "1", "2", "3", "4"}
STANDARD_LEVEL_SORT = {
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
}
NON_STANDARD_TITLE_TERMS = (
    "maternal",
    "child health",
    "immunisation",
    "nurse",
    "coordinator",
    "team leader",
    "executive",
    "senior officer",
)


def row_to_weekly(row: dict) -> Optional[float]:
    """Return the weekly rate for a pay table row, deriving if needed.

    Priority: weekly_rate -> annual_rate/52 -> fortnightly_rate/2.
    Returns None if none of those are present or numeric.
    """
    for key, divisor in [
        ("weekly_rate", 1),
        ("annual_rate", 52),
        ("fortnightly_rate", 2),
    ]:
        value = row.get(key)
        if value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if numeric <= 0:
            continue
        return numeric / divisor
    return None


def cell_key(row: dict) -> Optional[tuple[str, str]]:
    """Return (band, level) as strings for cell alignment, or None if either is missing."""
    band = row.get("band")
    level = row.get("level")
    if band is None or level is None:
        return None
    return (str(band), str(level))


def normalise_standard_band(value: object) -> Optional[str]:
    """Return a canonical numeric band string when the row uses standard banding."""
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    if not match:
        return None
    band = int(match.group(0))
    if STANDARD_BAND_MIN <= band <= STANDARD_BAND_MAX:
        return str(band)
    return None


def normalise_standard_level(value: object) -> Optional[str]:
    """Return a canonical level string for ordinary band/level matrices."""
    if value is None:
        return None
    text = str(value).strip().upper()
    for token in re.findall(r"[A-Z0-9]+", text):
        if token in STANDARD_LEVELS:
            return token
    return None


def is_standard_band_level_row(row: dict) -> bool:
    """Whether a pay-table row belongs to the benchmarkable employee band matrix."""
    title = str(row.get("title") or "").lower()
    if any(term in title for term in NON_STANDARD_TITLE_TERMS):
        return False
    return normalise_standard_band(row.get("band")) is not None and normalise_standard_level(row.get("level")) is not None


def standard_cell_key(row: dict) -> Optional[tuple[str, str]]:
    """Return canonical (band, level) only for benchmarkable standard rows."""
    band = normalise_standard_band(row.get("band"))
    level = normalise_standard_level(row.get("level"))
    if band is None or level is None:
        return None
    return (band, level)


def standard_band_level_metadata(row: dict) -> dict[str, object]:
    """Return stable dimensional fields for benchmarkable pay-band rows."""
    cell = standard_cell_key(row)
    if cell is None:
        return {}
    band, level = cell
    band_number = int(band)
    level_sort = STANDARD_LEVEL_SORT.get(level, 99)
    return {
        "standard_band": band,
        "standard_level": level,
        "classification_key": f"band_{band_number:02d}_level_{level}",
        "classification_label": f"Band {band} Level {level}",
        "classification_sort": band_number * 100 + level_sort,
    }
