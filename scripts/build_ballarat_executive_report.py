from __future__ import annotations

import base64
import csv
import datetime as dt
import html
import json
import math
import statistics
from pathlib import Path
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "exports" / "ballarat-executive-report"
SNAPSHOT_DATE = dt.date(2025, 7, 1)
BALLARAT_KEY = "BALLARAT"
CORE_BANDS = [4, 5, 6]
METRICS = [
    ("entry_weekly_rate", "Entry"),
    ("range_midpoint_weekly_rate", "Midpoint"),
    ("capacity_weekly_rate", "Capacity"),
]


PALETTE = {
    "ink": "#17201d",
    "muted": "#5f6d67",
    "line": "#d7dfd9",
    "panel": "#ffffff",
    "field": "#f4f7f4",
    "ballarat": "#d84f3f",
    "ballarat_dark": "#9f2f24",
    "teal": "#0f8d7e",
    "jade": "#2d7d52",
    "blue": "#315f9f",
    "gold": "#c8932e",
    "violet": "#69539b",
    "charcoal": "#23312c",
}


def read_csv(name: str) -> list[dict[str, str]]:
    path = ROOT / "data" / "datamarts" / name
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    return dt.date.fromisoformat(value)


def parse_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def money(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.{digits}f}/wk"


def money_plain(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.{digits}f}"


