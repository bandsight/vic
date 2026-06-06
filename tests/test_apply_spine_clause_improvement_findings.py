from pathlib import Path

from scripts.apply_spine_clause_improvement_findings import build_payload


def test_apply_spine_clause_improvement_findings_writes_process_rules():
    payload = build_payload(
        {
            "artifact_id": "spine-clause-improvement-test",
            "generated_at": "2026-05-10T01:00:00+00:00",
            "summary": {
                "target_agreements": 2,
                "document_maps_ready": 1,
                "document_map_backfill_needed": 1,
                "source_cache_repair_needed": 0,
                "entitlements": 1,
                "clause_only_cells": 3,
                "blocked_or_adjacent_cells": 2,
                "feature_card_cells": 4,
            },
            "document_spine": {
                "document_map_backfill_queue": [{"agreement_id": "ae-two"}],
                "source_cache_repair_queue": [],
            },
            "clause_process": {
                "source_container_type_counts": {"agreement_clause": 4},
                "process_rule_flag_counts": {"quantification_or_amount_not_stated_review": 3},
                "clause_quantification_queue": [{"agreement_id": "ae-one"}],
                "blocked_clause_review_queue": [{"agreement_id": "ae-three"}],
                "routing_or_front_matter_review_queue": [{"agreement_id": "ae-four"}],
                "entitlements": [{"entitlement_id": "leave-test"}],
            },
        },
        generated_at="2026-05-10T02:00:00+00:00",
        source_path=Path("improvement.json"),
    )

    assert payload["schema_version"] == "wiki.spine_clause_process_rules.v1"
    assert payload["summary"]["quantification_queue_items"] == 1
    assert "table-of-contents" in payload["document_spine_rules"]["routing_rules"][0].lower()
    assert payload["clause_process_rules"]["quantification_queue"][0]["agreement_id"] == "ae-one"
    assert payload["entitlement_process_actions"][0]["entitlement_id"] == "leave-test"
