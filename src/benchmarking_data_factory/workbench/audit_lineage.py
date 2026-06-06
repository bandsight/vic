from __future__ import annotations

from datetime import datetime
from typing import Any, Callable


def _audit_int(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def audit_latest_lineage_key(
    row: dict[str, Any],
    *,
    date_score: Callable[[Any], float],
) -> tuple[int, int, float, int, int]:
    status = str(row.get("pipeline_status") or "").lower()
    return (
        1 if status == "active" else 0,
        1 if row.get("source_ready") else 0,
        date_score(row.get("operative_date")),
        _audit_int(row.get("agreement_number")),
        _audit_int(row.get("published_year")),
    )


def audit_chronological_lineage_key(
    row: dict[str, Any],
    *,
    date_score: Callable[[Any], float],
) -> tuple[float, int, str]:
    return (
        date_score(row.get("operative_date")),
        _audit_int(row.get("agreement_number")),
        str(row.get("ae_id") or ""),
    )


def audit_event_sort_key(
    row: dict[str, Any],
    *,
    date_score: Callable[[Any], float],
) -> tuple[int, float, str]:
    raw = str(row.get("date") or "")
    if not raw:
        return (1, float("inf"), str(row.get("label") or ""))
    parsed = raw.replace("Z", "+00:00")
    try:
        if "T" in parsed:
            score = datetime.fromisoformat(parsed).timestamp()
        else:
            score = datetime.fromisoformat(parsed).timestamp()
    except ValueError:
        score = date_score(raw)
    return (0, score, str(row.get("label") or ""))


def _audit_source_size(entry: dict[str, Any] | None) -> int | None:
    if not entry:
        return None
    value = entry.get("file_size_bytes")
    try:
        if value in (None, ""):
            return None
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def audit_lineage_row(
    candidate: dict[str, Any],
    *,
    intake_row: dict[str, Any] | None,
    register_entry: dict[str, Any] | None,
    pdf_source_metadata: Callable[[str], dict[str, Any]],
    candidate_council_names: Callable[[dict[str, Any]], list[str]],
) -> dict[str, Any]:
    raw_ae_id = candidate.get("Agreement ID") or ((intake_row or {}).get("ae_id"))
    ae_id = str(raw_ae_id or "").strip().lower()
    decision = intake_row.get("intake_decision") if intake_row else {}
    pdf_source = pdf_source_metadata(ae_id) if ae_id else {"frozen": False}
    source_ready = bool((intake_row or {}).get("pdf_frozen") or register_entry or pdf_source.get("frozen"))
    return {
        "ae_id": ae_id,
        "title": candidate.get("Agreement Title") or (intake_row or {}).get("source_name") or ae_id,
        "operative_date": candidate.get("Operative Date") or "",
        "expiry_date": candidate.get("Expiry Date") or "",
        "published_year": candidate.get("published_year") or "",
        "matter_number": candidate.get("Matter Number") or "",
        "print_id": candidate.get("Print ID") or "",
        "version": candidate.get("Version") or "",
        "agreement_number": candidate.get("agreement_num_clean") or "",
        "pipeline_status": candidate.get("pipeline_status") or (intake_row or {}).get("candidate_stage") or "unknown",
        "likely_most_current": candidate.get("likely_most_current") or "",
        "superseded_by_ae_id": str(candidate.get("superseded_by_ae_id") or "").lower(),
        "matched_lgas": candidate_council_names(candidate),
        "scope_resolution_status": candidate.get("scope_resolution_status") or "",
        "match_strength": candidate.get("match_strength") or "",
        "lineage_key": candidate.get("lineage_key") or "",
        "lineage_basis": candidate.get("lineage_basis") or "",
        "source_ready": source_ready,
        "source_fetched_at": (register_entry or {}).get("fetched_at") or "",
        "source_status": (register_entry or {}).get("source_status") or "",
        "serviceability_status": (register_entry or {}).get("serviceability_status") or "",
        "source_size_bytes": _audit_source_size(register_entry) or (pdf_source.get("file_size_bytes") if isinstance(pdf_source, dict) else None),
        "source_origin": (register_entry or {}).get("source_origin") or candidate.get("pdf_url") or "",
        "content_hash": (register_entry or {}).get("content_hash") or "",
        "intake_state": (intake_row or {}).get("acceptance_state") or "",
        "intake_decided_at": (decision or {}).get("decided_at") or "",
        "intake_decision_reason": (decision or {}).get("reason") or "",
    }
