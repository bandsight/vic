"""Rate cap resolver — resolves rate-cap-linked quantum strings to concrete percentages.

Ported from benchmarking project 2026-04-20. Workbench-owned data source:
`src/benchmarking_data_factory/uplift_rules/external/rate-cap/*.csv`.

Public API:
  - RateCapResolutionError
  - date_to_financial_year(date_str) -> "YYYY-YY"
  - get_year_status(financial_year) -> "confirmed" | "pending_exceptions_check" | ...
  - resolve_rate_cap(lga_short_name, financial_year) -> float
  - classify_rate_cap_mode(quantum_string) -> mode label
  - resolve_effective_rate(lga, fy, quantum_string) -> dict
  - get_pending_rate_cap(effective_date) -> (fy, cap_pct) | None
"""
from __future__ import annotations

import csv
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path


class RateCapResolutionError(Exception):
    pass


RATE_CAP_DATA_DIR = Path(__file__).resolve().parent.parent / "external" / "rate-cap"
MATCH_TERMS = ("rate cap", "gazetted", "minister")
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)%")
DOLLAR_FLOOR_RE = re.compile(r"(\$\d+(?:\.\d{1,2})?\s+per\s+week)", re.IGNORECASE)
DOLLAR_FLOOR_VALUE_RE = re.compile(r"\$(\d+(?:\.\d{1,2})?)\s+per\s+week", re.IGNORECASE)
THRESHOLD_DIFFERENCE_TERMS_RE = re.compile(
    r"\bdifference\b.*\b(?:added|add)\b|\b(?:added|add)\b.*\bdifference\b",
    re.IGNORECASE,
)
RATE_CAP_QUALIFIER_WORDS = (
    "official",
    "general",
    "gazetted",
    "local",
    "government",
    "standard",
    "applicable",
    "relevant",
    "statewide",
    "ministerial",
)
RATE_CAP_QUALIFIER_PATTERN = (
    r"(?:(?:"
    + "|".join(RATE_CAP_QUALIFIER_WORDS)
    + r")\s+){0,6}"
)
# Accept only known qualifier words between "of the" and "rate cap".
# This prevents "3% of Base Salary or rate cap" being read as
# "3% of the rate cap"; that phrase means max(3%, rate cap).
FRACTION_RE = re.compile(
    r"(\d+(?:\.\d+)?)%\s+of\s+(?:the\s+)?" + RATE_CAP_QUALIFIER_PATTERN + r"rate\s+cap",
    re.IGNORECASE,
)
DELTA_RE = re.compile(
    r"(\d+(?:\.\d+)?)%\s+(above|below|greater\s+than|less\s+than)\s+(?:the\s+)?"
    + RATE_CAP_QUALIFIER_PATTERN
    + r"rate\s+cap",
    re.IGNORECASE,
)
DELTA_RE_INVERTED = re.compile(
    RATE_CAP_QUALIFIER_PATTERN
    + r"rate\s+cap\s+(plus|minus|above|below|less|more|greater)\s+(\d+(?:\.\d+)?)%",
    re.IGNORECASE,
)
THRESHOLD_RE = re.compile(
    r"rate\s+cap(?:ping)?\b.*?\b(?:exceeds|increases\s+above|above|greater\s+than)\s+(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _load_year_statuses() -> dict[str, dict[str, str]]:
    path = RATE_CAP_DATA_DIR / "rate-cap-year-status.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["financial_year"]: row for row in csv.DictReader(handle)}


@lru_cache(maxsize=1)
def _load_exceptions() -> dict[tuple[str, str], float]:
    path = RATE_CAP_DATA_DIR / "higher-cap-exceptions.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        return {
            (row["lga_short_name"], row["financial_year"]): float(row["approved_cap_pct"])
            for row in rows
            if row.get("approved_cap_pct")
        }


@lru_cache(maxsize=1)
def _load_standard_caps() -> dict[str, float]:
    path = RATE_CAP_DATA_DIR / "standard-statewide-rate-caps.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        return {row["period_year_label"]: float(row["rate_cap_value"]) for row in rows}


def get_year_status(financial_year: str) -> str:
    row = _load_year_statuses().get(financial_year)
    return row["resolution_status"] if row else "unknown"


