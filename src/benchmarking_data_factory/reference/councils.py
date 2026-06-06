"""Canonical Victorian council reference lookup."""
from __future__ import annotations

from collections import Counter
import csv
from functools import lru_cache
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CANONICAL_COUNCILS_PATH = ROOT / "data" / "reference" / "victorian-councils.csv"

_COUNCIL_KEY_RE = re.compile(r"[^A-Z0-9]+")


def normalise_council_key(value: Any) -> str:
    return _COUNCIL_KEY_RE.sub(" ", str(value or "").upper()).strip()


@lru_cache(maxsize=8)
def _load_canonical_councils_cached(path_key: str) -> tuple[dict[str, str], ...]:
    councils_path = Path(path_key)
    if not councils_path.exists():
        return ()
    with councils_path.open("r", encoding="utf-8", newline="") as handle:
        councils = []
        for row in csv.DictReader(handle):
            short_name = (row.get("short_name") or "").strip()
            if not short_name:
                continue
            long_name = (row.get("long_name") or "").strip()
            status = (row.get("status") or "").strip()
            council_category = (row.get("council_category") or "").strip()
            councils.append({
                "short_name": short_name,
                "long_name": long_name,
                "status": status,
                "council_category": council_category,
                "canonical_key": normalise_council_key(short_name),
            })
        return tuple(councils)


def load_canonical_councils(path: str | Path | None = None) -> list[dict[str, str]]:
    councils_path = Path(path) if path is not None else CANONICAL_COUNCILS_PATH
    return [dict(row) for row in _load_canonical_councils_cached(str(councils_path))]


def active_canonical_council_lookup(path: str | Path | None = None) -> dict[str, dict[str, str]]:
    return {
        row["short_name"]: row
        for row in load_canonical_councils(path)
        if row.get("status") == "active"
    }


def canonical_council_reference_payload(path: str | Path | None = None) -> dict[str, Any]:
    councils_path = Path(path) if path is not None else CANONICAL_COUNCILS_PATH
    councils = load_canonical_councils(councils_path)
    status_counts = Counter(row.get("status") or "unknown" for row in councils)
    category_counts = Counter(row.get("council_category") or "unknown" for row in councils)
    return {
        "set_id": "canonical_councils",
        "label": "Canonical Victorian Councils",
        "description": "First-class lookup of Victorian council short names, long names and register status.",
        "source": {
            "path": str(councils_path),
            "name": councils_path.name,
            "exists": councils_path.exists(),
        },
        "summary": {
            "total": len(councils),
            "active": status_counts.get("active", 0),
            "missing": status_counts.get("missing", 0),
            "excluded": status_counts.get("excluded", 0),
            "statuses": dict(sorted(status_counts.items())),
            "categories": dict(sorted(category_counts.items())),
        },
        "rows": councils,
        "lookup": {
            row["canonical_key"]: row
            for row in councils
            if row.get("canonical_key")
        },
    }
