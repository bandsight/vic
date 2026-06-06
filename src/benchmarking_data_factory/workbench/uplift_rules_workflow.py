from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from fastapi import HTTPException

from benchmarking_data_factory.uplift_rules.real_adapter import RealAdapter
from benchmarking_data_factory.uplift_rules.suggest import SuggestConfig


@dataclass(frozen=True)
class UpliftRulesWorkflowDependencies:
    pdf_path_for: Callable[[str], Any]
    get_page_count: Callable[[str], int]
    extract_page_text: Callable[[str, int], str]
    extract_all_page_texts: Callable[[str], list[str]]
    call_llm: Callable[..., str]
    configured_llm_model: Callable[[], str]
    run_uplift_suggest: Callable[..., Any]
    get_canonical: Callable[[str], dict[str, Any]]
    now_iso: Callable[[], str]
    apply_section_status: Callable[..., Any]
    save_canonical: Callable[[str, dict[str, Any]], None]


def serialise_suggestion(suggestion: Any) -> dict[str, Any]:
    """Convert an UpliftRulesSuggestion dataclass into a JSON-ready dict."""
    def convert(obj: Any) -> Any:
        if dataclasses.is_dataclass(obj):
            return {key: convert(value) for key, value in dataclasses.asdict(obj).items()}
        if isinstance(obj, tuple):
            return [convert(item) for item in obj]
        if isinstance(obj, list):
            return [convert(item) for item in obj]
        if isinstance(obj, dict):
            return {key: convert(value) for key, value in obj.items()}
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    return convert(suggestion)


def suggestion_status(payload: dict[str, Any]) -> str:
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        return ""
    return str(provenance.get("extraction_status") or "")


def failed_suggestion_detail(payload: dict[str, Any]) -> dict[str, str]:
    status = suggestion_status(payload) or "unknown"
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    raw = str((provenance or {}).get("llm_raw_response") or "").strip()
    if raw.startswith("ERROR:"):
        reason = raw
    elif raw:
        reason = raw[:500]
    else:
        reason = f"Extraction status was {status}"
    return {
        "message": "Uplift rule extraction failed; no suggestion was saved.",
        "status": status,
        "reason": reason,
    }


def uplift_adapter(deps: UpliftRulesWorkflowDependencies) -> RealAdapter:
    """Build a RealAdapter wired to the host application's helpers."""
    return RealAdapter(
        pdf_path_resolver=deps.pdf_path_for,
        page_count_fn=deps.get_page_count,
        page_text_fn=deps.extract_page_text,
        all_page_texts_fn=deps.extract_all_page_texts,
        call_llm_fn=deps.call_llm,
        default_model=deps.configured_llm_model(),
    )


def suggest_uplift_rules(
    ae_id: str,
    *,
    force_refresh: bool,
    deps: UpliftRulesWorkflowDependencies,
) -> dict[str, Any]:
    adapter = uplift_adapter(deps)
    cfg = SuggestConfig(
        model=deps.configured_llm_model(),
        force_refresh=force_refresh,
    )
    suggestion = deps.run_uplift_suggest(ae_id, adapter, cfg)
    payload = serialise_suggestion(suggestion)
    if suggestion_status(payload) != "ok":
        raise HTTPException(status_code=502, detail=failed_suggestion_detail(payload))
    canonical = deps.get_canonical(ae_id)
    section = canonical.setdefault("sections", {}).setdefault("uplift_rules", {})
    data = section.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    data["suggestion"] = payload
    data["suggestion_generated_at"] = deps.now_iso()
    section["data"] = data
    deps.apply_section_status(section, "in_progress", None)
    deps.save_canonical(ae_id, canonical)
    return {"suggestion": payload, "section_status": section.get("status")}


def get_uplift_rule_suggestion(ae_id: str, deps: UpliftRulesWorkflowDependencies) -> dict[str, Any]:
    canonical = deps.get_canonical(ae_id)
    section = (canonical.get("sections") or {}).get("uplift_rules") or {}
    data = section.get("data")
    if not isinstance(data, dict) or not data.get("suggestion"):
        raise HTTPException(status_code=404, detail="No suggestion persisted for this council")
    return {
        "suggestion": data["suggestion"],
        "suggestion_generated_at": data.get("suggestion_generated_at"),
        "accepted": data.get("accepted"),
        "accepted_at": data.get("accepted_at"),
        "section_status": section.get("status"),
    }