def date_to_financial_year(date_str: str) -> str:
    text = date_str.strip()
    candidates = [text]

    patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2} [A-Za-z]+ \d{4}\b",
        r"\b[A-Za-z]+ \d{1,2},? \d{4}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidates.append(match.group(0))

    formats = [
        "%Y-%m-%d",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d %B, %Y",
        "%B %d, %Y",
    ]
    for candidate in candidates:
        for fmt in formats:
            try:
                dt = datetime.strptime(candidate, fmt)
                start_year = dt.year if dt.month >= 7 else dt.year - 1
                end_suffix = str((start_year + 1) % 100).zfill(2)
                return f"{start_year}-{end_suffix}"
            except ValueError:
                continue

    raise RateCapResolutionError(f"Unable to parse effective_date: {date_str}")


def resolve_rate_cap(lga_short_name: str, financial_year: str) -> float:
    status = get_year_status(financial_year)
    if status in {"pending_exceptions_check", "blocked"}:
        raise RateCapResolutionError(
            f"Rate cap resolution blocked for {financial_year}: status={status}"
        )
    if status != "confirmed":
        raise RateCapResolutionError(
            f"Rate cap resolution unavailable for {financial_year}: status={status}"
        )

    exception_cap = _load_exceptions().get((lga_short_name, financial_year))
    if exception_cap is not None:
        return exception_cap

    standard_cap = _load_standard_caps().get(financial_year)
    if standard_cap is None:
        raise RateCapResolutionError(
            f"No standard statewide rate cap found for financial year {financial_year}"
        )
    return standard_cap


def classify_rate_cap_mode(quantum_string: str, external_ref: str | None = None) -> str:
    text = quantum_string or ""
    lowered = text.lower()
    if not any(term in lowered for term in MATCH_TERMS):
        # Fallback: rule may reference rate cap via quantum_external_ref instead of inline.
        ext_lowered = (external_ref or "").lower()
        if ext_lowered and any(term in ext_lowered for term in MATCH_TERMS):
            # External ref names rate cap; treat as full rate cap with whatever floor the inline text provides.
            return "full_rate_cap"
        return "no_rate_cap_ref"
    if THRESHOLD_RE.search(text):
        return "rate_cap_threshold"
    if DELTA_RE.search(text) or DELTA_RE_INVERTED.search(text):
        return "rate_cap_plus_minus"
    if FRACTION_RE.search(text):
        return "pct_of_rate_cap"
    return "full_rate_cap"


# Lookahead used by _parse_fixed_floor_pct: mirrors FRACTION_RE so that a
# percentage attached to "of (the) [adj] rate cap" is NOT treated as a fixed
# floor. Without the adjective tolerance, "90% of the OFFICIAL rate cap" was
# being picked up as a 90% floor, producing ~90% wage inflation bugs.
_FRACTION_LOOKAHEAD = re.compile(
    r"\s+of\s+(?:the\s+)?" + RATE_CAP_QUALIFIER_PATTERN + r"rate\s+cap",
    re.IGNORECASE,
)


def _parse_fixed_floor_pct(quantum_string: str) -> float | None:
    text = quantum_string or ""
    for match in PERCENT_RE.finditer(text):
        if _FRACTION_LOOKAHEAD.match(text[match.end():]):
            continue
        return float(match.group(1))
    return None


