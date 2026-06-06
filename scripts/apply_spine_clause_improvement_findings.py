from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_INPUT = ROOT / "wiki" / "artifacts" / "spine-clause-improvement" / "spine-clause-improvement-entitlement-locator-experiment-all-cached-79-offset-0.json"
DEFAULT_OUTPUT = ROOT / "data" / "review" / "spine_clause_process_rules.json"
SCHEMA_VERSION = "wiki.spine_clause_process_rules.v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wiki_as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_payload(improvement_payload: dict[str, Any], *, generated_at: str, source_path: Path) -> dict[str, Any]:
    summary = improvement_payload.get("summary") if isinstance(improvement_payload.get("summary"), dict) else {}
    spine = improvement_payload.get("document_spine") if isinstance(improvement_payload.get("document_spine"), dict) else {}
    clause = improvement_payload.get("clause_process") if isinstance(improvement_payload.get("clause_process"), dict) else {}
    quantification_queue = wiki_as_list(clause.get("clause_quantification_queue"))
    blocked_queue = wiki_as_list(clause.get("blocked_clause_review_queue"))
    routing_queue = wiki_as_list(clause.get("routing_or_front_matter_review_queue"))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_artifact": {
            "artifact_id": improvement_payload.get("artifact_id"),
            "path": str(source_path),
            "generated_at": improvement_payload.get("generated_at"),
        },
        "summary": {
            "target_agreements": summary.get("target_agreements", 0),
            "source_spines_ready": summary.get("source_spines_ready", 0),
            "document_maps_ready": summary.get("document_maps_ready", 0),
            "document_map_backfill_needed": summary.get("document_map_backfill_needed", 0),
            "source_cache_repair_needed": summary.get("source_cache_repair_needed", 0),
            "entitlements": summary.get("entitlements", 0),
            "clause_only_cells": summary.get("clause_only_cells", 0),
            "blocked_or_adjacent_cells": summary.get("blocked_or_adjacent_cells", 0),
            "feature_card_cells": summary.get("feature_card_cells", 0),
            "quantification_queue_items": len(quantification_queue),
            "blocked_review_queue_items": len(blocked_queue),
            "routing_or_front_matter_queue_items": len(routing_queue),
        },
        "document_spine_rules": {
            "target_source_policy": "Map every active latest-council agreement that has cached page text before judging entitlement absence.",
            "page_role_model": [
                "approval_decision_front_matter",
                "undertaking_source_term",
                "table_of_contents",
                "agreement_text",
                "schedule_or_appendix",
                "rates_or_allowances_table",
                "weak_text",
                "unclassified_source_text",
            ],
            "routing_rules": [
                "Table-of-contents pages are routing signals only; do not promote them as clause evidence.",
                "Approval decision pages are context for source custody and undertakings, not ordinary agreement clauses.",
                "Undertakings can be source terms, but must keep an undertaking_source_term flag through clause and feature review.",
                "Rates, allowances, and classification tables should stay as table containers until a specific entitlement value is selected.",
            ],
            "document_map_backfill_queue": wiki_as_list(spine.get("document_map_backfill_queue")),
            "source_cache_repair_queue": wiki_as_list(spine.get("source_cache_repair_queue")),
        },
        "clause_process_rules": {
            "promotion_gate": [
                "A green feature card needs source text, a clause/source container type, an evidence span, and no routing-only table-of-contents flag.",
                "Clause-found/value-missing rows enter quantification review or amount-not-stated review before they become feature cards.",
                "Blocked or adjacent rows are not failures; they are scope-boundary examples used to tune exclusions and accepted subclasses.",
                "Reference-heavy rows need a decision on whether the agreement adds a local entitlement or only points to NES, Award, Act, policy, or another clause.",
            ],
            "source_container_types": clause.get("source_container_type_counts") if isinstance(clause.get("source_container_type_counts"), dict) else {},
            "process_rule_flags": clause.get("process_rule_flag_counts") if isinstance(clause.get("process_rule_flag_counts"), dict) else {},
            "quantification_queue": quantification_queue,
            "blocked_clause_review_queue": blocked_queue,
            "routing_or_front_matter_review_queue": routing_queue,
        },
        "entitlement_process_actions": wiki_as_list(clause.get("entitlements")),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply spine/clause improvement findings as process rules.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = args.input.resolve()
    payload = build_payload(load_json(source_path), generated_at=utc_now_iso(), source_path=source_path)
    output_path = args.output.resolve()
    write_json(output_path, payload)
    print(json.dumps({
        "schema_version": "wiki.spine_clause_process_rules_build.v1",
        "generated_at": payload["generated_at"],
        "output_path": str(output_path),
        "summary": payload["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
