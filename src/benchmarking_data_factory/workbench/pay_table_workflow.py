from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import json
from typing import Any, Callable

import yaml
from fastapi import HTTPException


@dataclass(frozen=True)
class PayTableWorkflowDependencies:
    pay_keywords: Any
    uplift_keywords: Any
    page_render_dpi: int
    pay_table_extract_system: str
    pay_table_range_extract_system: str
    valid_section_statuses: set[str]
    find_candidate_pages: Callable[[str, Any], list[int]]
    require_vision_llm: Callable[[], Any]
    render_page_png: Callable[..., bytes]
    extract_page_text: Callable[[str, int], str]
    get_page_count: Callable[[str], int]
    call_llm: Callable[..., str]
    is_llm_error: Callable[[str], bool]
    llm_http_failure: Callable[..., HTTPException]
    strip_fences: Callable[[str], str]
    strip_json_preamble: Callable[[str], str]
    normalise_extracted_pay_table_candidates: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    get_canonical: Callable[[str], dict[str, Any]]
    fetch_metadata_for_ae_id: Callable[..., dict[str, Any] | None]
    build_provenance_stamp: Callable[[dict[str, Any], dict[str, Any] | None, str], dict[str, Any]]
    apply_section_status: Callable[..., Any]
    now_iso: Callable[[], str]
    get_nominated_expiry: Callable[[dict[str, Any]], str | None]
    get_uplift_rule_dates: Callable[[dict[str, Any]], list[str]]
    apply_timeline_policy_to_tables: Callable[..., dict[str, Any]]
    recalc_to_dates: Callable[..., Any]
    validate_pay_tables: Callable[[list[dict[str, Any]], str | None], list[dict[str, Any]]]
    pay_table_qa_events: Callable[..., list[dict[str, Any]]]
    append_qa_events: Callable[[Any, list[dict[str, Any]]], list[dict[str, Any]]]
    save_canonical: Callable[[str, dict[str, Any]], None]
    find_pdf: Callable[[str], Any]
    anthropic_client: Callable[[], Any]
    collect_uplift_pages_text: Callable[[str], list[dict[str, Any]]]


def find_pay_table_candidate_pages(ae_id: str, deps: PayTableWorkflowDependencies) -> dict[str, Any]:
    pay_table_pages = deps.find_candidate_pages(ae_id, deps.pay_keywords)
    uplift_rule_pages = deps.find_candidate_pages(ae_id, deps.uplift_keywords)
    candidate_pages = list(dict.fromkeys([*pay_table_pages, *uplift_rule_pages]))
    return {
        "candidate_pages": candidate_pages,
        "pay_table_pages": pay_table_pages,
        "uplift_rule_pages": uplift_rule_pages,
    }


def _stamp_extracted_tables(ae_id: str, tables: list[dict[str, Any]], deps: PayTableWorkflowDependencies) -> None:
    canonical = deps.get_canonical(ae_id)
    fetch_metadata = deps.fetch_metadata_for_ae_id(ae_id)
    stamp = deps.build_provenance_stamp(canonical, fetch_metadata, ae_id)
    for table in tables:
        table["provenance"] = stamp


def extract_pay_table_page(ae_id: str, request: Any, deps: PayTableWorkflowDependencies) -> dict[str, Any]:
    deps.require_vision_llm()
    page_num = request.page_num
    png_bytes = deps.render_page_png(ae_id, page_num, dpi=deps.page_render_dpi)
    page_text = deps.extract_page_text(ae_id, page_num)
    page_count = deps.get_page_count(ae_id)
    nearby_context: list[str] = []
    for context_page in (page_num - 1, page_num + 1):
        if 1 <= context_page <= page_count:
            nearby_context.append(f"[Nearby page {context_page} text]\n{deps.extract_page_text(ae_id, context_page)[:1500]}")
    b64 = base64.b64encode(png_bytes).decode("ascii")
    raw = deps.call_llm(
        deps.pay_table_extract_system,
        [
            {"type": "text", "text": f"Page {page_num} text:\n{page_text[:4000]}"},
            *({"type": "text", "text": context} for context in nearby_context),
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64},
            },
            {"type": "text", "text": f"Extract every pay-rate table on page {page_num}. Return YAML only."},
        ],
        max_tokens=16000,
    )
    if deps.is_llm_error(raw):
        raise deps.llm_http_failure(raw, action="extract_pay_table_page", message="Pay-table extraction failed.")
    cleaned = deps.strip_fences(raw)
    try:
        parsed = yaml.safe_load(cleaned) if cleaned else None
    except yaml.YAMLError as exc:
        return {"error": str(exc), "raw": raw, "tables": []}

    tables: list[dict[str, Any]] = []
    if isinstance(parsed, dict) and isinstance(parsed.get("tables"), list):
        tables = deps.normalise_extracted_pay_table_candidates([t for t in parsed["tables"] if isinstance(t, dict)])
    _stamp_extracted_tables(ae_id, tables, deps)
    return {"tables": tables, "raw": raw}


