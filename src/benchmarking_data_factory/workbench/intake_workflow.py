from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable

import requests
from fastapi import HTTPException

from benchmarking_data_factory.workbench.intake_candidates import (
    build_intake_candidate_rows_from_sources,
)
from benchmarking_data_factory.workbench.intake_quality import (
    build_intake_quality_summary as build_intake_quality_payload,
)
from benchmarking_data_factory.workbench.source_document_intake import (
    FWC_REQUEST_HEADERS,
    download_pdf_to_path,
    find_fwc_document_download_url,
    freeze_intake_candidate_pdf as source_document_freeze_intake_candidate_pdf,
    fwc_download_link_from_html,
    fwc_get,
    fwc_search_terms,
)


@dataclass(frozen=True)
class IntakeWorkflowDependencies:
    candidate_agreements_json: Callable[[], Path]
    root_path: Callable[[], Path]
    immutable_dir: Callable[[], Path]
    canonical_dir: Callable[[], Path]
    scenario_overrides_dir: Callable[[], Path]
    cache_dir: Callable[[], Path]
    clear_records_dir: Callable[[], Path]
    distribution_point_analysis_json: Callable[[], Path]
    load_candidate_agreement_rows: Callable[[], list[dict[str, Any]]]
    load_candidate_agreements: Callable[[], dict[str, dict[str, Any]]]
    load_intake_decisions: Callable[[], dict[str, dict[str, Any]]]
    load_registry: Callable[[], dict[str, str]]
    list_pdfs: Callable[[], list[str]]
    api_councils: Callable[[bool], list[dict[str, Any]]]
    pdf_source_metadata: Callable[[str], dict[str, Any]]
    run_phase1: Callable[..., dict[str, Any]]
    clear_intake_source_caches: Callable[[], None]
    record_intake_decision: Callable[[str, str, str, str], dict[str, Any]]
    find_pdf: Callable[[str], Path | None]
    sha256_file: Callable[[Path], str]
    record_frozen_source_document: Callable[..., dict[str, str]]
    find_fwc_document_download_url: Callable[..., str | None]
    download_pdf_to_path: Callable[[str, Path], None]
    load_multi_council_decisions: Callable[[], dict[str, dict[str, Any]]]
    write_multi_council_decisions: Callable[[dict[str, dict[str, Any]]], None]
    record_multi_council_decision: Callable[[str, bool, list[str], str, list[str], str], None]
    split_ae_id: Callable[[str], tuple[str, str | None]]
    lga_slug: Callable[[str], str]
    active_canonical_council_lookup: Callable[[], dict[str, dict[str, str]]]
    fresh_canonical: Callable[[str, str], dict[str, Any]]
    save_canonical: Callable[[str, dict[str, Any]], None]
    fetch_metadata_for_ae_id: Callable[..., dict[str, Any] | None]
    now_iso: Callable[[], str]


def build_intake_quality_summary(
    council_rows: list[dict[str, Any]] | None,
    deps: IntakeWorkflowDependencies,
) -> dict[str, Any]:
    return build_intake_quality_payload(council_rows, deps)


def build_intake_candidate_rows(deps: IntakeWorkflowDependencies) -> list[dict[str, Any]]:
    return build_intake_candidate_rows_from_sources(
        candidate_rows=deps.load_candidate_agreement_rows(),
        registry=deps.load_registry(),
        frozen_pdf_ids=set(deps.list_pdfs()),
        intake_decisions=deps.load_intake_decisions(),
        pdf_source_lookup=deps.pdf_source_metadata,
    )


