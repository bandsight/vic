from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

DISPLAY_EMPTY = "Not stated"
PAY_STRUCTURE_METRIC_TOKENS = {
    "entry_rate",
    "entry rate",
    "capacity_rate",
    "capacity rate",
    "range_midpoint_rate",
    "range midpoint",
    "midpoint rate",
    "service_year_1_rate",
    "service horizon year 1",
    "year 1 service-horizon",
    "year-1",
    "year 1",
    "service_year_2_rate",
    "service horizon year 2",
    "year 2 service-horizon",
    "year-2",
    "year 2",
    "service_year_3_rate",
    "service horizon year 3",
    "year 3 service-horizon",
    "year-3",
    "year 3",
    "service_year_4_rate",
    "service horizon year 4",
    "year 4 service-horizon",
    "year-4",
    "year 4",
    "service_year_5_rate",
    "service horizon year 5",
    "year 5 service-horizon",
    "year-5",
    "year 5",
    "service_year_6_rate",
    "service horizon year 6",
    "year 6 service-horizon",
    "year-6",
    "year 6",
    "progression spread",
    "step mean",
}

_ISO_DATETIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ]")


def display_value(value: Any, empty: str = DISPLAY_EMPTY) -> str:
    if value is None or value == "":
        return empty
    if isinstance(value, list):
        values = [display_value(item, "") for item in value]
        cleaned = [item for item in values if item]
        return ", ".join(cleaned) if cleaned else empty
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def display_code_label(value: Any, empty: str = DISPLAY_EMPTY) -> str:
    raw = display_value(value, empty)
    if raw == "title_only_unresolved":
        return empty
    return raw if raw == empty else raw.replace("_", " ")


def display_date(value: Any, empty: str = DISPLAY_EMPTY) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = display_value(value, "").strip()
    if not raw:
        return empty
    match = _ISO_DATETIME_RE.match(raw)
    if match:
        return match.group(1)
    return raw


def display_date_range(start: Any, end: Any, empty: str = "Dates not stated") -> str:
    from_date = display_date(start, "")
    to_date = display_date(end, "")
    if from_date and to_date:
        return f"{from_date} to {to_date}"
    if from_date:
        return f"{from_date} to open ended"
    if to_date:
        return f"Until {to_date}"
    return empty


def display_pages(value: Any, empty: str = DISPLAY_EMPTY) -> str:
    pages = value if isinstance(value, list) else ([] if value is None or value == "" else [value])
    clean = [str(page).strip() for page in pages if str(page).strip()]
    if not clean:
        return empty
    prefix = "p." if len(clean) == 1 else "pp."
    return f"{prefix} {', '.join(clean)}"


def _number_from(value: Any, *, strip: str = "") -> float | None:
    if value is None or value == "":
        return None
    try:
        raw = str(value)
        for char in strip:
            raw = raw.replace(char, "")
        raw = raw.replace(",", "").strip()
        return float(raw)
    except (TypeError, ValueError):
        return None


def display_number(value: Any, empty: str = DISPLAY_EMPTY) -> str:
    number = _number_from(value)
    if number is None:
        return empty if value is None or value == "" else str(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,}"


def display_currency(value: Any, empty: str = DISPLAY_EMPTY) -> str:
    number = _number_from(value, strip="$")
    if number is None:
        return empty if value is None or value == "" else str(value)
    return f"A${number:,.2f}"


def display_currency_delta(value: Any, empty: str = DISPLAY_EMPTY) -> str:
    number = _number_from(value, strip="$")
    if number is None:
        return empty if value is None or value == "" else str(value)
    sign = "+" if number >= 0 else "-"
    return f"{sign}{display_currency(abs(number), empty)}"


def display_percent(value: Any, empty: str = DISPLAY_EMPTY) -> str:
    number = _number_from(value, strip="%")
    if number is None:
        return empty if value is None or value == "" else str(value)
    text = str(int(number)) if number.is_integer() else f"{number:.2f}".rstrip("0").rstrip(".")
    return f"{text}%"