def extract_pay_table_range(ae_id: str, request: Any, deps: PayTableWorkflowDependencies) -> dict[str, Any]:
    start = max(1, request.start_page)
    end = min(deps.get_page_count(ae_id), request.end_page)
    if end < start:
        return {"error": "end_page < start_page", "tables": [], "raw": ""}
    if end - start + 1 > 20:
        return {"error": "range too large (max 20 pages)", "tables": [], "raw": ""}
    deps.require_vision_llm()

    content: list[dict[str, Any]] = []
    if start > 1:
        content.append({"type": "text", "text": f"[Nearby page {start - 1} text]\n{deps.extract_page_text(ae_id, start - 1)[:1500]}"})
    for page_num in range(start, end + 1):
        page_text = deps.extract_page_text(ae_id, page_num)[:3000]
        content.append({"type": "text", "text": f"[Page {page_num} text]\n{page_text}"})
        png_bytes = deps.render_page_png(ae_id, page_num, dpi=deps.page_render_dpi)
        b64 = base64.b64encode(png_bytes).decode("ascii")
        content.append({"type": "text", "text": f"[Page {page_num} image follows]"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        })
    page_count = deps.get_page_count(ae_id)
    if end < page_count:
        content.append({"type": "text", "text": f"[Nearby page {end + 1} text]\n{deps.extract_page_text(ae_id, end + 1)[:1500]}"})
    content.append({"type": "text", "text": f"Extract all pay-rate tables across pages {start}-{end}. Return YAML only."})

    raw = deps.call_llm(deps.pay_table_range_extract_system, content, max_tokens=16000)
    if deps.is_llm_error(raw):
        raise deps.llm_http_failure(raw, action="extract_pay_table_range", message="Pay-table range extraction failed.")
    cleaned = deps.strip_fences(raw)
    try:
        parsed = yaml.safe_load(cleaned) if cleaned else None
    except yaml.YAMLError as exc:
        return {"error": str(exc), "raw": raw, "tables": []}

    tables: list[dict[str, Any]] = []
    if isinstance(parsed, dict) and isinstance(parsed.get("tables"), list):
        tables = deps.normalise_extracted_pay_table_candidates([t for t in parsed["tables"] if isinstance(t, dict)])
    _stamp_extracted_tables(ae_id, tables, deps)
    return {"tables": tables, "raw": raw}


