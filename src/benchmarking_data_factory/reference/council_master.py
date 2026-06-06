"""Victorian council master reference lookup."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from benchmarking_data_factory.spatial.council_geography import build_council_geography_payload


ROOT = Path(__file__).resolve().parents[3]
COUNCIL_MASTER_PATH = ROOT / "data" / "reference" / "victorian-council-master.json"


def _fallback_payload() -> dict[str, Any]:
    geography = build_council_geography_payload()
    return {
        "set_id": "victorian_council_master",
        "label": "Victorian Council Master",
        "description": "Fallback council master built from the council geography reference.",
        "sources": geography.get("sources", {}),
        "summary": geography.get("summary", {}),
        "rows": geography.get("rows", []),
        "lookup": {
            row.get("council_key"): row
            for row in geography.get("rows", [])
            if row.get("council_key")
        },
    }


@lru_cache(maxsize=8)
def _load_council_master_cached(path_key: str) -> dict[str, Any]:
    master_path = Path(path_key)
    if not master_path.exists():
        return _fallback_payload()
    with master_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    rows = payload.get("rows") or []
    payload.setdefault("lookup", {
        row.get("council_key"): row
        for row in rows
        if row.get("council_key")
    })
    return payload


def load_council_master(path: str | Path | None = None) -> dict[str, Any]:
    master_path = Path(path) if path is not None else COUNCIL_MASTER_PATH
    return _load_council_master_cached(str(master_path))


def council_master_reference_payload(path: str | Path | None = None) -> dict[str, Any]:
    return load_council_master(path)
