from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from benchmarking_data_factory.workbench.intake_candidates import (
    VALID_INTAKE_DECISIONS,
    intake_decisions_payload,
    load_candidate_rows_from_path,
    load_intake_decisions_from_path,
    map_candidate_agreements,
)


def load_candidate_agreement_rows(
    candidate_agreements_json: Path,
    cached_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if cached_rows is not None:
        return cached_rows
    return load_candidate_rows_from_path(candidate_agreements_json)


def load_candidate_agreements(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return map_candidate_agreements(rows)


def load_intake_decisions(
    intake_decisions_json: Path,
    cached_decisions: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    if cached_decisions is not None:
        return cached_decisions
    return load_intake_decisions_from_path(intake_decisions_json)


def save_intake_decisions(
    decisions: dict[str, dict[str, Any]],
    intake_decisions_json: Path,
) -> None:
    intake_decisions_json.parent.mkdir(parents=True, exist_ok=True)
    intake_decisions_json.write_text(
        json.dumps(intake_decisions_payload(decisions), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def record_intake_decision(
    ae_id: str,
    status: str,
    reason: str,
    notes: str,
    decisions: dict[str, dict[str, Any]],
    *,
    now_iso: Callable[[], str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    normalised = ae_id.lower().removesuffix(".pdf")
    if status not in VALID_INTAKE_DECISIONS:
        raise ValueError("Unsupported intake decision status")
    updated_decisions = dict(decisions)
    previous = updated_decisions.get(normalised, {})
    updated_decisions[normalised] = {
        **previous,
        "ae_id": normalised,
        "status": status,
        "reason": reason.strip(),
        "notes": notes.strip(),
        "decided_at": now_iso(),
        "decided_by": "local analyst",
    }
    return updated_decisions, updated_decisions[normalised]


def fetch_metadata_for_ae_id(
    ae_id: str,
    *,
    load_candidate_agreements: Callable[[], dict[str, dict[str, Any]]],
    split_ae_id: Callable[[str], tuple[str, str | None]],
    load_multi_council_decisions: Callable[[], dict[str, dict[str, Any]]],
    resolve_assigned_lga: Callable[[str, dict[str, Any] | None], str | None],
    decisions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    parent_ae_id, split_slug = split_ae_id(ae_id)
    metadata = load_candidate_agreements().get(parent_ae_id)
    if metadata is None:
        return None
    cloned = json.loads(json.dumps(metadata))
    if split_slug:
        assigned_lga = resolve_assigned_lga(
            ae_id,
            (decisions or load_multi_council_decisions()).get(parent_ae_id),
        )
        if assigned_lga:
            cloned["matched_lga_names"] = assigned_lga
            cloned["matched_lga_count"] = 1
    return cloned