def display_fraction_percent(value: Any, empty: str = DISPLAY_EMPTY) -> str:
    number = _number_from(value)
    if number is None:
        return empty if value is None or value == "" else str(value)
    return display_percent(number * 100, empty)


def display_percent_delta(value: Any, empty: str = DISPLAY_EMPTY, *, fraction: bool = False) -> str:
    number = _number_from(value)
    if number is None:
        return empty if value is None or value == "" else str(value)
    percent_value = abs(number) * 100 if fraction else abs(number)
    sign = "+" if number >= 0 else "-"
    return f"{sign}{display_percent(percent_value, empty)}"


def display_file_size(value: Any, empty: str = DISPLAY_EMPTY) -> str:
    size = _number_from(value)
    if size is None or size < 0:
        return empty
    if size < 1024:
        return f"{int(size)} B" if size.is_integer() else f"{size:g} B"
    units = ["KB", "MB", "GB"]
    current = size / 1024
    unit_index = 0
    while current >= 1024 and unit_index < len(units) - 1:
        current /= 1024
        unit_index += 1
    amount = f"{current:.0f}" if current >= 10 else f"{current:.1f}"
    return f"{amount} {units[unit_index]}"


def validate_pay_metric_claim(
    claim: str,
    comparison_metric: str | None = None,
    *,
    actual_step_count: int | None = None,
    progression_rule_status: str | None = None,
) -> dict[str, Any]:
    text = str(claim or "").strip().lower()
    unsafe_ordinal = any(token in text for token in ["level 6", "year 6 level", "sixth increment", "6th increment"])
    if unsafe_ordinal and (actual_step_count is None or actual_step_count < 6):
        return {
            "valid": False,
            "comparison_metric": comparison_metric,
            "reason": "unsafe_service_horizon_ordinal_language",
            "recommended_action": "Use service-horizon/capacity carry-forward language; do not imply a sixth structural level.",
        }
    if "after six years of service" in text and progression_rule_status not in {"governed", "reviewed", "accepted"}:
        return {
            "valid": False,
            "comparison_metric": comparison_metric,
            "reason": "ungoverned_progression_claim",
            "recommended_action": "Use caveated service-horizon wording unless governed progression logic supports the claim.",
        }
    explicit = bool(comparison_metric) or any(token in text for token in PAY_STRUCTURE_METRIC_TOKENS)
    pay_claim = any(token in text for token in ["pay", "rate", "band", "market", "median", "above", "below", "position"])
    comparative = any(token in text for token in ["above", "below", "market", "median", "position", "higher", "lower", "sits"])
    valid = explicit or not (pay_claim and comparative)
    return {
        "valid": valid,
        "comparison_metric": comparison_metric,
        "reason": None if valid else "pay_metric_missing",
        "recommended_action": None if valid else "State entry, capacity, range midpoint, service-horizon, or spread metric before using this claim.",
    }


def validate_service_horizon_chart_title(
    title: str,
    *,
    standard_band: str | int | None = None,
    cohort_name: str | None = None,
    service_horizon_window_label: str | None = None,
) -> dict[str, Any]:
    text = str(title or "").strip().lower()
    band_text = f"band {standard_band}".lower() if standard_band not in (None, "") else None
    missing: list[str] = []
    if band_text and band_text not in text:
        missing.append("band")
    if service_horizon_window_label and str(service_horizon_window_label).strip().lower() not in text:
        missing.append("service_horizon_window_label")
    has_window_language = any(
        token in text
        for token in [
            "entry rate",
            "capacity rate",
            "service-horizon",
            "entry-to-year",
            "year-3-to-year-6",
            "entry-to-capacity",
        ]
    )
    if not has_window_language:
        missing.append("service_horizon_window")
    if cohort_name and str(cohort_name).strip().lower() not in text:
        missing.append("cohort")
    if missing:
        return {
            "valid": False,
            "reason": "chart_title_missing_service_horizon_context",
            "missing": sorted(set(missing)),
            "recommended_action": "State band, cohort, and service_horizon_window_label in chart titles.",
        }
    return {
        "valid": True,
        "reason": None,
        "missing": [],
        "recommended_action": None,
    }