def save_pay_tables(ae_id: str, request: Any, deps: PayTableWorkflowDependencies) -> dict[str, Any]:
    if request.action not in {"append", "replace"}:
        raise HTTPException(status_code=400, detail="Invalid action")
    if request.status not in deps.valid_section_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")
    canonical = deps.get_canonical(ae_id)
    section = canonical["sections"]["pay_tables"]
    previous_tables = deepcopy(section.get("tables") or [])
    previous_notes = section.get("notes", "")
    previous_source_ref = section.get("source_ref", "")
    if request.action == "replace":
        section["tables"] = request.tables
    else:
        section.setdefault("tables", []).extend(request.tables)
    section["source_ref"] = request.source_ref
    section["notes"] = request.notes
    deps.apply_section_status(section, "done", deps.now_iso())

    missing_provenance = [table for table in section["tables"] if not table.get("provenance")]
    if missing_provenance:
        fetch_metadata = deps.fetch_metadata_for_ae_id(ae_id)
        stamp = deps.build_provenance_stamp(canonical, fetch_metadata, ae_id)
        for table in missing_provenance:
            table["provenance"] = stamp

    nominated_expiry = deps.get_nominated_expiry(canonical)
    uplift_rule_dates = deps.get_uplift_rule_dates(canonical)
    timeline_result = deps.apply_timeline_policy_to_tables(
        section["tables"],
        request.timeline_policy,
        uplift_rule_dates,
    )
    deps.recalc_to_dates(section["tables"], nominated_expiry, uplift_rule_dates)
    section["timeline_policy"] = request.timeline_policy
    section["timeline_policy_status"] = timeline_result["timeline_policy_status"]
    section["timeline_policy_issue"] = timeline_result["timeline_policy_issue"]

    from benchmarking_data_factory.uplift_rules import snap_rule_dates_to_tables  # noqa: PLC0415
    from benchmarking_data_factory.uplift_rules.table_alignment import (  # noqa: PLC0415
        record_rule_table_alignment_issues,
    )

    snap_rule_dates_to_tables(canonical)
    section["validations"] = deps.validate_pay_tables(section["tables"], nominated_expiry)
    alignment_issues = record_rule_table_alignment_issues(canonical)
    if alignment_issues:
        deps.apply_section_status(canonical["sections"]["uplift_rules"], "flagged", None)
    has_dup = any(
        validation.get("code") == "duplicate_effective_kind" and validation.get("level") == "error"
        for validation in section["validations"]
    )
    if has_dup:
        raise HTTPException(status_code=400, detail={
            "code": "duplicate_effective_kind",
            "message": "Duplicate (effective_from, rate_kind) pairs block save. Resolve conflicts first.",
            "validations": section["validations"],
        })
    changed_at = deps.now_iso()
    qa_events = deps.pay_table_qa_events(
        previous_tables,
        section.get("tables") or [],
        previous_notes,
        section.get("notes", ""),
        previous_source_ref,
        section.get("source_ref", ""),
        changed_at,
        {"action": request.action, "timeline_policy": request.timeline_policy},
    )
    section["qa_events"] = deps.append_qa_events(section.get("qa_events"), qa_events)
    deps.save_canonical(ae_id, canonical)
    return {
        "ok": True,
        "section_status": section.get("status"),
        "completed_at": section.get("completed_at"),
        "validations": section["validations"],
        "uplift_rule_table_alignment_issues": alignment_issues,
        "timeline_policy_status": section.get("timeline_policy_status"),
        "timeline_policy_issue": section.get("timeline_policy_issue"),
        "qa_events": section.get("qa_events", []),
    }


def validate_pay_table_section(ae_id: str, deps: PayTableWorkflowDependencies) -> dict[str, Any]:
    canonical = deps.get_canonical(ae_id)
    tables = canonical["sections"]["pay_tables"].get("tables", []) or []
    nominated_expiry = deps.get_nominated_expiry(canonical)
    return {"validations": deps.validate_pay_tables(tables, nominated_expiry)}


def recalc_pay_table_dates(ae_id: str, request: Any | None, deps: PayTableWorkflowDependencies) -> dict[str, Any]:
    canonical = deps.get_canonical(ae_id)
    section = canonical["sections"]["pay_tables"]
    tables = section.get("tables", []) or []
    nominated_expiry = deps.get_nominated_expiry(canonical)
    timeline_policy = request.timeline_policy if request else "rule_anchored"
    uplift_rule_dates = deps.get_uplift_rule_dates(canonical)
    timeline_result = deps.apply_timeline_policy_to_tables(
        tables,
        timeline_policy,
        uplift_rule_dates,
    )
    deps.recalc_to_dates(tables, nominated_expiry, uplift_rule_dates)
    section["tables"] = tables
    section["timeline_policy"] = timeline_policy
    section["timeline_policy_status"] = timeline_result["timeline_policy_status"]
    section["timeline_policy_issue"] = timeline_result["timeline_policy_issue"]
    section["validations"] = deps.validate_pay_tables(tables, nominated_expiry)
    deps.save_canonical(ae_id, canonical)
    return {
        "ok": True,
        "tables": tables,
        "validations": section["validations"],
        "timeline_policy_status": section.get("timeline_policy_status"),
        "timeline_policy_issue": section.get("timeline_policy_issue"),
    }


