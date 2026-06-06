from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from benchmarking_data_factory.workbench.report_values import fetch_metadata_report_values

VALID_INTAKE_DECISIONS = {"accepted", "rejected", "needs_review"}


def normalise_candidate_date(value: Any) -> Any:
    if isinstance(value, int):
        return (datetime(1899, 12, 30) + timedelta(days=value)).date().isoformat()
    if isinstance(value, float) and value.is_integer():
        return (datetime(1899, 12, 30) + timedelta(days=int(value))).date().isoformat()
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return (datetime(1899, 12, 30) + timedelta(days=int(s))).date().isoformat()
    return value


def load_candidate_rows_from_path(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        record = dict(row)
        for key in ("Operative Date", "Expiry Date"):
            record[key] = normalise_candidate_date(record.get(key))
        records.append(record)
    return records


def map_candidate_agreements(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for record in rows:
        agreement_id = str(record.get("Agreement ID") or "").strip().lower()
        if agreement_id:
            mapped[agreement_id] = record
    return mapped


def load_intake_decisions_from_path(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    rows = payload.get("decisions", payload) if isinstance(payload, dict) else payload
    result: dict[str, dict[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            ae_id = str(row.get("ae_id") or "").strip().lower()
            if ae_id:
                result[ae_id] = dict(row, ae_id=ae_id)
    elif isinstance(rows, dict):
        for key, row in rows.items():
            if isinstance(row, dict):
                ae_id = str(row.get("ae_id") or key).strip().lower()
                if ae_id:
                    result[ae_id] = dict(row, ae_id=ae_id)
    return result


def intake_decisions_payload(decisions: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    rows = sorted(decisions.values(), key=lambda row: str(row.get("ae_id") or ""))
    return {"decisions": rows}


def safe_float(value: Any, default: float = float("-inf")) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def candidate_date_ordinal(value: Any) -> float:
    if isinstance(value, date):
        return float(value.toordinal())
    if isinstance(value, datetime):
        return float(value.date().toordinal())
    if isinstance(value, (int, float)):
        return float((datetime(1899, 12, 30) + timedelta(days=int(value))).date().toordinal())
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return float("-inf")
        if s.isdigit():
            return float((datetime(1899, 12, 30) + timedelta(days=int(s))).date().toordinal())
        try:
            return float(datetime.fromisoformat(s).date().toordinal())
        except ValueError:
            return float("-inf")
    return float("-inf")


def candidate_rank_key(row: dict[str, Any]) -> tuple[int, float, float, float]:
    return (
        0 if str(row.get("Agreement ID") or "").strip() else 1,
        -safe_float(row.get("agreement_num_clean")),
        -candidate_date_ordinal(row.get("Operative Date")),
        -safe_float(row.get("published_year")),
    )


def candidate_lgas(row: dict[str, Any]) -> list[str]:
    raw = row.get("matched_lga_names")
    if isinstance(raw, list):
        names = [str(part).strip() for part in raw if str(part).strip()]
    elif isinstance(raw, str):
        names = [part.strip() for part in raw.split("|") if part.strip()]
    else:
        names = []
    if not names and str(row.get("lga_short_name") or "").strip():
        names = [str(row.get("lga_short_name")).strip()]
    return names


def intake_acceptance_state(
    *,
    decision_status: str,
    in_working_set: bool,
    pipeline_status: str,
) -> str:
    if decision_status in VALID_INTAKE_DECISIONS:
        return decision_status
    if in_working_set:
        return "accepted"
    if "superseded" in pipeline_status:
        return "rejected"
    return "candidate"


def intake_candidate_sort_key(item: dict[str, Any]) -> tuple[int, int, str, str]:
    status_rank = {
        "active": 0,
        "superseded_by_newer": 2,
        "superseded_in_lineage": 3,
    }.get(item.get("candidate_stage"), 4)
    gate_rank = 1 if item.get("processing_gated") else 0
    council = str(item.get("canonical_lga_short_name") or "zzzz").lower()
    title = str(item.get("source_name") or item.get("ae_id") or "").lower()
    return (status_rank, gate_rank, council, title)


def build_intake_candidate_rows_from_sources(
    *,
    candidate_rows: list[dict[str, Any]],
    registry: dict[str, str],
    frozen_pdf_ids: set[str],
    intake_decisions: dict[str, dict[str, Any]],
    pdf_source_lookup: Callable[[str], dict[str, Any]],
) -> list[dict[str, Any]]:
    working_set_ids = set(registry.keys()) | frozen_pdf_ids
    rows: list[dict[str, Any]] = []

    for index, row in enumerate(candidate_rows):
        ae_id = str(row.get("Agreement ID") or "").strip().lower()
        if not ae_id:
            continue

        metadata = json.loads(json.dumps(row))
        matched_lgas = candidate_lgas(row)
        title = str(row.get("Agreement Title") or "").strip()
        pipeline_status = str(row.get("pipeline_status") or "unknown")
        scope_status = str(row.get("scope_resolution_status") or "")
        pdf_frozen = ae_id in frozen_pdf_ids
        pdf_source = pdf_source_lookup(ae_id)
        in_working_set = ae_id in working_set_ids
        qa_available = pdf_frozen or ae_id in registry
        intake_decision = intake_decisions.get(ae_id, {})
        decision_status = str(intake_decision.get("status") or "").strip()
        needs_scope_review = (
            not matched_lgas
            or "unresolved" in scope_status
            or bool(row.get("possible_multi_council_flag"))
        )
        processing_gated = pipeline_status == "active" and (not pdf_frozen or needs_scope_review)

        rows.append({
            "row_key": f"{ae_id}:{index}",
            "candidate_index": index + 1,
            "ae_id": ae_id,
            "source_name": registry.get(ae_id) or title or ae_id,
            "canonical_lga_short_name": matched_lgas[0] if matched_lgas else None,
            "fetch_metadata": metadata,
            "candidate_stage": pipeline_status,
            "likely_most_current": row.get("likely_most_current") or "",
            "matched_lgas": matched_lgas,
            "matched_lga_count": len(matched_lgas),
            "scope_resolution_status": scope_status,
            "possible_multi_council_flag": bool(row.get("possible_multi_council_flag")),
            "pdf_frozen": pdf_frozen,
            "pdf_source": pdf_source,
            "in_working_set": in_working_set,
            "acceptance_state": intake_acceptance_state(
                decision_status=decision_status,
                in_working_set=in_working_set,
                pipeline_status=pipeline_status,
            ),
            "intake_decision": intake_decision,
            "decision_source": "analyst" if decision_status else "working_set" if in_working_set else "pipeline",
            "qa_available": qa_available,
            "processing_gated": processing_gated,
            "registry_source_name": registry.get(ae_id),
            "pdf_url": row.get("pdf_url") or "",
            "superseded_by_ae_id": row.get("superseded_by_ae_id") or "",
            "rank": {
                "agreement_num_clean": row.get("agreement_num_clean") or "",
                "operative_ordinal": candidate_date_ordinal(row.get("Operative Date")),
                "published_year": row.get("published_year") or "",
            },
            "report_values": fetch_metadata_report_values(metadata, pdf_source=pdf_source),
        })

    rows.sort(key=intake_candidate_sort_key)
    return rows