def resolve_effective_rate(
    lga_short_name: str,
    financial_year: str,
    quantum_string: str,
    external_ref: str | None = None,
) -> dict:
    text = quantum_string or ""
    mode = classify_rate_cap_mode(text, external_ref)

    result = {
        "mode": mode,
        "raw_rate_cap": None,
        "effective_rate": None,
        "fixed_floor_pct": None,
        "dollar_floor": None,
        "dollar_floor_per_week": None,
        "fraction": None,
        "delta": None,
        "threshold": None,
        "resolution_note": "",
        "unresolved": False,
    }

    if mode == "no_rate_cap_ref":
        result["resolution_note"] = "No rate cap reference found in quantum string."
        return result

    raw_rate_cap = resolve_rate_cap(lga_short_name, financial_year)
    result["raw_rate_cap"] = raw_rate_cap
    result["fixed_floor_pct"] = _parse_fixed_floor_pct(text)

    dollar_match = DOLLAR_FLOOR_RE.search(text)
    if dollar_match:
        result["dollar_floor"] = dollar_match.group(1)
        dollar_value_match = DOLLAR_FLOOR_VALUE_RE.search(dollar_match.group(1))
        if dollar_value_match:
            result["dollar_floor_per_week"] = float(dollar_value_match.group(1))

    effective_rate: float | None = None
    floor_already_applied = False

    if mode == "pct_of_rate_cap":
        fraction_match = FRACTION_RE.search(text)
        if fraction_match:
            fraction = float(fraction_match.group(1)) / 100.0
            result["fraction"] = fraction
            effective_rate = raw_rate_cap * fraction
            note = f"Computed {raw_rate_cap:.3f}% × {fraction:.2f}."
        else:
            note = "Could not parse fraction of rate cap."
    elif mode == "rate_cap_plus_minus":
        delta_match = DELTA_RE.search(text)
        if delta_match:
            delta = float(delta_match.group(1))
            direction = re.sub(r"\s+", " ", delta_match.group(2).lower().strip())
            is_positive = direction in {"above", "greater than"}
            signed_delta = delta if is_positive else -delta
            result["delta"] = signed_delta
            effective_rate = raw_rate_cap + signed_delta
            note = f"Computed {raw_rate_cap:.3f}% {direction} {delta:.3f}%."
        else:
            inv_match = DELTA_RE_INVERTED.search(text)
            if inv_match:
                connector = inv_match.group(1).lower()
                delta = float(inv_match.group(2))
                is_positive = connector in {"plus", "above", "more", "greater"}
                signed_delta = delta if is_positive else -delta
                result["delta"] = signed_delta
                effective_rate = raw_rate_cap + signed_delta
                note = f"Computed {raw_rate_cap:.3f}% rate cap {connector} {delta:.3f}%."
            else:
                note = "Could not parse above/below rate cap adjustment."
    elif mode == "rate_cap_threshold":
        threshold_match = THRESHOLD_RE.search(text)
        if threshold_match:
            threshold = float(threshold_match.group(1))
            result["threshold"] = threshold
            floor_pct = result["fixed_floor_pct"]
            if floor_pct is not None and THRESHOLD_DIFFERENCE_TERMS_RE.search(text):
                excess = max(0.0, raw_rate_cap - threshold)
                effective_rate = floor_pct + excess
                note = (
                    f"Computed fixed floor {floor_pct:.3f}% plus rate-cap excess "
                    f"max(0, {raw_rate_cap:.3f}% - {threshold:.3f}%)."
                )
                result["delta"] = excess
                floor_already_applied = True
            elif raw_rate_cap > threshold:
                effective_rate = raw_rate_cap
                note = f"Rate cap {raw_rate_cap:.3f}% exceeds threshold {threshold:.3f}%."
            else:
                note = f"Rate cap {raw_rate_cap:.3f}% does not exceed threshold {threshold:.3f}%."
        else:
            note = "Could not parse threshold condition."
    else:
        effective_rate = raw_rate_cap
        note = f"Using full applicable rate cap {raw_rate_cap:.3f}%."

    floor_pct = result["fixed_floor_pct"]
    if effective_rate is not None and floor_pct is not None and not floor_already_applied:
        effective_rate = max(floor_pct, effective_rate)
        note += f" Applied fixed floor {floor_pct:.3f}% via max()."

    result["effective_rate"] = effective_rate
    result["unresolved"] = effective_rate is None
    result["resolution_note"] = note
    return result


def get_pending_rate_cap(effective_date: str) -> tuple[str, float] | None:
    """
    Get the standard rate cap for a date even if status is pending_exceptions_check.
    Returns (financial_year, cap_pct) or None if unavailable.

    This allows early resolution when the floor > pending cap.
    """
    try:
        fy = date_to_financial_year(effective_date)
    except RateCapResolutionError:
        return None

    status = get_year_status(fy)
    # Allow pending_exceptions_check - we'll use standard cap as lower bound
    if status not in {"confirmed", "pending_exceptions_check"}:
        return None

    standard_cap = _load_standard_caps().get(fy)
    if standard_cap is None:
        return None

    return (fy, standard_cap)


def invalidate_caches() -> None:
    """Clear all LRU caches in this module. Call after writing to the rate cap CSVs."""
    _load_year_statuses.cache_clear()
    _load_exceptions.cache_clear()
    _load_standard_caps.cache_clear()



def get_year_status_row(financial_year: str) -> dict[str, str] | None:
    """Return the full CSV row for a financial year, or None if absent."""
    return _load_year_statuses().get(financial_year)