def _suggest_effective_dates_system_prompt() -> str:
    return (
        "You are reviewing an enterprise agreement to determine the correct effective_from date for each pay table. "
        "You will be given excerpts from uplift/timing clauses and a list of pay tables currently in draft. "
        "For each table, decide whether the text fixes a concrete ISO date (YYYY-MM-DD) for when its rates take effect. "
        "\n\nSIGNALS TO USE:\n"
        "1. `table_title` and `effective_from_note`: the exact phrase captured at extraction. These often appear verbatim in the relevant clause.\n"
        "2. ORDINAL / CHRONOLOGICAL alignment: if the uplift clause lists N dated increases and you have N dated tables plus K undated 'prior'/'sign-off' tables, align them by position and wording. The first rate increase listed, whether backdated or not, is typically the 'Effective from Sign off' rate. Rates 'Prior to Agreement commencing' are the pre-operative baseline rates.\n"
        "3. Dollar amounts: if the uplift rule says 'rates will increase by X% or $Y', sanity-check row values where possible.\n"
        "4. Agreement operative/approval date, if stated in uplift text, is often the natural answer for 'Effective from Sign off'.\n\n"
        "REASONING: Read the clause holistically and map tables to dates by context. Explain your reasoning in `rationale`.\n\n"
        "CONFIDENCE:\n"
        "- high: clause explicitly names the table or phrase, or one unambiguous date match\n"
        "- medium: ordinal/contextual inference is strong and alignment is obvious\n"
        "- low: inference requires a leap or multiple dates plausibly fit; return null instead of guessing\n\n"
        "DATE SEMANTICS - 'Prior' vs 'Sign off':\n"
        "- 'Prior to Agreement commencing' rates are never effective on the same day as the 'Sign off' table.\n"
        "- The prior table's correct `effective_from` is almost always unknowable from this agreement alone. Return null unless the text explicitly states a historical date for those specific rates.\n"
        "- The prior table's `to_date` would naturally be 'D minus one day', but to_date is derived automatically by the workbench.\n"
        "- For 'Effective from Sign off' phrasing: use the first listed uplift date or the agreement's operative/approval date from the uplift text.\n"
        "- If the sign-off table is dated D, and there is also a 'prior' table, the prior table must be dated before D or null, never D itself.\n"
        "\n\nCRITICAL OUTPUT RULE: Your entire response must be a single JSON object. No prose or markdown fences. "
        "The first character must be `{` and the last character must be `}`. Put reasoning inside `rationale`.\n"
        "LABELLING: Refer to tables by `display_label` in prose. The `index` field is only for routing.\n"
        'Output a strict JSON object with this shape:\n{ "suggestions": [ { "index": int, "suggested_effective_from": "YYYY-MM-DD" or null, "clause_ref": string or null, "confidence": "high"|"medium"|"low", "rationale": string } ] }\n'
        "One entry per input table, in input order. No extra keys."
    )


def _snap_suggestions_to_rule_dates(
    suggestions: list[dict[str, Any]],
    rule_dates_str: list[str],
) -> None:
    rule_dates = [date.fromisoformat(value) for value in rule_dates_str]
    snap_window_days = 14
    if not rule_dates:
        return
    for suggestion in suggestions:
        try:
            suggested = date.fromisoformat(suggestion["suggested_effective_from"])
        except (ValueError, TypeError):
            continue
        candidates = [
            (abs((rule_date - suggested).days), rule_date)
            for rule_date in rule_dates
            if abs((rule_date - suggested).days) <= snap_window_days
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda item: (item[0], item[1].isoformat()))
        best_delta, best_rule_date = candidates[0]
        ties = [rule_date for delta, rule_date in candidates if delta == best_delta and rule_date != best_rule_date]
        if ties:
            suggestion["rationale"] = (
                (suggestion.get("rationale") or "").rstrip()
                + f"\n\n[snap: skipped - {suggested.isoformat()} equidistant between rule dates "
                + ", ".join(sorted({best_rule_date.isoformat(), *[tie.isoformat() for tie in ties]}))
                + "]"
            )
            continue
        if best_rule_date == suggested:
            continue
        original_suggestion = suggestion["suggested_effective_from"]
        suggestion["suggested_effective_from"] = best_rule_date.isoformat()
        suggestion["snapped_from"] = original_suggestion
        suggestion["snapped_to_rule_date"] = best_rule_date.isoformat()
        suggestion["rationale"] = (
            (suggestion.get("rationale") or "").rstrip()
            + f"\n\n[snap: {original_suggestion} -> {best_rule_date.isoformat()} "
            + f"(uplift rule effective_date within +/-{snap_window_days}d)]"
        )