def delta_money(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value > 0 else ""
    return f"{sign}${value:,.{digits}f}/wk"


def pct(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}%"


def quantile(values: Iterable[float], q: float) -> float:
    sorted_values = sorted(values)
    if not sorted_values:
        raise ValueError("Cannot compute quantile of empty sequence.")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[int(pos)]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def percentile_rank(values: list[float], selected: float) -> float:
    ordered = sorted(values)
    below = sum(1 for value in ordered if value < selected)
    equal = sum(1 for value in ordered if value == selected)
    return ((below + (equal * 0.5)) / len(ordered)) * 100


def stable_jitter(key: str, width: float) -> float:
    total = sum((index + 1) * ord(char) for index, char in enumerate(key))
    return ((total % 997) / 997 - 0.5) * width


def nice_domain(values: Iterable[float], pad_ratio: float = 0.08) -> tuple[float, float]:
    vals = list(values)
    lower = min(vals)
    upper = max(vals)
    span = max(upper - lower, 1)
    return lower - span * pad_ratio, upper + span * pad_ratio


def scale(value: float, domain: tuple[float, float], start: float, end: float) -> float:
    lower, upper = domain
    return start + ((value - lower) / (upper - lower)) * (end - start)


def svg_text(
    x: float,
    y: float,
    text: object,
    size: int = 12,
    fill: str = "#17201d",
    weight: int = 500,
    anchor: str = "start",
    extra: str = "",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
        f'font-weight="{weight}" text-anchor="{anchor}" {extra}>{esc(text)}</text>'
    )


def axis_ticks(domain: tuple[float, float], count: int = 5) -> list[float]:
    lower, upper = domain
    raw_step = (upper - lower) / max(count - 1, 1)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    residual = raw_step / magnitude
    if residual >= 5:
        step = 5 * magnitude
    elif residual >= 2:
        step = 2 * magnitude
    else:
        step = magnitude
    first = math.ceil(lower / step) * step
    ticks = []
    value = first
    while value <= upper:
        ticks.append(value)
        value += step
    return ticks


def load_logo_data_uri() -> str:
    logo_path = ROOT / "static" / "brand-assets" / "municipal-benchmark-horizontal-lockup-primary-clean.png"
    if not logo_path.exists():
        return ""
    data = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def load_data() -> tuple[list[dict], dict[str, dict], dict[str, dict], list[str]]:
    profiles = {row["council_key"]: row for row in read_csv("council_profile_mart.csv")}
    spatial = {row["council_key"]: row for row in read_csv("spatial_context_mart.csv")}
    raw_rows = read_csv("pay_range_summary_mart.csv")

    latest: dict[tuple[str, int], dict] = {}
    for row in raw_rows:
        if row.get("governed_canonical_status") != "governed":
            continue
        effective_from = parse_date(row.get("effective_from"))
        effective_to = parse_date(row.get("effective_to"))
        if not effective_from or effective_from > SNAPSHOT_DATE:
            continue
        if effective_to and effective_to < SNAPSHOT_DATE:
            continue
        try:
            band = int(float(row["standard_band"]))
        except (TypeError, ValueError):
            continue

        parsed = dict(row)
        parsed["standard_band_int"] = band
        parsed["effective_from_date"] = effective_from
        parsed["effective_to_date"] = effective_to
        for metric_key, _ in METRICS:
            parsed[metric_key] = parse_float(row.get(metric_key))
        parsed["progression_spread_abs"] = parse_float(row.get("progression_spread_abs"))
        parsed["progression_spread_pct"] = parse_float(row.get("progression_spread_pct"))
        parsed["point_count"] = int(float(row["point_count"])) if row.get("point_count") else None

        key = (parsed["canonical_council_id"], band)
        current = latest.get(key)
        current_sort = ("", "")
        if current:
            current_sort = (current["effective_from"], current["agreement_id"])
        next_sort = (parsed["effective_from"], parsed["agreement_id"])
        if current is None or next_sort > current_sort:
            latest[key] = parsed

    ballarat_spatial = spatial[BALLARAT_KEY]
    lat0 = float(ballarat_spatial["office_lat"])
    lon0 = float(ballarat_spatial["office_lon"])

    def haversine(row: dict[str, str]) -> float:
        lat1 = float(row["office_lat"])
        lon1 = float(row["office_lon"])
        earth_km = 6371
        phi1 = math.radians(lat0)
        phi2 = math.radians(lat1)
        delta_phi = math.radians(lat1 - lat0)
        delta_lambda = math.radians(lon1 - lon0)
        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        return 2 * earth_km * math.asin(math.sqrt(a))

    nearby = []
    for key, row in spatial.items():
        if key == BALLARAT_KEY or not row.get("office_lat") or not row.get("office_lon"):
            continue
        nearby.append((haversine(row), key))
    nearest_peer_keys = [key for _, key in sorted(nearby)[:10]]
    nearest_peer_keys.append(BALLARAT_KEY)
    return list(latest.values()), profiles, spatial, nearest_peer_keys


def values_for(rows: list[dict], band: int, metric: str, filter_func: Callable[[dict], bool] | None = None) -> list[dict]:
    filtered = []
    for row in rows:
        if row["standard_band_int"] != band:
            continue
        if row.get(metric) is None:
            continue
        if filter_func and not filter_func(row):
            continue
        filtered.append(row)
    return filtered


def summary_stats(rows: list[dict], band: int, metric: str, filter_func: Callable[[dict], bool] | None = None) -> dict:
    metric_rows = values_for(rows, band, metric, filter_func)
    values = [row[metric] for row in metric_rows]
    ballarat = next(row for row in metric_rows if row["canonical_council_id"] == BALLARAT_KEY)
    selected = ballarat[metric]
    return {
        "count": len(values),
        "min": min(values),
        "p25": quantile(values, 0.25),
        "median": statistics.median(values),
        "p75": quantile(values, 0.75),
        "max": max(values),
        "ballarat": selected,
        "delta_to_median": selected - statistics.median(values),
        "percentile": percentile_rank(values, selected),
    }


def distribution_dotplot(rows: list[dict], profiles: dict[str, dict], band: int, metric: str) -> str:
    chart_rows = values_for(rows, band, metric)
    stats = summary_stats(rows, band, metric)
    values = [row[metric] for row in chart_rows]
    domain = nice_domain(values, 0.07)
    width, height = 930, 345
    left, right, top, bottom = 70, 40, 34, 66
    plot_top, plot_bottom = top + 38, height - bottom
    center_y = (plot_top + plot_bottom) / 2 + 8
    plot_left, plot_right = left, width - right
    iqr_x1 = scale(stats["p25"], domain, plot_left, plot_right)
    iqr_x2 = scale(stats["p75"], domain, plot_left, plot_right)
    median_x = scale(stats["median"], domain, plot_left, plot_right)
    ball_x = scale(stats["ballarat"], domain, plot_left, plot_right)

    category_colors = {
        "Regional": PALETTE["teal"],
        "Metropolitan": PALETTE["blue"],
        "Large shire": PALETTE["jade"],
        "Small shire": PALETTE["gold"],
        "Interface": PALETTE["violet"],
    }

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Band {band} midpoint distribution dot plot">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="#fbfcfb"/>',
        svg_text(left, 28, f"Band {band} midpoint distribution", 18, PALETTE["ink"], 760),
        svg_text(width - right, 28, "All governed comparable LGA rows active 1 Jul 2025", 11, PALETTE["muted"], 500, "end"),
        f'<line x1="{plot_left}" y1="{center_y}" x2="{plot_right}" y2="{center_y}" stroke="{PALETTE["line"]}" stroke-width="1.2"/>',
        f'<rect x="{iqr_x1:.1f}" y="{plot_top + 34:.1f}" width="{iqr_x2 - iqr_x1:.1f}" height="{plot_bottom - plot_top - 44:.1f}" rx="12" fill="#d9eee9"/>',
        f'<line x1="{median_x:.1f}" y1="{plot_top + 20}" x2="{median_x:.1f}" y2="{plot_bottom - 6}" stroke="{PALETTE["teal"]}" stroke-width="2.4"/>',
        f'<line x1="{ball_x:.1f}" y1="{plot_top + 4}" x2="{ball_x:.1f}" y2="{plot_bottom + 5}" stroke="{PALETTE["ballarat"]}" stroke-width="2.8"/>',
    ]

    for tick in axis_ticks(domain, 6):
        x = scale(tick, domain, plot_left, plot_right)
        parts.append(f'<line x1="{x:.1f}" y1="{plot_bottom + 15}" x2="{x:.1f}" y2="{plot_bottom + 22}" stroke="{PALETTE["line"]}" />')
        parts.append(svg_text(x, plot_bottom + 42, money_plain(tick), 10, PALETTE["muted"], 500, "middle"))

    for row in sorted(chart_rows, key=lambda item: item[metric]):
        key = row["canonical_council_id"]
        profile = profiles.get(key, {})
        category = profile.get("council_category", "Other")
        color = category_colors.get(category, "#9da8a2")
        x = scale(row[metric], domain, plot_left, plot_right)
        y = center_y + stable_jitter(key + str(band), 74)
        if key == BALLARAT_KEY:
            continue
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.4" fill="{color}" opacity="0.58" stroke="#fff" stroke-width="1"/>'
        )

    parts.extend(
        [
            f'<circle cx="{ball_x:.1f}" cy="{center_y:.1f}" r="10.2" fill="{PALETTE["ballarat"]}" stroke="#fff" stroke-width="2.4"/>',
            f'<circle cx="{ball_x:.1f}" cy="{center_y:.1f}" r="15.5" fill="none" stroke="{PALETTE["ballarat"]}" stroke-width="1.6" opacity="0.42"/>',
            svg_text(ball_x + 18, center_y - 15, "Ballarat", 13, PALETTE["ballarat_dark"], 800),
            svg_text(ball_x + 18, center_y + 2, money(stats["ballarat"]), 12, PALETTE["ballarat_dark"], 700),
            svg_text(median_x + 8, plot_top + 31, f"Median {money(stats['median'])}", 11, PALETTE["teal"], 700),
            svg_text(iqr_x1, plot_top + 16, "middle 50% of LGAs", 10, PALETTE["muted"], 600),
            svg_text(plot_left, height - 12, "Colour separates council categories; muted points keep the field readable while Ballarat carries the decision signal.", 10, PALETTE["muted"], 500),
        ]
    )
    parts.append("</svg>")
    return "\n".join(parts)


