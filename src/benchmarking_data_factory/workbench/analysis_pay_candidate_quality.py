from __future__ import annotations

from collections import Counter
import re
from typing import Any, Callable

from benchmarking_data_factory.uplift_rules.section_picker import (
    DOLLAR_PATTERN,
    PAY_KEYWORDS,
    UPLIFT_KEYWORDS,
    is_toc_like,
)


_ALLOWANCE_FALSE_POSITIVE_RE = re.compile(
    r"\b(allowance|allowances|expense|expenses|reimbursement|meal|travel|tool|uniform|first\s+aid|"
    r"vehicle|kilometre|laundry|telephone|on[-\s]?call|standby|overtime|penalt(?:y|ies))\b",
    re.IGNORECASE,
)
_SPECIALIST_FALSE_POSITIVE_RE = re.compile(
    r"\b(maternal|child\s+health|immunisation|nurse|library|leisure|aquatic|early\s+childhood|"
    r"school\s+crossing|sessional|waste|recycling|outdoor|infrastructure|executive|"
    r"senior\s+officer|coordinator|team\s+leader|preschool)\b",
    re.IGNORECASE,
)
_APPENDIX_FALSE_POSITIVE_RE = re.compile(
    r"\b(appendix|schedule|annex(?:ure)?|undertaking|variation|side[-\s]?letter|special\s+conditions)\b",
    re.IGNORECASE,
)
_STANDARD_PAY_TABLE_RE = re.compile(
    r"\b(band\s+\d|level\s+[A-D1-4]|weekly\s+rate|annual\s+rate|salary\s+scale|classification)\b",
    re.IGNORECASE,
)


def _normalise_page_list(values: Any) -> list[int]:
    raw_values = values if isinstance(values, list) else [values]
    pages: set[int] = set()
    for value in raw_values:
        try:
            page = int(value)
        except (TypeError, ValueError):
            continue
        if page > 0:
            pages.add(page)
    return sorted(pages)


def _candidate_pay_pages_from_canonical(canonical: dict[str, Any]) -> list[int]:
    overview = canonical.get("overview") or {}
    overview_section = (((canonical.get("sections") or {}).get("overview") or {}).get("data") or {})
    return _normalise_page_list([
        *(overview.get("likely_pay_table_pages") or []),
        *(overview_section.get("likely_pay_table_pages") or []),
    ])


def _table_source_pages(table: dict[str, Any]) -> list[int]:
    values: list[Any] = []
    for key in ("source_pages", "pages"):
        raw = table.get(key)
        if isinstance(raw, list):
            values.extend(raw)
        elif raw is not None:
            values.append(raw)
    for key in ("source_page", "page"):
        if table.get(key) is not None:
            values.append(table.get(key))
    for row in table.get("rows") or []:
        if not isinstance(row, dict):
            continue
        raw_pages = row.get("source_pages")
        if isinstance(raw_pages, list):
            values.extend(raw_pages)
        elif raw_pages is not None:
            values.append(raw_pages)
        if row.get("source_page") is not None:
            values.append(row.get("source_page"))
    return _normalise_page_list(values)


def _used_pay_pages_from_canonical(canonical: dict[str, Any]) -> list[int]:
    values: list[int] = []
    pay_tables = (((canonical.get("sections") or {}).get("pay_tables") or {}).get("tables") or [])
    for table in pay_tables:
        if isinstance(table, dict):
            values.extend(_table_source_pages(table))
    periods = ((((canonical.get("sections") or {}).get("uplifts") or {}).get("data") or {}).get("periods") or [])
    for period in periods:
        if not isinstance(period, dict):
            continue
        table = period.get("pay_table")
        if isinstance(table, dict):
            values.extend(_table_source_pages(table))
    return _normalise_page_list(values)


