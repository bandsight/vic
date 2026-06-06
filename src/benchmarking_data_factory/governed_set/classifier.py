"""Classify an uplift rule into a governed-set metadata payload."""
from __future__ import annotations

import re
from typing import Any

UPLIFT_ARCHETYPES = (
    "flat_pct",
    "flat_dollar",
    "pct_OR_floor",
    "rate_cap_tracking",
    "rate_cap_plus_margin",
    "cpi_linked",
    "stepped_schedule",
    "negotiated_oneoff",
    "hybrid",
    "unclassified",
)

_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_DOLLAR_RE = re.compile(r"\$\s*(\d+(?:,\d{3})*(?:\.\d+)?)")
_RATE_CAP_RE = re.compile(r"\b(rate\s*-?\s*cap|gazetted|esc|essential services|minister)\b", re.IGNORECASE)
_CPI_RE = re.compile(r"\b(cpi|consumer price index|all groups)\b", re.IGNORECASE)
_OR_RE = re.compile(r"\b(whichever\s+is\s+(?:the\s+)?(?:greater|higher)|or\s+\$|greater of|higher of)\b", re.IGNORECASE)
_WEEKLY_RE = re.compile(r"\bper\s+week\b|\bweekly\b|/week", re.IGNORECASE)
_FORTNIGHTLY_RE = re.compile(r"\bper\s+fortnight\b|\bfortnightly\b|/fortnight", re.IGNORECASE)
_ANNUAL_RE = re.compile(r"\bper\s+(?:annum|year)\b|\bannual(?:ly)?\b|/year", re.IGNORECASE)
_RATE_CAP_SHARE_TAIL_RE = re.compile(
    r"\s+of\s+(?:the\s+)?(?:[a-z]+\s+)?rate\s*-?\s*cap",
    re.IGNORECASE,
)
_RATE_CAP_DELTA_TAIL_RE = re.compile(
    r"\s+(above|below|greater\s+than|less\s+than)\s+(?:the\s+)?(?:official\s+)?(?:general\s+)?rate\s*-?\s*cap",
    re.IGNORECASE,
)
_RATE_CAP_HEAD_RE = re.compile(r"rate\s*-?\s*cap\s*\(?\s*$", re.IGNORECASE)
_INVERTED_RATE_CAP_DELTA_RE = re.compile(
    r"rate\s*-?\s*cap\s+(plus|minus|above|below|less|more|greater)\s+(\d+(?:\.\d+)?)%",
    re.IGNORECASE,
)


def _parse_pct(text: str) -> float | None:
    m = _PCT_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _parse_dollar(text: str) -> float | None:
    m = _DOLLAR_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_dollar_basis(text: str) -> str | None:
    if _WEEKLY_RE.search(text):
        return "weekly"
    if _FORTNIGHTLY_RE.search(text):
        return "fortnightly"
    if _ANNUAL_RE.search(text):
        return "annual"
    return None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("%", "").replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _pct_tokens(text: str) -> dict[str, Any]:
    fixed_pct_candidates: list[float] = []
    rate_cap_display_candidates: list[float] = []
    rate_cap_share: float | None = None
    rate_cap_delta: float | None = None

    for match in _PCT_RE.finditer(text or ""):
        value = _to_float(match.group(1))
        if value is None:
            continue
        tail = text[match.end():]
        head = text[max(0, match.start() - 28):match.start()]
        if _RATE_CAP_SHARE_TAIL_RE.match(tail):
            rate_cap_share = value / 100.0
            continue
        delta_match = _RATE_CAP_DELTA_TAIL_RE.match(tail)
        if delta_match:
            direction = re.sub(r"\s+", " ", delta_match.group(1).lower().strip())
            rate_cap_delta = value if direction in {"above", "greater than"} else -value
            continue
        if _RATE_CAP_HEAD_RE.search(head):
            rate_cap_display_candidates.append(value)
            continue
        fixed_pct_candidates.append(value)

    inverted = _INVERTED_RATE_CAP_DELTA_RE.search(text or "")
    if inverted:
        connector = inverted.group(1).lower()
        value = _to_float(inverted.group(2))
        if value is not None:
            rate_cap_delta = value if connector in {"plus", "above", "more", "greater"} else -value

    return {
        "fixed_pct_candidates": fixed_pct_candidates,
        "rate_cap_display_candidates": rate_cap_display_candidates,
        "rate_cap_share": rate_cap_share,
        "rate_cap_delta": rate_cap_delta,
    }


