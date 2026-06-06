"""Content-addressed cache for uplift rules suggestions.

Cache key is a SHA-256 of the ExtractionInputs fields that uniquely
identify a run: pdf_sha + page_numbers + page_text_sha + prompt_sha + model.
Entries are stored as JSON under the cache root. Replay is byte-deterministic
when the inputs match.

The cache is *append-only* in normal use. A caller may delete an entry to
force a rerun, but suggest() never deletes.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from benchmarking_data_factory.uplift_rules.schema import (
    ExtractionInputs,
    Provenance,
    RulesDocument,
    UpliftRule,
    UpliftRulesSuggestion,
)


def _canonical_key_bytes(inputs: ExtractionInputs) -> bytes:
    payload = {
        "pdf_sha256": inputs.pdf_sha256,
        "page_numbers": list(inputs.page_numbers),
        "page_text_sha256": inputs.page_text_sha256,
        "prompt_sha256": inputs.prompt_sha256,
        "prompt_version": inputs.prompt_version,
        "model": inputs.model,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_suggestion_id(inputs: ExtractionInputs) -> str:
    """Return the canonical cache key (a hex SHA-256)."""
    return hashlib.sha256(_canonical_key_bytes(inputs)).hexdigest()


def _to_jsonable(obj):
    if dataclasses.is_dataclass(obj):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, tuple):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, list):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def _from_jsonable_suggestion(raw: dict) -> UpliftRulesSuggestion:
    doc_raw = raw["document"]
    prov_raw = raw["provenance"]
    rules = tuple(
        UpliftRule(
            **{
                **r,
                "nearby_table_headings": tuple(r.get("nearby_table_headings") or ()),
                "extraction_warnings": tuple(r.get("extraction_warnings") or ()),
            }
        )
        for r in doc_raw["rules"]
    )
    document = RulesDocument(
        ae_id=doc_raw["ae_id"],
        council=doc_raw["council"],
        timing_pattern=doc_raw["timing_pattern"],
        rules=rules,
        notes=doc_raw.get("notes", ""),
        covered_councils=tuple(doc_raw.get("covered_councils", ())),
        multi_employer=doc_raw.get("multi_employer", False),
    )
    inputs = ExtractionInputs(
        pdf_sha256=prov_raw["inputs"]["pdf_sha256"],
        page_numbers=tuple(prov_raw["inputs"]["page_numbers"]),
        page_text_sha256=prov_raw["inputs"]["page_text_sha256"],
        prompt_version=prov_raw["inputs"]["prompt_version"],
        prompt_sha256=prov_raw["inputs"]["prompt_sha256"],
        model=prov_raw["inputs"]["model"],
    )
    provenance = Provenance(
        inputs=inputs,
        code_git_sha=prov_raw["code_git_sha"],
        run_started_at=datetime.fromisoformat(prov_raw["run_started_at"]),
        run_completed_at=datetime.fromisoformat(prov_raw["run_completed_at"]),
        run_duration_ms=prov_raw["run_duration_ms"],
        llm_raw_response=prov_raw["llm_raw_response"],
        extraction_status=prov_raw["extraction_status"],
    )
    return UpliftRulesSuggestion(
        document=document,
        provenance=provenance,
        suggestion_id=raw["suggestion_id"],
    )


class SuggestionCache:
    """JSON-on-disk cache; one file per suggestion_id."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, suggestion_id: str) -> Path:
        return self.root / f"{suggestion_id}.json"

    def get(self, suggestion_id: str) -> Optional[UpliftRulesSuggestion]:
        p = self._path_for(suggestion_id)
        if not p.exists():
            return None
        raw = json.loads(p.read_text(encoding="utf-8"))
        return _from_jsonable_suggestion(raw)

    def put(self, suggestion: UpliftRulesSuggestion) -> Path:
        p = self._path_for(suggestion.suggestion_id)
        p.write_text(
            json.dumps(_to_jsonable(suggestion), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return p

    def has(self, suggestion_id: str) -> bool:
        return self._path_for(suggestion_id).exists()


__all__ = [
    "SuggestionCache",
    "compute_suggestion_id",
]