def fetch_fair_work_registry_intake(
    *,
    force_registry: bool,
    fetch_pdfs: bool,
    pdf_limit: int | None,
    deps: IntakeWorkflowDependencies,
) -> dict[str, Any]:
    if pdf_limit is not None and pdf_limit < 0:
        raise HTTPException(status_code=400, detail="pdf_limit must be zero or greater")
    try:
        run = deps.run_phase1(
            fetch_pdfs=fetch_pdfs,
            pdf_limit=pdf_limit,
            force_registry=force_registry,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Fair Work registry fetch failed: {exc}") from exc
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=500, detail=f"Fair Work registry rebuild failed: {exc}") from exc

    deps.clear_intake_source_caches()
    candidates = build_intake_candidate_rows(deps)
    quality = build_intake_quality_summary(None, deps)
    return {
        "ok": True,
        "run_id": "FWC-LOCAL-DRYRUN",
        "run": run,
        "candidates": candidates,
        "quality": quality,
    }


def freeze_intake_candidate_pdf(
    ae_id: str,
    *,
    force_refresh: bool,
    deps: IntakeWorkflowDependencies,
) -> dict[str, Any]:
    return source_document_freeze_intake_candidate_pdf(ae_id, force_refresh=force_refresh, deps=deps)


def intake_decision_response(
    ae_id: str,
    *,
    status: str,
    reason: str,
    notes: str,
    deps: IntakeWorkflowDependencies,
) -> dict[str, Any]:
    normalised = ae_id.lower().removesuffix(".pdf")
    if not any(row.get("ae_id") == normalised for row in build_intake_candidate_rows(deps)):
        raise HTTPException(status_code=404, detail="Intake candidate not found")
    decision = deps.record_intake_decision(normalised, status, reason, notes)
    for row in build_intake_candidate_rows(deps):
        if row.get("ae_id") == normalised:
            return {"decision": decision, "candidate": row}
    return {"decision": decision, "candidate": None}


def intake_freeze_candidate_response(
    ae_id: str,
    *,
    force_refresh: bool,
    deps: IntakeWorkflowDependencies,
) -> dict[str, Any]:
    normalised = ae_id.lower().removesuffix(".pdf")
    result = freeze_intake_candidate_pdf(normalised, force_refresh=force_refresh, deps=deps)
    for row in build_intake_candidate_rows(deps):
        if row.get("ae_id") == normalised:
            return {**result, "candidate": row}
    return {**result, "candidate": None}


def split_council(ae_id: str, request: Any, deps: IntakeWorkflowDependencies) -> dict[str, Any]:
    ae_id = ae_id.lower()
    active_lookup = deps.active_canonical_council_lookup()
    invalid_lgas = [lga for lga in request.lgas if lga not in active_lookup]
    if invalid_lgas:
        raise HTTPException(status_code=400, detail={"invalid_lgas": invalid_lgas})
    unique_lgas = []
    for lga in request.lgas:
        if lga not in unique_lgas:
            unique_lgas.append(lga)
    if len(unique_lgas) < 2:
        raise HTTPException(status_code=400, detail="At least 2 councils are required to split")
    parent_ae_id, split_slug = deps.split_ae_id(ae_id)
    if split_slug is not None:
        raise HTTPException(status_code=400, detail="Split rows cannot be split again")
    original_pdf = deps.find_pdf(parent_ae_id)
    if original_pdf is None:
        raise HTTPException(status_code=404, detail="Original PDF not found")
    parent_hash = deps.sha256_file(original_pdf)
    split_files: list[str] = []
    for lga in unique_lgas:
        filename = f"{parent_ae_id}__{deps.lga_slug(lga)}.pdf"
        shutil.copy2(original_pdf, deps.immutable_dir() / filename)
        split_files.append(filename)
    deps.record_multi_council_decision(parent_ae_id, True, unique_lgas, parent_hash, split_files, request.notes)
    return {
        "ae_id": parent_ae_id,
        "is_multi": True,
        "split_files": split_files,
        "parent_content_hash": parent_hash,
    }