def suggest_effective_dates(ae_id: str, request: Any, deps: PayTableWorkflowDependencies) -> dict[str, Any]:
    if deps.find_pdf(ae_id) is None:
        raise HTTPException(status_code=404, detail="PDF not found")
    if not request.tables:
        raise HTTPException(status_code=400, detail="tables array is empty")
    if deps.anthropic_client() is None:
        raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY not set")

    uplift_blocks = deps.collect_uplift_pages_text(ae_id)
    if not uplift_blocks:
        return {
            "ok": True,
            "pages_used": [],
            "suggestions": [],
            "unsuggested_indices": list(range(len(request.tables))),
            "note": "No uplift/timing pages found",
        }

    pages_text = "\n\n".join(f"[Page {block['page']}]\n{block['text']}" for block in uplift_blocks)
    tables_summary = []
    for index, table in enumerate(request.tables):
        tables_summary.append({
            "index": index,
            "display_label": f"Table {index + 1}",
            "table_title": table.get("table_title") or "",
            "rate_kind": table.get("rate_kind") or "",
            "period_label_source": table.get("period_label_source") or "",
            "effective_from_note": table.get("effective_from_note") or "",
            "current_effective_from": table.get("effective_from") or "",
        })

    user_text = (
        "PAY TABLES IN DRAFT:\n"
        + json.dumps(tables_summary, indent=2)
        + "\n\nUPLIFT / TIMING CLAUSES FROM THE AGREEMENT:\n\n"
        + pages_text
    )

    raw = deps.call_llm(_suggest_effective_dates_system_prompt(), [{"type": "text", "text": user_text}], max_tokens=4000)
    if deps.is_llm_error(raw):
        raise deps.llm_http_failure(raw, action="suggest_effective_dates", message="Effective-date suggestion failed.")

    cleaned = deps.strip_json_preamble(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"LLM returned unparseable JSON: {exc}; raw={cleaned[:500]}")

    raw_suggestions = parsed.get("suggestions") or []
    suggestions: list[dict[str, Any]] = []
    unsuggested: list[int] = []
    for item in raw_suggestions:
        idx = item.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(request.tables):
            continue
        suggested_from = item.get("suggested_effective_from")
        if suggested_from:
            try:
                date.fromisoformat(suggested_from)
            except (ValueError, TypeError):
                unsuggested.append(idx)
                continue
            suggestions.append({
                "index": idx,
                "current_effective_from": request.tables[idx].get("effective_from") or "",
                "suggested_effective_from": suggested_from,
                "clause_ref": item.get("clause_ref"),
                "confidence": item.get("confidence") or "medium",
                "rationale": item.get("rationale") or "",
            })
        else:
            unsuggested.append(idx)

    mentioned = {suggestion["index"] for suggestion in suggestions} | set(unsuggested)
    for index in range(len(request.tables)):
        if index not in mentioned:
            unsuggested.append(index)

    try:
        canonical_for_rules = deps.get_canonical(ae_id)
    except Exception:
        canonical_for_rules = None
    rule_dates_str = deps.get_uplift_rule_dates(canonical_for_rules) if canonical_for_rules else []
    _snap_suggestions_to_rule_dates(suggestions, rule_dates_str)

    return {
        "ok": True,
        "pages_used": [block["page"] for block in uplift_blocks],
        "suggestions": suggestions,
        "unsuggested_indices": sorted(set(unsuggested)),
    }