def pay_table_report_values(table: dict[str, Any] | None) -> dict[str, str]:
    table = table or {}
    page_value = table.get("source_pages") if table.get("source_pages") is not None else table.get("source_page")
    return {
        "table_title": display_value(table.get("table_title")),
        "source_clause": display_value(table.get("source_clause")),
        "source_pages": display_pages(page_value),
        "effective_from": display_date(table.get("effective_from")),
        "to_date": display_date(table.get("to_date")),
        "effective_period": display_date_range(table.get("effective_from"), table.get("to_date")),
        "rate_kind": display_code_label(table.get("rate_kind")),
    }


def agreement_report_values(
    *,
    canonical: dict[str, Any] | None,
    fetch_metadata: dict[str, Any] | None = None,
    pdf_source: dict[str, Any] | None = None,
    landed_at: Any = None,
    pay_table_summary: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    canonical = canonical or {}
    fetch_metadata = fetch_metadata or {}
    pdf_source = pdf_source or {}
    overview = canonical.get("overview") if isinstance(canonical.get("overview"), dict) else {}
    fwc = canonical.get("fwc") if isinstance(canonical.get("fwc"), dict) else {}
    operative_date = fwc.get("operative_date") or fetch_metadata.get("Operative Date")
    expiry_date = fwc.get("expiry_date") or fetch_metadata.get("Expiry Date")
    pay_tables = pay_table_summary or []
    fetched_pdf_size = display_file_size(pdf_source.get("file_size_bytes"))
    fetched_pdf_health = display_code_label(pdf_source.get("size_status"))
    return {
        "agreement_period": display_date_range(operative_date, expiry_date),
        "operative_date": display_date(operative_date),
        "expiry_date": display_date(expiry_date),
        "landed_at": display_date(landed_at),
        "page_count": display_number(overview.get("page_count")),
        "likely_pay_table_pages": display_pages(overview.get("likely_pay_table_pages") or []),
        "likely_uplift_pages": display_pages(overview.get("likely_uplift_pages") or []),
        "fetched_pdf_size": fetched_pdf_size,
        "fetched_pdf_health": fetched_pdf_health,
        "frozen_pdf_size": fetched_pdf_size,
        "frozen_pdf_health": fetched_pdf_health,
        "pay_table_count": display_number(len(pay_tables)),
    }


def fetch_metadata_report_values(
    fetch_metadata: dict[str, Any] | None,
    *,
    pdf_source: dict[str, Any] | None = None,
) -> dict[str, str]:
    fetch_metadata = fetch_metadata or {}
    pdf_source = pdf_source or {}
    fetched_pdf_size = display_file_size(pdf_source.get("file_size_bytes"))
    fetched_pdf_health = display_code_label(pdf_source.get("size_status"))
    return {
        "agreement_period": display_date_range(fetch_metadata.get("Operative Date"), fetch_metadata.get("Expiry Date")),
        "operative_date": display_date(fetch_metadata.get("Operative Date")),
        "expiry_date": display_date(fetch_metadata.get("Expiry Date")),
        "agreement_number": display_value(fetch_metadata.get("agreement_num_clean")),
        "match_strength": display_code_label(fetch_metadata.get("match_strength")),
        "scope_resolution_status": display_code_label(fetch_metadata.get("scope_resolution_status")),
        "fetched_pdf_size": fetched_pdf_size,
        "fetched_pdf_health": fetched_pdf_health,
        "frozen_pdf_size": fetched_pdf_size,
        "frozen_pdf_health": fetched_pdf_health,
    }
