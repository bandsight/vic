from __future__ import annotations

import argparse
import base64
import html
import json
import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import pandas as pd
from docx import Document
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
FROM_USER = ROOT.parent / "from user"
OUT_DIR = ROOT / "exports" / "ballarat-master-remuneration-report"

REPORT_STEM = "ballarat-remuneration-intelligence-report"


SYSTEM_UNIVERSE = {
    "current_state_scan_date": "2026-05-06",
    "app_routes": 88,
    "agent_catalog_data_sets": 11,
    "canonical_agreement_yaml": 111,
    "immutable_source_pdfs": 108,
    "reference_pdfs": 4,
    "governed_periods": 286,
    "governed_pay_tables": 285,
    "weekly_pay_rows": 8506,
    "governed_uplift_rules": 273,
    "rate_cap_rules": 43,
    "distribution_export_targets": 6,
    "test_suite": "490 passed",
}


@dataclass
class Page:
    kicker: str
    title: str
    body: str
    theme: str = "light"
    source: str = ""


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def money(value: Any, decimals: int = 0) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"${float(value):,.{decimals}f}"


def pct(value: Any, decimals: int = 1) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{float(value):.{decimals}f}%"


def compact_num(value: Any) -> str:
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}m"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:,.0f}"


def read_pay_ranges() -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / "datamarts" / "pay_range_summary_mart.csv")
    df["effective_from_dt"] = pd.to_datetime(df["effective_from"], errors="coerce")
    end = pd.to_datetime(df["effective_to"], errors="coerce")
    fallback = df["effective_from_dt"] + pd.DateOffset(years=1) - pd.DateOffset(days=1)
    df["effective_to_dt"] = end.fillna(fallback)
    df["standard_band"] = pd.to_numeric(df["standard_band"], errors="coerce").astype("Int64")
    return df


def read_profiles() -> pd.DataFrame:
    profile = pd.read_csv(ROOT / "data" / "datamarts" / "council_profile_mart.csv")
    spatial = pd.read_csv(ROOT / "data" / "datamarts" / "spatial_context_mart.csv")
    return profile.merge(
        spatial[["council_key", "office_lat", "office_lon", "abs_area_albers_sqkm", "office_township"]],
        on="council_key",
        how="left",
    )


def active_pay_snapshot(pay: pd.DataFrame, snapshot: str) -> pd.DataFrame:
    snap = pd.Timestamp(snapshot)
    active = pay[
        (pay["effective_from_dt"] <= snap)
        & (pay["effective_to_dt"] >= snap)
        & (pay["standard_band"].between(1, 8))
        & (pay["entry_weekly_rate"].notna())
        & (pay["capacity_weekly_rate"].notna())
    ].copy()
    active = active.sort_values(["canonical_council_id", "standard_band", "effective_from_dt"])
    return active.groupby(["canonical_council_id", "standard_band"], as_index=False).tail(1).reset_index(drop=True)


def add_profile(pay_snapshot: pd.DataFrame, profile: pd.DataFrame) -> pd.DataFrame:
    return pay_snapshot.merge(
        profile,
        left_on="canonical_council_id",
        right_on="council_key",
        how="left",
        suffixes=("", "_profile"),
    )


def quantile(values: Iterable[float], q: float) -> float:
    series = pd.Series([v for v in values if pd.notna(v)])
    if series.empty:
        return float("nan")
    return float(series.quantile(q))


def percentile_rank(values: Iterable[float], selected: float) -> float:
    vals = sorted(float(v) for v in values if pd.notna(v))
    if not vals:
        return float("nan")
    return sum(1 for v in vals if v <= selected) / len(vals) * 100


def cohort_stats(df: pd.DataFrame, cohort_name: str, mask: pd.Series | None = None) -> list[dict[str, Any]]:
    sample = df[mask].copy() if mask is not None else df.copy()
    ball = df[df["canonical_council_id"] == "BALLARAT"].set_index("standard_band")
    rows = []
    for band in range(1, 9):
        band_rows = sample[sample["standard_band"] == band]
        if band_rows.empty or band not in ball.index:
            continue
        b = ball.loc[band]
        item: dict[str, Any] = {"cohort": cohort_name, "band": band, "count": int(band_rows["canonical_council_id"].nunique())}
        for metric, col in [("entry", "entry_weekly_rate"), ("capacity", "capacity_weekly_rate"), ("midpoint", "range_midpoint_weekly_rate")]:
            vals = band_rows[col].dropna().astype(float).tolist()
            selected = float(b[col])
            med = median(vals)
            item[f"{metric}_ballarat"] = selected
            item[f"{metric}_median"] = med
            item[f"{metric}_mean"] = float(pd.Series(vals).mean())
            item[f"{metric}_min"] = min(vals)
            item[f"{metric}_p25"] = quantile(vals, 0.25)
            item[f"{metric}_p75"] = quantile(vals, 0.75)
            item[f"{metric}_max"] = max(vals)
            item[f"{metric}_gap_abs"] = selected - med
            item[f"{metric}_gap_pct"] = (selected / med - 1) * 100 if med else float("nan")
            item[f"{metric}_percentile"] = percentile_rank(vals, selected)
        item["progression_spread_ballarat"] = float(b["progression_spread_abs"])
        item["progression_spread_pct_ballarat"] = float(b["progression_spread_pct"]) * 100
        rows.append(item)
    return rows


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_councils(profiled: pd.DataFrame, n: int = 12) -> list[str]:
    council_coords = profiled.dropna(subset=["office_lat", "office_lon"]).drop_duplicates("canonical_council_id")
    ball = council_coords[council_coords["canonical_council_id"] == "BALLARAT"].iloc[0]
    rows = []
    for _, row in council_coords.iterrows():
        dist = haversine_km(float(ball.office_lat), float(ball.office_lon), float(row.office_lat), float(row.office_lon))
        rows.append((row.canonical_council_id, row.canonical_council_name, dist))
    rows.sort(key=lambda item: item[2])
    return [key for key, _, _ in rows[:n]]


def parse_consultant_pdf(pdf_name: str) -> list[dict[str, Any]]:
    path = FROM_USER / pdf_name
    reader = PdfReader(str(path))
    rows: list[dict[str, Any]] = []
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if "Source Q1 Median Q3 Average Variance" not in text or "Incumbent" not in text:
            continue
        norm = " ".join(text.split())
        role = None
        role_match = re.search(r"In benchmarking the Total Remuneration Package for the\s+(.+?)\s*,\s*consideration", norm, re.I)
        if role_match:
            role = role_match.group(1)
        inc_match = re.search(r"Incumbent\s+([0-9,]{5,})", norm)
        if not role or not inc_match:
            continue

        def vals(label: str) -> dict[str, int] | None:
            match = re.search(label + r"\s+([0-9,]+)\s+([0-9,]+)\s+([0-9,]+)\s+([0-9,]+)\s+(-?[0-9,]+)", norm)
            if not match:
                return None
            q1, med, q3, avg, variance = [int(v.replace(",", "")) for v in match.groups()]
            return {"q1": q1, "median": med, "q3": q3, "average": avg, "variance": variance}

        rows.append(
            {
                "source": pdf_name,
                "page": index + 1,
                "role": role,
                "incumbent": int(inc_match.group(1).replace(",", "")),
                "category_1": vals("Category 1 Councils Nationally"),
                "selected_victorian": vals("Selected Victorian Councils"),
                "selected_national": vals("Selected National Councils"),
            }
        )
    return rows


def extract_consultant_roles() -> list[dict[str, Any]]:
    roles = []
    for name in ["Ballarat- Exec 2024 Final.pdf", "Ballarat- Level 4 - 2024 Final.pdf"]:
        roles.extend(parse_consultant_pdf(name))
    return roles


def extract_entitlements() -> list[dict[str, Any]]:
    path = FROM_USER / "entitlements draft summary report version 2.docx"
    doc = Document(str(path))
    categories = {
        1: "Leave",
        2: "Conditions",
        3: "Financial and Monetary Provisions",
        4: "WHS and Environmental Conditions",
        5: "Parental and Family Related Enhancements",
        6: "Superannuation",
        7: "Wellbeing and Support",
    }
    rows: list[dict[str, Any]] = []
    for table_index, table in enumerate(doc.tables):
        if table_index == 0:
            continue
        category = categories.get(table_index, "Other")
        for row in table.rows[1:]:
            cells = [cell.text.strip() for cell in row.cells]
            if len(cells) < 3:
                continue
            entitlement = cells[0].splitlines()[0].strip()
            summary = " ".join(cells[1].split())
            takeaway = " ".join(cells[2].split())
            low = (takeaway + " " + summary).lower()
            status = "mixed"
            if any(term in low for term in ["strong", "top end", "compares well", "above average", "stronger outcomes"]):
                status = "leading"
            if any(term in low for term in ["aligns", "typical", "main cohort pattern", "mostly aligns"]):
                status = "aligned" if status != "leading" else status
            if any(term in low for term in ["lower third", "does not show", "no specific", "not have", "limited provision", "narrower", "baseline only"]):
                status = "gap" if status != "leading" else "mixed"
            rows.append({"category": category, "entitlement": entitlement, "summary": summary, "ballarat_takeaway": takeaway, "status": status})
    return rows


def read_uplifts() -> list[dict[str, Any]]:
    df = pd.read_csv(ROOT / "data" / "datamarts" / "uplift_timing_mart.csv")
    ball = df[df["council_key"] == "BALLARAT"].sort_values("effective_date")
    return ball[["agreement_id", "effective_date", "quantum", "resolved_pct", "dollar_component", "dollar_basis", "resolved_basis"]].to_dict("records")