def classify_rule(
    rule: dict[str, Any],
    rate_cap_value: float | None = None,
    rate_cap_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify a single uplift rule into governed-set metadata.

    Args:
        rule: The rule dict from canonical (must contain quantum, quantum_type).
        rate_cap_value: The raw external rate cap % for this period if available.
        rate_cap_resolution: Optional resolver output, including raw cap, cap share,
            fixed floor, dollar floor and effective/resolved percentage.

    Returns:
        A flat dict with the governed metadata fields. All fields present; unknowns are None.
    """
    quantum = str(rule.get("quantum") or "")
    quantum_type = str(rule.get("quantum_type") or "unknown")
    external_ref = str(rule.get("quantum_external_ref") or "")
    resolution = rate_cap_resolution or {}

    tokens = _pct_tokens(quantum)
    fixed_pct_candidates = list(tokens["fixed_pct_candidates"])
    dollar_component = _parse_dollar(quantum)
    dollar_basis = _parse_dollar_basis(quantum) if dollar_component is not None else None

    has_rate_cap_keyword = bool(_RATE_CAP_RE.search(quantum) or _RATE_CAP_RE.search(external_ref))
    has_cpi_keyword = bool(_CPI_RE.search(quantum))
    has_or_keyword = bool(_OR_RE.search(quantum))

    raw_rate_cap = _to_float(resolution.get("raw_rate_cap")) or _to_float(rate_cap_value)
    external_cap_share = _to_float(resolution.get("fraction"))
    if external_cap_share is None:
        external_cap_share = tokens["rate_cap_share"]
    external_cap_delta = _to_float(resolution.get("delta"))
    if external_cap_delta is None:
        external_cap_delta = tokens["rate_cap_delta"]

    if has_rate_cap_keyword and external_cap_share is None and external_cap_delta is None:
        external_cap_share = 1.0

    external_cap_pct = raw_rate_cap
    if external_cap_pct is None and tokens["rate_cap_display_candidates"]:
        external_cap_pct = max(tokens["rate_cap_display_candidates"])

    external_formula_pct = None
    if external_cap_pct is not None and has_rate_cap_keyword:
        external_formula_pct = external_cap_pct * (external_cap_share if external_cap_share is not None else 1.0)
        if external_cap_delta is not None:
            external_formula_pct += external_cap_delta
        external_formula_pct = round(external_formula_pct, 6)

    resolver_fixed_floor = _to_float(resolution.get("fixed_floor_pct"))
    if resolver_fixed_floor is not None:
        fixed_pct_candidates.append(resolver_fixed_floor)

    internal_pct_component: float | None
    pct_floor_component: float | None = None
    if has_rate_cap_keyword:
        internal_pct_component = max(fixed_pct_candidates) if fixed_pct_candidates else None
        if internal_pct_component is not None:
            pct_floor_component = internal_pct_component
    elif has_or_keyword or quantum_type == "pct_OR_floor":
        internal_pct_component = max(fixed_pct_candidates) if fixed_pct_candidates else None
        if len(fixed_pct_candidates) >= 2:
            pct_floor_component = min(fixed_pct_candidates)
    else:
        internal_pct_component = fixed_pct_candidates[0] if fixed_pct_candidates else _parse_pct(quantum)

    floor_dollar: float | None = None
    if has_or_keyword or quantum_type == "pct_OR_floor":
        if dollar_component is not None:
            floor_dollar = dollar_component
    resolver_dollar_floor = _to_float(resolution.get("dollar_floor_per_week"))
    if resolver_dollar_floor is not None:
        floor_dollar = resolver_dollar_floor
        dollar_basis = dollar_basis or "weekly"
    if has_rate_cap_keyword and dollar_component is not None:
        floor_dollar = floor_dollar if floor_dollar is not None else dollar_component

    flat_dollar_component = dollar_component if quantum_type == "flat" and not has_or_keyword else None

    resolver_effective = _to_float(resolution.get("effective_rate"))
    pct_candidates: list[tuple[str, float]] = []
    if external_formula_pct is not None:
        pct_candidates.append(("external_cap", external_formula_pct))
    if internal_pct_component is not None:
        pct_candidates.append(("internal_pct_floor" if has_rate_cap_keyword else "internal_pct", internal_pct_component))
    if resolver_effective is not None:
        resolved_pct = round(resolver_effective, 6)
    elif pct_candidates:
        resolved_pct = round(max(value for _, value in pct_candidates), 6)
    else:
        resolved_pct = None
    resolved_basis = "unresolved"
    if resolved_pct is not None and pct_candidates:
        tied = [basis for basis, value in pct_candidates if abs(value - resolved_pct) < 0.000001]
        if len(tied) > 1:
            resolved_basis = "tie_internal_external"
        elif tied:
            resolved_basis = tied[0]
        elif resolver_effective is not None:
            resolved_basis = "resolver_effective_rate"

    if quantum_type == "table_embedded":
        archetype = "stepped_schedule"
    elif quantum_type == "conditional" or has_rate_cap_keyword:
        comparison_cap = external_formula_pct if external_formula_pct is not None else external_cap_pct
        if internal_pct_component and comparison_cap and internal_pct_component > comparison_cap * 1.05:
            archetype = "rate_cap_plus_margin"
        else:
            archetype = "rate_cap_tracking"
    elif has_cpi_keyword:
        archetype = "cpi_linked"
    elif quantum_type == "pct_OR_floor" or (internal_pct_component is not None and (floor_dollar is not None or pct_floor_component is not None)):
        archetype = "pct_OR_floor"
    elif quantum_type == "percentage" or (internal_pct_component is not None and dollar_component is None):
        archetype = "flat_pct"
    elif quantum_type == "flat" or (dollar_component is not None and internal_pct_component is None):
        archetype = "flat_dollar"
    elif quantum_type == "unknown" and not internal_pct_component and not dollar_component:
        archetype = "unclassified"
    else:
        archetype = "hybrid"

    notes: list[str] = []
    raw_pct = _parse_pct(quantum)
    if has_rate_cap_keyword and raw_pct is not None and raw_pct > 20:
        notes.append("Raw leading percentage is a rate-cap share, not an internal uplift percentage.")
    if floor_dollar is not None:
        notes.append("Dollar floor may decide individual cell outcomes even when resolved_pct is available.")

    return {
        "pct_component": internal_pct_component,
        "dollar_component": dollar_component,
        "dollar_basis": dollar_basis,
        "rate_cap_component": external_cap_pct,
        "pct_of_rate_cap": external_cap_share,
        "floor_dollar": floor_dollar,
        "floor_pct": pct_floor_component,
        "internal_pct_component": internal_pct_component,
        "pct_floor_component": pct_floor_component,
        "dollar_floor_component": floor_dollar,
        "dollar_floor_basis": dollar_basis if floor_dollar is not None else None,
        "flat_dollar_component": flat_dollar_component,
        "external_cap_pct": external_cap_pct,
        "external_cap_share": external_cap_share,
        "external_cap_delta_pct": external_cap_delta,
        "external_formula_pct": external_formula_pct,
        "resolved_pct": resolved_pct,
        "resolved_basis": resolved_basis,
        "component_parse_notes": notes,
        "pattern_archetype": archetype,
        "pattern_variant": quantum.strip(),
        "source_rule_id": rule.get("rule_id") or f"{rule.get('effective_date', '')}::{rule.get('period_label', '')}",
        "source_quantum_type": quantum_type,
        "source_quantum": quantum.strip(),
        "source_external_ref": external_ref or None,
        "effective_date": rule.get("effective_date"),
    }
