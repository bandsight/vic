"""Write accepted uplift rules to legacy-compatible gold JSON files.

The schema is the format used by benchmarking's `data/gold/rules/<ae_id>.rules.json`:
    {
      "uplift_rules": [ {...}, ... ],
      "timing_pattern": "...",
      "notes": "...",
      "file": "<ae_id>.pdf",
      "council": "...",
      "covered_councils": [...],
      "multi_employer": bool,
      "ae_id": "<ae_id>",
      "provenance": { ... }   # new in workbench
    }

The workbench adds a `provenance` block that downstream code may ignore.
This keeps the format a strict superset — readers of benchmarking's old
format keep working.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from benchmarking_data_factory.uplift_rules.schema import UpliftRulesSuggestion


def _rule_to_dict(rule) -> dict[str, Any]:
    d = dataclasses.asdict(rule)
    # Preserve the ordering that benchmarking readers expect
    ordered = {
        "period_label": d.get("period_label"),
        "effective_date": d.get("effective_date"),
        "quantum": d.get("quantum"),
        "quantum_type": d.get("quantum_type"),
        "quantum_floor": d.get("quantum_floor"),
        "quantum_ceiling": d.get("quantum_ceiling"),
        "quantum_external_ref": d.get("quantum_external_ref"),
        "quantum_external_definition": d.get("quantum_external_definition"),
        "quantum_resolution": d.get("quantum_resolution"),
        "timing_clause": d.get("timing_clause"),
        "source_page": d.get("source_page"),
        "applies_to": d.get("applies_to"),
        "nearby_table_headings": list(d.get("nearby_table_headings") or []),
        "extraction_warnings": list(d.get("extraction_warnings") or []),
        "confidence": d.get("confidence"),
    }
    return ordered


def build_gold_payload(suggestion: UpliftRulesSuggestion) -> dict[str, Any]:
    """Convert a suggestion into the legacy-compatible gold dict."""
    doc = suggestion.document
    prov = suggestion.provenance
    return {
        "uplift_rules": [_rule_to_dict(r) for r in doc.rules],
        "timing_pattern": doc.timing_pattern,
        "notes": doc.notes,
        "file": f"{doc.ae_id}.pdf",
        "council": doc.council,
        "covered_councils": list(doc.covered_councils),
        "multi_employer": doc.multi_employer,
        "ae_id": doc.ae_id,
        "provenance": {
            "model": prov.inputs.model,
            "prompt_version": prov.inputs.prompt_version,
            "prompt_sha256": prov.inputs.prompt_sha256,
            "pdf_sha256": prov.inputs.pdf_sha256,
            "page_numbers": list(prov.inputs.page_numbers),
            "page_text_sha256": prov.inputs.page_text_sha256,
            "code_git_sha": prov.code_git_sha,
            "suggestion_id": suggestion.suggestion_id,
            "run_started_at": prov.run_started_at.isoformat(),
            "run_completed_at": prov.run_completed_at.isoformat(),
            "run_duration_ms": prov.run_duration_ms,
            "extraction_status": prov.extraction_status,
        },
    }


def write_gold(suggestion: UpliftRulesSuggestion, out_dir: Path) -> Path:
    """Write the gold JSON file. Returns the path written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{suggestion.document.ae_id}.rules.json"
    payload = build_gold_payload(suggestion)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


__all__ = ["build_gold_payload", "write_gold"]
