from __future__ import annotations

import json
from typing import Any, Callable

from benchmarking_data_factory.workbench.llm_boundary import is_llm_error


StripJsonPreamble = Callable[[str], str]


def parse_overview_response(
    raw: str,
    page_count: int,
    pay_pages: list[int],
    uplift_pages: list[int],
    alteration_pages: list[int],
    *,
    strip_json_preamble: StripJsonPreamble,
) -> dict[str, Any]:
    cleaned = strip_json_preamble(raw)
    llm_error = is_llm_error(cleaned)
    fallback = {
        "page_count": page_count,
        "likely_pay_table_pages": pay_pages,
        "likely_uplift_pages": uplift_pages,
        "estimated_earliest_commencing": None,
        "estimated_latest_commencing": None,
        "document_structure_notes": "" if llm_error else cleaned,
        "red_flags": [],
        "band_level_alterations": [],
        "generation_warning": cleaned if llm_error else "",
    }
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return fallback

    legacy_period = parsed.get("operative_period")
    legacy_earliest = None
    legacy_latest = None
    if isinstance(legacy_period, str) and " to " in legacy_period:
        parts = [p.strip() for p in legacy_period.split(" to ", 1)]
        if len(parts) == 2:
            legacy_earliest = parts[0] if parts[0] and parts[0].lower() != "null" else None
            legacy_latest = parts[1] if parts[1] and parts[1].lower() != "null" else None
    return {
        "page_count": parsed.get("page_count", page_count),
        "likely_pay_table_pages": parsed.get("likely_pay_table_pages") or pay_pages,
        "likely_uplift_pages": parsed.get("likely_uplift_pages") or uplift_pages,
        "estimated_earliest_commencing": parsed.get("estimated_earliest_commencing") or legacy_earliest,
        "estimated_latest_commencing": parsed.get("estimated_latest_commencing") or legacy_latest,
        "document_structure_notes": parsed.get("document_structure_notes") or "",
        "red_flags": parsed.get("red_flags") or [],
        "band_level_alterations": parsed.get("band_level_alterations") or [],
        "generation_warning": "",
    }


__all__ = ["parse_overview_response"]