def confirm_single_council(ae_id: str, request: Any, deps: IntakeWorkflowDependencies) -> dict[str, Any]:
    active_lookup = deps.active_canonical_council_lookup()
    ae_id = ae_id.lower()
    if request.lga not in active_lookup:
        raise HTTPException(status_code=400, detail={"invalid_lgas": [request.lga]})
    parent_ae_id, split_slug = deps.split_ae_id(ae_id)
    if split_slug is not None:
        raise HTTPException(status_code=400, detail="Split rows cannot be confirmed as single")
    original_pdf = deps.find_pdf(parent_ae_id)
    if original_pdf is None:
        raise HTTPException(status_code=404, detail="Original PDF not found")
    parent_hash = deps.sha256_file(original_pdf)
    decisions = deps.load_multi_council_decisions()
    existing = decisions.get(parent_ae_id, {})
    removed = []
    for filename in existing.get("split_files") or []:
        split_path = deps.immutable_dir() / filename
        if split_path.exists():
            split_path.unlink()
            removed.append(filename)
        else:
            print(f"[multi-council] split file already missing: {split_path}")
    notes = request.notes or ""
    if removed:
        extra = f"[unsplit on undo: removed {len(removed)} file(s)]"
        notes = f"{notes}\n{extra}".strip()
    deps.record_multi_council_decision(parent_ae_id, False, [request.lga], parent_hash, [], notes)
    return {
        "ae_id": parent_ae_id,
        "is_multi": False,
        "lga": request.lga,
        "parent_content_hash": parent_hash,
        "removed_split_files": removed,
    }


def unsplit_council(ae_id: str, deps: IntakeWorkflowDependencies) -> dict[str, Any]:
    parent_ae_id, _ = deps.split_ae_id(ae_id.lower())
    decisions = deps.load_multi_council_decisions()
    decision = decisions.get(parent_ae_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="No multi-council decision recorded")
    if not decision.get("is_multi"):
        raise HTTPException(status_code=400, detail="Council is not currently marked multi-council")
    removed = []
    for filename in decision.get("split_files") or []:
        split_path = deps.immutable_dir() / filename
        if split_path.exists():
            split_path.unlink()
            removed.append(filename)
        else:
            print(f"[multi-council] split file already missing: {split_path}")
    parent_pdf = deps.find_pdf(parent_ae_id)
    parent_hash = deps.sha256_file(parent_pdf) if parent_pdf else ""
    unsplit_note = f"[unsplit at {deps.now_iso()}]"
    notes = "\n".join(part for part in [decision.get("notes") or "", unsplit_note] if part)
    deps.record_multi_council_decision(parent_ae_id, False, [], parent_hash, [], notes)
    return {"ae_id": parent_ae_id, "removed_split_files": removed, "is_multi": False}


def _safe_clear_record_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "-", value.lower()).strip("-") or "agreement"


def _clear_record_archive_dir(parent_ae_id: str, cleared_at: str, deps: IntakeWorkflowDependencies) -> Path:
    stamp = datetime.fromisoformat(cleared_at).strftime("%Y%m%dT%H%M%SZ")
    base = deps.clear_records_dir() / f"{stamp}_{_safe_clear_record_slug(parent_ae_id)}"
    archive_dir = base
    suffix = 2
    while archive_dir.exists():
        archive_dir = deps.clear_records_dir() / f"{base.name}_{suffix}"
        suffix += 1
    return archive_dir


def _path_counts(path: Path) -> tuple[int, int]:
    if path.is_file():
        return (1, path.stat().st_size)
    if not path.is_dir():
        return (0, 0)
    files = [child for child in path.rglob("*") if child.is_file()]
    return (len(files), sum(child.stat().st_size for child in files))


def _path_relative_to_root(path: Path, deps: IntakeWorkflowDependencies) -> str:
    try:
        return path.resolve().relative_to(deps.root_path().resolve()).as_posix()
    except ValueError:
        return path.name


def _unique_archive_target(archive_dir: Path, source_path: Path, deps: IntakeWorkflowDependencies) -> Path:
    relative = Path(_path_relative_to_root(source_path, deps))
    target = archive_dir / "files" / relative
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _move_clear_artifact(
    path: Path,
    archive_dir: Path,
    manifest: dict[str, Any],
    deps: IntakeWorkflowDependencies,
    *,
    kind: str,
    note: str = "",
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    file_count, byte_count = _path_counts(path)
    target = _unique_archive_target(archive_dir, path, deps)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target))
    record = {
        "kind": kind,
        "from": _path_relative_to_root(path, deps),
        "to": _path_relative_to_root(target, deps),
        "file_count": file_count,
        "bytes": byte_count,
    }
    if note:
        record["note"] = note
    manifest.setdefault("moved_artifacts", []).append(record)
    return record