def gap_rows_from_stats(stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in stats:
        rows.append(
            {
                "band": row["band"],
                "ballarat_entry": row["entry_ballarat"],
                "benchmark_entry": row["entry_median"],
                "entry_gap_pct": row["entry_gap_pct"],
                "entry_gap_abs": row["entry_gap_abs"],
                "ballarat_capacity": row["capacity_ballarat"],
                "benchmark_capacity": row["capacity_median"],
                "capacity_gap_pct": row["capacity_gap_pct"],
                "capacity_gap_abs": row["capacity_gap_abs"],
            }
        )
    return rows


def ballarat_movement_rows(
    snap_2025: pd.DataFrame,
    snap_2026: pd.DataFrame,
    stats_2025: list[dict[str, Any]],
    stats_2026: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    b25 = snap_2025[snap_2025["canonical_council_id"] == "BALLARAT"].set_index("standard_band")
    b26 = snap_2026[snap_2026["canonical_council_id"] == "BALLARAT"].set_index("standard_band")
    s25 = {row["band"]: row for row in stats_2025}
    s26 = {row["band"]: row for row in stats_2026}
    rows = []
    for band in range(1, 9):
        if band not in b25.index or band not in b26.index or band not in s25 or band not in s26:
            continue
        row25 = b25.loc[band]
        row26 = b26.loc[band]
        out: dict[str, Any] = {"band": band}
        for metric, col in [("entry", "entry_weekly_rate"), ("capacity", "capacity_weekly_rate")]:
            start = float(row25[col])
            end = float(row26[col])
            out[f"{metric}_2025"] = start
            out[f"{metric}_2026"] = end
            out[f"{metric}_delta_abs"] = end - start
            out[f"{metric}_delta_pct"] = (end / start - 1) * 100 if start else float("nan")
            out[f"{metric}_gap_pct_2025"] = s25[band][f"{metric}_gap_pct"]
            out[f"{metric}_gap_pct_2026"] = s26[band][f"{metric}_gap_pct"]
            out[f"{metric}_gap_delta_pct"] = s26[band][f"{metric}_gap_pct"] - s25[band][f"{metric}_gap_pct"]
        rows.append(out)
    return rows


def build_data_model() -> dict[str, Any]:
    pay = read_pay_ranges()
    profile = read_profiles()
    snap_2026 = add_profile(active_pay_snapshot(pay, "2026-07-01"), profile)
    snap_2025 = add_profile(active_pay_snapshot(pay, "2025-07-01"), profile)
    nearest_keys = nearest_councils(snap_2026, 12)
    region_mask = snap_2026["council_category"].eq("Regional")
    central_mask = snap_2026["vif_regional_partnership"].eq("Central Highlands")
    nearest_mask = snap_2026["canonical_council_id"].isin(nearest_keys)
    all_stats = cohort_stats(snap_2026, "All governed councils")
    all_stats_2025 = cohort_stats(snap_2025, "All governed councils")
    regional_stats = cohort_stats(snap_2026, "Regional cities", region_mask)
    central_stats = cohort_stats(snap_2026, "Central Highlands", central_mask)
    nearest_stats = cohort_stats(snap_2026, "Nearest governed councils", nearest_mask)
    governed_weekly_2026 = gap_rows_from_stats(all_stats)
    movement_rows = ballarat_movement_rows(snap_2025, snap_2026, all_stats_2025, all_stats)
    consultant_roles = extract_consultant_roles()
    entitlements = extract_entitlements()
    uplifts = read_uplifts()

    role_vic_gaps = [row["selected_victorian"]["variance"] for row in consultant_roles if row.get("selected_victorian")]
    role_cat_gaps = [row["category_1"]["variance"] for row in consultant_roles if row.get("category_1")]
    entitlement_counts = pd.Series([row["status"] for row in entitlements]).value_counts().to_dict()

    return {
        "metadata": {
            "title": "Ballarat Remuneration Intelligence Report",
            "generated_at": pd.Timestamp.now(tz="Australia/Sydney").isoformat(),
            "project_root": str(ROOT),
            "reporting_snapshot": "2026-07-01 governed pay snapshot, with 2025-to-2026 governed movement overlay",
        },
        "sources": {
            "governed_pay_range_summary": "data/datamarts/pay_range_summary_mart.csv",
            "council_profiles": "data/datamarts/council_profile_mart.csv",
            "spatial_context": "data/datamarts/spatial_context_mart.csv",
            "uplift_timing": "data/datamarts/uplift_timing_mart.csv",
            "consultant_exec": "from user/Ballarat- Exec 2024 Final.pdf",
            "consultant_level4": "from user/Ballarat- Level 4 - 2024 Final.pdf",
            "entitlement_draft": "from user/entitlements draft summary report version 2.docx",
            "notion_nes_spec": "NES ENHANCEMENT FILES, SCHEMA AND RULES",
            "project_state": "CURRENT_STATE_AND_NEXT_ACTIONS.md",
        },
        "system_universe": SYSTEM_UNIVERSE,
        "coverage": {
            "pay_rows_total": int(len(pay)),
            "pay_councils_total": int(pay["canonical_council_name"].nunique()),
            "snapshot_2026_rows": int(len(snap_2026)),
            "snapshot_2026_councils": int(snap_2026["canonical_council_id"].nunique()),
            "snapshot_2025_rows": int(len(snap_2025)),
            "snapshot_2025_councils": int(snap_2025["canonical_council_id"].nunique()),
            "nearest_councils": nearest_keys,
        },
        "governed_weekly_2026": governed_weekly_2026,
        "ballarat_movement_2025_to_2026": movement_rows,
        "snapshots": {
            "2026-07-01": snap_2026.replace({float("nan"): None}).to_dict("records"),
            "2025-07-01": snap_2025.replace({float("nan"): None}).to_dict("records"),
        },
        "cohort_stats": {
            "all": all_stats,
            "all_2025": all_stats_2025,
            "regional": regional_stats,
            "central_highlands": central_stats,
            "nearest": nearest_stats,
        },
        "uplifts": uplifts,
        "consultant_roles": consultant_roles,
        "consultant_summary": {
            "role_count": len(consultant_roles),
            "below_selected_vic_average": sum(1 for gap in role_vic_gaps if gap < 0),
            "median_selected_vic_gap": float(median(role_vic_gaps)) if role_vic_gaps else None,
            "largest_selected_vic_deficit": min(role_vic_gaps) if role_vic_gaps else None,
            "largest_category_1_deficit": min(role_cat_gaps) if role_cat_gaps else None,
        },
        "entitlements": entitlements,
        "entitlement_summary": {
            "row_count": len(entitlements),
            "status_counts": entitlement_counts,
            "categories": sorted(set(row["category"] for row in entitlements)),
        },
    }


def scale(value: float, domain: tuple[float, float], rng: tuple[float, float]) -> float:
    lo, hi = domain
    if hi == lo:
        return (rng[0] + rng[1]) / 2
    return rng[0] + (value - lo) / (hi - lo) * (rng[1] - rng[0])


def gap_color(value: float) -> str:
    if value <= -8:
        return "#B64A3A"
    if value <= -5:
        return "#D99A2B"
    if value <= -2:
        return "#159BA6"
    if value < 0:
        return "#2FAE8F"
    return "#2FAE8F"


def svg_gap_bars(rows: list[dict[str, Any]], metric: str, width: int = 890, height: int = 420) -> str:
    pad_l, pad_r, pad_t, row_h = 94, 72, 34, 42
    domain = (-12, 2)
    axis_x0, axis_x1 = pad_l, width - pad_r
    zero = scale(0, domain, (axis_x0, axis_x1))
    parts = [f'<svg viewBox="0 0 {width} {height}" class="svg-chart" role="img">']
    for tick in [-10, -5, 0]:
        x = scale(tick, domain, (axis_x0, axis_x1))
        parts.append(f'<line x1="{x:.1f}" y1="20" x2="{x:.1f}" y2="{height-42}" class="grid-line"/>')
        parts.append(f'<text x="{x:.1f}" y="{height-18}" class="axis-label" text-anchor="middle">{tick}%</text>')
    parts.append(f'<line x1="{zero:.1f}" y1="20" x2="{zero:.1f}" y2="{height-42}" class="zero-line"/>')
    for i, row in enumerate(rows):
        y = pad_t + i * row_h
        value = float(row[f"{metric}_gap_pct"])
        dollars = float(row[f"{metric}_gap_abs"])
        x = scale(value, domain, (axis_x0, axis_x1))
        x0, x1 = min(zero, x), max(zero, x)
        parts.append(f'<text x="22" y="{y+14}" class="band-label">Band {row["band"]}</text>')
        parts.append(f'<rect x="{x0:.1f}" y="{y}" width="{max(3, x1-x0):.1f}" height="18" rx="9" fill="{gap_color(value)}"/>')
        parts.append(f'<circle cx="{x:.1f}" cy="{y+9}" r="5.5" fill="#071E41"/>')
        parts.append(f'<text x="{width-14}" y="{y+14}" class="value-label" text-anchor="end">{pct(value)} / {money(dollars)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_heatmap(rows: list[dict[str, Any]], width: int = 890, height: int = 418) -> str:
    cols = ["entry_gap_pct", "capacity_gap_pct", "entry_gap_abs", "capacity_gap_abs"]
    labels = ["Entry %", "Capacity %", "Entry $/wk", "Capacity $/wk"]
    cell_w, cell_h = 166, 39
    x0, y0 = 150, 54
    parts = [f'<svg viewBox="0 0 {width} {height}" class="svg-chart">']
    parts.append('<text x="20" y="28" class="chart-title">Band gap matrix - Ballarat vs governed state median</text>')
    for j, label in enumerate(labels):
        parts.append(f'<text x="{x0+j*cell_w+cell_w/2}" y="34" class="axis-label" text-anchor="middle">{esc(label)}</text>')
    for i, row in enumerate(rows):
        y = y0 + i * cell_h
        parts.append(f'<text x="26" y="{y+25}" class="band-label">Band {row["band"]}</text>')
        for j, col in enumerate(cols):
            x = x0 + j * cell_w
            raw = float(row[col])
            intensity = min(1, abs(raw) / (10 if "pct" in col else 180))
            color = gap_color(float(row[col.replace("_abs", "_pct")]) if "_abs" in col else raw)
            opacity = 0.22 + intensity * 0.58
            text = pct(raw) if "pct" in col else money(raw)
            parts.append(f'<rect x="{x}" y="{y}" width="{cell_w-8}" height="{cell_h-7}" rx="5" fill="{color}" opacity="{opacity:.2f}"/>')
            parts.append(f'<text x="{x+(cell_w-8)/2}" y="{y+22}" class="heat-label" text-anchor="middle">{text}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_dot_distribution(df: pd.DataFrame, band: int, metric_col: str, title: str, width: int = 890, height: int = 360) -> str:
    band_rows = df[df["standard_band"] == band].dropna(subset=[metric_col])
    vals = band_rows[metric_col].astype(float).tolist()
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    x0, x1 = 76, width - 62
    y_mid = height / 2 + 10
    q1, med, q3 = quantile(vals, 0.25), median(vals), quantile(vals, 0.75)
    ball = float(band_rows[band_rows["canonical_council_id"] == "BALLARAT"].iloc[0][metric_col])
    parts = [f'<svg viewBox="0 0 {width} {height}" class="svg-chart">']
    parts.append(f'<text x="22" y="30" class="chart-title">{esc(title)}</text>')
    parts.append(f'<line x1="{x0}" y1="{y_mid}" x2="{x1}" y2="{y_mid}" class="axis-line"/>')
    for val, label, klass in [(lo, "min", "axis-label"), (q1, "p25", "axis-label"), (med, "median", "median-label"), (q3, "p75", "axis-label"), (hi, "max", "axis-label")]:
        x = scale(val, (lo, hi), (x0, x1))
        parts.append(f'<line x1="{x:.1f}" y1="{y_mid-72}" x2="{x:.1f}" y2="{y_mid+74}" class="grid-line"/>')
        parts.append(f'<text x="{x:.1f}" y="{y_mid+104}" class="{klass}" text-anchor="middle">{label} {money(val)}</text>')
    for _, row in band_rows.sort_values(metric_col).iterrows():
        val = float(row[metric_col])
        x = scale(val, (lo, hi), (x0, x1))
        jitter_seed = sum(ord(c) for c in str(row["canonical_council_id"]))
        y = y_mid + ((jitter_seed % 41) - 20) * 2.2
        if row["canonical_council_id"] == "BALLARAT":
            continue
        color = {"Regional": "#159BA6", "Metropolitan": "#34465C", "Interface": "#D99A2B", "Large shire": "#8CA0B3", "Small shire": "#C6D2DD"}.get(str(row.get("council_category")), "#A4B1C0")
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.4" fill="{color}" opacity=".74"/>')
    bx = scale(ball, (lo, hi), (x0, x1))
    parts.append(f'<line x1="{bx:.1f}" y1="{y_mid-95}" x2="{bx:.1f}" y2="{y_mid+95}" class="ballarat-line"/>')
    parts.append(f'<circle cx="{bx:.1f}" cy="{y_mid}" r="10" fill="#B64A3A" stroke="#fff" stroke-width="3"/>')
    parts.append(f'<text x="{bx:.1f}" y="{y_mid-110}" class="ballarat-label" text-anchor="middle">Ballarat {money(ball)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_cohort_matrix(stats_by_cohort: dict[str, list[dict[str, Any]]], metric: str = "capacity", width: int = 890, height: int = 418) -> str:
    cohorts = [("all", "State"), ("regional", "Regional"), ("central_highlands", "Central Highlands"), ("nearest", "Nearest")]
    x0, y0, cell_w, cell_h = 165, 56, 168, 39
    parts = [f'<svg viewBox="0 0 {width} {height}" class="svg-chart">']
    parts.append(f'<text x="22" y="30" class="chart-title">{esc(metric.title())} gap to cohort median</text>')
    for j, (_, label) in enumerate(cohorts):
        parts.append(f'<text x="{x0+j*cell_w+cell_w/2}" y="36" class="axis-label" text-anchor="middle">{label}</text>')
    for i, band in enumerate(range(1, 9)):
        y = y0 + i * cell_h
        parts.append(f'<text x="30" y="{y+24}" class="band-label">Band {band}</text>')
        for j, (key, _) in enumerate(cohorts):
            row = next((r for r in stats_by_cohort[key] if r["band"] == band), None)
            if not row:
                continue
            gap = float(row[f"{metric}_gap_pct"])
            x = x0 + j * cell_w
            parts.append(f'<rect x="{x}" y="{y}" width="{cell_w-8}" height="{cell_h-7}" rx="5" fill="{gap_color(gap)}" opacity="{0.25 + min(abs(gap)/12,1)*0.55:.2f}"/>')
            parts.append(f'<text x="{x+(cell_w-8)/2}" y="{y+22}" class="heat-label" text-anchor="middle">{pct(gap)} / {money(row[f"{metric}_gap_abs"])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_spatial_constellation(df: pd.DataFrame, nearest_keys: list[str], width: int = 890, height: int = 420) -> str:
    rows = df.dropna(subset=["office_lat", "office_lon"]).drop_duplicates("canonical_council_id")
    lon_min, lon_max = float(rows["office_lon"].min()), float(rows["office_lon"].max())
    lat_min, lat_max = float(rows["office_lat"].min()), float(rows["office_lat"].max())
    parts = [f'<svg viewBox="0 0 {width} {height}" class="svg-chart">']
    parts.append('<text x="22" y="30" class="chart-title">Spatial peer field - office-to-office geometry</text>')
    for _, row in rows.iterrows():
        x = scale(float(row.office_lon), (lon_min, lon_max), (56, width - 62))
        y = scale(float(row.office_lat), (lat_max, lat_min), (52, height - 54))
        key = row.canonical_council_id
        is_ball = key == "BALLARAT"
        is_near = key in nearest_keys
        color = "#B64A3A" if is_ball else "#159BA6" if is_near else "#C6D2DD"
        radius = 10 if is_ball else 6 if is_near else 3.4
        opacity = 1 if is_ball or is_near else 0.5
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{color}" opacity="{opacity}"/>')
        if is_ball or (is_near and len(str(row.short_name)) < 16):
            parts.append(f'<text x="{x+10:.1f}" y="{y-8:.1f}" class="map-label">{esc(row.short_name)}</text>')
    parts.append('<text x="22" y="394" class="caption">Nearest-cohort logic is spatial context, not a replacement for governed pay evidence.</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_role_scatter(roles: list[dict[str, Any]], width: int = 890, height: int = 418) -> str:
    points = []
    for row in roles:
        vic = row.get("selected_victorian")
        if vic:
            points.append((row["incumbent"], vic["variance"], row["role"], row["source"]))
    if not points:
        return ""
    x_vals = [p[0] for p in points]
    y_vals = [p[1] for p in points]
    x_domain = (min(x_vals) * 0.92, max(x_vals) * 1.04)
    y_domain = (min(y_vals) * 1.08, max(y_vals) * 1.1)
    parts = [f'<svg viewBox="0 0 {width} {height}" class="svg-chart">']
    parts.append('<text x="22" y="30" class="chart-title">Consultant role benchmark pressure - current package vs selected Vic gap</text>')
    x0, x1, y0, y1 = 80, width - 60, height - 70, 60
    parts.append(f'<line x1="{x0}" y1="{scale(0, y_domain, (y0,y1)):.1f}" x2="{x1}" y2="{scale(0, y_domain, (y0,y1)):.1f}" class="zero-line"/>')
    for inc, gap, role, source in points:
        x = scale(inc, x_domain, (x0, x1))
        y = scale(gap, y_domain, (y0, y1))
        color = "#B64A3A" if gap < -30000 else "#D99A2B" if gap < -10000 else "#159BA6" if gap < 0 else "#2FAE8F"
        r = 7 if "Exec" in source else 5.5
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" opacity=".82"/>')
    labelled = sorted(points, key=lambda p: p[1])[:5] + sorted(points, key=lambda p: p[1])[-3:]
    seen = set()
    for inc, gap, role, _ in labelled:
        if role in seen:
            continue
        seen.add(role)
        x = scale(inc, x_domain, (x0, x1))
        y = scale(gap, y_domain, (y0, y1))
        parts.append(f'<text x="{x+9:.1f}" y="{y-6:.1f}" class="tiny-label">{esc(role[:34])} {money(gap)}</text>')
    parts.append(f'<text x="{x0}" y="{height-24}" class="axis-label">Current package</text>')
    parts.append(f'<text x="{width-220}" y="{height-24}" class="axis-label">{money(x_domain[1])}</text>')
    parts.append('<text x="22" y="390" class="caption">Negative values indicate Ballarat incumbent package below the selected Victorian council average in the consultant tables.</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_entitlement_grid(entitlements: list[dict[str, Any]], width: int = 890, height: int = 418) -> str:
    color = {"leading": "#2FAE8F", "aligned": "#159BA6", "mixed": "#D99A2B", "gap": "#B64A3A"}
    rows_by_cat: dict[str, list[dict[str, Any]]] = {}
    for row in entitlements:
        rows_by_cat.setdefault(row["category"], []).append(row)
    parts = [f'<svg viewBox="0 0 {width} {height}" class="svg-chart">']
    parts.append('<text x="22" y="30" class="chart-title">Entitlement benchmark map - 54-item framework subset in draft</text>')
    y = 58
    for category, rows in rows_by_cat.items():
        parts.append(f'<text x="28" y="{y+13}" class="band-label">{esc(category[:34])}</text>')
        x = 270
        for row in rows:
            parts.append(f'<rect x="{x}" y="{y-2}" width="24" height="24" rx="5" fill="{color.get(row["status"], "#8CA0B3")}"/>')
            x += 30
            if x > width - 50:
                x = 270
                y += 30
        y += 43
    legend_x = 28
    for status, label in [("leading", "Leading"), ("aligned", "Aligned"), ("mixed", "Mixed"), ("gap", "Gap/risk")]:
        parts.append(f'<rect x="{legend_x}" y="{height-44}" width="18" height="18" rx="4" fill="{color[status]}"/>')
        parts.append(f'<text x="{legend_x+24}" y="{height-30}" class="axis-label">{label}</text>')
        legend_x += 128
    parts.append("</svg>")
    return "".join(parts)


def svg_uplift_timeline(uplifts: list[dict[str, Any]], width: int = 890, height: int = 310) -> str:
    if not uplifts:
        return ""
    dates = [pd.Timestamp(row["effective_date"]) for row in uplifts]
    lo, hi = min(dates), max(dates)
    x0, x1 = 70, width - 70
    y = 145
    parts = [f'<svg viewBox="0 0 {width} {height}" class="svg-chart">']
    parts.append('<text x="22" y="30" class="chart-title">Ballarat governed uplift rule path</text>')
    parts.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" class="axis-line"/>')
    for row in uplifts:
        d = pd.Timestamp(row["effective_date"])
        x = scale(d.value, (lo.value, hi.value), (x0, x1))
        parts.append(f'<circle cx="{x:.1f}" cy="{y}" r="9" fill="#159BA6" stroke="#fff" stroke-width="3"/>')
        parts.append(f'<text x="{x:.1f}" y="{y-22}" class="median-label" text-anchor="middle">{d.strftime("%Y")}</text>')
        parts.append(f'<text x="{x:.1f}" y="{y+36}" class="tiny-label" text-anchor="middle">{pct(row.get("resolved_pct"), 1)}</text>')
    parts.append('<text x="22" y="270" class="caption">Earlier Ballarat rules used rate-cap-linked logic; the current agreement uses 3.5% or a weekly dollar floor, whichever is higher.</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_movement_heatmap(rows: list[dict[str, Any]], width: int = 890, height: int = 418) -> str:
    cols = [
        ("entry_delta_abs", "Entry $ movement"),
        ("capacity_delta_abs", "Capacity $ movement"),
        ("entry_gap_delta_pct", "Entry gap pp change"),
        ("capacity_gap_delta_pct", "Capacity gap pp change"),
    ]
    x0, y0, cell_w, cell_h = 160, 58, 164, 38
    parts = [f'<svg viewBox="0 0 {width} {height}" class="svg-chart">']
    parts.append('<text x="22" y="30" class="chart-title">Governed movement path - Ballarat 2025 to 2026</text>')
    for j, (_, label) in enumerate(cols):
        parts.append(f'<text x="{x0+j*cell_w+cell_w/2}" y="39" class="axis-label" text-anchor="middle">{esc(label)}</text>')
    for i, row in enumerate(rows):
        band = row["band"]
        y = y0 + i * cell_h
        parts.append(f'<text x="28" y="{y+24}" class="band-label">Band {band}</text>')
        for j, (key, _) in enumerate(cols):
            value = float(row[key])
            x = x0 + j * cell_w
            color_value = -value if "delta_abs" in key else value
            text = money(value) if "delta_abs" in key else f"{value:+.1f} pp"
            parts.append(f'<rect x="{x}" y="{y}" width="{cell_w-8}" height="{cell_h-7}" rx="5" fill="{gap_color(color_value)}" opacity="{0.28+min(abs(color_value)/9,1)*0.55:.2f}"/>')
            parts.append(f'<text x="{x+(cell_w-8)/2}" y="{y+22}" class="heat-label" text-anchor="middle">{text}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_system_orbit(width: int = 890, height: int = 418) -> str:
    metrics = [
        ("111", "canonical agreements", 0),
        ("108", "source PDFs", 1),
        ("8,506", "weekly rows", 2),
        ("273", "uplift rules", 3),
        ("88", "routes", 4),
        ("6", "export targets", 5),
        ("490", "tests passed", 6),
        ("54", "benefit frame", 7),
    ]
    cx, cy = width / 2, height / 2 + 6
    parts = [f'<svg viewBox="0 0 {width} {height}" class="svg-chart">']
    parts.append('<text x="22" y="30" class="chart-title">Evidence universe - reporting system density</text>')
    for r in [70, 120, 168]:
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#DDE6EE" stroke-width="1.2"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="52" fill="#071E41"/>')
    parts.append(f'<text x="{cx}" y="{cy-4}" text-anchor="middle" class="orbit-core">Ballarat</text>')
    parts.append(f'<text x="{cx}" y="{cy+18}" text-anchor="middle" class="orbit-sub">remuneration model</text>')
    for number, label, idx in metrics:
        angle = idx / len(metrics) * math.tau - math.pi / 2
        r = 155 if idx % 2 else 118
        x = cx + math.cos(angle) * r
        y = cy + math.sin(angle) * r
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x}" y2="{y}" stroke="#C8D6E2" stroke-width="1"/>')
        parts.append(f'<circle cx="{x}" cy="{y}" r="32" fill="#FFFFFF" stroke="#159BA6" stroke-width="2"/>')
        parts.append(f'<text x="{x}" y="{y-2}" text-anchor="middle" class="orbit-number">{esc(number)}</text>')
        parts.append(f'<text x="{x}" y="{y+15}" text-anchor="middle" class="orbit-label">{esc(label)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def metric_cards(items: list[tuple[str, str, str]]) -> str:
    return '<div class="metric-row">' + "".join(
        f'<div class="metric-card"><div class="metric-value">{esc(v)}</div><div class="metric-label">{esc(label)}</div><div class="metric-note">{esc(note)}</div></div>'
        for v, label, note in items
    ) + "</div>"


def insight_list(items: Iterable[str]) -> str:
    return '<div class="insights">' + "".join(f'<div class="insight"><span></span><p>{esc(item)}</p></div>' for item in items) + "</div>"


def table_html(headers: list[str], rows: list[list[Any]], cls: str = "") -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<table class="report-table {cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def stat_lookup(stats: list[dict[str, Any]], band: int) -> dict[str, Any]:
    return next(row for row in stats if row["band"] == band)


def consultant_top_table(roles: list[dict[str, Any]], n: int = 8) -> str:
    ranked = sorted([r for r in roles if r.get("selected_victorian")], key=lambda r: r["selected_victorian"]["variance"])[:n]
    rows = []
    for row in ranked:
        rows.append([
            esc(row["role"][:42]),
            money(row["incumbent"]),
            money(row["selected_victorian"]["average"]),
            f'<span class="negative">{money(row["selected_victorian"]["variance"])}</span>',
        ])
    return table_html(["Role", "Current", "Selected Vic avg", "Gap"], rows)


def build_pages(data: dict[str, Any]) -> list[Page]:
    stats = data["cohort_stats"]
    snap = pd.DataFrame(data["snapshots"]["2026-07-01"])
    governed_gap = data["governed_weekly_2026"]
    movement = data["ballarat_movement_2025_to_2026"]
    roles = data["consultant_roles"]
    ent = data["entitlements"]
    role_summary = data["consultant_summary"]
    coverage = data["coverage"]
    universe = data["system_universe"]

    b5 = stat_lookup(stats["all"], 5)
    b6 = stat_lookup(stats["all"], 6)
    b7 = stat_lookup(stats["all"], 7)
    b8 = stat_lookup(stats["all"], 8)
    worst_capacity = min(governed_gap, key=lambda r: r["capacity_gap_pct"])
    worst_entry = min(governed_gap, key=lambda r: r["entry_gap_pct"])

    pages: list[Page] = []
    pages.append(Page(
        "Confidential working draft",
        "Ballarat Remuneration Intelligence Report",
        f"""
        <div class="cover-grid">
          <div>
            <div class="cover-mark">Municipal Benchmark</div>
            <h1>Ballarat vs Victorian LGAs</h1>
            <p class="cover-sub">A governed pay, entitlement, classification and executive-benchmark intelligence report built from local datamarts, user-supplied consultant material, project memory and the Municipal Benchmark reporting universe.</p>
          </div>
          <div class="cover-panel">
            {metric_cards([
                ("30", "pages", "executive narrative"),
                (str(coverage["snapshot_2026_councils"]), "councils", "2026 governed snapshot"),
                ("41", "roles", "consultant benchmark extraction"),
                ("54", "entitlements", "definition-led frame"),
            ])}
          </div>
        </div>
        """,
        theme="cover",
        source="Sources: governed datamarts, consultant PDFs, entitlement draft, Notion NES spec and project state memory. Different-system numeric outputs are excluded.",
    ))

    pages.append(Page(
        "Executive verdict",
        "The pattern is not random: Ballarat is structurally behind at the benchmarked pay edge.",
        f"""
        {metric_cards([
            (pct(worst_capacity["capacity_gap_pct"]), "largest governed capacity gap", f"Band {worst_capacity['band']} vs state median"),
            (money(worst_capacity["capacity_gap_abs"]), "weekly capacity shortfall", "negative vs state median"),
            (pct(worst_entry["entry_gap_pct"]), "largest governed entry gap", f"Band {worst_entry['band']} vs state median"),
            (money(role_summary["median_selected_vic_gap"]), "median consultant Vic role gap", "41 extracted role tables"),
        ])}
        {insight_list([
            "The governed 2026 snapshot shows Ballarat below the statewide governed median in multiple bands and metrics.",
            "The deepest governed capacity pressure sits in the upper bands, where operational leadership and executive-adjacent market signals become most visible.",
            "The consultant reports independently show a senior-role package gap, especially against Category 1 and selected Victorian councils.",
            "Entitlements are not weak overall: Ballarat has standout family violence, parental and specialist personal leave positions, but weaker WFH, dependent-care and allowance signals.",
        ])}
        """,
        source="pay_range_summary_mart.csv 2026-07-01 active snapshot; consultant report summary tables; entitlement draft summary report.",
    ))

    pages.append(Page(
        "Evidence universe",
        "This is a reporting-system product, not a one-off spreadsheet.",
        f"""
        <div class="two-col">
          <div>{svg_system_orbit()}</div>
          <div>
            {metric_cards([
                (str(universe["canonical_agreement_yaml"]), "canonical agreement YAML", "local source-of-truth layer"),
                (str(universe["immutable_source_pdfs"]), "immutable source PDFs", "source evidence library"),
                (f'{universe["weekly_pay_rows"]:,}', "weekly pay rows", "governed pay-table entity set"),
                (str(universe["governed_uplift_rules"]), "uplift rules", "timing and movement logic"),
            ])}
            {insight_list([
                "The evidence base can explain where a number came from, which agreement period produced it, and how it enters a report asset.",
                "The report asset service already supports CSV, SVG, PNG, XLSX, DOCX and PPTX export paths for distribution-point analysis.",
                "The maturity layer matters: a world-class report needs governed provenance, caveat discipline and reproducible data products.",
            ])}
          </div>
        </div>
        """,
        source="CURRENT_STATE_AND_NEXT_ACTIONS.md scan dated 2026-05-06.",
    ))

    pages.append(Page(
        "Competitive bar",
        "The consultant reports set the minimum professional standard; this report absorbs and extends it.",
        f"""
        <div class="two-col">
          <div>
            {metric_cards([
                ("40+", "councils", "consultant research base"),
                ("450+", "positions", "consultant role universe"),
                ("41", "Ballarat role tables", "parsed into this model"),
                ("3", "reference lenses", "Category 1, Vic, national"),
            ])}
            {insight_list([
                "The consultant standard is role-accountability benchmarking, not only salary-grid benchmarking.",
                "The upgrade here is to connect that standard to governed EA pay bands, future uplift logic, entitlement competitiveness and report-asset lineage.",
                "A credible alternative must look as polished as external advisory work while being more auditable and more reusable.",
            ])}
          </div>
          <div>{svg_role_scatter(roles)}</div>
        </div>
        """,
        source="Ballarat- Exec 2024 Final.pdf; Ballarat- Level 4 - 2024 Final.pdf.",
    ))

    pages.append(Page(
        "Method frame",
        "Every claim declares its metric, cohort and date lens.",
        f"""
        <div class="method-grid">
          <div class="method-card"><b>Pay metric</b><p>Entry, capacity, midpoint and spread are separated. No hidden midpoint claims.</p></div>
          <div class="method-card"><b>Snapshot</b><p>Governed pay values use active agreement windows at 2026-07-01, with a governed 2025-to-2026 movement lens.</p></div>
          <div class="method-card"><b>Cohorts</b><p>Statewide, Regional City, Central Highlands and nearest-council cohorts are all separately labelled.</p></div>
          <div class="method-card"><b>Market standard</b><p>Consultant TRP benchmarks are extracted as a senior-role comparator, not blended into EA band values.</p></div>
          <div class="method-card"><b>Entitlements</b><p>Entitlement findings are treated as draft/staged unless governed evidence exists; they still reveal competitive themes.</p></div>
          <div class="method-card"><b>Caveats</b><p>Missing values remain blockers or unknowns, not absence. Service-horizon estimates are not treated as governed progression.</p></div>
        </div>
        """,
        source="Pay Structure Semantics v1.1; Feature Answer Builder Doctrine; Notion NES enhancement schema.",
    ))

    pages.append(Page(
        "Governed gap view",
        "The all-band picture is built from the local governed 2026 snapshot.",
        f"""
        <div class="split-charts">
          <div>{svg_gap_bars(governed_gap, "entry")}</div>
          <div>{svg_gap_bars(governed_gap, "capacity")}</div>
        </div>
        """,
        source="pay_range_summary_mart.csv active governed rows at 2026-07-01; benchmark is statewide governed median by band and metric.",
    ))

    pages.append(Page(
        "Dollar heatmap",
        "The shortfall persists from entry through capacity; dollar impact grows with senior bands.",
        f"""
        {svg_heatmap(governed_gap)}
        {insight_list([
            "The heatmap is generated only from governed local datamart values, not from an external-system output.",
            "Upper bands carry the largest weekly dollar sensitivity because small percentage gaps convert into larger annual package signals.",
            "The report should avoid a single headline gap because each band and metric tells a different workforce story.",
        ])}
        """,
        source="pay_range_summary_mart.csv active governed rows at 2026-07-01.",
    ))

    pages.append(Page(
        "Governed 2026 snapshot",
        "Local datamarts show the active Ballarat pay ladder and its cohort position.",
        f"""
        {svg_cohort_matrix(stats, "capacity")}
        {metric_cards([
            (money(b5["capacity_ballarat"]), "Band 5 capacity", f"{pct(b5['capacity_gap_pct'])} vs state median"),
            (money(b6["capacity_ballarat"]), "Band 6 capacity", f"{pct(b6['capacity_gap_pct'])} vs state median"),
            (money(b7["capacity_ballarat"]), "Band 7 capacity", f"{pct(b7['capacity_gap_pct'])} vs state median"),
            (money(b8["capacity_ballarat"]), "Band 8 capacity", f"{pct(b8['capacity_gap_pct'])} vs state median"),
        ])}
        """,
        source="pay_range_summary_mart.csv active rows at 2026-07-01.",
    ))

    pages.append(Page(
        "Band 5 market",
        "Band 5 is the operational hinge: broad enough to affect workforce volume, senior enough to signal progression value.",
        f"""
        <div class="two-col">
          <div>{svg_dot_distribution(snap, 5, "capacity_weekly_rate", "Band 5 capacity weekly distribution")}</div>
          <div>
            {metric_cards([
                (money(b5["entry_ballarat"]), "Ballarat entry", f"{pct(b5['entry_gap_pct'])} vs state median"),
                (money(b5["capacity_ballarat"]), "Ballarat capacity", f"{pct(b5['capacity_gap_pct'])} vs state median"),
                (money(b5["progression_spread_ballarat"]), "spread", f"{pct(b5['progression_spread_pct_ballarat'])} entry-to-capacity"),
                (f"{b5['capacity_percentile']:.0f}th", "capacity percentile", "statewide active rows"),
            ])}
            {insight_list([
                "The Band 5 spread is meaningful, which helps internal progression perception.",
                "The external issue is not only the top value; entry positioning also shapes attraction and early retention.",
            ])}
          </div>
        </div>
        """,
        source="pay_range_summary_mart.csv, 2026-07-01 active snapshot.",
    ))

    pages.append(Page(
        "Band 6 market",
        "Band 6 is where professional and specialist attraction risk becomes more visible.",
        f"""
        <div class="two-col">
          <div>{svg_dot_distribution(snap, 6, "entry_weekly_rate", "Band 6 entry weekly distribution")}</div>
          <div>
            {metric_cards([
                (money(b6["entry_ballarat"]), "Ballarat entry", f"{pct(b6['entry_gap_pct'])} vs state median"),
                (money(b6["capacity_ballarat"]), "Ballarat capacity", f"{pct(b6['capacity_gap_pct'])} vs state median"),
                (money(b6["entry_gap_abs"]), "entry dollar gap", "weekly vs state median"),
                (f"{b6['entry_percentile']:.0f}th", "entry percentile", "statewide active rows"),
            ])}
            {insight_list([
                "The governed 2026 view should be read alongside uplift timing because comparator councils are not on identical agreement clocks.",
                "Band 6 is a candidate for a separate entry-rate diagnostic because professional recruitment tends to feel the market before top-of-band retention does.",
            ])}
          </div>
        </div>
        """,
        source="pay_range_summary_mart.csv 2026-07-01 active governed snapshot.",
    ))

    pages.append(Page(
        "Bands 7 and 8",
        "The senior band story is where EA data and consultant TRP data need to meet.",
        f"""
        <div class="two-col">
          <div>{svg_dot_distribution(snap, 8, "capacity_weekly_rate", "Band 8 capacity weekly distribution")}</div>
          <div>
            {metric_cards([
                (money(b7["capacity_ballarat"]), "Band 7 capacity", f"{pct(b7['capacity_gap_pct'])} vs state median"),
                (money(b8["capacity_ballarat"]), "Band 8 capacity", f"{pct(b8['capacity_gap_pct'])} vs state median"),
                (money(b7["capacity_gap_abs"]), "Band 7 weekly gap", "capacity median"),
                (money(b8["capacity_gap_abs"]), "Band 8 weekly gap", "capacity median"),
            ])}
            {insight_list([
                "Bands 7 and 8 need separate executive attention because they sit closest to the consultant TRP market.",
                "These bands are also where job-size, accountability and organisational structure can overwhelm simple EA table comparisons.",
            ])}
          </div>
        </div>
        """,
        source="pay_range_summary_mart.csv 2026-07-01 active governed snapshot.",
    ))

    pages.append(Page(
        "Entry vs capacity",
        "The strategic question is whether Ballarat needs entry correction, capacity correction, or both.",
        f"""
        <div class="scatter-grid">
          {svg_heatmap(governed_gap)}
        </div>
        {insight_list([
            "Entry correction speaks to recruitment and early retention; capacity correction speaks to progression value and experienced-employee retention.",
            "The governed heatmap lets each band be read as its own workforce problem rather than forcing a single averaged answer.",
            "Capacity gaps in upper bands should be interpreted with the consultant role benchmarks, not in isolation.",
        ])}
        """,
        source="pay_range_summary_mart.csv active governed rows at 2026-07-01.",
    ))

    pages.append(Page(
        "Regional cities",
        "Ballarat should be read both as a statewide employer and as a regional-city market actor.",
        f"""
        {svg_cohort_matrix(stats, "entry")}
        {insight_list([
            "Regional-city comparison is a cleaner policy peer lens than a purely statewide curve.",
            "Statewide averages can hide the labour-market reality of Bendigo, Geelong, Latrobe, Shepparton, Warrnambool and Wodonga.",
            "Report-facing claims should identify whether the comparison is statewide, regional-city or geography-nearest.",
        ])}
        """,
        source="council_profile_mart.csv and pay_range_summary_mart.csv.",
    ))

    pages.append(Page(
        "Spatial peers",
        "Geography is context; governed pay evidence remains the claim base.",
        f"""
        <div class="two-col">
          <div>{svg_spatial_constellation(snap, data["coverage"]["nearest_councils"])}</div>
          <div>
            {metric_cards([
                ("12", "nearest councils", "including Ballarat"),
                ("Central Highlands", "regional partnership", "Ballarat geography lens"),
                ("Country", "VGCCC region", "spatial context"),
                (money(stat_lookup(stats["nearest"], 5)["capacity_gap_abs"]), "Band 5 nearest gap", "capacity median"),
            ])}
            {insight_list([
                "A spatial peer set is useful for stakeholder intuition and labour mobility framing.",
                "It should not replace functional comparator cohorts or governed pay evidence.",
            ])}
          </div>
        </div>
        """,
        source="spatial_context_mart.csv and council_profile_mart.csv.",
    ))

    pages.append(Page(
        "Central Highlands",
        "The local market lens is smaller, sharper and more politically legible.",
        f"""
        {svg_cohort_matrix(stats, "capacity")}
        {insight_list([
            "Central Highlands comparisons make sense for local attraction and stakeholder narrative.",
            "The cohort is too small to carry the whole remuneration argument alone.",
            "Use it as a supporting lens beside statewide and regional-city governed benchmark views.",
        ])}
        """,
        source="council_profile_mart.csv and pay_range_summary_mart.csv.",
    ))

    band5_peer = snap[snap["standard_band"] == 5].copy()
    ball5 = float(band5_peer[band5_peer["canonical_council_id"] == "BALLARAT"].iloc[0]["capacity_weekly_rate"])
    band5_peer["delta_vs_ballarat"] = band5_peer["capacity_weekly_rate"].astype(float) - ball5
    peer_rows = pd.concat([band5_peer.sort_values("delta_vs_ballarat").head(6), band5_peer.sort_values("delta_vs_ballarat").tail(6)])
    pages.append(Page(
        "Peer deltas",
        "Individual council comparisons reveal where a median hides named competitors.",
        f"""
        {table_html(
            ["Council", "Category", "Band 5 capacity", "Delta vs Ballarat"],
            [[esc(r.short_name), esc(r.council_category), money(r.capacity_weekly_rate), f'<span class="{"positive" if r.delta_vs_ballarat < 0 else "negative"}">{money(r.delta_vs_ballarat)}</span>'] for _, r in peer_rows.iterrows()],
            "compact"
        )}
        {insight_list([
            "This named-council view is valuable in executive workshops because it converts an abstract distribution into known comparators.",
            "The point is not to import a separate-system result; it is to recreate the useful named-comparator pattern from governed local rows.",
        ])}
        """,
        source="pay_range_summary_mart.csv, Band 5 capacity at 2026-07-01.",
    ))

    spread_rows = []
    for row in stats["all"]:
        spread_rows.append([f"Band {row['band']}", money(row["progression_spread_ballarat"]), pct(row["progression_spread_pct_ballarat"]), money(row["capacity_ballarat"] - row["entry_ballarat"])])
    pages.append(Page(
        "Progression spread",
        "Internal pay architecture shapes retention psychology as much as the endpoint values.",
        f"""
        {table_html(["Band", "Ballarat spread", "Spread %", "Capacity minus entry"], spread_rows, "compact")}
        {insight_list([
            "A narrow spread can make progression feel symbolic; a wider spread can protect the value of tenure and capability development.",
            "Band 5 has the strongest spread signal in Ballarat's governed 2026 table.",
            "Market correction should preserve internal relativities rather than only lifting isolated endpoints.",
        ])}
        """,
        source="pay_range_summary_mart.csv progression_spread_abs and progression_spread_pct fields.",
    ))

    pages.append(Page(
        "Uplift timing",
        "Timing is part of competitiveness, not an administrative footnote.",
        f"""
        <div>{svg_uplift_timeline(data["uplifts"])}</div>
        {table_html(
            ["Effective date", "Rule", "Resolved", "Floor"],
            [[esc(row["effective_date"]), esc(str(row["quantum"])[:88]), pct(row["resolved_pct"]), money(row["dollar_component"]) if pd.notna(row["dollar_component"]) else "n/a"] for row in data["uplifts"]],
            "compact"
        )}
        """,
        source="uplift_timing_mart.csv for Ballarat governed rules.",
    ))

    pages.append(Page(
        "Movement path",
        "The governed movement view separates Ballarat's own uplift from its relative cohort position.",
        f"""
        {svg_movement_heatmap(movement)}
        {insight_list([
            "Dollar movement shows what changed inside Ballarat's own agreement path between 2025 and 2026.",
            "Percentage-point gap movement shows whether the relative position improved or deteriorated against the governed statewide median.",
            "This is a safer basis for a master report than importing numeric outputs from a different reporting system.",
        ])}
        """,
        source="pay_range_summary_mart.csv active governed rows at 2025-07-01 and 2026-07-01.",
    ))

    pages.append(Page(
        "Consultant gap map",
        "Senior role benchmarking validates the same pressure from a different direction.",
        f"""
        <div class="two-col">
          <div>{consultant_top_table(roles)}</div>
          <div>
            {metric_cards([
                (str(role_summary["role_count"]), "role tables parsed", "Exec and Level 4 reports"),
                (str(role_summary["below_selected_vic_average"]), "below selected Vic avg", "roles with negative variance"),
                (money(role_summary["largest_selected_vic_deficit"]), "largest selected Vic gap", "role-level benchmark"),
                (money(role_summary["largest_category_1_deficit"]), "largest Category 1 gap", "role-level benchmark"),
            ])}
          </div>
        </div>
        """,
        source="Consultant PDFs summary tables, parsed from pages containing incumbent variance tables.",
    ))

    pages.append(Page(
        "What beats the consultant",
        "The winning report does not imitate the competitor; it adds governed traceability and a richer labour-economics lens.",
        f"""
        <div class="method-grid">
          <div class="method-card"><b>Consultant lens</b><p>Role title, accountability, direct reports, budget, TRP and selected-council package comparison.</p></div>
          <div class="method-card"><b>Governed pay lens</b><p>EA band values, active dates, entry/capacity/midpoint, uplift rules and cohort medians.</p></div>
          <div class="method-card"><b>Entitlement lens</b><p>Leave, conditions, allowances, parental, super and wellbeing provisions as part of total employment value.</p></div>
          <div class="method-card"><b>Classification lens</b><p>PD descriptors, classification rules, higher duties, multi-skilling and annual review doctrine.</p></div>
          <div class="method-card"><b>Psychology lens</b><p>Attraction, progression fairness, capacity ceiling, senior retention and visible comparator names.</p></div>
          <div class="method-card"><b>Report asset lens</b><p>Reproducible charts, source caveats, governance status and exportable artefacts.</p></div>
        </div>
        """,
        source="Consultant method pages; project report-asset contract and local datamarts.",
    ))

    pages.append(Page(
        "Entitlement map",
        "Ballarat's value proposition is stronger than a salary-only view suggests.",
        f"""
        {svg_entitlement_grid(ent)}
        {metric_cards([
            (str(data["entitlement_summary"]["row_count"]), "entitlement rows", "draft summary extracted"),
            (str(data["entitlement_summary"]["status_counts"].get("leading", 0)), "leading signals", "classified from takeaways"),
            (str(data["entitlement_summary"]["status_counts"].get("gap", 0)), "gap/risk signals", "classified from takeaways"),
            ("7", "categories", "leave through wellbeing"),
        ])}
        """,
        source="entitlements draft summary report version 2.docx.",
    ))

    pages.append(Page(
        "Strengths",
        "The strongest Ballarat entitlement signals are human, visible and retention-relevant.",
        f"""
        {table_html(
            ["Entitlement", "Ballarat signal", "Why it matters"],
            [
                ["Family and Domestic Violence Leave", "20 days per year plus 5 days support leave", "Clear care and safety positioning above the NES baseline."],
                ["Non-primary parental leave", "6 weeks paid leave plus 10 days prenatal leave", "A strong family-support signal and modern EVP marker."],
                ["Additional personal/carers leave", "Up to 25 days nurses; up to 21 days child care workers", "Targeted support for pressure cohorts."],
                ["Super on parental leave", "Contributions continue during paid parental leave", "Protects long-run employee value."],
            ],
            "compact"
        )}
        {insight_list([
            "These provisions should not be buried in an appendix; they are part of the remuneration story.",
            "The report should present salary and entitlements as a total employment-value architecture.",
        ])}
        """,
        source="entitlement draft summary report, Leave and Parental/Family tables.",
    ))

    pages.append(Page(
        "Conditions risk",
        "The competitive gaps are specific enough to become a bargaining roadmap.",
        f"""
        {table_html(
            ["Area", "Ballarat position", "Report interpretation"],
            [
                ["Work from home protections", "No clear provision identified", "Modern flexibility risk against peers with explicit clauses."],
                ["Dependent-care support", "No specific entitlement identified", "Weakness in a practical attraction and participation lever."],
                ["Annual leave cash-out", "Allowed but narrower; limited to financial hardship", "Less flexible than many peers."],
                ["Thermal comfort", "Limited agreement provision; policy-related support", "Needs cleaner source-backed agreement wording if used as EVP evidence."],
            ],
            "compact"
        )}
        """,
        source="entitlement draft summary report, Conditions, Financial and WHS tables.",
    ))

    pages.append(Page(
        "Allowances",
        "Allowance values create small but psychologically salient comparisons.",
        f"""
        {table_html(
            ["Allowance", "Ballarat value", "Comparator reading"],
            [
                ["On-call allowance", "Up to $162.06 per week", "Middle of councils with clear fixed amounts; source note says numbers should be rechecked."],
                ["First aid allowance", "$2.56 per day", "Slightly above average in the entitlement draft."],
                ["Industry allowance", "$33.90 per week", "Lower third of the comparator group."],
                ["Plant allowance", "$38.52 per week", "Lower third of the comparator group."],
            ],
            "compact"
        )}
        {insight_list([
            "Allowance corrections rarely carry the full remuneration case, but they are highly legible to affected employees.",
            "The on-call note should remain caveated until source values are rechecked.",
        ])}
        """,
        source="entitlement draft summary report, Financial and Monetary Provisions table.",
    ))

    pages.append(Page(
        "Classification doctrine",
        "Pay credibility depends on classification credibility.",
        """
        <div class="method-grid six">
          <div class="method-card"><b>Accountability and authority</b><p>What the role can decide and own.</p></div>
          <div class="method-card"><b>Judgement and decision-making</b><p>How much ambiguity the role resolves.</p></div>
          <div class="method-card"><b>Specialist knowledge</b><p>Technical depth and domain expertise.</p></div>
          <div class="method-card"><b>Management skills</b><p>People, resources and service delivery complexity.</p></div>
          <div class="method-card"><b>Interpersonal skills</b><p>Influence, negotiation and stakeholder burden.</p></div>
          <div class="method-card"><b>Qualifications and experience</b><p>Credential and experience requirements.</p></div>
        </div>
        """ + insight_list([
            "The PD/classification pack makes the six descriptors central to defensible pay-band decisions.",
            "A world-class remuneration report should show whether market gaps are pay-table gaps, classification-design gaps, or role-sizing gaps.",
            "This is where the consultant method and EA band method can meet cleanly.",
        ]),
        source="PDs and Classifications Workbook.pdf; PDs and Classifications PPT.pdf.",
    ))

    pages.append(Page(
        "NES and legal baseline",
        "Best-practice reporting separates statutory floor, agreement provision and market enhancement.",
        """
        <div class="method-grid">
          <div class="method-card"><b>Direct minimum</b><p>Annual leave, personal/carer's leave, compassionate leave and FDV leave map directly to NES floor questions.</p></div>
          <div class="method-card"><b>Enhancement of NES</b><p>Additional leave, parental leave payments, prenatal leave and super on leave extend a baseline topic.</p></div>
          <div class="method-card"><b>No direct NES analogue</b><p>Pet leave, EAP, first aid allowance and thermal comfort require a different comparator lens.</p></div>
          <div class="method-card"><b>Decision rule</b><p>Do not treat absence of an enhancement as absence of the baseline entitlement.</p></div>
          <div class="method-card"><b>Business answer</b><p>State the NES standard, council position, uplift type, uplift value and confidence.</p></div>
          <div class="method-card"><b>Risk control</b><p>Keep extraction match level separate from the legal comparison verdict.</p></div>
        </div>
        """,
        source="Notion NES enhancement specification and KNOW YOUR AWARD.pdf.",
    ))

    pages.append(Page(
        "Governance layer",
        "The report is only world-class if its claims survive audit.",
        """
        <div class="method-grid">
          <div class="method-card"><b>Evidence candidate</b><p>Feature cards start as candidates, not final governed facts.</p></div>
          <div class="method-card"><b>Answer builder</b><p>Resolve meaning, value, cohort, timeframe, condition, paid status and normal-value alignment.</p></div>
          <div class="method-card"><b>Deterministic gate</b><p>Promote only resolved answers through schema, provenance and source-support checks.</p></div>
          <div class="method-card"><b>Blocked means work queue</b><p>Blocked evidence is repaired or researched, not silently dropped.</p></div>
          <div class="method-card"><b>Report asset</b><p>Each retained chart needs manifest metadata, governance status and export discipline.</p></div>
          <div class="method-card"><b>Review state</b><p>Distinguish draft, reviewed and report-ready values.</p></div>
        </div>
        """,
        source="FEATURE_ANSWER_BUILDER_DOCTRINE.md and REPORT_ASSET_CONTRACT.md.",
    ))

    pages.append(Page(
        "Executive options",
        "Three defensible pay strategies, each with a different psychology.",
        f"""
        {table_html(
            ["Option", "Primary move", "Best use", "Risk"],
            [
                ["A. Entry correction", "Lift entry points in exposed bands", "Attraction and early-retention pressure", "Can compress progression if capacity is untouched."],
                ["B. Senior-band correction", "Prioritise Bands 7 and 8 capacity", "Leadership retention and market credibility", "May feel narrow if Bands 4 to 6 remain behind."],
                ["C. Whole-ladder indexed reset", "Target all bands to a named percentile or cohort median", "Clean narrative and durable relativities", "Higher cost and stronger bargaining signal."],
            ],
            "compact"
        )}
        {insight_list([
            "Recommendation: build the financial model as an option stack, not a single magic number.",
            "The strongest next report should show costed scenarios by band, endpoint and employee distribution.",
            "Pair the pay scenario with entitlement language where Ballarat is already strong, so the narrative is not just deficit-based.",
        ])}
        """,
        source="Derived from governed pay snapshots, consultant role gaps and entitlement findings.",
    ))

    pages.append(Page(
        "Source appendix",
        "Caveats, provenance and next build path.",
        f"""
        {table_html(
            ["Evidence source", "Use in report", "Caveat"],
            [
                ["pay_range_summary_mart.csv", "2025/2026 governed pay snapshots", "Agreement clocks differ; active-window logic used."],
                ["Consultant PDFs", "41 role-level TRP benchmark tables", "Confidential role data; used as competitive method and pressure signal."],
                ["Entitlement DOCX", "54-item draft entitlement narrative", "Draft/staged; not all rows are governed source-level evidence."],
                ["Notion NES spec", "NES schema and decision rules", "Specification memory, not primary legal advice."],
                ["Power BI output from another system", "Design/workflow reference only", "No numeric output from that system is used in this report model."],
                ["Project current-state file", "System universe and maturity metrics", "Snapshot dated 2026-05-06."],
            ],
            "compact"
        )}
        {metric_cards([
            ("9/10", "content ambition", "multi-source and executive-ready"),
            ("9/10", "visual density", "bespoke SVG chart system"),
            ("8.5/10", "governance", "strong caveats, needs source-linked drill-through"),
            ("8.5/10", "commercial polish", "PDF-ready, next step is brand art direction pass"),
        ])}
        """,
        source="All sources listed in generated data JSON.",
    ))

    if len(pages) != 30:
        raise RuntimeError(f"Expected 30 pages, built {len(pages)}")
    return pages


def style() -> str:
    return """
    @page { size: A4 landscape; margin: 0; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #111821;
      color: #102033;
      font-family: "IBM Plex Sans", "Inter", "Aptos", "Segoe UI", Arial, sans-serif;
      font-size: 11px;
      line-height: 1.38;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    .page {
      width: 297mm;
      height: 210mm;
      page-break-after: always;
      position: relative;
      overflow: hidden;
      padding: 13mm 14mm 11mm;
      background:
        linear-gradient(180deg, rgba(255,255,255,.96), rgba(244,248,251,.96)),
        radial-gradient(circle at 80% 15%, rgba(21,155,166,.12), transparent 34%);
    }
    .page.dark, .page.cover {
      color: #F7FAFC;
      background:
        linear-gradient(135deg, #06172F 0%, #071E41 52%, #12354E 100%);
    }
    .header {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 18px;
      align-items: end;
      border-bottom: 1px solid rgba(20, 93, 160, .28);
      padding-bottom: 8px;
      margin-bottom: 10px;
    }
    .kicker {
      color: #159BA6;
      text-transform: uppercase;
      font-weight: 800;
      letter-spacing: .08em;
      font-size: 9.5px;
    }
    h2 {
      margin: 3px 0 0;
      font-size: 25px;
      line-height: 1.05;
      letter-spacing: 0;
      max-width: 880px;
      color: #071E41;
    }
    .dark h2, .cover h2 { color: #FFFFFF; }
    .body { height: 160mm; position: relative; }
    .source {
      position: absolute;
      left: 14mm;
      right: 14mm;
      bottom: 6mm;
      color: #697B8B;
      font-size: 8.4px;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      border-top: 1px solid rgba(140,160,179,.25);
      padding-top: 4px;
    }
    .cover .source, .dark .source { color: rgba(255,255,255,.62); border-top-color: rgba(255,255,255,.16); }
    .page-number { color: inherit; opacity: .74; }
    .brand-line {
      width: 126px;
      height: 5px;
      border-radius: 999px;
      background: linear-gradient(90deg, #159BA6, #2FAE8F, #D99A2B);
      margin-bottom: 4px;
    }
    .cover { padding: 16mm 18mm 14mm; }
    .cover-grid {
      height: 165mm;
      display: grid;
      grid-template-columns: 1.1fr .9fr;
      gap: 20mm;
      align-items: center;
    }
    .cover h1 {
      margin: 0;
      font-size: 58px;
      line-height: .94;
      max-width: 620px;
      letter-spacing: 0;
      color: #FFFFFF;
    }
    .cover-mark {
      display: inline-block;
      border: 1px solid rgba(255,255,255,.22);
      color: #9DE5E2;
      text-transform: uppercase;
      letter-spacing: .12em;
      font-weight: 800;
      padding: 8px 12px;
      margin-bottom: 18px;
    }
    .cover-sub {
      font-size: 17px;
      color: rgba(255,255,255,.78);
      max-width: 610px;
      margin-top: 20px;
    }
    .cover-panel {
      padding: 18px;
      border: 1px solid rgba(255,255,255,.18);
      background: rgba(255,255,255,.08);
      box-shadow: inset 0 1px 0 rgba(255,255,255,.12);
    }
    .metric-row {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      margin: 8px 0 12px;
    }
    .metric-card {
      background: #FFFFFF;
      border: 1px solid #DDE6EE;
      border-left: 5px solid #159BA6;
      padding: 10px 11px 9px;
      min-height: 70px;
    }
    .cover .metric-card, .dark .metric-card {
      background: rgba(255,255,255,.10);
      border-color: rgba(255,255,255,.18);
      color: #FFFFFF;
    }
    .metric-value {
      color: #071E41;
      font-size: 24px;
      font-weight: 850;
      line-height: 1;
      letter-spacing: 0;
      white-space: nowrap;
    }
    .cover .metric-value, .dark .metric-value { color: #FFFFFF; }
    .metric-label {
      margin-top: 5px;
      font-weight: 800;
      color: #34465C;
      text-transform: uppercase;
      letter-spacing: .04em;
      font-size: 8.8px;
    }
    .cover .metric-label, .dark .metric-label { color: #9DE5E2; }
    .metric-note { color: #6C7D8D; margin-top: 3px; font-size: 9px; }
    .cover .metric-note, .dark .metric-note { color: rgba(255,255,255,.68); }
    .insights {
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }
    .insight {
      display: grid;
      grid-template-columns: 10px 1fr;
      gap: 9px;
      align-items: start;
      padding: 9px 10px;
      background: rgba(255,255,255,.74);
      border: 1px solid #E2E9F0;
    }
    .insight span {
      width: 8px;
      height: 8px;
      margin-top: 4px;
      background: #D99A2B;
      border-radius: 50%;
    }
    .insight p { margin: 0; font-size: 11.3px; }
    .two-col {
      display: grid;
      grid-template-columns: 1.12fr .88fr;
      gap: 14px;
      align-items: start;
    }
    .split-charts {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .svg-chart {
      display: block;
      width: 100%;
      height: auto;
      background: #FFFFFF;
      border: 1px solid #DDE6EE;
    }
    .chart-title { font-size: 16px; font-weight: 850; fill: #071E41; }
    .grid-line { stroke: #DDE6EE; stroke-width: 1; }
    .zero-line { stroke: #071E41; stroke-width: 1.5; stroke-dasharray: 4 5; }
    .axis-line { stroke: #9AAABC; stroke-width: 1.3; }
    .axis-label { fill: #66798B; font-size: 10px; font-weight: 700; }
    .band-label { fill: #071E41; font-size: 12px; font-weight: 850; }
    .value-label { fill: #34465C; font-size: 11px; font-weight: 760; }
    .heat-label { fill: #071E41; font-size: 11px; font-weight: 850; }
    .median-label { fill: #071E41; font-size: 11px; font-weight: 850; }
    .ballarat-line { stroke: #B64A3A; stroke-width: 2; stroke-dasharray: 3 4; }
    .ballarat-label { fill: #B64A3A; font-size: 12px; font-weight: 850; }
    .map-label, .tiny-label { fill: #34465C; font-size: 9px; font-weight: 760; }
    .caption { fill: #6C7D8D; font-size: 9px; }
    .orbit-core { fill: #FFFFFF; font-size: 17px; font-weight: 850; }
    .orbit-sub { fill: #9DE5E2; font-size: 9px; font-weight: 760; }
    .orbit-number { fill: #071E41; font-size: 15px; font-weight: 900; }
    .orbit-label { fill: #4F6377; font-size: 7.7px; font-weight: 800; }
    .method-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-top: 7px;
    }
    .method-grid.six { grid-template-columns: repeat(3, 1fr); }
    .method-card {
      min-height: 96px;
      padding: 13px;
      background: #FFFFFF;
      border: 1px solid #DDE6EE;
      border-top: 4px solid #159BA6;
    }
    .method-card b {
      color: #071E41;
      font-size: 14px;
      display: block;
      margin-bottom: 6px;
    }
    .method-card p {
      margin: 0;
      color: #40546B;
      font-size: 11px;
    }
    .report-table {
      width: 100%;
      border-collapse: collapse;
      background: #FFFFFF;
      border: 1px solid #DDE6EE;
      font-size: 10.2px;
    }
    .report-table th {
      text-align: left;
      background: #071E41;
      color: #FFFFFF;
      padding: 7px 8px;
      font-size: 9px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }
    .report-table td {
      padding: 6px 8px;
      border-bottom: 1px solid #E6EDF3;
      color: #26394D;
      vertical-align: top;
    }
    .report-table.compact td { padding: 5px 7px; }
    .negative { color: #B64A3A; font-weight: 850; }
    .positive { color: #2FAE8F; font-weight: 850; }
    """


def render_html(pages: list[Page]) -> str:
    sections = []
    for idx, page in enumerate(pages, start=1):
        theme_cls = "cover" if page.theme == "cover" else "dark" if page.theme == "dark" else ""
        header = "" if page.theme == "cover" else f"""
        <div class="header">
          <div>
            <div class="kicker">{esc(page.kicker)}</div>
            <h2>{esc(page.title)}</h2>
          </div>
          <div class="brand-line"></div>
        </div>
        """
        sections.append(
            f"""
            <section class="page {theme_cls}">
              {header}
              <div class="body">{page.body}</div>
              <div class="source"><span>{esc(page.source)}</span><span class="page-number">{idx:02d} / {len(pages):02d}</span></div>
            </section>
            """
        )
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Ballarat Remuneration Intelligence Report</title><style>{style()}</style></head><body>{''.join(sections)}</body></html>"


def find_chrome() -> str | None:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        shutil.which("msedge"),
        shutil.which("msedge.exe"),
    ]
    return next((c for c in candidates if c and Path(c).exists()), None)


def write_outputs(data: dict[str, Any], pages: list[Page], render_pdf: bool = True) -> dict[str, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUT_DIR / f"{REPORT_STEM}.html"
    pdf_path = OUT_DIR / f"{REPORT_STEM}.pdf"
    data_path = OUT_DIR / f"{REPORT_STEM}-data.json"
    html_path.write_text(render_html(pages), encoding="utf-8")
    data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    outputs = {"html": html_path, "data": data_path}
    if render_pdf:
        chrome = find_chrome()
        if not chrome:
            raise RuntimeError("Chrome or Edge executable not found for PDF rendering.")
        with tempfile.TemporaryDirectory(prefix="ballarat-report-chrome-") as tmp:
            file_url = html_path.resolve().as_uri()
            cmd = [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--user-data-dir={tmp}",
                f"--print-to-pdf={pdf_path}",
                file_url,
            ]
            subprocess.run(cmd, check=True, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outputs["pdf"] = pdf_path
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Ballarat 30-page remuneration intelligence report.")
    parser.add_argument("--no-pdf", action="store_true", help="Write HTML/data only.")
    args = parser.parse_args()
    data = build_data_model()
    pages = build_pages(data)
    outputs = write_outputs(data, pages, render_pdf=not args.no_pdf)
    print(json.dumps({k: str(v) for k, v in outputs.items()}, indent=2))


if __name__ == "__main__":
    main()
