from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATAMART_DIR = DATA_DIR / "datamarts"
OUTPUT_PATH = APP_DIR / "data" / "workspace-small-council-state.json"

AS_OF_DATE = "2026-01-01"
AS_OF = date.fromisoformat(AS_OF_DATE)
HORIZON_DATE = "2027-07-01"
SMALL_CATEGORY = "Small shire"
BOUNDARY_GEOJSON_URL = "/static/data/victoria-lga-boundaries.geojson"
BANDS = list(range(1, 9))
FOCUS_BAND = 5
DISTRIBUTION_HIGHLIGHT_COUNCIL_KEY = "BALLARAT"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(value: str | None, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except ValueError:
        return default


def percentile(values: list[float], fraction: float) -> float:
    clean = sorted(values)
    if not clean:
        return 0.0
    if len(clean) == 1:
        return clean[0]
    index = (len(clean) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(clean) - 1)
    if lower == upper:
        return clean[lower]
    return clean[lower] + ((clean[upper] - clean[lower]) * (index - lower))


def round_money(value: float | int | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def add_one_calendar_year(value: date) -> date:
    try:
        return value.replace(year=value.year + 1)
    except ValueError:
        return value.replace(year=value.year + 1, day=28)


def row_contains_report_date(row: dict[str, str]) -> bool:
    effective_from = parse_date(row.get("effective_from"))
    if not effective_from or effective_from > AS_OF:
        return False
    effective_to = parse_date(row.get("effective_to"))
    operative_to = effective_to or add_one_calendar_year(effective_from)
    return effective_from <= AS_OF <= operative_to


def active_snapshot_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    active = []
    for row in rows:
        band = row.get("standard_band")
        if band not in {str(item) for item in BANDS}:
            continue
        if not row.get("range_midpoint_weekly_rate"):
            continue
        if row_contains_report_date(row):
            active.append(row)
    return active


def is_report_valid_council(profile: dict[str, str] | None) -> bool:
    if not profile:
        return False
    return profile.get("status") == "active" and profile.get("is_active") == "True"


def row_has_report_valid_council(
    row: dict[str, str],
    profiles: dict[str, dict[str, str]],
) -> bool:
    return is_report_valid_council(profiles.get(row.get("canonical_council_id", "")))


def row_category(row: dict[str, str], profiles: dict[str, dict[str, str]]) -> str:
    return profiles.get(row.get("canonical_council_id", ""), {}).get("council_category", "")


def apply_uplifts(current: float, rules: list[dict[str, str]]) -> tuple[float, list[dict[str, object]]]:
    value = current
    applied = []
    for rule in sorted(rules, key=lambda item: item.get("effective_date", "")):
        pct = number(rule.get("resolved_pct"), number(rule.get("pct_component")))
        dollar = number(rule.get("dollar_component"))
        pct_increment = value * pct / 100 if pct is not None else None
        dollar_increment = dollar if dollar is not None and rule.get("dollar_basis") in ("", "weekly") else None
        quantum_type = rule.get("quantum_type", "")
        if quantum_type == "pct_OR_floor" and pct_increment is not None and dollar_increment is not None:
            increment = max(pct_increment, dollar_increment)
        elif pct_increment is not None and pct_increment != 0:
            increment = pct_increment
        elif dollar_increment is not None:
            increment = dollar_increment
        else:
            increment = 0.0
        value += increment
        display = f"{pct:g}%" if pct is not None and pct != 0 else ""
        if dollar_increment is not None:
            display = f"{display} / ${dollar_increment:g}" if display else f"${dollar_increment:g}"
        applied.append(
            {
                "date": rule.get("effective_date"),
                "pct": pct,
                "dollar": dollar_increment,
                "display": display or rule.get("quantum") or "uplift",
                "label": rule.get("quantum") or rule.get("timing_clause") or "Scheduled uplift",
                "projectedWeekly": round_money(value),
                "sourceRuleId": rule.get("uplift_rule_id"),
            }
        )
    return value, applied


def value_rows_for_band(rows: list[dict[str, str]], band: int) -> list[dict[str, object]]:
    output = []
    for row in rows:
        if row.get("standard_band") != str(band):
            continue
        value = number(row.get("range_midpoint_weekly_rate"))
        if value is None:
            continue
        output.append(
            {
                "councilKey": row.get("canonical_council_id"),
                "councilName": row.get("canonical_council_name"),
                "agreementId": row.get("agreement_id"),
                "effectiveFrom": row.get("effective_from"),
                "effectiveTo": row.get("effective_to"),
                "value": value,
            }
        )
    return output


def stats(values: list[float]) -> dict[str, float | int | None]:
    clean = sorted(values)
    if not clean:
        return {
            "count": 0,
            "min": None,
            "p10": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p90": None,
            "max": None,
        }
    return {
        "count": len(clean),
        "min": round_money(clean[0]),
        "p10": round_money(percentile(clean, 0.10)),
        "p25": round_money(percentile(clean, 0.25)),
        "median": round_money(median(clean)),
        "p75": round_money(percentile(clean, 0.75)),
        "p90": round_money(percentile(clean, 0.90)),
        "max": round_money(clean[-1]),
    }


def histogram_bins(values: list[float], bin_count: int = 14) -> list[dict[str, object]]:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return []
    lo = min(clean)
    hi = max(clean)
    width = (hi - lo) / bin_count if hi > lo else 1
    bins = []
    for index in range(bin_count):
        start = lo + (width * index)
        end = lo + (width * (index + 1))
        count = sum(
            1
            for value in clean
            if value >= start and (value <= end if index == bin_count - 1 else value < end)
        )
        bins.append(
            {
                "index": index,
                "start": round_money(start),
                "end": round_money(end),
                "count": count,
            }
        )
    return bins


def peak_diagnostics(
    density_bins: list[dict[str, object]],
    observations: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not density_bins:
        return []

    max_count = max(int(item.get("count") or 0) for item in density_bins)
    min_peak_count = max(2, round(max_count * 0.25))
    candidate_bins = []

    for index, item in enumerate(density_bins):
        count = int(item.get("count") or 0)
        previous_count = int(density_bins[index - 1].get("count") or 0) if index > 0 else -1
        next_count = int(density_bins[index + 1].get("count") or 0) if index < len(density_bins) - 1 else -1
        is_local_peak = count >= previous_count and count >= next_count and (count > previous_count or count > next_count)
        if is_local_peak and count >= min_peak_count:
            candidate_bins.append(item)

    if not candidate_bins:
        candidate_bins = [max(density_bins, key=lambda item: int(item.get("count") or 0))]

    merged_bins = []
    for item in sorted(candidate_bins, key=lambda item: int(item.get("index") or 0)):
        if merged_bins and int(item.get("index") or 0) == int(merged_bins[-1].get("endIndex") or 0) + 1:
            merged_bins[-1]["endIndex"] = item.get("index")
            merged_bins[-1]["end"] = item.get("end")
            merged_bins[-1]["count"] = int(merged_bins[-1].get("count") or 0) + int(item.get("count") or 0)
            continue
        merged_bins.append(
            {
                **item,
                "endIndex": item.get("index"),
            }
        )

    peak_bins = sorted(merged_bins, key=lambda item: int(item.get("count") or 0), reverse=True)[:3]
    enriched = []
    for item in peak_bins:
        start = number(item.get("start"))
        end = number(item.get("end"))
        if start is None or end is None:
            continue
        observations_in_bin = [
            row
            for row in observations
            if number(row.get("value")) is not None
            and number(row.get("value")) >= start
            and number(row.get("value")) <= end
        ]
        category_counts = Counter(row.get("category") or "Unknown" for row in observations_in_bin)
        dominant_categories = [
            {
                "category": category,
                "count": count,
            }
            for category, count in category_counts.most_common(3)
        ]
        count = int(item.get("count") or len(observations_in_bin))
        dominant_label = dominant_categories[0]["category"] if dominant_categories else "mixed cohorts"
        enriched.append(
            {
                "range": [round_money(start), round_money(end)],
                "count": count,
                "label": f"{count} councils",
                "dominantCategories": dominant_categories,
                "description": f"Most common cohort in this band: {dominant_label}.",
            }
        )

    return sorted(enriched, key=lambda item: item["range"][0])


def distribution_shape_diagnostics(
    density_bins: list[dict[str, object]],
    observations: list[dict[str, object]],
    value_basis_label: str,
) -> dict[str, object]:
    peaks = peak_diagnostics(density_bins, observations)
    peak_count = len(peaks)
    if peak_count > 1:
        reading = f"{peak_count} material peaks in the {value_basis_label.lower()} distribution."
    elif peak_count == 1:
        reading = f"One material peak in the {value_basis_label.lower()} distribution."
    else:
        reading = f"No material peaks detected in the {value_basis_label.lower()} distribution."

    return {
        "reading": reading,
        "method": f"Dynamic local-maximum scan over a fixed 14-bin histogram using {value_basis_label.lower()} values; bins with fewer than two councils or below 25% of the largest bin are not labelled as primary peaks.",
        "primaryPeaks": peaks,
        "interpretation": "Peak labels are generated from the active Band 5 values, so the annotation follows the current snapshot instead of fixed narrative text.",
        "caveat": "Peak detection is bin-sensitive and should be treated as a descriptive diagnostic, not a formal distribution test.",
    }


def build_distribution_profile(
    focus_values: list[dict[str, object]],
    *,
    key: str,
    title: str,
    value_basis_label: str,
) -> dict[str, object]:
    observations = sorted(focus_values, key=lambda item: (number(item.get("value")) or 0, item.get("councilName") or ""))
    small_values = [number(item.get("value")) for item in observations if item.get("isSmallCouncil")]
    state_values = [number(item.get("value")) for item in observations]
    cohort_order = ["Small shire", "Large shire", "Regional", "Interface", "Metropolitan", "Unknown"]
    cohort_stats = []
    for category in cohort_order:
        category_values = [
            number(item.get("value"))
            for item in observations
            if item.get("category") == category
        ]
        category_values = [value for value in category_values if value is not None]
        if not category_values:
            continue
        cohort_stats.append(
            {
                "category": category,
                "count": len(category_values),
                "stats": stats(category_values),
            }
        )

    clean_state_values = [value for value in state_values if value is not None]
    clean_small_values = [value for value in small_values if value is not None]
    density_bins = histogram_bins(clean_state_values, 14)
    highlight_observation = next(
        (
            item
            for item in observations
            if str(item.get("councilKey")) == str(DISTRIBUTION_HIGHLIGHT_COUNCIL_KEY)
        ),
        None,
    )
    return {
        "key": key,
        "title": title,
        "valueBasisLabel": value_basis_label,
        "stateStats": stats(clean_state_values),
        "smallStats": stats(clean_small_values),
        "cohortStats": cohort_stats,
        "densityBins": density_bins,
        "observations": observations,
        "shapeDiagnostics": distribution_shape_diagnostics(density_bins, observations, value_basis_label),
        "highlightObservation": {
            "councilKey": highlight_observation["councilKey"],
            "councilName": highlight_observation["councilName"],
            "category": highlight_observation["category"],
            "value": highlight_observation["value"],
            "label": "Ballarat",
            "reason": "Named statewide anchor requested for distribution reading.",
        } if highlight_observation else None,
    }


def build_smoothed_focus_values(
    focus_values: list[dict[str, object]],
    pay_range_rows: list[dict[str, str]],
    profiles: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    as_of = parse_date(AS_OF_DATE)
    rows_by_council: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in pay_range_rows:
        if row.get("standard_band") != str(FOCUS_BAND):
            continue
        council_key = str(row.get("canonical_council_id") or "")
        if not council_key or council_key not in profiles:
            continue
        value = number(row.get("range_midpoint_weekly_rate"))
        effective_from = parse_date(row.get("effective_from", ""))
        if value is None or not effective_from:
            continue
        rows_by_council[council_key].append(
            {
                "date": effective_from,
                "dateRaw": row.get("effective_from", ""),
                "value": value,
            }
        )

    for rows in rows_by_council.values():
        rows.sort(key=lambda item: item["date"])

    smoothed = []
    for item in focus_values:
        raw_value = number(item.get("value"))
        if raw_value is None or not as_of:
            smoothed.append({**item, "rawValue": raw_value, "smoothingMethod": "raw_fallback"})
            continue

        rows = rows_by_council.get(str(item.get("councilKey")), [])
        previous_rows = [row for row in rows if row["date"] <= as_of]
        next_rows = [row for row in rows if row["date"] > as_of]
        previous_row = previous_rows[-1] if previous_rows else None
        next_row = next_rows[0] if next_rows else None
        smoothed_value = raw_value
        smoothing_method = "raw_active_value"

        if previous_row and next_row and previous_row["date"] < next_row["date"]:
            span_days = (next_row["date"] - previous_row["date"]).days
            elapsed_days = (as_of - previous_row["date"]).days
            if span_days > 0:
                fraction = max(0, min(1, elapsed_days / span_days))
                smoothed_value = previous_row["value"] + ((next_row["value"] - previous_row["value"]) * fraction)
                smoothing_method = "linear_interpolation_to_next_known_period"

        smoothed.append(
            {
                **item,
                "rawValue": round_money(raw_value),
                "value": round_money(smoothed_value),
                "smoothingMethod": smoothing_method,
                "smoothingFrom": {
                    "effectiveFrom": previous_row["dateRaw"],
                    "value": round_money(previous_row["value"]),
                } if previous_row else None,
                "smoothingTo": {
                    "effectiveFrom": next_row["dateRaw"],
                    "value": round_money(next_row["value"]),
                } if next_row else None,
            }
        )

    return smoothed


def build_pay_point_galaxy(
    pay_range_rows: list[dict[str, str]],
    profiles: dict[str, dict[str, str]],
) -> dict[str, object]:
    grouped: dict[tuple[str, str, int, str], list[dict[str, object]]] = defaultdict(list)
    source_rows = 0
    small_source_rows = 0
    councils = set()
    small_councils = set()

    for row in pay_range_rows:
        band_raw = row.get("standard_band")
        if band_raw not in {str(item) for item in BANDS}:
            continue
        date = row.get("effective_from")
        if not date:
            continue
        value = number(row.get("step_mean_weekly_rate"), number(row.get("range_midpoint_weekly_rate")))
        if value is None:
            continue
        band = int(band_raw)
        level = row.get("classification_label_raw") or f"Band {band}"
        council_key = row.get("canonical_council_id")
        profile = profiles.get(council_key or "")
        if not is_report_valid_council(profile):
            continue
        council_category = profile.get("council_category", "")
        point_payload = {
            "value": value,
            "councilKey": council_key,
            "agreementId": row.get("agreement_id"),
            "effectiveTo": row.get("effective_to"),
        }
        grouped[("statewide", date, band, level)].append(point_payload)
        source_rows += 1
        if council_key:
            councils.add(council_key)
        if council_category == SMALL_CATEGORY:
            grouped[("small_shire", date, band, level)].append(point_payload)
            small_source_rows += 1
            if council_key:
                small_councils.add(council_key)

    observations = []
    for (cohort_id, date, band, level), rows in grouped.items():
        values = [float(item["value"]) for item in rows]
        council_count = len({item["councilKey"] for item in rows if item.get("councilKey")})
        observations.append(
            {
                "id": f"{cohort_id}::{date}::band_{band}::{level.lower().replace(' ', '_')}",
                "cohort": cohort_id,
                "cohortLabel": "Small shire" if cohort_id == "small_shire" else "Statewide",
                "date": date,
                "band": band,
                "levelLabel": level,
                "averageWeekly": round_money(sum(values) / len(values)),
                "minWeekly": round_money(min(values)),
                "maxWeekly": round_money(max(values)),
                "rowCount": len(rows),
                "councilCount": council_count,
            }
        )

    observations.sort(key=lambda item: (item["date"], item["band"], item["cohort"]))
    values = [float(item["averageWeekly"]) for item in observations if item.get("averageWeekly") is not None]
    dates = [str(item["date"]) for item in observations if item.get("date")]

    return {
        "question": "What does the whole pay field look like over time?",
        "title": "Pay point galaxy",
        "summary": "Each point is an average weekly pay value for a cohort, standard band, level label, and effective date. The view turns the pay mart from a table into a temporal field of observations.",
        "metric": "Average weekly rate, using step_mean_weekly_rate where available and range_midpoint_weekly_rate as fallback",
        "sourceDataset": "pay_range_summary_mart + council_profile_mart",
        "cohorts": [
            {
                "id": "statewide",
                "label": "Statewide",
                "description": "All councils represented in pay_range_summary_mart.",
            },
            {
                "id": "small_shire",
                "label": "Small shire",
                "description": "Rows where council_profile_mart.council_category equals Small shire.",
            },
        ],
        "summaryMetrics": [
            {
                "label": "Pay summary rows",
                "value": f"{source_rows:,}",
                "detail": "statewide rows with usable weekly values",
            },
            {
                "label": "Small shire rows",
                "value": f"{small_source_rows:,}",
                "detail": "controlled cohort rows",
            },
            {
                "label": "Effective period",
                "value": f"{min(dates)[:4]}-{max(dates)[:4]}" if dates else "n/a",
                "detail": "all mart timeframes",
            },
            {
                "label": "Galaxy points",
                "value": f"{len(observations):,}",
                "detail": "cohort x date x band x level averages",
            },
        ],
        "coverage": {
            "statewideSourceRows": source_rows,
            "smallShireSourceRows": small_source_rows,
            "statewideCouncils": len(councils),
            "smallShireCouncils": len(small_councils),
            "dateStart": min(dates) if dates else None,
            "dateEnd": max(dates) if dates else None,
            "valueMin": round_money(min(values)) if values else None,
            "valueMax": round_money(max(values)) if values else None,
            "bandCount": len(BANDS),
        },
        "observations": observations,
        "caveat": "This is a real local workspace aggregation, not a final governed product view. It compares available mart rows over all effective dates and does not apply headcount weighting, agreement recency filtering, or final coverage governance.",
    }


def band_rows(active_rows: list[dict[str, str]], profiles: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    rows = []
    for band in BANDS:
        band_values = value_rows_for_band(active_rows, band)
        state_values = [item["value"] for item in band_values]
        small_values = [
            item["value"]
            for item in band_values
            if profiles.get(str(item["councilKey"]), {}).get("council_category") == SMALL_CATEGORY
        ]
        state_stats = stats(state_values)
        small_stats = stats(small_values)
        state_median = state_stats["median"] or 0
        small_median = small_stats["median"] or 0
        gap = small_median - state_median
        abs_gap = abs(gap)
        if abs_gap >= 45:
            focus = "large_gap"
        elif abs_gap <= 35:
            focus = "narrow_gap"
        else:
            focus = "moderate_gap"
        rows.append(
            {
                "band": band,
                "label": f"Band {band}",
                "stateMedian": state_median,
                "smallMedian": small_median,
                "gap": round_money(gap),
                "gapPct": round((gap / state_median) * 100, 1) if state_median else 0,
                "statewideRange": [state_stats["min"], state_stats["max"]],
                "smallRange": [small_stats["min"], small_stats["max"]],
                "stateStats": state_stats,
                "smallStats": small_stats,
                "stateCount": state_stats["count"],
                "smallCount": small_stats["count"],
                "timingSensitive": band in (5, 6),
                "focus": focus,
                "note": f"Active {AS_OF_DATE} snapshot from pay_range_summary_mart: n={state_stats['count']} statewide, n={small_stats['count']} Small shire.",
            }
        )
    return rows


def build_distribution(
    active_rows: list[dict[str, str]],
    profiles: dict[str, dict[str, str]],
    pay_bands: list[dict[str, object]],
    pay_range_rows: list[dict[str, str]],
) -> dict[str, object]:
    range_ribbons = []
    for band in (3, 5, 7):
        row = next(item for item in pay_bands if item["band"] == band)
        range_ribbons.append(
            {
                "band": band,
                "stateP10": row["stateStats"]["p10"],
                "stateP25": row["stateStats"]["p25"],
                "stateMedian": row["stateStats"]["median"],
                "stateP75": row["stateStats"]["p75"],
                "stateP90": row["stateStats"]["p90"],
                "smallP25": row["smallStats"]["p25"],
                "smallMedian": row["smallStats"]["median"],
                "smallP75": row["smallStats"]["p75"],
            }
        )

    focus_values = []
    for item in value_rows_for_band(active_rows, FOCUS_BAND):
        profile = profiles.get(str(item["councilKey"]), {})
        effective_from = parse_date(str(item.get("effectiveFrom") or ""))
        effective_to = str(item.get("effectiveTo") or "")
        operative_end = effective_to or (add_one_calendar_year(effective_from).isoformat() if effective_from else "")
        focus_values.append(
            {
                "councilKey": item["councilKey"],
                "councilName": item["councilName"],
                "value": round_money(item["value"]),
                "category": profile.get("council_category", "Unknown"),
                "isSmallCouncil": profile.get("council_category") == SMALL_CATEGORY,
                "agreementId": item["agreementId"],
                "effectiveFrom": item["effectiveFrom"],
                "effectiveTo": effective_to,
                "operativeEnd": operative_end,
            }
        )
    focus_values.sort(key=lambda item: (item["value"] or 0, item["councilName"] or ""))
    raw_profile = build_distribution_profile(
        focus_values,
        key="raw",
        title=f"Band {FOCUS_BAND} active midpoint distribution",
        value_basis_label="Raw midpoint",
    )
    smoothed_profile = build_distribution_profile(
        build_smoothed_focus_values(focus_values, pay_range_rows, profiles),
        key="smoothed",
        title=f"Band {FOCUS_BAND} date-smoothed midpoint distribution",
        value_basis_label="Smoothed midpoint",
    )
    return {
        "question": "Is the gap uniform, or does it depend where you look?",
        "metric": "Weekly range midpoint rate",
        "asOfDate": AS_OF_DATE,
        "summary": "The active Band 5 distribution is not a smooth bell curve. It shows at least two concentrations of councils, and the Small shire median sits below the statewide median while still overlapping other cohort ranges.",
        "focusBand": FOCUS_BAND,
        "sourceAsset": "distribution_point_analysis_default",
        "sourceDataset": "pay_range_summary_mart active snapshot, cross-checked against the distribution prototype contract",
        "inclusionRule": f"Includes councils with an eligible Band {FOCUS_BAND} range_midpoint_weekly_rate row where the report date {AS_OF_DATE} falls between effective_from and effective_to. If effective_to is blank, the operative window is effective_from through effective_from + 1 calendar year. canonical_council_id must also resolve to council_profile_mart with status=active and is_active=True.",
        "snapshotRule": {
            "asOfDate": AS_OF_DATE,
            "dateFields": ["effective_from", "effective_to"],
            "blankEffectiveToFallback": "effective_from_plus_1_calendar_year",
            "councilEligibility": "council_profile_mart.status=active and council_profile_mart.is_active=True",
        },
        "rangeRibbons": range_ribbons,
        "shapeDiagnostics": raw_profile["shapeDiagnostics"],
        "highlightObservation": raw_profile["highlightObservation"],
        "prototypeStyle": {
            **raw_profile,
            "defaultProfile": "raw",
            "profiles": {
                "raw": raw_profile,
                "smoothed": smoothed_profile,
            },
        },
        "caveat": "Workspace snapshot from active pay range summaries. This uses real local workbench values but still needs final report governance before publication.",
    }


def build_uplift_timeline(
    active_rows: list[dict[str, str]],
    profiles: dict[str, dict[str, str]],
    uplift_rows: list[dict[str, str]],
) -> dict[str, object]:
    rules_by_agreement: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in uplift_rows:
        if AS_OF_DATE < row.get("effective_date", "") <= HORIZON_DATE:
            rules_by_agreement[row["agreement_id"]].append(row)

    band5 = []
    for row in active_rows:
        if row.get("standard_band") != str(FOCUS_BAND):
            continue
        current = number(row.get("range_midpoint_weekly_rate"))
        if current is None:
            continue
        horizon, applied = apply_uplifts(current, rules_by_agreement.get(row["agreement_id"], []))
        band5.append(
            {
                "name": row.get("canonical_council_name"),
                "councilKey": row.get("canonical_council_id"),
                "agreementId": row.get("agreement_id"),
                "current": current,
                "horizon": horizon,
                "uplifts": applied,
                "category": row_category(row, profiles),
            }
        )

    small = [row for row in band5 if row["category"] == SMALL_CATEGORY]
    all_current = [row["current"] for row in band5]
    all_horizon = [row["horizon"] for row in band5]
    small_current = [row["current"] for row in small]
    small_horizon = [row["horizon"] for row in small]

    def aggregate_series(name: str, segment: str, rows: list[dict[str, object]]) -> dict[str, object]:
        current = median([row["current"] for row in rows])
        horizon = median([row["horizon"] for row in rows])
        with_uplifts = sum(1 for row in rows if row["uplifts"])
        return {
            "name": name,
            "segment": segment,
            "currentWeekly": round_money(current),
            "horizonWeekly": round_money(horizon),
            "cycleStatus": f"{with_uplifts} of {len(rows)} Band {FOCUS_BAND} rows have scheduled uplifts to {HORIZON_DATE}",
            "uplifts": [],
        }

    examples = sorted(small, key=lambda row: row["horizon"] - row["current"], reverse=True)[:3]
    series = [
        aggregate_series("Small shire median", "Small shire", small),
        aggregate_series("Statewide median", "All active councils", band5),
    ]
    for row in examples:
        series.append(
            {
                "name": row["name"],
                "segment": "Small shire example",
                "currentWeekly": round_money(row["current"]),
                "horizonWeekly": round_money(row["horizon"]),
                "cycleStatus": f"{len(row['uplifts'])} scheduled uplift event(s) to {HORIZON_DATE}",
                "uplifts": row["uplifts"],
            }
        )

    return {
        "question": "Is this a structural pay gap, or a timing artefact?",
        "snapshotDate": AS_OF_DATE,
        "horizonDate": HORIZON_DATE,
        "metric": f"Band {FOCUS_BAND} weekly range midpoint rate",
        "summary": "Snapshot comparisons can mislead when councils sit at different points in their agreement cycle.",
        "phases": [
            {
                "id": "current",
                "label": "Current snapshot",
                "description": "Compare active Band 5 midpoint rates as at the report date.",
            },
            {
                "id": "uplifts",
                "label": "Scheduled uplifts",
                "description": "Reveal governed uplift rules that land before the horizon date.",
            },
            {
                "id": "horizon",
                "label": "Horizon view",
                "description": "Project the same rows after known scheduled uplift events.",
            },
        ],
        "series": series,
        "coverage": {
            "stateBand5Rows": len(band5),
            "smallBand5Rows": len(small),
            "stateCurrentMedian": round_money(median(all_current)),
            "smallCurrentMedian": round_money(median(small_current)),
            "stateHorizonMedian": round_money(median(all_horizon)),
            "smallHorizonMedian": round_money(median(small_horizon)),
        },
        "caveat": "Real uplift rules from uplift_timing_mart are applied mechanically to active Band 5 midpoint rows. Dollar floors are approximated as weekly increments where the rule states a weekly basis.",
    }


def build_entitlements(entitlement_rows: list[dict[str, str]]) -> dict[str, object]:
    category_counts = Counter(row.get("category", "Unknown") for row in entitlement_rows)
    return {
        "question": "Do small councils compete differently?",
        "status": "workspace_taxonomy_not_governed_presence",
        "summary": "The local entitlement mart is currently a staged taxonomy, not a governed council-by-council comparison. It is still useful here because it shows the employment-value categories the reporting layer can connect to next.",
        "columns": ["Pay", "Leave", "Allowances", "Flexibility", "Progression"],
        "rows": [
            {
                "segment": "Small shire cohort",
                "scores": {
                    "Pay": {
                        "rating": "below",
                        "label": "Below median",
                        "note": "Real Band 5-6 active snapshot sits below statewide median.",
                    },
                    "Leave": {
                        "rating": "watch",
                        "label": f"{category_counts.get('Leave', 0)} taxonomy items",
                        "note": "Staged entitlement taxonomy, not presence scoring.",
                    },
                    "Allowances": {
                        "rating": "mixed",
                        "label": f"{category_counts.get('Financial and Monetary Provisions', 0)} monetary items",
                        "note": "Allowance comparison requires governed summaries.",
                    },
                    "Flexibility": {
                        "rating": "watch",
                        "label": f"{category_counts.get('Conditions', 0)} condition items",
                        "note": "Potential employment-value lever, not yet scored.",
                    },
                    "Progression": {
                        "rating": "watch",
                        "label": "Pay ladder context",
                        "note": "Progression is visible in pay range summaries; rule-level progression remains partial.",
                    },
                },
            },
            {
                "segment": "Statewide position",
                "scores": {
                    "Pay": {
                        "rating": "baseline",
                        "label": "Benchmark",
                        "note": "All active councils in the local snapshot.",
                    },
                    "Leave": {
                        "rating": "baseline",
                        "label": "Taxonomy baseline",
                        "note": "No governed sector scoring yet.",
                    },
                    "Allowances": {
                        "rating": "baseline",
                        "label": "Taxonomy baseline",
                        "note": "No governed sector scoring yet.",
                    },
                    "Flexibility": {
                        "rating": "baseline",
                        "label": "Taxonomy baseline",
                        "note": "No governed sector scoring yet.",
                    },
                    "Progression": {
                        "rating": "baseline",
                        "label": "Benchmark",
                        "note": "Comparison needs metric-aware progression rules.",
                    },
                },
            },
        ],
        "sourceSummary": dict(category_counts),
        "caveat": "Entitlement content is real local taxonomy from entitlement_summary_mart, but it is staged_not_governed and must not be read as council-level entitlement evidence.",
    }


def build_cohort_map(
    small_councils: list[dict[str, str]],
    small_active_keys: set[str | None],
) -> dict[str, object]:
    label_keys = [
        "WEST WIMMERA",
        "HINDMARSH",
        "PYRENEES",
        "CENTRAL GOLDFIELDS",
        "HEPBURN",
        "ARARAT",
        "ALPINE",
    ]
    councils = []
    for row in sorted(small_councils, key=lambda item: item.get("short_name") or item.get("canonical_council_name", "")):
        spatial_key = row.get("council_key", "")
        councils.append(
            {
                "name": row.get("canonical_council_name"),
                "shortName": row.get("short_name") or row.get("canonical_council_name"),
                "spatialName": row.get("spatial_name"),
                "spatialKey": spatial_key,
                "category": row.get("council_category"),
                "type": row.get("council_type"),
                "regionalPartnership": row.get("vif_regional_partnership") or "Not classified",
                "hasActivePayCoverage": spatial_key in small_active_keys,
                "governanceBasis": "council_profile_mart.council_category",
            }
        )

    available_keys = {item["spatialKey"] for item in councils}
    return {
        "title": "Victoria LGA boundary context",
        "boundaryGeojsonUrl": BOUNDARY_GEOJSON_URL,
        "source": "council_profile_mart + static/data/victoria-lga-boundaries.geojson",
        "categoryField": "council_category",
        "categoryValue": SMALL_CATEGORY,
        "smallSpatialKeys": [item["spatialKey"] for item in councils],
        "activePaySpatialKeys": [item["spatialKey"] for item in councils if item["hasActivePayCoverage"]],
        "labelSpatialKeys": [key for key in label_keys if key in available_keys],
        "allSmallShireCouncils": councils,
        "legend": [
            {
                "label": "Victorian council boundary",
                "status": "statewide_context",
            },
            {
                "label": "Small shire profile member",
                "status": "controlled_cohort",
            },
            {
                "label": "Small shire with active pay rows",
                "status": "active_pay_coverage",
            },
        ],
        "caveat": "Boundary shading uses controlled council profile metadata. Active pay coverage is narrower than full council coverage and should be carried as a report warning.",
    }


def main() -> None:
    profiles_list = read_csv(DATAMART_DIR / "council_profile_mart.csv")
    profiles = {row["council_key"]: row for row in profiles_list}
    pay_range_rows = read_csv(DATAMART_DIR / "pay_range_summary_mart.csv")
    uplift_rows = read_csv(DATAMART_DIR / "uplift_timing_mart.csv")
    entitlement_rows = read_csv(DATAMART_DIR / "entitlement_summary_mart.csv")
    active_rows = [
        row
        for row in active_snapshot_rows(pay_range_rows)
        if row_has_report_valid_council(row, profiles)
    ]
    small_councils = [row for row in profiles_list if row.get("council_category") == SMALL_CATEGORY]
    small_active_keys = {
        row.get("canonical_council_id")
        for row in active_rows
        if row_category(row, profiles) == SMALL_CATEGORY
    }
    pay_bands = band_rows(active_rows, profiles)
    band5 = next(row for row in pay_bands if row["band"] == FOCUS_BAND)
    band6 = next(row for row in pay_bands if row["band"] == 6)
    largest_gap = max(pay_bands, key=lambda row: abs(float(row["gap"] or 0)))
    current_row_counts = Counter(row.get("standard_band") for row in active_rows)
    category_counts = Counter(row_category(row, profiles) for row in active_rows)

    payload = {
        "metadata": {
            "reportId": "small-council-state-scroll-report",
            "title": "How do small councils compare to the state?",
            "subtitle": "Small councils are often assumed to sit behind the broader sector. The real picture is more uneven - and more useful.",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "jurisdiction": "Victoria, Australia",
            "dataStatus": "workspace_snapshot_mixed_governance",
            "decisionUse": "exploratory_not_for_decision_making_without_review",
            "prototypeLabel": "Workspace data snapshot - mixed governance status",
            "caveat": "This version uses real local EBA Workbench datamart values, including governed pay-derived rows and staged or partial downstream assets. It is suitable for product demonstration and analytical review, not external decision-making without governance sign-off.",
            "futureSourcePath": "Replace this file with a reviewed report_product_input_mart payload once the report asset is promoted.",
            "asOfDate": AS_OF_DATE,
            "horizonDate": HORIZON_DATE,
            "snapshotRule": {
                "payRows": "Report date must fall inside the pay row operative window.",
                "operativeFrom": "pay_range_summary_mart.effective_from",
                "operativeTo": "pay_range_summary_mart.effective_to, or effective_from + 1 calendar year when effective_to is blank",
                "councilEligibility": "canonical council must be active in council_profile_mart",
            },
        },
        "reportManifest": {
            "asset_id": "prototype_small_council_state_scroll_report_workspace_snapshot",
            "asset_type": "report_asset",
            "title": "Small Council vs State Scrollytelling Prototype - Workspace Snapshot",
            "report_title_candidate": "How do small councils compare to the state?",
            "source_dataset": "local_datamart_workspace_snapshot",
            "source_dataset_version": f"local_{AS_OF_DATE.replace('-', '_')}_active_snapshot",
            "generated_by": "build-workspace-snapshot.py",
            "status": "draft",
            "brand_profile": "executive_digital_report",
            "comparison_basis": "council_category_small_shire_vs_active_statewide_snapshot",
            "period_basis": f"active_as_of_{AS_OF_DATE}_plus_horizon_{HORIZON_DATE}",
            "sourceDatasetsExpectedLater": [
                "council_profile_mart",
                "cohort_comparison_mart",
                "pay_range_summary_mart",
                "pay_distribution_point_mart",
                "uplift_timing_mart",
                "entitlement_summary_mart",
                "evidence_trace_mart",
                "report_product_input_mart",
            ],
            "quality_flags": [
                "workspace_snapshot",
                "mixed_governance_status",
                "entitlement_taxonomy_not_presence_scoring",
                "active_snapshot_coverage_not_full_sector_current_state",
                "blank_effective_to_rows_use_one_year_operative_window",
            ],
            "metric_definition": "Active weekly range midpoint rates by standard band, comparing council_category=Small shire with active statewide rows.",
            "visual_encoding": {
                "pay_point_galaxy": "custom_svg_temporal_pay_scatter",
                "pay_chart": "custom_svg_band_median_gap_chart",
                "distribution_chart": "custom_svg_midpoint_distribution_points",
                "uplift_chart": "custom_svg_cycle_horizon_view",
                "entitlement_matrix": "semantic_dom_matrix",
            },
        },
        "heroMetrics": [
            {
                "label": "Small shire pay cohort",
                "value": str(len(small_active_keys)),
                "detail": f"active pay councils as at {AS_OF_DATE}",
                "source": "pay_range_summary_mart + council_profile_mart",
            },
            {
                "label": "Statewide active pay universe",
                "value": str(len({row.get("canonical_council_id") for row in active_rows})),
                "detail": "councils with active band rows",
                "source": "pay_range_summary_mart",
            },
            {
                "label": "Band 5 median gap",
                "value": f"${abs(round(band5['gap'])):,.0f}",
                "detail": "Small shire below statewide weekly midpoint",
                "source": "range_midpoint_rate",
            },
            {
                "label": "Agreement timing coverage",
                "value": f"{build_uplift_timeline(active_rows, profiles, uplift_rows)['coverage']['smallBand5Rows']}",
                "detail": "Small shire Band 5 rows in horizon analysis",
                "source": "uplift_timing_mart",
            },
        ],
        "payPointGalaxy": build_pay_point_galaxy(pay_range_rows, profiles),
        "cohort": {
            "title": "Small shire is a controlled cohort, not a handpicked peer set.",
            "definition": "This version uses the controlled council_category field from council_profile_mart: Small shire.",
            "smallCouncilDefinition": "Victorian councils where council_category equals Small shire in the local council profile mart.",
            "statewideDefinition": f"All councils with active standard band range midpoint rows as at {AS_OF_DATE}.",
            "productionCaveat": "The cohort definition is real local metadata, but final production reporting should still carry governance status and coverage warnings.",
            "map": build_cohort_map(small_councils, small_active_keys),
            "smallCouncilExamples": [
                {
                    "name": row["canonical_council_name"],
                    "type": row.get("council_type") or SMALL_CATEGORY,
                    "placeholderRole": "controlled cohort member",
                }
                for row in small_councils[:8]
            ],
            "comparisonUniverse": {
                "smallCouncilCount": len(small_councils),
                "smallCouncilPayCoverage": len(small_active_keys),
                "statewideCouncilCount": len(profiles_list),
                "statewidePayCoverage": len({row.get("canonical_council_id") for row in active_rows}),
                "bandCount": len(BANDS),
            },
        },
        "evidenceChain": [
            {
                "stage": "Council identity",
                "description": "Small shire membership comes from controlled council profile metadata.",
            },
            {
                "stage": "Governed pay ranges",
                "description": "Active weekly midpoint rows are derived from pay_range_summary_mart.",
            },
            {
                "stage": "Distribution asset logic",
                "description": "Distribution framing follows the existing distribution-point report asset contract.",
            },
            {
                "stage": "Uplift rules",
                "description": "Scheduled horizon changes use uplift_timing_mart where rules land before the horizon date.",
            },
            {
                "stage": "Draft report asset",
                "description": "This standalone web report remains a draft product layer until reviewed.",
            },
        ],
        "payByBand": {
            "question": "Do small councils pay less?",
            "metric": "Weekly range midpoint rate",
            "units": "AUD per week",
            "currentPeriod": f"Active snapshot as at {AS_OF_DATE}",
            "payMetricSet": "pay_structure_semantics_v1",
            "bands": pay_bands,
            "states": {
                "state_only": {
                    "label": "Statewide active median",
                    "summary": "Start with active statewide midpoint rows for Bands 1-8.",
                },
                "small_vs_state": {
                    "label": "Small shire vs state",
                    "summary": "Layer the controlled Small shire cohort over the active statewide pattern.",
                },
                "gap_highlight": {
                    "label": "Largest observed gaps",
                    "summary": f"The largest weekly median gap in this snapshot is Band {largest_gap['band']} ({largest_gap['gap']:+.2f}).",
                },
                "band_focus": {
                    "label": "Narrower gaps",
                    "summary": "Some bands sit closer, which changes the executive interpretation.",
                },
                "timing_sensitive": {
                    "label": "Timing sensitive",
                    "summary": "Bands 5 and 6 are the pressure point and connect directly to the uplift horizon.",
                },
                "takeaway": {
                    "label": "Takeaway",
                    "summary": "The live workspace data shows a consistent Small shire discount, but the size and meaning vary by band.",
                },
            },
            "takeaway": f"In the active {AS_OF_DATE} workspace snapshot, Small shire medians sit below the statewide median across Bands 1-8. The gap is most commercially interesting around Bands 5-6: Band 5 is ${abs(round(band5['gap'])):,.0f}/week lower and Band 6 is ${abs(round(band6['gap'])):,.0f}/week lower on the explicit range_midpoint_rate metric.",
            "coverage": {
                "activeRows": len(active_rows),
                "bandRowCounts": dict(current_row_counts),
                "categoryRowCounts": dict(category_counts),
            },
        },
        "distribution": build_distribution(active_rows, profiles, pay_bands, pay_range_rows),
        "classificationContext": {
            "question": "Are we comparing the same workforce shape?",
            "summary": "Band-level comparison reduces noise, but it does not remove workforce-shape risk. The active pay rows show stronger mid-band exposure, where councils often face professional, technical, supervisory, and specialist recruitment pressure.",
            "bands": [
                {
                    "band": band,
                    "label": f"Band {band}",
                    "workforceSignal": {
                        1: "entry / operational support",
                        2: "routine operational roles",
                        3: "skilled operational and administrative roles",
                        4: "experienced technical and service roles",
                        5: "professional / supervisory pressure point",
                        6: "senior professional and specialist roles",
                        7: "advanced specialist / management roles",
                        8: "senior management / principal roles",
                    }[band],
                }
                for band in BANDS
            ],
            "productionNote": "Production reporting should add workforce composition weights; this prototype compares available active band midpoint rows without headcount weighting.",
        },
        "upliftTimeline": build_uplift_timeline(active_rows, profiles, uplift_rows),
        "entitlements": build_entitlements(entitlement_rows),
        "executiveTakeaways": [
            {
                "title": "Exposure",
                "body": f"Small shire medians are below the active statewide median across all analysed bands, with the most useful sales/demo story around Bands 5-6.",
            },
            {
                "title": "Distribution",
                "body": "The Band 5 distribution shows overlap with the state, so the story is not a simplistic lower-versus-higher binary.",
            },
            {
                "title": "Timing risk",
                "body": "Known future uplift rules narrow or reshape some gaps by the horizon date, which is exactly where the workbench adds value.",
            },
        ],
        "narrativeSteps": [
            {
                "id": "state-only",
                "visualState": "state_only",
                "eyebrow": "Reference",
                "title": "Start with the active state",
                "body": "The statewide line now uses real active range midpoint rows from the local mart, not placeholder values.",
                "annotation": "Statewide median only",
            },
            {
                "id": "small-vs-state",
                "visualState": "small_vs_state",
                "eyebrow": "Comparison",
                "title": "Layer the Small shire cohort",
                "body": "The controlled Small shire cohort sits below the state across each standard band in this workspace snapshot.",
                "annotation": "Small shire median added",
            },
            {
                "id": "gap-highlight",
                "visualState": "gap_highlight",
                "eyebrow": "Exposure",
                "title": "The gap concentrates in mid and upper bands",
                "body": "Bands 5 and 6 are the sharper executive story because the weekly difference is larger and easier to connect to attraction and retention pressure.",
                "annotation": "Largest gaps highlighted",
            },
            {
                "id": "band-focus",
                "visualState": "band_focus",
                "eyebrow": "Nuance",
                "title": "Lower bands are closer",
                "body": "The lower-band gap exists, but the magnitude is smaller. That matters when deciding where exposure is operationally meaningful.",
                "annotation": "Narrower gaps highlighted",
            },
            {
                "id": "timing-sensitive",
                "visualState": "timing_sensitive",
                "eyebrow": "Timing",
                "title": "The pay horizon changes the reading",
                "body": "The current snapshot is not the full answer. Scheduled uplifts can narrow, widen, or re-order the comparison by the next horizon.",
                "annotation": "Timing-sensitive bands marked",
            },
            {
                "id": "takeaway",
                "visualState": "takeaway",
                "eyebrow": "Takeaway",
                "title": "The answer is real, but conditional",
                "body": "The workspace data supports a sharper claim than the placeholder prototype: Small shire councils sit lower on active midpoint pay, but the report needs distribution, timing, and coverage caveats to be credible.",
                "annotation": "Executive reading",
            },
        ],
    }

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