def _archive_clear_json_record(
    archive_dir: Path,
    manifest: dict[str, Any],
    deps: IntakeWorkflowDependencies,
    *,
    kind: str,
    name: str,
    data: Any,
) -> None:
    target = archive_dir / "records" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    manifest.setdefault("archived_records", []).append({
        "kind": kind,
        "to": _path_relative_to_root(target, deps),
    })


def _related_review_clear_ids(
    parent_ae_id: str,
    requested_ae_id: str,
    include_related: bool,
    deps: IntakeWorkflowDependencies,
) -> list[str]:
    parent = parent_ae_id.lower()
    requested = requested_ae_id.lower()
    if not include_related:
        return [requested]

    related = {parent, requested}
    decision = deps.load_multi_council_decisions().get(parent) or {}
    for filename in decision.get("split_files") or []:
        stem = Path(str(filename)).stem.lower()
        if stem:
            related.add(stem)

    for directory, suffix in (
        (deps.canonical_dir(), ".yaml"),
        (deps.scenario_overrides_dir(), ".json"),
        (deps.immutable_dir(), ".pdf"),
    ):
        if not directory.exists():
            continue
        for path in directory.glob(f"{parent}__*{suffix}"):
            related.add(path.stem.lower())

    cache_dir = deps.cache_dir()
    if cache_dir.exists():
        for path in cache_dir.glob(f"{parent}__*"):
            related.add(path.name.lower())

    return sorted(related)


def _agreement_named_generated_artifacts(
    related_ae_ids: list[str],
    archive_dir: Path,
    deps: IntakeWorkflowDependencies,
) -> list[Path]:
    needles = [ae_id.lower() for ae_id in related_ae_ids if ae_id]
    if not needles:
        return []
    candidates: list[Path] = []
    clear_records_dir = deps.clear_records_dir()
    for directory in (deps.root_path() / "artifacts", deps.root_path() / "exports", deps.root_path() / "var"):
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            if clear_records_dir in path.parents or archive_dir in path.parents:
                continue
            filename = path.name.lower()
            if any(needle in filename for needle in needles):
                candidates.append(path)
    return candidates


def _remove_multi_council_decision(parent_ae_id: str, deps: IntakeWorkflowDependencies) -> dict[str, Any] | None:
    decisions = dict(deps.load_multi_council_decisions())
    removed = decisions.pop(parent_ae_id.lower(), None)
    if removed is None:
        return None
    deps.write_multi_council_decisions(decisions)
    return removed


