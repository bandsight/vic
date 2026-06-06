from __future__ import annotations

import re
from typing import Any


def _analysis_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).replace("%", "").replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _analysis_rule_has_rate_cap(rule: dict[str, Any]) -> bool:
    archetype = str(rule.get("pattern_archetype") or "").lower()
    variant = str(rule.get("pattern_variant") or "").lower()
    source_quantum = str(rule.get("source_quantum") or rule.get("quantum") or "").lower()
    source_external_ref = str(rule.get("source_external_ref") or rule.get("quantum_external_ref") or "").lower()
    return any([
        rule.get("rate_cap_component") not in (None, ""),
        rule.get("pct_of_rate_cap") not in (None, ""),
        "rate_cap" in archetype,
        "rate cap" in variant,
        "rate cap" in source_quantum,
        "rate cap" in source_external_ref,
    ])


_ANALYSIS_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_ANALYSIS_RATE_CAP_TAIL_RE = re.compile(
    r"\s+of\s+(?:the\s+)?(?:[a-z]+\s+)?rate\s*-?\s*cap",
    re.IGNORECASE,
)
_ANALYSIS_DELTA_TAIL_RE = re.compile(
    r"\s+(above|below|greater\s+than|less\s+than)\s+(?:the\s+)?(?:official\s+)?(?:general\s+)?rate\s*-?\s*cap",
    re.IGNORECASE,
)
_ANALYSIS_RATE_CAP_HEAD_RE = re.compile(r"rate\s*-?\s*cap\s*\(?\s*$", re.IGNORECASE)
_ANALYSIS_INVERTED_DELTA_RE = re.compile(
    r"rate\s*-?\s*cap\s+(plus|minus|above|below|less|more|greater)\s+(\d+(?:\.\d+)?)%",
    re.IGNORECASE,
)


def _analysis_pct_tokens(text: str) -> dict[str, Any]:
    fixed_pct_candidates: list[float] = []
    cap_display_candidates: list[float] = []
    cap_share: float | None = None
    cap_delta: float | None = None
    for match in _ANALYSIS_PCT_RE.finditer(text or ""):
        value = _analysis_number(match.group(1))
        if value is None:
            continue
        tail = text[match.end():]
        head = text[max(0, match.start() - 28):match.start()]
        if _ANALYSIS_RATE_CAP_TAIL_RE.match(tail):
            cap_share = value / 100.0
            continue
        delta_match = _ANALYSIS_DELTA_TAIL_RE.match(tail)
        if delta_match:
            direction = re.sub(r"\s+", " ", delta_match.group(1).lower().strip())
            cap_delta = value if direction in {"above", "greater than"} else -value
            continue
        if _ANALYSIS_RATE_CAP_HEAD_RE.search(head):
            cap_display_candidates.append(value)
            continue
        fixed_pct_candidates.append(value)

    inverted = _ANALYSIS_INVERTED_DELTA_RE.search(text or "")
    if inverted:
        connector = inverted.group(1).lower()
        value = _analysis_number(inverted.group(2))
        if value is not None:
            cap_delta = value if connector in {"plus", "above", "more", "greater"} else -value

    return {
        "fixed_pct_candidates": fixed_pct_candidates,
        "cap_display_candidates": cap_display_candidates,
        "cap_share": cap_share,
        "cap_delta": cap_delta,
    }


