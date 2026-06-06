from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Callable


SCHEMA_VERSION = "end_of_band_dollars.v1"

_PAGE_MARKER_RE = re.compile(r"^===== PAGE\s+(\d+) =====\n", re.MULTILINE)
_TERM_RE = re.compile(r"(?i)\b(?:end[-\s]+of[-\s]+band|top[-\s]+of[-\s]+band)\b")
_CASHISH_RE = re.compile(r"(?i)\b(?:payment|payments|lump\s+sum|bonus|amount|salary|earnings|ote|mid[-\s]?point)\b")
_DOLLAR_RE = re.compile(r"\$\s*\d[\d,]*(?:\.\d+)?|(?<![\d.])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d.])")
_PCT_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:%|per\s+cent)(?![a-z])", re.IGNORECASE)
_CLAUSE_RE = re.compile(
    r"(?P<number>\b\d+(?:\.\d+){0,4})\.?\s+(?P<heading>[A-Z][A-Za-z\s/-]{0,80}?(?:End|Top)[-\s]+of[-\s]+Band[A-Za-z\s/-]{0,80})",
    re.IGNORECASE,
)
_BAND_TOKEN_RE = re.compile(r"\b(?:band|bands)\s+([0-9,\sand&-]+)", re.IGNORECASE)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _money_value(value: str) -> float | None:
    text = str(value or "").replace("$", "").replace(",", "").strip()
    try:
        number = float(text)
    except ValueError:
        return None
    if number <= 0:
        return None
    return round(number, 2)


def _money_values(text: str) -> list[float]:
    values: list[float] = []
    for match in _DOLLAR_RE.finditer(text):
        value = _money_value(match.group(0))
        if value is None:
            continue
        if value not in values:
            values.append(value)
    return values


def _pct_values(text: str) -> list[float]:
    values: list[float] = []
    for match in _PCT_RE.finditer(text):
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        if 0 < value < 100 and value not in values:
            values.append(value)
    return values