def range_matrix(rows: list[dict]) -> str:
    matrix = []
    all_values = []
    for band in CORE_BANDS:
        for metric, label in METRICS:
            metric_rows = values_for(rows, band, metric)
            values = [row[metric] for row in metric_rows]
            stats = summary_stats(rows, band, metric)
            matrix.append((band, metric, label, values, stats))
            all_values.extend(values)

    domain = nice_domain(all_values, 0.04)
    width, height = 940, 430
    left, right, top, bottom = 135, 54, 38, 52
    plot_left, plot_right = left, width - right
    row_gap = (height - top - bottom) / len(matrix)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Pay range matrix">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="#fbfcfb"/>',
        svg_text(left, 27, "Entry, midpoint and capacity: Ballarat against the distribution", 17, PALETTE["ink"], 760),
        svg_text(width - right, 27, "IQR bar, statewide median tick, Ballarat dot", 11, PALETTE["muted"], 500, "end"),
    ]

    for tick in axis_ticks(domain, 7):
        x = scale(tick, domain, plot_left, plot_right)
        parts.append(f'<line x1="{x:.1f}" y1="{top + 22}" x2="{x:.1f}" y2="{height - bottom + 3}" stroke="#edf1ee" stroke-width="1"/>')
        parts.append(svg_text(x, height - 18, money_plain(tick), 10, PALETTE["muted"], 500, "middle"))

    for index, (band, _, label, values, stats) in enumerate(matrix):
        y = top + 42 + index * row_gap
        x_min = scale(min(values), domain, plot_left, plot_right)
        x_max = scale(max(values), domain, plot_left, plot_right)
        x_p25 = scale(stats["p25"], domain, plot_left, plot_right)
        x_p75 = scale(stats["p75"], domain, plot_left, plot_right)
        x_median = scale(stats["median"], domain, plot_left, plot_right)
        x_ballarat = scale(stats["ballarat"], domain, plot_left, plot_right)
        row_label = f"Band {band} {label}"
        parts.append(svg_text(24, y + 4, row_label, 11, PALETTE["ink"], 760))
        parts.append(f'<line x1="{x_min:.1f}" y1="{y:.1f}" x2="{x_max:.1f}" y2="{y:.1f}" stroke="#cbd5ce" stroke-width="1.4"/>')
        parts.append(f'<line x1="{x_p25:.1f}" y1="{y:.1f}" x2="{x_p75:.1f}" y2="{y:.1f}" stroke="#91d0c4" stroke-width="12" stroke-linecap="round" opacity="0.78"/>')
        parts.append(f'<line x1="{x_median:.1f}" y1="{y - 13:.1f}" x2="{x_median:.1f}" y2="{y + 13:.1f}" stroke="{PALETTE["teal"]}" stroke-width="2.2"/>')
        parts.append(f'<circle cx="{x_ballarat:.1f}" cy="{y:.1f}" r="7.4" fill="{PALETTE["ballarat"]}" stroke="#fff" stroke-width="2"/>')
        parts.append(svg_text(width - 38, y + 4, delta_money(stats["delta_to_median"]), 10, PALETTE["ballarat_dark"], 740, "end"))

    parts.extend(
        [
            svg_text(plot_left, height - 36, "Lower", 10, PALETTE["muted"], 600),
            svg_text(plot_right, height - 36, "Higher", 10, PALETTE["muted"], 600, "end"),
            svg_text(width - 38, top + 42 + len(matrix) * row_gap + 2, "vs median", 9, PALETTE["muted"], 600, "end"),
            "</svg>",
        ]
    )
    return "\n".join(parts)