def _analysis_normalise_uplift_rule(
    rule: dict[str, Any],
    *,
    rate_cap_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    variant = str(rule.get("source_quantum") or rule.get("pattern_variant") or rule.get("quantum") or "")
    has_rate_cap = _analysis_rule_has_rate_cap(rule)
    resolution = rate_cap_resolution or {}
    tokens = _analysis_pct_tokens(variant)

    raw_pct_component = _analysis_number(rule.get("pct_component"))
    raw_dollar_component = _analysis_number(rule.get("dollar_component"))
    raw_rate_cap_component = (
        _analysis_number(resolution.get("raw_rate_cap"))
        if resolution
        else None
    )
    if raw_rate_cap_component is None:
        raw_rate_cap_component = _analysis_number(rule.get("rate_cap_component"))
    raw_pct_of_rate_cap = (
        _analysis_number(resolution.get("fraction"))
        if resolution
        else None
    )
    if raw_pct_of_rate_cap is None:
        raw_pct_of_rate_cap = _analysis_number(rule.get("pct_of_rate_cap"))
    raw_floor_pct = (
        _analysis_number(resolution.get("fixed_floor_pct"))
        if resolution
        else None
    )
    if raw_floor_pct is None:
        raw_floor_pct = _analysis_number(rule.get("floor_pct"))
    raw_floor_dollar = (
        _analysis_number(resolution.get("dollar_floor_per_week"))
        if resolution
        else None
    )
    if raw_floor_dollar is None:
        raw_floor_dollar = _analysis_number(rule.get("floor_dollar"))

    fixed_candidates = tokens["fixed_pct_candidates"]
    internal_pct = raw_floor_pct if has_rate_cap and raw_floor_pct is not None else None
    if internal_pct is None:
        internal_pct = max(fixed_candidates) if has_rate_cap and fixed_candidates else raw_pct_component
    external_cap_pct = raw_rate_cap_component
    if external_cap_pct is None and tokens["cap_display_candidates"]:
        external_cap_pct = max(tokens["cap_display_candidates"])

    external_cap_share = raw_pct_of_rate_cap if raw_pct_of_rate_cap is not None else tokens["cap_share"]
    if external_cap_share is None and has_rate_cap and raw_pct_of_rate_cap and 0 < raw_pct_of_rate_cap <= 2:
        external_cap_share = raw_pct_of_rate_cap
    if external_cap_share is None and has_rate_cap:
        external_cap_share = 1.0

    external_delta_pct = _analysis_number(resolution.get("delta")) if resolution else None
    if external_delta_pct is None:
        external_delta_pct = tokens["cap_delta"]
    external_formula_pct = None
    if external_cap_pct is not None and (external_cap_share is not None or external_delta_pct is not None):
        external_formula_pct = external_cap_pct * (external_cap_share if external_cap_share is not None else 1.0)
        if external_delta_pct is not None:
            external_formula_pct += external_delta_pct
        external_formula_pct = round(external_formula_pct, 6)

    pattern_archetype = str(rule.get("pattern_archetype") or "")
    dollar_floor = raw_floor_dollar
    if dollar_floor is None and raw_dollar_component is not None and (
        has_rate_cap or pattern_archetype in {"pct_OR_floor", "hybrid"}
    ):
        dollar_floor = raw_dollar_component
    flat_dollar = raw_dollar_component if pattern_archetype == "flat_dollar" else None

    pct_floor = None
    if has_rate_cap and internal_pct is not None:
        pct_floor = internal_pct
    elif raw_floor_pct is not None:
        pct_floor = raw_floor_pct

    resolved_pct = None
    resolved_basis = "unresolved"
    pct_candidates: list[tuple[str, float]] = []
    if external_formula_pct is not None:
        pct_candidates.append(("external_cap", external_formula_pct))
    if internal_pct is not None:
        pct_candidates.append(("internal_pct_floor" if has_rate_cap else "internal_pct", internal_pct))
    if pct_candidates:
        resolved_basis, resolved_pct = max(pct_candidates, key=lambda item: item[1])
        tied = [basis for basis, value in pct_candidates if abs(value - resolved_pct) < 0.000001]
        if len(tied) > 1:
            resolved_basis = "tie_internal_external"
        resolved_pct = round(resolved_pct, 6)

    notes: list[str] = []
    if has_rate_cap and raw_pct_component is not None and raw_pct_component > 20:
        notes.append("Raw pct_component appears to be a rate-cap share, not an internal wage percentage.")
    if dollar_floor is not None:
        notes.append("Resolved percentage does not decide dollar-floor outcomes for individual pay cells.")
    if raw_floor_pct is not None and has_rate_cap and raw_floor_pct != pct_floor:
        notes.append("Raw floor_pct was reinterpreted through rate-cap component parsing.")

    return {
        "internal_pct_component": internal_pct,
        "pct_floor_component": pct_floor,
        "dollar_floor_component": dollar_floor,
        "dollar_floor_basis": rule.get("dollar_basis"),
        "flat_dollar_component": flat_dollar,
        "external_cap_pct": external_cap_pct,
        "external_cap_share": external_cap_share,
        "external_cap_delta_pct": external_delta_pct,
        "external_formula_pct": external_formula_pct,
        "resolved_pct": resolved_pct,
        "resolved_basis": resolved_basis,
        "rate_cap_financial_year": resolution.get("financial_year"),
        "rate_cap_resolution_note": resolution.get("resolution_note"),
        "raw_pct_component": raw_pct_component,
        "raw_pct_of_rate_cap": raw_pct_of_rate_cap,
        "has_rate_cap": has_rate_cap,
        "notes": notes,
    }


def _rate_cap_resolution_for_rule(
    rule: dict[str, Any],
    *,
    lga_short_name: str | None = None,
    effective_from: str | None = None,
) -> dict[str, Any] | None:
    if not lga_short_name or not effective_from or not _analysis_rule_has_rate_cap(rule):
        return None
    quantum = str(rule.get("source_quantum") or rule.get("pattern_variant") or rule.get("quantum") or "")
    external_ref = str(rule.get("source_external_ref") or rule.get("quantum_external_ref") or "")
    if not quantum and not external_ref:
        return None

    from benchmarking_data_factory.uplift_rules.rate_cap.resolver import (  # noqa: PLC0415
        RateCapResolutionError,
        date_to_financial_year,
        resolve_effective_rate,
    )

    try:
        financial_year = date_to_financial_year(str(effective_from))
        resolution = resolve_effective_rate(str(lga_short_name), financial_year, quantum, external_ref)
    except (RateCapResolutionError, TypeError, ValueError):
        return None
    if not isinstance(resolution, dict) or resolution.get("mode") == "no_rate_cap_ref":
        return None
    resolution = dict(resolution)
    resolution["financial_year"] = financial_year
    return resolution


def _normalised_governed_rule_for_response(
    rule: dict[str, Any],
    *,
    lga_short_name: str | None = None,
    effective_from: str | None = None,
) -> dict[str, Any]:
    rate_cap_resolution = _rate_cap_resolution_for_rule(
        rule,
        lga_short_name=lga_short_name,
        effective_from=effective_from or rule.get("effective_date"),
    )
    normalised = _analysis_normalise_uplift_rule(rule, rate_cap_resolution=rate_cap_resolution)
    out = dict(rule)
    out.update({
        "pct_component": normalised["internal_pct_component"],
        "floor_pct": normalised["pct_floor_component"],
        "floor_dollar": normalised["dollar_floor_component"],
        "rate_cap_component": normalised["external_cap_pct"],
        "pct_of_rate_cap": normalised["external_cap_share"],
        "internal_pct_component": normalised["internal_pct_component"],
        "pct_floor_component": normalised["pct_floor_component"],
        "dollar_floor_component": normalised["dollar_floor_component"],
        "dollar_floor_basis": normalised["dollar_floor_basis"],
        "flat_dollar_component": normalised["flat_dollar_component"],
        "external_cap_pct": normalised["external_cap_pct"],
        "external_cap_share": normalised["external_cap_share"],
        "external_cap_delta_pct": normalised["external_cap_delta_pct"],
        "external_formula_pct": normalised["external_formula_pct"],
        "resolved_pct": normalised["resolved_pct"],
        "resolved_basis": normalised["resolved_basis"],
        "rate_cap_financial_year": normalised["rate_cap_financial_year"],
        "rate_cap_resolution_note": normalised["rate_cap_resolution_note"],
        "normalised_components": normalised,
    })
    if normalised["notes"]:
        out["component_parse_notes"] = normalised["notes"]
    return out
