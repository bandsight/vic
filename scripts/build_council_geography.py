from __future__ import annotations

import csv
from datetime import datetime, timezone
from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import struct
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = Path(os.environ.get("EBA_GEOGRAPHY_SOURCE_DIR", ROOT / "data" / "source" / "spatial"))
COUNCIL_REFERENCE_PATH = ROOT / "data" / "reference" / "victorian-councils.csv"
OFFICE_CSV_PATH = SOURCE_DIR / "Victorian_LGA_Office_Addresses_with_Geo.csv"
POLYGON_DBF_PATH = SOURCE_DIR / "AD_LGA_AREA_POLYGON.dbf"
POLYGON_SHP_PATH = SOURCE_DIR / "AD_LGA_AREA_POLYGON.shp"
GEOGRAPHY_OUTPUT_PATH = ROOT / "data" / "reference" / "victorian-council-geography.json"
BOUNDARY_OUTPUT_PATH = ROOT / "static" / "data" / "victoria-lga-boundaries.geojson"

SIMPLIFICATION_TOLERANCE_DEGREES = 0.01
_SPATIAL_KEY_RE = re.compile(r"[^A-Z0-9]+")


def normalise_spatial_key(value: Any) -> str:
    return _SPATIAL_KEY_RE.sub(" ", str(value or "").upper()).strip()


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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def read_dbf(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    record_count = struct.unpack("<I", raw[4:8])[0]
    header_len = struct.unpack("<H", raw[8:10])[0]
    record_len = struct.unpack("<H", raw[10:12])[0]
    fields: list[tuple[str, str, int, int]] = []
    offset = 32
    while offset < header_len and raw[offset] != 0x0D:
        descriptor = raw[offset:offset + 32]
        name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii", errors="replace")
        fields.append((name, chr(descriptor[11]), descriptor[16], descriptor[17]))
        offset += 32

    records: list[dict[str, Any]] = []
    position = header_len
    for _ in range(record_count):
        record = raw[position:position + record_len]
        position += record_len
        if not record or record[0:1] == b"*":
            continue
        cursor = 1
        item: dict[str, Any] = {}
        for name, field_type, field_len, decimal_count in fields:
            value = record[cursor:cursor + field_len].decode("latin-1", errors="replace").strip()
            cursor += field_len
            if field_type in {"N", "F"} and value:
                try:
                    item[name] = float(value) if decimal_count else int(value)
                except ValueError:
                    item[name] = value
            else:
                item[name] = value or None
        records.append(item)
    return records


def point_line_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    if start == end:
        return math.dist(point, start)
    x, y = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def simplify_ring(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    if len(points) <= 3:
        return points
    closed = points[0] == points[-1]
    working = points[:-1] if closed else points

    def recurse(segment: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(segment) <= 2:
            return segment
        start = segment[0]
        end = segment[-1]
        max_distance = -1.0
        max_index = -1
        for index, point in enumerate(segment[1:-1], 1):
            distance = point_line_distance(point, start, end)
            if distance > max_distance:
                max_distance = distance
                max_index = index
        if max_distance > tolerance:
            return recurse(segment[:max_index + 1])[:-1] + recurse(segment[max_index:])
        return [start, end]

    simplified = recurse(working)
    if closed and simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    return simplified


def read_shp_polygons(path: Path, tolerance: float) -> list[dict[str, Any] | None]:
    raw = path.read_bytes()
    position = 100
    shapes: list[dict[str, Any] | None] = []
    while position < len(raw):
        _record_number, content_len_words = struct.unpack(">2i", raw[position:position + 8])
        position += 8
        content = raw[position:position + content_len_words * 2]
        position += content_len_words * 2
        shape_type = struct.unpack("<i", content[:4])[0]
        if shape_type == 0:
            shapes.append(None)
            continue
        if shape_type != 5:
            raise ValueError(f"Expected Polygon shape type 5, got {shape_type}")
        bbox = struct.unpack("<4d", content[4:36])
        part_count, point_count = struct.unpack("<2i", content[36:44])
        part_indexes = list(struct.unpack("<" + "i" * part_count, content[44:44 + 4 * part_count]))
        points_offset = 44 + 4 * part_count
        raw_points = struct.unpack("<" + "d" * (point_count * 2), content[points_offset:points_offset + point_count * 16])
        points = [
            (round(raw_points[index], 6), round(raw_points[index + 1], 6))
            for index in range(0, len(raw_points), 2)
        ]
        rings = []
        for part_index, start in enumerate(part_indexes):
            end = part_indexes[part_index + 1] if part_index + 1 < len(part_indexes) else point_count
            ring = points[start:end]
            if len(ring) >= 4:
                rings.append(simplify_ring(ring, tolerance))
        shapes.append({"bbox": bbox, "rings": rings})
    return shapes


def source_metadata(path: Path) -> dict[str, Any]:
    return {
        "name": path.name,
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else None,
        "modified": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        if path.exists()
        else None,
    }


def build_council_geography() -> dict[str, Any]:
    council_rows = read_csv_rows(COUNCIL_REFERENCE_PATH)
    office_rows = read_csv_rows(OFFICE_CSV_PATH)
    dbf_records = read_dbf(POLYGON_DBF_PATH)

    office_by_key = {
        normalise_spatial_key(row.get("Spatial Polygon Name")): row
        for row in office_rows
        if normalise_spatial_key(row.get("Spatial Polygon Name"))
    }
    polygon_by_key: dict[str, list[dict[str, Any]]] = {}
    for record in dbf_records:
        key = normalise_spatial_key(record.get("NAME"))
        if record.get("STATE") == "VIC" and key:
            polygon_by_key.setdefault(key, []).append(record)

    councils: list[dict[str, Any]] = []
    for row in council_rows:
        short_name = row.get("short_name") or ""
        long_name = row.get("long_name") or ""
        status = row.get("status") or ""
        council_category = row.get("council_category") or ""
        key = normalise_spatial_key(short_name)
        office_row = office_by_key.get(key)
        polygon_records = polygon_by_key.get(key) or []
        polygon_record = polygon_records[0] if polygon_records else {}
        official_name = polygon_record.get("OFFICIALNM")
        council_type = council_type_from_name(long_name, official_name)
        office = None
        if office_row:
            office = {
                "seat_township": office_row.get("Seat Township") or None,
                "address": office_row.get("Council Office Address") or None,
                "match_key": office_row.get("match_key") or None,
                "lat": float(office_row["lat"]) if office_row.get("lat") else None,
                "lon": float(office_row["lon"]) if office_row.get("lon") else None,
            }
        councils.append({
            "short_name": short_name,
            "long_name": long_name,
            "status": status,
            "council_category": council_category,
            "spatial_name": short_name,
            "spatial_key": key,
            "official_name": official_name,
            "lga_code": polygon_record.get("LGA_CODE"),
            "abs_lga_code": polygon_record.get("ABSLGACODE"),
            "state": polygon_record.get("STATE"),
            "polygon_record_count": len(polygon_records),
            "council_type": council_type,
            "office": office,
            "cohorts": {
                "council_type": council_type,
                "council_category": council_category or "unknown",
                "register_status": status or "unknown",
                "office_geocoded": "yes" if office and office.get("lat") is not None and office.get("lon") is not None else "missing",
                "polygon_attributed": "yes" if polygon_record else "missing",
            },
        })

    council_keys = {c["spatial_key"] for c in councils}
    polygon_extras = sorted(
        record.get("NAME")
        for key, records in polygon_by_key.items()
        if key not in council_keys
        for record in records[:1]
    )
    missing_offices = sorted(c["short_name"] for c in councils if c.get("office") is None)
    missing_polygons = sorted(c["short_name"] for c in councils if not c.get("lga_code"))
    category_counts = Counter(c.get("council_category") or "unknown" for c in councils)
    return {
        "set_id": "council_geography",
        "label": "Council Geography",
        "description": "Council geography building blocks for cohort analysis and infographic map outputs.",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sources": {
            "canonical_councils": source_metadata(COUNCIL_REFERENCE_PATH),
            "office_addresses": source_metadata(OFFICE_CSV_PATH),
            "polygon_attributes": source_metadata(POLYGON_DBF_PATH),
            "polygon_shapes": source_metadata(POLYGON_SHP_PATH),
        },
        "summary": {
            "councils": len(councils),
            "councils_with_office_points": sum(1 for c in councils if c.get("office")),
            "councils_with_polygon_attributes": sum(1 for c in councils if c.get("lga_code")),
            "office_rows": len(office_rows),
            "polygon_attribute_records": len(dbf_records),
            "missing_office_points": missing_offices,
            "missing_polygon_attributes": missing_polygons,
            "extra_polygon_names": polygon_extras,
            "categories": dict(sorted(category_counts.items())),
        },
        "councils": sorted(councils, key=lambda c: c["short_name"]),
    }


def build_boundary_geojson(geography_payload: dict[str, Any]) -> dict[str, Any]:
    dbf_records = read_dbf(POLYGON_DBF_PATH)
    shapes = read_shp_polygons(POLYGON_SHP_PATH, SIMPLIFICATION_TOLERANCE_DEGREES)
    reference_keys = {
        council.get("spatial_key")
        for council in geography_payload.get("councils") or []
        if council.get("spatial_key")
    }
    features = []
    bounds: list[float] | None = None
    for record, shape in zip(dbf_records, shapes):
        if not shape or record.get("STATE") != "VIC":
            continue
        key = normalise_spatial_key(record.get("NAME"))
        rings = [
            [[x, y] for x, y in ring]
            for ring in shape.get("rings") or []
            if len(ring) >= 4
        ]
        if not rings:
            continue
        bbox = list(shape["bbox"])
        if bounds is None:
            bounds = bbox.copy()
        else:
            bounds = [
                min(bounds[0], bbox[0]),
                min(bounds[1], bbox[1]),
                max(bounds[2], bbox[2]),
                max(bounds[3], bbox[3]),
            ]
        features.append({
            "type": "Feature",
            "properties": {
                "spatial_name": record.get("NAME"),
                "spatial_key": key,
                "official_name": record.get("OFFICIALNM"),
                "lga_code": record.get("LGA_CODE"),
                "abs_lga_code": record.get("ABSLGACODE"),
                "state": record.get("STATE"),
                "is_reference_council": key in reference_keys,
            },
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[ring] for ring in rings],
            },
        })
    geography_payload["summary"]["boundary_features"] = len(features)
    geography_payload["summary"]["boundary_bounds"] = bounds
    geography_payload["summary"]["boundary_simplification_tolerance_degrees"] = SIMPLIFICATION_TOLERANCE_DEGREES
    return {
        "type": "FeatureCollection",
        "name": "victoria_lga_boundaries_simplified",
        "bbox": bounds,
        "features": features,
    }


def main() -> None:
    GEOGRAPHY_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    BOUNDARY_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    geography_payload = build_council_geography()
    boundary_geojson = build_boundary_geojson(geography_payload)
    GEOGRAPHY_OUTPUT_PATH.write_text(json.dumps(geography_payload, indent=2) + "\n", encoding="utf-8")
    BOUNDARY_OUTPUT_PATH.write_text(json.dumps(boundary_geojson, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote {GEOGRAPHY_OUTPUT_PATH}")
    print(f"Wrote {BOUNDARY_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