def band5_scatter(rows: list[dict], profiles: dict[str, dict]) -> str:
    chart_rows = [
        row
        for row in values_for(rows, 5, "entry_weekly_rate")
        if row.get("capacity_weekly_rate") is not None
    ]
    x_values = [row["entry_weekly_rate"] for row in chart_rows]
    y_values = [row["capacity_weekly_rate"] for row in chart_rows]
    x_domain = nice_domain(x_values, 0.08)
    y_domain = nice_domain(y_values, 0.08)
    width, height = 545, 384
    left, right, top, bottom = 70, 34, 36, 58
    plot_left, plot_right = left, width - right
    plot_top, plot_bottom = top, height - bottom
    category_colors = {
        "Regional": PALETTE["teal"],
        "Metropolitan": PALETTE["blue"],
        "Large shire": PALETTE["jade"],
        "Small shire": PALETTE["gold"],
        "Interface": PALETTE["violet"],
    }
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Band 5 entry and capacity scatter">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="#fbfcfb"/>',
        svg_text(24, 28, "Band 5 structure: entry vs capacity", 16, PALETTE["ink"], 760),
    ]
    for tick in axis_ticks(x_domain, 5):
        x = scale(tick, x_domain, plot_left, plot_right)
        parts.append(f'<line x1="{x:.1f}" y1="{plot_top}" x2="{x:.1f}" y2="{plot_bottom}" stroke="#edf1ee"/>')
        parts.append(svg_text(x, plot_bottom + 27, money_plain(tick), 9, PALETTE["muted"], 500, "middle"))
    for tick in axis_ticks(y_domain, 5):
        y = scale(tick, y_domain, plot_bottom, plot_top)
        parts.append(f'<line x1="{plot_left}" y1="{y:.1f}" x2="{plot_right}" y2="{y:.1f}" stroke="#edf1ee"/>')
        parts.append(svg_text(plot_left - 12, y + 3, money_plain(tick), 9, PALETTE["muted"], 500, "end"))
    parts.append(f'<rect x="{plot_left}" y="{plot_top}" width="{plot_right - plot_left}" height="{plot_bottom - plot_top}" fill="none" stroke="{PALETTE["line"]}"/>')

    for row in chart_rows:
        key = row["canonical_council_id"]
        x = scale(row["entry_weekly_rate"], x_domain, plot_left, plot_right)
        y = scale(row["capacity_weekly_rate"], y_domain, plot_bottom, plot_top)
        if key == BALLARAT_KEY:
            continue
        category = profiles.get(key, {}).get("council_category", "")
        color = category_colors.get(category, "#a7b0aa")
        radius = 4.8 if category == "Regional" else 3.9
        opacity = 0.72 if category == "Regional" else 0.45
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{color}" opacity="{opacity}" stroke="#fff" stroke-width="0.8"/>')

    ballarat = next(row for row in chart_rows if row["canonical_council_id"] == BALLARAT_KEY)
    bx = scale(ballarat["entry_weekly_rate"], x_domain, plot_left, plot_right)
    by = scale(ballarat["capacity_weekly_rate"], y_domain, plot_bottom, plot_top)
    parts.extend(
        [
            f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="8.8" fill="{PALETTE["ballarat"]}" stroke="#fff" stroke-width="2"/>',
            f'<path d="M {bx + 8:.1f} {by - 8:.1f} L {bx + 58:.1f} {by - 42:.1f}" stroke="{PALETTE["ballarat"]}" stroke-width="1.2"/>',
            svg_text(bx + 62, by - 45, "Ballarat", 12, PALETTE["ballarat_dark"], 800),
            svg_text(bx + 62, by - 29, f"{money(ballarat['entry_weekly_rate'])} entry", 10, PALETTE["ballarat_dark"], 600),
            svg_text(bx + 62, by - 15, f"{money(ballarat['capacity_weekly_rate'])} capacity", 10, PALETTE["ballarat_dark"], 600),
            svg_text(plot_left, height - 12, "Entry weekly rate (x); capacity weekly rate (y)", 10, PALETTE["muted"], 650),
            "</svg>",
        ]
    )
    return "\n".join(parts)


def cohort_delta_heatmap(
    rows: list[dict],
    profiles: dict[str, dict],
    nearest_peer_keys: list[str],
) -> tuple[str, dict[str, dict]]:
    cohort_filters: list[tuple[str, Callable[[dict], bool]]] = [
        ("Statewide", lambda row: True),
        ("Regional cities", lambda row: profiles.get(row["canonical_council_id"], {}).get("council_category") == "Regional"),
        ("Central Highlands", lambda row: profiles.get(row["canonical_council_id"], {}).get("vif_regional_partnership") == "Central Highlands"),
        ("Nearest peers", lambda row: row["canonical_council_id"] in nearest_peer_keys),
    ]
    records = []
    max_abs = 0.0
    for band in CORE_BANDS:
        for metric, metric_label in METRICS:
            row_record = {
                "label": f"B{band} {metric_label}",
                "band": band,
                "metric": metric,
                "cells": [],
            }
            for cohort_name, cohort_filter in cohort_filters:
                stats = summary_stats(rows, band, metric, cohort_filter)
                max_abs = max(max_abs, abs(stats["delta_to_median"]))
                row_record["cells"].append((cohort_name, stats))
            records.append(row_record)

    width, height = 705, 430
    left, top = 112, 58
    cell_w, cell_h = 136, 34
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Cohort delta heatmap">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="#fbfcfb"/>',
        svg_text(24, 28, "Ballarat delta to cohort median", 17, PALETTE["ink"], 760),
        svg_text(width - 24, 28, "Negative values indicate Ballarat below median", 10, PALETTE["muted"], 500, "end"),
    ]
    for col_index, (cohort_name, _) in enumerate(cohort_filters):
        x = left + col_index * cell_w + cell_w / 2
        parts.append(svg_text(x, top - 16, cohort_name, 10, PALETTE["muted"], 760, "middle"))

    for row_index, record in enumerate(records):
        y = top + row_index * cell_h
        parts.append(svg_text(23, y + 22, record["label"], 10, PALETTE["ink"], 760))
        for col_index, (_, stats) in enumerate(record["cells"]):
            x = left + col_index * cell_w
            delta = stats["delta_to_median"]
            intensity = min(abs(delta) / max_abs, 1) if max_abs else 0
            if delta < 0:
                fill = f"rgba(216, 79, 63, {0.13 + intensity * 0.60:.3f})"
                stroke = "#e0a098"
                text_fill = PALETTE["ballarat_dark"]
            else:
                fill = f"rgba(15, 141, 126, {0.10 + intensity * 0.50:.3f})"
                stroke = "#96cfc7"
                text_fill = PALETTE["teal"]
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_w - 8}" height="{cell_h - 6}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="0.8"/>')
            parts.append(svg_text(x + (cell_w - 8) / 2, y + 20, delta_money(delta), 10, text_fill, 760, "middle"))

    parts.extend(
        [
            svg_text(24, height - 34, "Read horizontally: the same Ballarat pay point is tested against different executive peer frames.", 10, PALETTE["muted"], 500),
            "</svg>",
        ]
    )
    audit = {}
    for record in records:
        audit[record["label"]] = {
            cohort_name: {
                "count": stats["count"],
                "median": round(stats["median"], 2),
                "ballarat": round(stats["ballarat"], 2),
                "delta_to_median": round(stats["delta_to_median"], 2),
                "percentile": round(stats["percentile"], 1),
            }
            for cohort_name, stats in record["cells"]
        }
    return "\n".join(parts), audit