def _read_pages_json(path: Path) -> list[tuple[int, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [(index, str(text or "")) for index, text in enumerate(payload, start=1)]


def cached_page_texts(root: Path, ae_id: str) -> list[tuple[int, str]]:
    cache_ids = [ae_id.lower()]
    if "__" in ae_id:
        cache_ids.append(ae_id.lower().split("__", 1)[0])
    for cache_id in cache_ids:
        cache_dir = root / "cache" / cache_id
        full_text_path = cache_dir / "full_text.txt"
        if full_text_path.exists():
            text = full_text_path.read_text(encoding="utf-8", errors="ignore")
            markers = list(_PAGE_MARKER_RE.finditer(text))
            if markers:
                pages: list[tuple[int, str]] = []
                for index, marker in enumerate(markers):
                    start = marker.end()
                    end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
                    pages.append((int(marker.group(1)), text[start:end]))
                return pages
        pages_path = cache_dir / "pages.json"
        if pages_path.exists():
            pages = _read_pages_json(pages_path)
            if pages:
                return pages
    return []


def _snippet_for_match(text: str, start: int, end: int, radius: int = 1800) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return _clean_text(text[left:right])


def _exclusion_reasons(snippet: str) -> list[str]:
    text = snippet.lower()
    money = _money_values(snippet)
    reasons: list[str] = []
    if len(money) > 20 and max(money or [0]) > 10000:
        reasons.append("pay_table_rate_matrix_not_clause")
    if "built into" in text or "absorbed into existing pay scales" in text or "no further claims" in text:
        reasons.append("absorbed_or_built_into_pay_scale")
    if "annual leave" in text or "service recognition leave" in text:
        reasons.append("leave_not_cash")
    if "reward and recognition" in text or "end of band recognition" in text or "radar" in text:
        reasons.append("recognition_program_not_cash")
    if "qualification allowance" in text or "higher qualifications allowance" in text:
        reasons.append("allowance_context_not_eob_cash")
    if "grandfather" in text or "eligible existing employees" in text:
        reasons.append("grandfathered_or_closed_cohort")
    if "only for employees who commenced" in text or "commenced prior" in text or "commenced before" in text:
        reasons.append("grandfathered_or_closed_cohort")
    if re.search(r"\bemployees(?:\s+of\s+council)?\s+as\s+at\s+\d{1,2}\s+june\b", text):
        reasons.append("grandfathered_or_closed_cohort")
    if "will continue to qualify" in text:
        reasons.append("grandfathered_or_closed_cohort")
    if "not entitled to any other" in text or "not eligible for the end of band payment as detailed above" in text:
        reasons.append("not_current_positive_entitlement")
    one_off = "one-off" in text or "one off" in text
    if one_off and "annual basis" not in text and ("as at " in text or "vote closes" in text or "cost of living" in text):
        reasons.append("one_off_or_date_gated_bonus")
    return sorted(set(reasons))


def _clause_fields(snippet: str) -> tuple[str | None, str | None]:
    matches = list(_CLAUSE_RE.finditer(snippet))
    if not matches:
        return None, None
    match = matches[-1]
    return match.group("number"), _clean_text(match.group("heading"))


def _candidate_score(snippet: str, has_cash: bool, exclusions: list[str]) -> int:
    text = snippet.lower()
    score = 0
    if has_cash:
        score += 20
    if "shall be entitled" in text or "will be entitled" in text:
        score += 12
    if "lump sum" in text or "per annum" in text:
        score += 8
    if "whichever is greater" in text:
        score += 6
    if "end of band payment" in text or "top of band payment" in text:
        score += 10
    if "table of contents" in text or "................................................................" in text:
        score -= 15
    if "allowance table" in text and "shall be entitled" not in text:
        score -= 8
    if len(_money_values(snippet)) > 8:
        score -= 25
    if exclusions:
        score -= 40
    return score


def _rule_kind(snippet: str, money: list[float], percentages: list[float]) -> str:
    text = snippet.lower()
    if "whichever is greater" in text and percentages and money:
        return "best_of_fixed_or_percentage"
    if "mid-point" in text or "midpoint" in text:
        return "midpoint_formula"
    if _strathbogie_band_amounts(snippet):
        return "band_specific"
    if len(money) > 1 and ("year 1" in text or "1st year" in text or "subsequent" in text):
        return "tiered_max"
    if percentages and not money:
        return "percentage_of_salary"
    return "fixed_cash"


def end_of_band_candidates(root: Path, ae_id: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for page, text in cached_page_texts(root, ae_id):
        for match in _TERM_RE.finditer(text):
            snippet = _snippet_for_match(text, match.start(), match.end())
            value_window = _snippet_for_match(text, match.start(), match.end(), radius=500)
            money = _money_values(value_window)
            percentages = _pct_values(value_window)
            has_cash = bool(money or (percentages and _CASHISH_RE.search(value_window)) or "midpoint" in value_window.lower())
            exclusions = sorted(set([*_exclusion_reasons(value_window), *_exclusion_reasons(snippet)]))
            clause_number, clause_heading = _clause_fields(snippet)
            candidates.append({
                "page": page,
                "match_text": match.group(0),
                "clause_number": clause_number,
                "clause_heading": clause_heading,
                "amounts": money,
                "percentages": percentages,
                "cash_candidate": has_cash,
                "exclusion_reasons": exclusions,
                "rule_kind": _rule_kind(snippet, money, percentages),
                "score": _candidate_score(value_window, has_cash, exclusions),
                "extract": snippet[:2400],
            })
    candidates.sort(key=lambda item: (int(item["score"]), int(item["page"])), reverse=True)
    return candidates


def select_end_of_band_rule(root: Path, ae_id: str) -> dict[str, Any] | None:
    candidates = end_of_band_candidates(root, ae_id)
    for candidate in candidates:
        if candidate.get("cash_candidate") and not candidate.get("exclusion_reasons"):
            return candidate
    return None


def _normalised_band(value: Any) -> str | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return str(int(match.group(0))) if match else str(value).strip() or None


def _weekly_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _band_stats(table: dict[str, Any]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for row in table.get("rows") or []:
        if not isinstance(row, dict):
            continue
        band = _normalised_band(row.get("standard_band") or row.get("band"))
        weekly = _weekly_number(row.get("weekly_rate"))
        if band is None or weekly is None:
            continue
        bucket = stats.setdefault(band, {"min_weekly_rate": weekly, "max_weekly_rate": weekly})
        bucket["min_weekly_rate"] = min(bucket["min_weekly_rate"], weekly)
        bucket["max_weekly_rate"] = max(bucket["max_weekly_rate"], weekly)
    return stats


def _parse_rate_table_effective_date(text: str) -> str | None:
    match = re.search(
        r"effective\s+full\s+pay\s+period\s+commencing\s+on\s+or\s+after\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d %B %Y").date().isoformat()
    except ValueError:
        return None


def _parse_explicit_e_level_rows(text: str) -> dict[str, dict[str, float]]:
    if "E (End of Band)" not in text:
        return {}
    lines = [_clean_text(line) for line in text.splitlines() if _clean_text(line)]
    rows: dict[str, dict[str, float]] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not re.fullmatch(r"\d{1,2}", line):
            index += 1
            continue
        band = str(int(line))
        values: list[float | None] = []
        cursor = index + 1
        while cursor < len(lines):
            current = lines[cursor]
            if re.fullmatch(r"\d{1,2}", current) or re.match(r"\d+(?:\.\d+)+\b", current):
                break
            if current.lower() == "n/a":
                values.append(None)
            else:
                money = _money_value(current)
                if money is not None:
                    values.append(money)
            cursor += 1
        if len(values) >= 10:
            weekly_values = [values[position] for position in (0, 2, 4, 6, 8)]
            upper_weekly = next(
                (value for value in reversed(weekly_values[:4]) if value is not None),
                None,
            )
            e_weekly = weekly_values[4]
            if upper_weekly is not None and e_weekly is not None and e_weekly > upper_weekly:
                rows[band] = {
                    "upper_weekly_rate": upper_weekly,
                    "end_of_band_weekly_rate": e_weekly,
                }
        index = cursor if cursor > index else index + 1
    return rows


def explicit_e_level_rate_tables(root: Path, ae_id: str) -> dict[str, dict[str, dict[str, float]]]:
    tables: dict[str, dict[str, dict[str, float]]] = {}
    for _page, text in cached_page_texts(root, ae_id):
        effective_from = _parse_rate_table_effective_date(text)
        if not effective_from:
            continue
        rows = _parse_explicit_e_level_rows(text)
        if rows:
            tables[effective_from] = rows
    return tables


def _explicit_e_rates_for_period(
    tables: dict[str, dict[str, dict[str, float]]],
    effective_from: Any,
) -> tuple[dict[str, dict[str, float]], str | None]:
    if not tables:
        return {}, None
    period_date = str(effective_from or "")
    if period_date in tables:
        return tables[period_date], period_date
    return {}, None


def _band_sort_key(band: str) -> tuple[int, str]:
    match = re.search(r"\d+", band)
    return (int(match.group(0)) if match else 9999, band)


def _parse_band_set(text: str) -> set[str]:
    bands: set[str] = set()
    cleaned = text.replace("&", " and ")
    for start, end in re.findall(r"(\d+)\s*-\s*(\d+)", cleaned):
        for number in range(int(start), int(end) + 1):
            bands.add(str(number))
    for number in re.findall(r"\d+", cleaned):
        bands.add(str(int(number)))
    return bands


def _strathbogie_band_amounts(snippet: str) -> dict[str, float]:
    text = snippet.lower()
    if not ("bands 1" in text and "bands 4" in text and "$750" in text.replace(",", "")):
        return {}
    amounts: dict[str, float] = {}
    if re.search(r"bands?\s+1\s*(?:&|and)\s*3", text) and re.search(r"\$?\s*1,?000", text):
        amounts.update({"1": 1000.0, "3": 1000.0})
    if re.search(r"bands?\s+4\s*(?:-|to)\s*8", text) and re.search(r"\$?\s*750", text):
        for band in range(4, 9):
            amounts[str(band)] = 750.0
    return amounts


def _band_specific_amounts(rule: dict[str, Any]) -> dict[str, float]:
    snippet = str(rule.get("extract") or "")
    special = _strathbogie_band_amounts(snippet)
    if special:
        return special
    amounts: dict[str, float] = {}
    for match in _BAND_TOKEN_RE.finditer(snippet):
        band_text = match.group(1)
        tail = snippet[match.end():match.end() + 160]
        money = _money_values(tail)
        if not money:
            continue
        for band in _parse_band_set(band_text):
            amounts[band] = max(money)
    return amounts


def _next_band_min_weekly(band: str, band_stats: dict[str, dict[str, float]]) -> float | None:
    current_key = _band_sort_key(band)[0]
    higher = [
        (number, stats["min_weekly_rate"])
        for candidate, stats in band_stats.items()
        for number in [_band_sort_key(candidate)[0]]
        if number > current_key
    ]
    if not higher:
        return None
    higher.sort(key=lambda item: item[0])
    return higher[0][1]


def resolve_amount_for_band(
    rule: dict[str, Any],
    band: str,
    band_stats: dict[str, dict[str, float]],
    explicit_e_rates: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any] | None:
    snippet = str(rule.get("extract") or "")
    kind = str(rule.get("rule_kind") or "fixed_cash")
    amounts = [float(value) for value in (rule.get("amounts") or []) if value not in (None, "")]
    percentages = [float(value) for value in (rule.get("percentages") or []) if value not in (None, "")]
    stats = band_stats.get(band) or {}
    max_weekly = stats.get("max_weekly_rate")
    if kind == "band_specific":
        band_amounts = _band_specific_amounts(rule)
        amount = band_amounts.get(band)
        if amount is None:
            return None
        return {
            "amount": amount,
            "amount_basis": "band_specific_clause_amount",
            "calculation_status": "explicit_clause_amount",
            "max_weekly_rate": max_weekly,
            "next_band_min_weekly_rate": None,
        }
    if kind == "midpoint_formula":
        floor = max(amounts) if amounts else None
        next_min = _next_band_min_weekly(band, band_stats)
        explicit_e = (explicit_e_rates or {}).get(band)
        if max_weekly is not None and explicit_e:
            base_upper = explicit_e.get("upper_weekly_rate")
            base_e = explicit_e.get("end_of_band_weekly_rate")
            if base_upper and base_e and base_upper > 0 and base_e > base_upper:
                uplift_ratio = max_weekly / base_upper
                e_weekly = round(base_e * uplift_ratio, 2)
                explicit_delta = max(0.0, (e_weekly - max_weekly) * 52.0)
                amount = max([value for value in [floor, explicit_delta] if value is not None])
                return {
                    "amount": round(amount, 2),
                    "amount_basis": "greater_of_fixed_floor_or_eob_rate_table_delta",
                    "calculation_status": "computed_from_eob_rate_table",
                    "max_weekly_rate": max_weekly,
                    "next_band_min_weekly_rate": next_min,
                    "end_of_band_weekly_rate": e_weekly,
                }
        if max_weekly is not None and next_min is not None:
            midpoint_gap_amount = max(0.0, ((next_min - max_weekly) * 52.0) / 2.0)
            amount = max([value for value in [floor, midpoint_gap_amount] if value is not None])
            return {
                "amount": round(amount, 2),
                "amount_basis": "greater_of_fixed_floor_or_next_band_midpoint_gap",
                "calculation_status": "computed_from_governed_weekly_band_gap",
                "max_weekly_rate": max_weekly,
                "next_band_min_weekly_rate": next_min,
            }
        if floor is None:
            return None
        return {
            "amount": floor,
            "amount_basis": "fixed_floor_midpoint_formula_unresolved",
            "calculation_status": "formula_floor_only",
            "max_weekly_rate": max_weekly,
            "next_band_min_weekly_rate": next_min,
        }
    percentage_amount = None
    if percentages and max_weekly is not None:
        percentage_amount = max_weekly * 52.0 * max(percentages) / 100.0
    fixed_amount = max(amounts) if amounts else None
    if kind == "best_of_fixed_or_percentage":
        if fixed_amount is None and percentage_amount is None:
            return None
        amount = max(value for value in [fixed_amount, percentage_amount] if value is not None)
        return {
            "amount": round(amount, 2),
            "amount_basis": "greater_of_fixed_amount_or_percentage_of_annualised_weekly_rate",
            "calculation_status": "computed_from_governed_weekly_rate" if percentage_amount is not None else "explicit_clause_amount",
            "max_weekly_rate": max_weekly,
            "next_band_min_weekly_rate": None,
        }
    if kind == "percentage_of_salary":
        if percentage_amount is None:
            return None
        return {
            "amount": round(percentage_amount, 2),
            "amount_basis": "percentage_of_annualised_weekly_rate",
            "calculation_status": "computed_from_governed_weekly_rate",
            "max_weekly_rate": max_weekly,
            "next_band_min_weekly_rate": None,
        }
    if fixed_amount is None:
        return None
    basis = "explicit_clause_amount"
    if "per annum" in snippet.lower():
        basis = "explicit_annual_clause_amount"
    return {
        "amount": fixed_amount,
        "amount_basis": basis,
        "calculation_status": "explicit_clause_amount",
        "max_weekly_rate": max_weekly,
        "next_band_min_weekly_rate": None,
    }


def project_end_of_band_rows(
    *,
    ae_id: str,
    canonical: dict[str, Any],
    root: Path,
    registry_name: str | None,
    lga_short_name: str | None,
    geography_fields: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates = end_of_band_candidates(root, ae_id)
    rule = next(
        (candidate for candidate in candidates if candidate.get("cash_candidate") and not candidate.get("exclusion_reasons")),
        None,
    )
    periods = ((((canonical.get("sections") or {}).get("uplifts") or {}).get("data") or {}).get("periods") or [])
    governed_period_count = 0
    rows: list[dict[str, Any]] = []
    if rule is None:
        return rows, {
            "candidate_count": len(candidates),
            "excluded_candidate_count": len([item for item in candidates if item.get("exclusion_reasons")]),
            "governed_periods": len([period for period in periods if isinstance(period, dict)]),
            "source_text_status": "candidate_not_found" if not candidates else "no_in_scope_cash_candidate",
        }
    agreement_name = canonical.get("source_name") or registry_name or ae_id
    explicit_e_tables = (
        explicit_e_level_rate_tables(root, ae_id)
        if rule.get("rule_kind") == "midpoint_formula"
        else {}
    )
    for period_index, period in enumerate(periods):
        if not isinstance(period, dict):
            continue
        pay_table = period.get("pay_table")
        governed_at = period.get("pay_table_governed_at")
        if not isinstance(pay_table, dict) or not governed_at:
            continue
        governed_period_count += 1
        band_stats = _band_stats(pay_table)
        explicit_e_rates, explicit_e_source_effective_from = _explicit_e_rates_for_period(
            explicit_e_tables,
            period.get("effective_from") or pay_table.get("effective_from"),
        )
        period_effective_from = period.get("effective_from") or pay_table.get("effective_from")
        for band in sorted(band_stats, key=_band_sort_key):
            resolved = resolve_amount_for_band(
                rule,
                band,
                band_stats,
                explicit_e_rates,
            )
            if resolved is None:
                continue
            amount = resolved["amount"]
            rows.append({
                "end_of_band_id": f"eob::{ae_id}::{period_index}::band_{band}",
                "ae_id": ae_id,
                "agreement_name": agreement_name,
                "canonical_lga_short_name": lga_short_name,
                "effective_from": period_effective_from,
                "to_date": pay_table.get("to_date") or period.get("to_date"),
                "period_index": period_index,
                "band": band,
                "end_of_band_cash_amount": amount,
                "amount_basis": resolved["amount_basis"],
                "calculation_status": resolved["calculation_status"],
                "rule_kind": rule.get("rule_kind"),
                "clause_number": rule.get("clause_number"),
                "clause_heading": rule.get("clause_heading"),
                "source_page": rule.get("page"),
                "clause_extract": rule.get("extract"),
                "governed_at": governed_at,
                "source_text_status": "in_scope_cash_candidate",
                "candidate_count": len(candidates),
                "excluded_candidate_count": len([item for item in candidates if item.get("exclusion_reasons")]),
                "max_weekly_rate": resolved.get("max_weekly_rate"),
                "next_band_min_weekly_rate": resolved.get("next_band_min_weekly_rate"),
                "end_of_band_weekly_rate": resolved.get("end_of_band_weekly_rate"),
                "end_of_band_rate_source_effective_from": explicit_e_source_effective_from,
                **geography_fields,
            })
    return rows, {
        "candidate_count": len(candidates),
        "excluded_candidate_count": len([item for item in candidates if item.get("exclusion_reasons")]),
        "governed_periods": governed_period_count,
        "source_text_status": "in_scope_cash_candidate",
    }


def build_end_of_band_dollars_analysis(
    *,
    visible_ae_ids: list[str],
    load_registry: Callable[[], dict[str, str]],
    load_multi_council_decisions: Callable[[], dict[str, dict[str, Any]]],
    get_canonical: Callable[[str], dict[str, Any]],
    fetch_metadata_for_ae_id: Callable[..., dict[str, Any]],
    resolve_canonical_lga_short_name: Callable[..., str | None],
    analysis_geography_fields: Callable[[Any], dict[str, Any]],
    root_path: Callable[[], Path],
) -> dict[str, Any]:
    registry = load_registry()
    decisions = load_multi_council_decisions()
    root = root_path()
    rows: list[dict[str, Any]] = []
    agreement_statuses: dict[str, dict[str, Any]] = {}
    governed_periods = 0
    for ae_id in visible_ae_ids:
        canonical = get_canonical(ae_id)
        fetch_metadata = fetch_metadata_for_ae_id(ae_id, decisions)
        lga = resolve_canonical_lga_short_name(ae_id, fetch_metadata, decisions)
        geography = analysis_geography_fields(lga)
        projected, status = project_end_of_band_rows(
            ae_id=ae_id,
            canonical=canonical,
            root=root,
            registry_name=registry.get(ae_id),
            lga_short_name=lga,
            geography_fields=geography,
        )
        rows.extend(projected)
        governed_periods += int(status.get("governed_periods") or 0)
        agreement_statuses[ae_id] = status
    rows.sort(key=lambda item: (
        str(item.get("effective_from") or "9999-99-99"),
        str(item.get("canonical_lga_short_name") or item.get("agreement_name") or "").lower(),
        _band_sort_key(str(item.get("band") or "")),
    ))
    patterns: dict[str, int] = {}
    for row in rows:
        key = str(row.get("rule_kind") or "unknown")
        patterns[key] = patterns.get(key, 0) + 1
    dates = [
        str(row.get("effective_from"))
        for row in rows
        if isinstance(row.get("effective_from"), str) and re.match(r"^\d{4}-\d{2}-\d{2}$", str(row.get("effective_from")))
    ]
    agreement_ids = {str(row.get("ae_id")) for row in rows if row.get("ae_id")}
    band_keys = {(str(row.get("ae_id")), str(row.get("effective_from")), str(row.get("band"))) for row in rows}
    return {
        "set_id": "set_4_end_of_band_dollars",
        "schema_version": SCHEMA_VERSION,
        "label": "End of Band Dollars",
        "description": "Band-level governed cash end-of-band amounts derived from agreement clause text and governed pay periods.",
        "summary": {
            "agreements_scanned": len(visible_ae_ids),
            "agreements_with_end_of_band_cash": len(agreement_ids),
            "governed_periods": governed_periods,
            "bands": len(band_keys),
            "rows": len(rows),
            "candidates": sum(int(item.get("candidate_count") or 0) for item in agreement_statuses.values()),
            "excluded_candidates": sum(int(item.get("excluded_candidate_count") or 0) for item in agreement_statuses.values()),
            "earliest_effective_from": min(dates) if dates else None,
            "latest_effective_from": max(dates) if dates else None,
        },
        "patterns": [
            {"pattern": key, "count": count}
            for key, count in sorted(patterns.items(), key=lambda item: (-item[1], item[0]))
        ],
        "agreement_statuses": agreement_statuses,
        "rows": rows,
    }
