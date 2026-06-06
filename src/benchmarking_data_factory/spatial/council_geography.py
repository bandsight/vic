"""Council geography lookup used by cohort analysis and map outputs."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

from benchmarking_data_factory.reference.councils import (
    CANONICAL_COUNCILS_PATH as COUNCIL_REFERENCE_PATH,
    load_canonical_councils,
)

ROOT = Path(__file__).resolve().parents[3]
GEOGRAPHY_REFERENCE_PATH = ROOT / "data" / "reference" / "victorian-council-geography.json"
BOUNDARY_GEOJSON_PATH = ROOT / "static" / "data" / "victoria-lga-boundaries.geojson"

_SPATIAL_KEY_RE = re.compile(r"[^A-Z0-9]+")
_COUNCIL_SUFFIX_RE = re.compile(
    r"\b(?:RURAL CITY|CITY|SHIRE|BOROUGH|COUNCIL)\b",
    re.IGNORECASE,
)


def normalise_spatial_key(value: Any) -> str:
    """Return a stable key for joining council names across CSV/DBF/report sources."""
    return _SPATIAL_KEY_RE.sub(" ", str(value or "").upper()).strip()


def spatial_key_aliases(*values: Any) -> set[str]:
    aliases: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        candidates = {text}
        candidates.add(re.sub(r"^\s*City\s+of\s+", "", text, flags=re.IGNORECASE))
        candidates.add(_COUNCIL_SUFFIX_RE.sub(" ", text))
        for candidate in list(candidates):
            candidates.add(re.sub(r"^\s*City\s+of\s+", "", candidate, flags=re.IGNORECASE))
            candidates.add(_COUNCIL_SUFFIX_RE.sub(" ", candidate))
        for candidate in candidates:
            key = normalise_spatial_key(candidate)
            if key:
                aliases.add(key)
    return aliases


def council_type_from_name(long_name: str | None, official_name: str | None = None) -> str:
    text = f"{long_name or ''} {official_name or ''}".upper()
    if "RURAL CITY" in text:
        return "rural_city"
    if "BOROUGH" in text:
        return "borough"
    if "CITY" in text:
        return "city"
    if "SHIRE" in text:
        return "shire"
    return "other"


def _fallback_councils() -> list[dict[str, Any]]:
    councils = []
    for row in load_canonical_councils():
        short_name = row.get("short_name") or ""
        long_name = row.get("long_name") or ""
        status = row.get("status") or ""
        council_category = row.get("council_category") or ""
        council_type = council_type_from_name(long_name)
        councils.append({
            "short_name": short_name,
            "long_name": long_name,
            "status": status,
            "council_category": council_category,
            "spatial_name": short_name,
            "spatial_key": normalise_spatial_key(short_name),
            "official_name": None,
            "lga_code": None,
            "abs_lga_code": None,
            "council_type": council_type,
            "office": None,
            "cohorts": {
                "council_type": council_type,
                "council_category": council_category or "unknown",
                "register_status": status or "unknown",
                "office_geocoded": "missing",
                "polygon_attributed": "missing",
            },
        })
    return councils


def _fallback_payload() -> dict[str, Any]:
    councils = _fallback_councils()
    return {
        "set_id": "council_geography",
        "label": "Council Geography",
        "description": "Fallback council geography built from the canonical council register.",
        "sources": {},
        "summary": {
            "councils": len(councils),
            "councils_with_office_points": 0,
            "councils_with_polygon_attributes": 0,
        },
        "councils": councils,
    }


@lru_cache(maxsize=8)
def _load_council_geography_cached(path_key: str) -> dict[str, Any]:
    geography_path = Path(path_key)
    if not geography_path.exists():
        return _fallback_payload()
    with geography_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    payload.setdefault("councils", [])
    payload.setdefault("summary", {})
    payload.setdefault("sources", {})
    return payload


def load_council_geography(path: str | Path | None = None) -> dict[str, Any]:
    geography_path = Path(path) if path is not None else GEOGRAPHY_REFERENCE_PATH
    return _load_council_geography_cached(str(geography_path))


@lru_cache(maxsize=8)
def _council_index_for_path(path_key: str) -> dict[str, dict[str, Any]]:
    return _council_index(load_council_geography(path_key))


def _council_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index = {}
    for council in payload.get("councils") or []:
        for key in spatial_key_aliases(
            council.get("short_name"),
            council.get("long_name"),
            council.get("spatial_name"),
            council.get("official_name"),
            council.get("spatial_key"),
        ):
            index.setdefault(key, council)
    return index


def geography_for_lga(lga_name: str | None, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
    keys = spatial_key_aliases(lga_name)
    if not keys:
        return None
    index = _council_index(payload) if payload is not None else _council_index_for_path(str(GEOGRAPHY_REFERENCE_PATH))
    for key in keys:
        council = index.get(key)
        if council:
            return deepcopy(council)
    return None


def analysis_geography_fields(lga_name: str | None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    council = geography_for_lga(lga_name, payload)
    if not council:
        return {
            "lga_code": None,
            "abs_lga_code": None,
            "council_type": None,
            "office_lat": None,
            "office_lon": None,
            "office_township": None,
            "spatial_cohorts": {},
        }
    office = council.get("office") if isinstance(council.get("office"), dict) else {}
    return {
        "lga_code": council.get("lga_code"),
        "abs_lga_code": council.get("abs_lga_code"),
        "council_type": council.get("council_type"),
        "office_lat": office.get("lat"),
        "office_lon": office.get("lon"),
        "office_township": office.get("seat_township"),
        "spatial_cohorts": council.get("cohorts") or {},
    }


def _cohort_counts(councils: list[dict[str, Any]], cohort_name: str) -> list[dict[str, Any]]:
    counts = Counter(
        (council.get("cohorts") or {}).get(cohort_name) or "unknown"
        for council in councils
    )
    return [
        {"cohort": cohort, "count": count}
        for cohort, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _office_point_features(councils: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = []
    for council in councils:
        office = council.get("office") if isinstance(council.get("office"), dict) else None
        if not office or office.get("lat") is None or office.get("lon") is None:
            continue
        features.append({
            "type": "Feature",
            "properties": {
                "short_name": council.get("short_name"),
                "long_name": council.get("long_name"),
                "lga_code": council.get("lga_code"),
                "abs_lga_code": council.get("abs_lga_code"),
                "council_type": council.get("council_type"),
                "council_category": council.get("council_category"),
                "seat_township": office.get("seat_township"),
                "address": office.get("address"),
            },
            "geometry": {
                "type": "Point",
                "coordinates": [office.get("lon"), office.get("lat")],
            },
        })
    return features


def _council_dimension_rows(councils: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for council in councils:
        office = council.get("office") if isinstance(council.get("office"), dict) else {}
        cohorts = council.get("cohorts") if isinstance(council.get("cohorts"), dict) else {}
        rows.append({
            "council_key": normalise_spatial_key(council.get("short_name") or council.get("spatial_name")),
            "short_name": council.get("short_name"),
            "long_name": council.get("long_name"),
            "status": council.get("status"),
            "council_category": council.get("council_category") or cohorts.get("council_category"),
            "council_type": council.get("council_type") or cohorts.get("council_type"),
            "spatial_name": council.get("spatial_name"),
            "spatial_key": council.get("spatial_key"),
            "official_name": council.get("official_name"),
            "lga_code": council.get("lga_code"),
            "abs_lga_code": council.get("abs_lga_code"),
            "state": council.get("state"),
            "office_township": office.get("seat_township"),
            "office_address": office.get("address"),
            "office_match_key": office.get("match_key"),
            "office_lat": office.get("lat"),
            "office_lon": office.get("lon"),
            "office_geocoded": cohorts.get("office_geocoded"),
            "polygon_attributed": cohorts.get("polygon_attributed"),
            "polygon_record_count": council.get("polygon_record_count"),
            "map_join_key": council.get("spatial_key") or normalise_spatial_key(council.get("short_name")),
        })
    return rows


def build_council_geography_payload(path: str | Path | None = None) -> dict[str, Any]:
    payload = load_council_geography(path)
    councils = payload.get("councils") or []
    dimension_rows = _council_dimension_rows(councils)
    office_points = _office_point_features(councils)
    bounds = payload.get("summary", {}).get("boundary_bounds")
    return {
        "set_id": "council_geography",
        "label": "Council Geography",
        "description": "Council dimension table and geography building blocks for cohort analysis and infographic map outputs.",
        "sources": payload.get("sources") or {},
        "summary": {
            **(payload.get("summary") or {}),
            "rows": len(dimension_rows),
            "office_point_features": len(office_points),
            "boundary_geojson_url": "/static/data/victoria-lga-boundaries.geojson"
            if BOUNDARY_GEOJSON_PATH.exists()
            else None,
        },
        "cohorts": {
            "council_type": _cohort_counts(councils, "council_type"),
            "council_category": _cohort_counts(councils, "council_category"),
            "register_status": _cohort_counts(councils, "register_status"),
            "office_geocoded": _cohort_counts(councils, "office_geocoded"),
            "polygon_attributed": _cohort_counts(councils, "polygon_attributed"),
        },
        "map": {
            "bounds": bounds,
            "boundary_geojson_url": "/static/data/victoria-lga-boundaries.geojson"
            if BOUNDARY_GEOJSON_PATH.exists()
            else None,
            "office_points": {
                "type": "FeatureCollection",
                "features": office_points,
            },
        },
        "rows": dimension_rows,
        "councils": councils,
    }