def nearest_peer_strip(rows: list[dict], profiles: dict[str, dict], nearest_peer_keys: list[str]) -> str:
    band = 5
    metric = "range_midpoint_weekly_rate"
    chart_rows = [
        row
        for row in values_for(rows, band, metric)
        if row["canonical_council_id"] in nearest_peer_keys
    ]
    values = [row[metric] for row in chart_rows]
    domain = nice_domain(values, 0.12)
    median_value = statistics.median(values)
    width, height = 705, 225
    left, right, top, bottom = 64, 30, 44, 52
    plot_left, plot_right = left, width - right
    baseline_y = 102
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Nearest peer strip plot">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="#fbfcfb"/>',
        svg_text(24, 27, "Nearest office peers: Band 5 midpoint", 16, PALETTE["ink"], 760),
        f'<line x1="{plot_left}" y1="{baseline_y}" x2="{plot_right}" y2="{baseline_y}" stroke="{PALETTE["line"]}" stroke-width="1.2"/>',
    ]
    for tick in axis_ticks(domain, 6):
        x = scale(tick, domain, plot_left, plot_right)
        parts.append(f'<line x1="{x:.1f}" y1="{baseline_y + 42}" x2="{x:.1f}" y2="{baseline_y + 49}" stroke="{PALETTE["line"]}"/>')
        parts.append(svg_text(x, baseline_y + 69, money_plain(tick), 9, PALETTE["muted"], 500, "middle"))

    median_x = scale(median_value, domain, plot_left, plot_right)
    parts.append(f'<line x1="{median_x:.1f}" y1="{baseline_y - 56}" x2="{median_x:.1f}" y2="{baseline_y + 38}" stroke="{PALETTE["teal"]}" stroke-width="2"/>')
    parts.append(svg_text(median_x + 7, baseline_y - 42, f"Peer median {money(median_value)}", 10, PALETTE["teal"], 750))

    label_offsets = {
        "BALLARAT": (0, -18, "middle", PALETTE["ballarat_dark"]),
        "HEPBURN": (0, -18, "middle", PALETTE["muted"]),
        "MOORABOOL": (-10, 28, "end", PALETTE["muted"]),
        "WYNDHAM": (0, -18, "middle", PALETTE["muted"]),
    }

    for row in sorted(chart_rows, key=lambda item: item[metric]):
        key = row["canonical_council_id"]
        value = row[metric]
        x = scale(value, domain, plot_left, plot_right)
        y = baseline_y + stable_jitter(key, 44)
        if key == BALLARAT_KEY:
            fill = PALETTE["ballarat"]
            radius = 8.5
            opacity = 1
        else:
            category = profiles.get(key, {}).get("council_category")
            fill = PALETTE["jade"] if category and "shire" in category.lower() else PALETTE["blue"]
            radius = 5.2
            opacity = 0.62
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{fill}" opacity="{opacity}" stroke="#fff" stroke-width="1.5"/>')
        short_name = profiles.get(key, {}).get("short_name", key.title())
        if key in label_offsets:
            dx, dy, anchor, color = label_offsets[key]
            parts.append(svg_text(x + dx, y + dy, short_name, 9, color, 700, anchor))

    ballarat = next(row for row in chart_rows if row["canonical_council_id"] == BALLARAT_KEY)
    parts.append(svg_text(24, height - 15, f"Ballarat: {money(ballarat[metric])}; peer median: {money(median_value)}; gap: {delta_money(ballarat[metric] - median_value)}.", 10, PALETTE["muted"], 550))
    parts.append("</svg>")
    return "\n".join(parts)


def build_audit_dataset(
    rows: list[dict],
    profiles: dict[str, dict],
    nearest_peer_keys: list[str],
    heatmap_audit: dict[str, dict],
) -> dict:
    band_metric_summary = {}
    for band in CORE_BANDS:
        for metric, metric_label in METRICS:
            stats = summary_stats(rows, band, metric)
            band_metric_summary[f"band_{band}_{metric}"] = {
                "band": band,
                "metric": metric,
                "metric_label": metric_label,
                "count": stats["count"],
                "ballarat": round(stats["ballarat"], 2),
                "statewide_median": round(stats["median"], 2),
                "delta_to_statewide_median": round(stats["delta_to_median"], 2),
                "percentile_rank": round(stats["percentile"], 1),
                "min": round(stats["min"], 2),
                "p25": round(stats["p25"], 2),
                "p75": round(stats["p75"], 2),
                "max": round(stats["max"], 2),
            }

    peer_list = [
        {
            "council_key": key,
            "short_name": profiles.get(key, {}).get("short_name", key.title()),
            "category": profiles.get(key, {}).get("council_category"),
            "regional_partnership": profiles.get(key, {}).get("vif_regional_partnership"),
        }
        for key in nearest_peer_keys
    ]
    return {
        "report_title": "Ballarat City Council - Executive LGA Benchmark",
        "snapshot_date": SNAPSHOT_DATE.isoformat(),
        "source_dataset": "data/datamarts/pay_range_summary_mart.csv",
        "row_basis": "latest governed row by council and standard band active at the snapshot date",
        "core_bands": CORE_BANDS,
        "summary": band_metric_summary,
        "cohort_deltas": heatmap_audit,
        "nearest_peer_keys": peer_list,
        "caveats": [
            "Executive prototype for review, not a final publication clearance.",
            "Pay values use governed workbench pay rows active on the snapshot date.",
            "Rows are deduplicated by council and band using the latest effective_from date active at the snapshot.",
            "The report focuses on Bands 4-6 because they carry the broadest executive decision value in the current workbench data.",
        ],
    }