def clear_review_record(
    ae_id: str,
    *,
    reason: str,
    include_related: bool,
    deps: IntakeWorkflowDependencies,
) -> dict[str, Any]:
    requested_ae_id = ae_id.lower().removesuffix(".pdf")
    parent_ae_id, _ = deps.split_ae_id(requested_ae_id)
    related_ae_ids = _related_review_clear_ids(parent_ae_id, requested_ae_id, include_related, deps)

    known_artifact_exists = any(
        path.exists()
        for related_id in related_ae_ids
        for path in (
            deps.canonical_dir() / f"{related_id}.yaml",
            deps.scenario_overrides_dir() / f"{related_id}.json",
            deps.cache_dir() / related_id,
        )
    )
    if (
        not known_artifact_exists
        and deps.find_pdf(parent_ae_id) is None
        and parent_ae_id not in deps.load_registry()
    ):
        raise HTTPException(status_code=404, detail="Agreement not found")

    cleared_at = deps.now_iso()
    archive_dir = _clear_record_archive_dir(parent_ae_id, cleared_at, deps)
    archive_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schema_version": "review_clear_record.v1",
        "agreement_id": parent_ae_id,
        "requested_ae_id": requested_ae_id,
        "related_ae_ids": related_ae_ids,
        "cleared_at": cleared_at,
        "cleared_by": "local analyst",
        "reason": reason.strip(),
        "archive_id": archive_dir.name,
        "archive_path": str(archive_dir),
        "moved_artifacts": [],
        "archived_records": [],
        "retained_boundaries": [
            "documents/immutable source PDF",
            "source-document register row",
            "Fair Work candidate metadata",
            "intake decision state",
        ],
    }

    if include_related:
        decision = _remove_multi_council_decision(parent_ae_id, deps)
        if decision:
            _archive_clear_json_record(
                archive_dir,
                manifest,
                deps,
                kind="multi_council_decision",
                name="multi-council-decision.json",
                data=decision,
            )

    for related_id in related_ae_ids:
        _move_clear_artifact(
            deps.canonical_dir() / f"{related_id}.yaml",
            archive_dir,
            manifest,
            deps,
            kind="canonical_state",
        )
        _move_clear_artifact(
            deps.scenario_overrides_dir() / f"{related_id}.json",
            archive_dir,
            manifest,
            deps,
            kind="scenario_override_state",
        )
        _move_clear_artifact(
            deps.cache_dir() / related_id,
            archive_dir,
            manifest,
            deps,
            kind="workspace_cache",
        )
        if "__" in related_id:
            _move_clear_artifact(
                deps.immutable_dir() / f"{related_id}.pdf",
                archive_dir,
                manifest,
                deps,
                kind="split_source_pdf",
                note="Split PDF generated from parent source during Review Board scope handling.",
            )

    distribution_point_analysis_json = deps.distribution_point_analysis_json()
    if include_related and distribution_point_analysis_json.exists():
        _move_clear_artifact(
            distribution_point_analysis_json,
            archive_dir,
            manifest,
            deps,
            kind="derived_analysis_asset",
            note="Global derived analysis cache invalidated because it may include this agreement.",
        )

    for path in _agreement_named_generated_artifacts(related_ae_ids, archive_dir, deps):
        _move_clear_artifact(
            path,
            archive_dir,
            manifest,
            deps,
            kind="generated_artifact",
        )

    reset_ae_id = parent_ae_id if include_related else requested_ae_id
    reset_parent_ae_id, _ = deps.split_ae_id(reset_ae_id)
    fetch_metadata = deps.fetch_metadata_for_ae_id(reset_ae_id) or {}
    registry = deps.load_registry()
    source_name = (
        registry.get(reset_ae_id)
        or registry.get(reset_parent_ae_id)
        or fetch_metadata.get("Agreement Title")
        or reset_ae_id
    )
    reset_canonical = deps.fresh_canonical(reset_ae_id, str(source_name))
    reset_canonical["review_clear_records"] = [{
        "agreement_id": reset_ae_id,
        "cleared_at": cleared_at,
        "cleared_by": "local analyst",
        "reason": reason.strip(),
        "archive_id": archive_dir.name,
        "archive_path": str(archive_dir),
        "related_ae_ids": related_ae_ids,
        "moved_artifact_count": len(manifest["moved_artifacts"]),
        "archived_record_count": len(manifest["archived_records"]),
    }]
    deps.save_canonical(reset_ae_id, reset_canonical)

    manifest["reset_canonical"] = {
        "agreement_id": reset_ae_id,
        "path": _path_relative_to_root(deps.canonical_dir() / f"{reset_ae_id}.yaml", deps),
    }
    manifest_path = archive_dir / "clear-record-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    return {
        "ok": True,
        "clear_record": reset_canonical["review_clear_records"][-1],
        "manifest": {
            "path": str(manifest_path),
            "relative_path": _path_relative_to_root(manifest_path, deps),
        },
        "moved_artifacts": manifest["moved_artifacts"],
        "archived_records": manifest["archived_records"],
        "retained_boundaries": manifest["retained_boundaries"],
    }