def accept_uplift_rules(
    ae_id: str,
    deps: UpliftRulesWorkflowDependencies,
    *,
    rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    canonical = deps.get_canonical(ae_id)
    section = canonical.setdefault("sections", {}).setdefault("uplift_rules", {})
    data = section.get("data") if isinstance(section.get("data"), dict) else {}
    suggestion = data.get("suggestion")
    if not suggestion:
        raise HTTPException(status_code=400, detail="No suggestion to accept - run /suggest first")
    if isinstance(suggestion, dict) and suggestion_status(suggestion) not in {"", "ok"}:
        raise HTTPException(status_code=400, detail="Cannot accept failed uplift rule suggestion; re-run extraction first")
    accepted_document = dict(suggestion.get("document") or {})
    if rules is not None:
        accepted_document["rules"] = rules
    data["accepted"] = {
        "document": accepted_document,
        "suggestion_id": suggestion.get("suggestion_id"),
        "prompt_version": (suggestion.get("provenance", {}).get("inputs") or {}).get("prompt_version"),
        "model": (suggestion.get("provenance", {}).get("inputs") or {}).get("model"),
        "code_git_sha": suggestion.get("provenance", {}).get("code_git_sha"),
    }
    data["accepted_at"] = deps.now_iso()
    section["data"] = data
    deps.apply_section_status(section, "done", deps.now_iso())
    _record_alignment_issues_if_pay_tables_exist(canonical, deps)
    deps.save_canonical(ae_id, canonical)
    return {"accepted": data["accepted"], "section_status": section.get("status")}


def discard_uplift_rule_suggestion(
    ae_id: str,
    deps: UpliftRulesWorkflowDependencies,
) -> dict[str, Any]:
    canonical = deps.get_canonical(ae_id)
    section = canonical.setdefault("sections", {}).setdefault("uplift_rules", {})
    data = section.get("data") if isinstance(section.get("data"), dict) else {}
    discarded = bool(data.get("suggestion"))
    data.pop("suggestion", None)
    data.pop("suggestion_generated_at", None)
    section["data"] = data
    if data.get("accepted") and data.get("table_alignment_issues"):
        deps.apply_section_status(section, "flagged", None)
    elif data.get("accepted"):
        deps.apply_section_status(section, "done", data.get("accepted_at") or deps.now_iso())
    else:
        deps.apply_section_status(section, "not_started", None)
    deps.save_canonical(ae_id, canonical)
    return {
        "discarded": discarded,
        "accepted": data.get("accepted"),
        "section_status": section.get("status"),
    }


def update_accepted_uplift_rules(
    ae_id: str,
    rules: list[dict[str, Any]],
    deps: UpliftRulesWorkflowDependencies,
) -> dict[str, Any]:
    canonical = deps.get_canonical(ae_id)
    section = canonical.setdefault("sections", {}).setdefault("uplift_rules", {})
    data = section.get("data") if isinstance(section.get("data"), dict) else {}
    accepted = data.get("accepted")
    if not accepted:
        raise HTTPException(status_code=400, detail="No accepted rules block - accept the suggestion first")
    accepted.setdefault("document", {})["rules"] = rules
    data["accepted"] = accepted
    section["data"] = data
    _record_alignment_issues_if_pay_tables_exist(canonical, deps)
    deps.save_canonical(ae_id, canonical)
    return {"rules": rules}


def _record_alignment_issues_if_pay_tables_exist(
    canonical: dict[str, Any],
    deps: UpliftRulesWorkflowDependencies,
) -> None:
    pay_section = (canonical.get("sections") or {}).get("pay_tables") or {}
    if pay_section.get("status") != "done" or not pay_section.get("tables"):
        return
    from benchmarking_data_factory.uplift_rules.table_alignment import (  # noqa: PLC0415
        record_rule_table_alignment_issues,
    )

    issues = record_rule_table_alignment_issues(canonical)
    if issues:
        deps.apply_section_status(canonical["sections"]["uplift_rules"], "flagged", None)
