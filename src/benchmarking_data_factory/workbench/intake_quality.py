from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Any, Callable

from benchmarking_data_factory.workbench.intake_candidates import (
    candidate_lgas,
    candidate_rank_key,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _candidate_file_signature(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "mtime_ns": None,
            "size": None,
        }
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def build_intake_quality_summary(
    council_rows: list[dict[str, Any]] | None,
    deps: Any,
) -> dict[str, Any]:
    candidates = deps.load_candidate_agreement_rows()
    unique_agreement_ids = {
        str(row.get("Agreement ID") or "").strip().lower()
        for row in candidates
        if str(row.get("Agreement ID") or "").strip()
    }
    status_counts: dict[str, int] = {}
    for row in candidates:
        status = str(row.get("pipeline_status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    matched_rows = [row for row in candidates if candidate_lgas(row)]
    active_rows = [row for row in candidates if row.get("pipeline_status") == "active"]
    active_matched_rows = [row for row in active_rows if candidate_lgas(row)]
    unmatched_active_rows = [row for row in active_rows if not candidate_lgas(row)]
    likely_current_but_demoted = [
        row
        for row in candidates
        if row.get("likely_most_current") == "likely_current"
        and row.get("pipeline_status") not in ("active", None, "")
    ]

    by_lga: dict[str, list[dict[str, Any]]] = {}
    for row in matched_rows:
        for lga in candidate_lgas(row):
            by_lga.setdefault(lga, []).append(row)

    top_two_ids: set[str] = set()
    runner_up_by_id: dict[str, dict[str, Any]] = {}
    councils_with_runner_up = 0
    for lga, rows in by_lga.items():
        ranked = sorted(rows, key=candidate_rank_key)[:2]
        for index, row in enumerate(ranked):
            ae_id = str(row.get("Agreement ID") or "").strip().lower()
            if not ae_id:
                continue
            top_two_ids.add(ae_id)
            if index == 1:
                councils_with_runner_up += 1
                runner_up_by_id.setdefault(
                    ae_id,
                    {
                        "council": lga,
                        "ae_id": ae_id,
                        "title": row.get("Agreement Title") or "",
                        "operative_date": row.get("Operative Date") or "",
                        "expiry_date": row.get("Expiry Date") or "",
                        "pipeline_status": row.get("pipeline_status") or "unknown",
                        "superseded_by_ae_id": row.get("superseded_by_ae_id") or "",
                    },
                )

    council_rows = council_rows if council_rows is not None else deps.api_councils(False)
    visible_superseded = [
        row for row in council_rows
        if "superseded" in str((row.get("fetch_metadata") or {}).get("pipeline_status") or "")
    ]
    missing_metadata = [row for row in council_rows if not row.get("fetch_metadata")]
    visible_active = len(council_rows) - len(visible_superseded)

    flags: list[dict[str, Any]] = []
    if not candidates:
        flags.append({
            "severity": "error",
            "label": "No candidate file",
            "detail": "The Fair Work candidate agreement file is missing or empty.",
        })
    if unmatched_active_rows:
        flags.append({
            "severity": "warning",
            "label": "Unmatched active candidates",
            "value": len(unmatched_active_rows),
            "detail": "Active registry rows survived the fetch but did not map to a Victorian LGA.",
        })
    if visible_superseded:
        flags.append({
            "severity": "warning",
            "label": "Superseded in working set",
            "value": len(visible_superseded),
            "detail": "Fetched intake rows include sources that the fetch marked as superseded.",
        })
    if missing_metadata:
        flags.append({
            "severity": "warning",
            "label": "Missing fetch metadata",
            "value": len(missing_metadata),
            "detail": "Fetched rows lack the candidate-register metadata used for scope and status checks.",
        })
    if runner_up_by_id:
        flags.append({
            "severity": "info",
            "label": "Runner-up review available",
            "value": len(runner_up_by_id),
            "detail": "A top-two QA lens can show near-current alternatives before promotion.",
        })

    source_mtime = None
    candidate_agreements_json = deps.candidate_agreements_json()
    if candidate_agreements_json.exists():
        source_mtime = datetime.fromtimestamp(
            candidate_agreements_json.stat().st_mtime,
            timezone.utc,
        ).isoformat()

    return {
        "source": {
            "candidate_file": str(candidate_agreements_json),
            "last_modified": source_mtime,
        },
        "candidate_records": {
            "total": len(candidates),
            "unique_agreement_ids": len(unique_agreement_ids),
            "by_status": status_counts,
            "active": status_counts.get("active", 0),
            "superseded_by_newer": status_counts.get("superseded_by_newer", 0),
            "superseded_in_lineage": status_counts.get("superseded_in_lineage", 0),
            "likely_current_but_demoted": len(likely_current_but_demoted),
            "matched": len(matched_rows),
            "active_matched": len(active_matched_rows),
            "active_unmatched": len(unmatched_active_rows),
        },
        "working_set": {
            "visible": len(council_rows),
            "visible_active": visible_active,
            "visible_superseded": len(visible_superseded),
            "missing_metadata": len(missing_metadata),
            "registry_rows": len(deps.load_registry()),
            "frozen_pdfs": len(deps.list_pdfs()),
        },
        "top_two_review": {
            "councils_grouped": len(by_lga),
            "unique_top_two_candidates": len(top_two_ids),
            "unique_runner_up_candidates": len(runner_up_by_id),
            "councils_with_runner_up": councils_with_runner_up,
            "runner_up_examples": sorted(
                runner_up_by_id.values(),
                key=lambda item: (item["council"].lower(), item["ae_id"]),
            )[:6],
        },
        "selection_rule": {
            "lineage_grouping": "Council context plus Matter Number; if Matter Number is absent, council context plus title signature.",
            "ranking": "Agreement ID present, highest agreement number, newest operative date, newest published year.",
            "promotion_policy": "The fetch keeps all candidate rows, promotes the best row to active, and demotes older council-level rows unless the operative dates tie.",
            "top_two_note": "Top-two review is a QA view over the retained candidates, not the current promotion rule.",
        },
        "flags": flags,
    }


@dataclass
class IntakeQualityService:
    deps_factory: Callable[[], Any]
    now: Callable[[], str] = _utc_now_iso
    ttl_seconds: int = 300
    _cache: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def invalidate(self, reason: str = "manual") -> None:
        with self._lock:
            self._cache = None
            self._last_invalidation_reason = reason

    def summary(
        self,
        council_rows: list[dict[str, Any]] | None = None,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        if council_rows is not None:
            return self._build_uncached(council_rows, cache_state="uncached")

        deps = self.deps_factory()
        source_signature = _candidate_file_signature(deps.candidate_agreements_json())
        now = self.now()
        with self._lock:
            if not force_refresh and self._cache and self._cache["source_signature"] == source_signature:
                age_seconds = max(0.0, perf_counter() - self._cache["created_monotonic"])
                if age_seconds <= self.ttl_seconds:
                    payload = deepcopy(self._cache["payload"])
                    payload["cache"] = {
                        **payload["cache"],
                        "state": "cached",
                        "served_at": now,
                        "age_seconds": round(age_seconds, 3),
                    }
                    return payload

        return self._build_and_store(deps, source_signature, now)

    def _build_uncached(self, council_rows: list[dict[str, Any]], *, cache_state: str) -> dict[str, Any]:
        deps = self.deps_factory()
        started = perf_counter()
        payload = build_intake_quality_summary(council_rows, deps)
        payload["cache"] = {
            "state": cache_state,
            "generated_at": self.now(),
            "served_at": self.now(),
            "age_seconds": 0,
            "ttl_seconds": self.ttl_seconds,
            "elapsed_ms": round((perf_counter() - started) * 1000, 3),
            "source_signature": _candidate_file_signature(deps.candidate_agreements_json()),
        }
        return payload

    def _build_and_store(self, deps: Any, source_signature: dict[str, Any], now: str) -> dict[str, Any]:
        started = perf_counter()
        payload = build_intake_quality_summary(None, deps)
        payload["cache"] = {
            "state": "refreshed",
            "generated_at": now,
            "served_at": now,
            "age_seconds": 0,
            "ttl_seconds": self.ttl_seconds,
            "elapsed_ms": round((perf_counter() - started) * 1000, 3),
            "source_signature": source_signature,
        }
        with self._lock:
            self._cache = {
                "payload": deepcopy(payload),
                "source_signature": source_signature,
                "created_monotonic": perf_counter(),
            }
        return payload


__all__ = [
    "IntakeQualityService",
    "build_intake_quality_summary",
]