def _short_text_excerpt(text: str, limit: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def _pay_candidate_page_signal(
    ae_id: str,
    page: int,
    *,
    extract_page_text: Callable[[str, int], str],
) -> dict[str, Any]:
    text = extract_page_text(ae_id, page) or ""
    dollar_count = len(DOLLAR_PATTERN.findall(text))
    pay_keyword_count = len(PAY_KEYWORDS.findall(text))
    uplift_keyword_count = len(UPLIFT_KEYWORDS.findall(text))
    standard_signal = bool(_STANDARD_PAY_TABLE_RE.search(text))
    allowance_signal = bool(_ALLOWANCE_FALSE_POSITIVE_RE.search(text))
    specialist_signal = bool(_SPECIALIST_FALSE_POSITIVE_RE.search(text))
    appendix_signal = bool(_APPENDIX_FALSE_POSITIVE_RE.search(text))
    hourly_only = bool(re.search(r"\bhourly\s+rate\b", text, re.IGNORECASE)) and not bool(
        re.search(r"\bweekly\s+rate\b|\bannual\s+rate\b", text, re.IGNORECASE)
    )
    if not text.strip():
        reason = "text_unavailable"
    elif is_toc_like(text):
        reason = "toc_like"
    elif hourly_only:
        reason = "hourly_only"
    elif allowance_signal and not standard_signal:
        reason = "allowance_or_penalty_schedule"
    elif specialist_signal:
        reason = "specialist_cohort"
    elif uplift_keyword_count > pay_keyword_count and not standard_signal:
        reason = "uplift_clause_overlap"
    elif appendix_signal and dollar_count >= 3 and not standard_signal:
        reason = "appendix_dollar_density"
    elif dollar_count >= 3 and not standard_signal:
        reason = "dollar_density_only"
    elif pay_keyword_count > 0:
        reason = "pay_keyword_unused"
    else:
        reason = "unknown_unused_candidate"
    return {
        "reason": reason,
        "dollar_count": dollar_count,
        "pay_keyword_count": pay_keyword_count,
        "uplift_keyword_count": uplift_keyword_count,
        "standard_signal": standard_signal,
        "allowance_signal": allowance_signal,
        "specialist_signal": specialist_signal,
        "appendix_signal": appendix_signal,
        "hourly_only": hourly_only,
        "text_available": bool(text.strip()),
        "excerpt": _short_text_excerpt(text),
    }


def _candidate_quality_recommendations(reason_counts: Counter[str]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    if reason_counts.get("allowance_or_penalty_schedule", 0) or reason_counts.get("appendix_dollar_density", 0):
        recommendations.append({
            "rule": "downrank_allowance_dollar_density",
            "message": "Down-rank dollar-dense pages when allowance/penalty terms appear without standard band signals.",
            "evidence_count": reason_counts.get("allowance_or_penalty_schedule", 0) + reason_counts.get("appendix_dollar_density", 0),
        })
    if reason_counts.get("uplift_clause_overlap", 0):
        recommendations.append({
            "rule": "separate_uplift_clause_candidates",
            "message": "Keep uplift-clause pages out of pay-table extraction candidates unless standard table signals are also present.",
            "evidence_count": reason_counts["uplift_clause_overlap"],
        })
    if reason_counts.get("hourly_only", 0):
        recommendations.append({
            "rule": "drop_hourly_only_pages",
            "message": "Drop hourly-only pages from pay-table candidates because extraction skips hourly rates.",
            "evidence_count": reason_counts["hourly_only"],
        })
    if reason_counts.get("specialist_cohort", 0):
        recommendations.append({
            "rule": "downrank_specialist_cohort_pages",
            "message": "Down-rank specialist cohort pages unless they also contain a standard band/level matrix.",
            "evidence_count": reason_counts["specialist_cohort"],
        })
    return recommendations


def build_pay_candidate_quality(
    visible_ae_ids: list[str],
    registry: dict[str, str],
    decisions: dict[str, dict[str, Any]],
    *,
    get_canonical: Callable[[str], dict[str, Any]],
    fetch_metadata_for_ae_id: Callable[[str, dict[str, dict[str, Any]]], dict[str, Any]],
    resolve_canonical_lga_short_name: Callable[[str, dict[str, Any] | None, dict[str, dict[str, Any]] | None], str | None],
    extract_page_text: Callable[[str, int], str],
) -> dict[str, Any]:
    false_positive_pages: list[dict[str, Any]] = []
    missed_used_pages: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    candidate_total = 0
    used_candidate_total = 0
    used_page_total = 0
    agreements_with_candidate_pages = 0
    agreements_with_unused_candidate_pages = 0

    for ae_id in visible_ae_ids:
        canonical = get_canonical(ae_id)
        fetch_metadata = fetch_metadata_for_ae_id(ae_id, decisions)
        lga = resolve_canonical_lga_short_name(ae_id, fetch_metadata, decisions)
        agreement_name = canonical.get("source_name") or registry.get(ae_id) or ae_id
        candidate_pages = _candidate_pay_pages_from_canonical(canonical)
        used_pages = _used_pay_pages_from_canonical(canonical)
        candidate_set = set(candidate_pages)
        used_set = set(used_pages)
        if candidate_set:
            agreements_with_candidate_pages += 1
        candidate_total += len(candidate_set)
        used_page_total += len(used_set)
        used_candidate_total += len(candidate_set & used_set)
        unused_pages = sorted(candidate_set - used_set)
        if unused_pages:
            agreements_with_unused_candidate_pages += 1
        for page in unused_pages:
            signal = _pay_candidate_page_signal(ae_id, page, extract_page_text=extract_page_text)
            reason_counts[signal["reason"]] += 1
            false_positive_pages.append({
                "ae_id": ae_id,
                "agreement_name": agreement_name,
                "canonical_lga_short_name": lga,
                "page": page,
                "candidate_source": "overview.likely_pay_table_pages",
                **signal,
            })
        for page in sorted(used_set - candidate_set):
            missed_used_pages.append({
                "ae_id": ae_id,
                "agreement_name": agreement_name,
                "canonical_lga_short_name": lga,
                "page": page,
                "used_source": "saved_or_governed_pay_table",
            })

    false_positive_pages.sort(key=lambda item: (
        str(item.get("reason") or ""),
        str(item.get("canonical_lga_short_name") or item.get("agreement_name") or ""),
        int(item.get("page") or 0),
    ))
    missed_used_pages.sort(key=lambda item: (
        str(item.get("canonical_lga_short_name") or item.get("agreement_name") or ""),
        int(item.get("page") or 0),
    ))
    unused_total = len(false_positive_pages)
    return {
        "summary": {
            "agreements_with_candidate_pages": agreements_with_candidate_pages,
            "agreements_with_unused_candidate_pages": agreements_with_unused_candidate_pages,
            "candidate_pages": candidate_total,
            "used_candidate_pages": used_candidate_total,
            "unused_candidate_pages": unused_total,
            "used_pages": used_page_total,
            "missed_used_pages": len(missed_used_pages),
            "unused_candidate_rate": round(unused_total / candidate_total, 4) if candidate_total else 0.0,
        },
        "patterns": [
            {"pattern": reason, "count": count}
            for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "false_positive_pages": false_positive_pages,
        "missed_used_pages": missed_used_pages,
        "recommendations": _candidate_quality_recommendations(reason_counts),
    }