def build_html() -> tuple[str, dict]:
    rows, profiles, _spatial, nearest_peer_keys = load_data()
    logo_data_uri = load_logo_data_uri()

    band5_mid = summary_stats(rows, 5, "range_midpoint_weekly_rate")
    band4_mid = summary_stats(rows, 4, "range_midpoint_weekly_rate")
    band6_mid = summary_stats(rows, 6, "range_midpoint_weekly_rate")
    nearest_band5_mid = summary_stats(
        rows,
        5,
        "range_midpoint_weekly_rate",
        lambda row: row["canonical_council_id"] in nearest_peer_keys,
    )
    distribution_svg = distribution_dotplot(rows, profiles, 5, "range_midpoint_weekly_rate")
    matrix_svg = range_matrix(rows)
    scatter_svg = band5_scatter(rows, profiles)
    heatmap_svg, heatmap_audit = cohort_delta_heatmap(rows, profiles, nearest_peer_keys)
    peer_strip_svg = nearest_peer_strip(rows, profiles, nearest_peer_keys)
    audit = build_audit_dataset(rows, profiles, nearest_peer_keys, heatmap_audit)

    html_text = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Ballarat City Council - Executive LGA Benchmark</title>
<style>
@page {{
  size: A4 landscape;
  margin: 0;
}}
* {{
  box-sizing: border-box;
}}
html, body {{
  margin: 0;
  padding: 0;
  background: #dfe6e1;
  color: {PALETTE["ink"]};
  font-family: "Segoe UI", Arial, sans-serif;
  letter-spacing: 0;
}}
.page {{
  position: relative;
  width: 297mm;
  height: 210mm;
  padding: 13mm 14mm 11mm 14mm;
  background:
    linear-gradient(90deg, rgba(15, 141, 126, 0.05) 0 1px, transparent 1px 48px),
    linear-gradient(0deg, rgba(35, 49, 44, 0.045) 0 1px, transparent 1px 48px),
    #f6f8f5;
  overflow: hidden;
  page-break-after: always;
}}
.page:last-child {{
  page-break-after: auto;
}}
.page::before {{
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6mm;
  background: linear-gradient(180deg, {PALETTE["teal"]}, {PALETTE["gold"]} 48%, {PALETTE["ballarat"]});
}}
.report-header {{
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: start;
  gap: 18px;
  margin-bottom: 8mm;
}}
.brand {{
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 28px;
}}
.brand img {{
  width: 196px;
  height: auto;
  object-fit: contain;
}}
.brand-fallback {{
  font-size: 13px;
  font-weight: 800;
  color: {PALETTE["charcoal"]};
}}
.meta {{
  text-align: right;
  color: {PALETTE["muted"]};
  font-size: 10.5px;
  line-height: 1.45;
}}
.kicker {{
  margin-top: 3mm;
  color: {PALETTE["teal"]};
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}}
h1 {{
  margin: 2mm 0 0;
  font-size: 35px;
  line-height: 1.02;
  font-weight: 820;
  color: {PALETTE["ink"]};
  max-width: 710px;
}}
h2 {{
  margin: 0;
  font-size: 24px;
  line-height: 1.08;
  font-weight: 820;
  color: {PALETTE["ink"]};
}}
.subhead {{
  margin-top: 4mm;
  max-width: 750px;
  color: {PALETTE["muted"]};
  font-size: 13.5px;
  line-height: 1.42;
}}
.grid-p1 {{
  display: grid;
  grid-template-columns: 1.35fr 0.65fr;
  gap: 8mm;
  align-items: start;
}}
.left-stack {{
  display: grid;
  gap: 10px;
}}
.quick-reads {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}}
.read-card {{
  background: rgba(255, 255, 255, 0.93);
  border: 1px solid {PALETTE["line"]};
  border-radius: 10px;
  padding: 11px 12px 10px;
  min-height: 90px;
}}
.read-card .eyebrow {{
  color: {PALETTE["teal"]};
  font-size: 9.3px;
  font-weight: 820;
  text-transform: uppercase;
}}
.read-card strong {{
  display: block;
  margin-top: 5px;
  color: {PALETTE["ink"]};
  font-size: 12.7px;
  line-height: 1.2;
}}
.read-card span {{
  display: block;
  margin-top: 5px;
  color: {PALETTE["muted"]};
  font-size: 10.2px;
  line-height: 1.3;
}}
.grid-p2 {{
  display: grid;
  grid-template-columns: 1.35fr 0.78fr;
  gap: 7mm;
  align-items: start;
}}
.grid-p3 {{
  display: grid;
  grid-template-columns: 0.94fr 0.9fr;
  gap: 7mm;
  align-items: start;
}}
.panel {{
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(215, 223, 217, 0.95);
  border-radius: 12px;
  box-shadow: 0 12px 30px rgba(23, 32, 29, 0.06);
  overflow: hidden;
}}
.panel.pad {{
  padding: 15px 17px;
}}
.signal-stack {{
  display: grid;
  grid-template-rows: auto auto auto 1fr;
  gap: 10px;
}}
.signal {{
  background: #ffffff;
  border: 1px solid {PALETTE["line"]};
  border-radius: 11px;
  padding: 13px 14px;
}}
.signal .label {{
  color: {PALETTE["muted"]};
  font-size: 10px;
  font-weight: 750;
  text-transform: uppercase;
}}
.signal .value {{
  color: {PALETTE["ink"]};
  font-size: 25px;
  line-height: 1.05;
  font-weight: 840;
  margin-top: 5px;
}}
.signal .caption {{
  color: {PALETTE["muted"]};
  font-size: 11px;
  line-height: 1.33;
  margin-top: 6px;
}}
.signal.accent {{
  border-color: rgba(216, 79, 63, 0.35);
  background: linear-gradient(135deg, #fff 0%, #fff7f5 100%);
}}
.signal.accent .value {{
  color: {PALETTE["ballarat_dark"]};
}}
.executive-note {{
  background: {PALETTE["charcoal"]};
  color: #eef6f1;
  border-radius: 12px;
  padding: 15px;
  font-size: 12px;
  line-height: 1.42;
}}
.executive-note strong {{
  color: #ffffff;
}}
.section-title {{
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
  margin-bottom: 6mm;
}}
.section-title p {{
  max-width: 520px;
  margin: 0;
  color: {PALETTE["muted"]};
  font-size: 12.5px;
  line-height: 1.38;
}}
.two-up {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6mm;
}}
.mini-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 10.7px;
}}
.mini-table th {{
  text-align: left;
  color: {PALETTE["muted"]};
  font-size: 9px;
  text-transform: uppercase;
  padding: 7px 6px;
  border-bottom: 1px solid {PALETTE["line"]};
}}
.mini-table td {{
  padding: 7px 6px;
  border-bottom: 1px solid #edf1ee;
  vertical-align: top;
}}
.mini-table td:last-child {{
  text-align: right;
  font-weight: 760;
  color: {PALETTE["ballarat_dark"]};
}}
.interpretation {{
  display: grid;
  gap: 10px;
}}
.callout {{
  border-left: 4px solid {PALETTE["teal"]};
  background: #ffffff;
  border-radius: 8px;
  padding: 11px 12px;
  color: {PALETTE["muted"]};
  font-size: 11.4px;
  line-height: 1.42;
}}
.callout strong {{
  color: {PALETTE["ink"]};
}}
.action-list {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 8px;
}}
.action {{
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid {PALETTE["line"]};
  border-radius: 10px;
  padding: 11px 12px;
  min-height: 82px;
}}
.action .n {{
  color: {PALETTE["teal"]};
  font-weight: 840;
  font-size: 11px;
}}
.action h3 {{
  margin: 4px 0 5px;
  font-size: 13px;
  color: {PALETTE["ink"]};
}}
.action p {{
  margin: 0;
  color: {PALETTE["muted"]};
  font-size: 10.5px;
  line-height: 1.32;
}}
.footer {{
  position: absolute;
  left: 14mm;
  right: 14mm;
  bottom: 6mm;
  display: flex;
  justify-content: space-between;
  color: #728078;
  font-size: 9.4px;
  line-height: 1.25;
}}
.footer strong {{
  color: {PALETTE["ink"]};
}}
.badge {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 999px;
  background: #e7f3ef;
  color: {PALETTE["teal"]};
  font-size: 10px;
  font-weight: 760;
}}
.legend-dot {{
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}}
svg {{
  width: 100%;
  height: auto;
  display: block;
}}
.caveat {{
  font-size: 9.4px;
  line-height: 1.3;
  color: {PALETTE["muted"]};
}}
</style>
</head>
<body>
  <section class="page">
    <header class="report-header">
      <div>
        <div class="brand">
          {'<img src="' + logo_data_uri + '" alt="Municipal Benchmark">' if logo_data_uri else '<span class="brand-fallback">Municipal Benchmark</span>'}
        </div>
        <div class="kicker">Executive LGA benchmark</div>
        <h1>Ballarat sits below the governed pay median across the core operational bands.</h1>
        <p class="subhead">A dense, executive-grade read of Ballarat City Council against other Victorian LGAs, using governed pay rows active at 1 July 2025. The report emphasises distribution, cohort context and commercial interpretation over simple ranking.</p>
      </div>
      <div class="meta">
        Prepared from EBA Workbench datamarts<br>
        Snapshot: <strong>{SNAPSHOT_DATE.strftime("%d %b %Y")}</strong><br>
        Scope: Bands 4-6, weekly rates
      </div>
    </header>
    <div class="grid-p1">
      <div class="left-stack">
        <div class="panel">
          {distribution_svg}
        </div>
        <div class="quick-reads">
          <div class="read-card"><div class="eyebrow">Position</div><strong>Below median and near the lower quartile</strong><span>Band 5 midpoint sits at the {pct(band5_mid["percentile"])} percentile across the governed LGA field.</span></div>
          <div class="read-card"><div class="eyebrow">Pattern</div><strong>Repeated across Bands 4-6</strong><span>The signal appears at entry, midpoint and capacity, making it more credible than a single-rate exception.</span></div>
          <div class="read-card"><div class="eyebrow">Peer pressure</div><strong>{delta_money(nearest_band5_mid["delta_to_median"])} against nearby peers</strong><span>Nearby LGAs create the sharpest labour-market comparison frame for the executive story.</span></div>
        </div>
      </div>
      <aside class="signal-stack">
        <div class="signal accent">
          <div class="label">Ballarat Band 5 midpoint</div>
          <div class="value">{money(band5_mid["ballarat"])}</div>
          <div class="caption">{delta_money(band5_mid["delta_to_median"])} versus statewide median; {pct(band5_mid["percentile"])} percentile across {band5_mid["count"]} LGAs.</div>
        </div>
        <div class="signal">
          <div class="label">Band 4 midpoint</div>
          <div class="value">{delta_money(band4_mid["delta_to_median"])}</div>
          <div class="caption">Below median despite a complete four-point Ballarat range.</div>
        </div>
        <div class="signal">
          <div class="label">Band 6 midpoint</div>
          <div class="value">{delta_money(band6_mid["delta_to_median"])}</div>
          <div class="caption">Less extreme than Band 5, but still below the statewide centre.</div>
        </div>
        <div class="executive-note">
          <strong>Executive reading.</strong> Ballarat is not merely a low outlier on one pay point. The pattern repeats across entry, midpoint and capacity for Bands 4-6, which means the commercial story is about pay architecture and cohort positioning, not a single anomalous cell.
        </div>
      </aside>
    </div>
    <div class="footer">
      <span><strong>Source:</strong> data/datamarts/pay_range_summary_mart.csv; latest governed row by council/band active at snapshot.</span>
      <span>01 / 03</span>
    </div>
  </section>

  <section class="page">
    <div class="section-title">
      <div>
        <div class="kicker">Pay architecture</div>
        <h2>The gap is structural: it appears at entry, midpoint and capacity.</h2>
      </div>
      <p>The matrix uses a compact analyst visual: full range, middle 50%, statewide median and Ballarat dot. This gives executives more information than a bar chart while preserving a fast decision signal.</p>
    </div>
    <div class="grid-p2">
      <div class="panel">
        {matrix_svg}
      </div>
      <div class="interpretation">
        <div class="panel">
          {scatter_svg}
        </div>
        <div class="panel pad">
          <table class="mini-table">
            <thead>
              <tr><th>Signal</th><th>Executive implication</th></tr>
            </thead>
            <tbody>
              <tr><td>Band 5 midpoint below median</td><td>{delta_money(band5_mid["delta_to_median"])}</td></tr>
              <tr><td>Band 5 capacity below median</td><td>{delta_money(summary_stats(rows, 5, "capacity_weekly_rate")["delta_to_median"])}</td></tr>
              <tr><td>Band 6 midpoint below median</td><td>{delta_money(band6_mid["delta_to_median"])}</td></tr>
              <tr><td>Observed breadth</td><td>{band5_mid["count"]} LGAs</td></tr>
            </tbody>
          </table>
        </div>
        <div class="callout"><strong>Why this chart form matters.</strong> Entry, midpoint and capacity carry different workforce psychology. Entry affects attraction; midpoint affects experienced staff relativity; capacity affects retention and bargaining pressure. Showing all three prevents a false sense of precision from a single aggregate.</div>
      </div>
    </div>
    <div class="footer">
      <span><strong>Design note:</strong> IQR and dot/scatter views preserve density without forcing executives into a spreadsheet.</span>
      <span>02 / 03</span>
    </div>
  </section>

  <section class="page">
    <div class="section-title">
      <div>
        <div class="kicker">Peer lens and action</div>
        <h2>The nearby-peer gap is the sharpest commercial signal.</h2>
      </div>
      <p>Statewide comparison is useful, but local labour-market psychology is often shaped by nearby councils and recognisable regional peers. The heatmap tests the same Ballarat values against four executive frames.</p>
    </div>
    <div class="grid-p3">
      <div class="panel">
        {heatmap_svg}
      </div>
      <div class="interpretation">
        <div class="panel">
          {peer_strip_svg}
        </div>
        <div class="action-list">
          <div class="action"><div class="n">01</div><h3>Frame the risk precisely</h3><p>Use Bands 4-6 to describe market pressure without overstating the whole agreement. The current signal is concentrated enough to be credible.</p></div>
          <div class="action"><div class="n">02</div><h3>Separate attraction and retention</h3><p>Entry, midpoint and capacity should be considered separately. One uplift design may not solve all three workforce moments.</p></div>
          <div class="action"><div class="n">03</div><h3>Use local peers carefully</h3><p>Nearby LGAs create the strongest comparison pressure. Pair that view with statewide medians to avoid a narrow anecdotal frame.</p></div>
          <div class="action"><div class="n">04</div><h3>Govern before publication</h3><p>This is an executive prototype. Promote the asset only after source evidence, cohort selection and narrative caveats are reviewed.</p></div>
        </div>
        <div class="callout"><strong>Bottom line.</strong> Ballarat can tell a disciplined story: pay is not at the market centre for core operational bands, and the gap becomes more salient when viewed through nearby LGAs. The recommended posture is calm, evidence-led positioning rather than broad-brush alarm.</div>
      </div>
    </div>
    <div class="footer">
      <span><strong>Caveat:</strong> Report is not legal or payroll advice. Values are governed workbench pay rows, but this artifact remains review-stage.</span>
      <span>03 / 03</span>
    </div>
  </section>
</body>
</html>
"""
    return html_text, audit


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_text, audit = build_html()
    html_path = OUTPUT_DIR / "ballarat-vs-lgas-executive-report.html"
    audit_path = OUTPUT_DIR / "ballarat-vs-lgas-executive-report-data.json"
    html_path.write_text(html_text, encoding="utf-8")
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(html_path)
    print(audit_path)


if __name__ == "__main__":
    main()
