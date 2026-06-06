import json
from pathlib import Path

from scripts.build_spine_clause_improvement_pass import build_payload


def _locator_payload():
    return {
        "artifact_id": "entitlement-locator-experiment-test",
        "generated_at": "2026-05-10T00:00:00+00:00",
        "target_comparator_set": [
            {"council": "Alpha", "agreement_id": "ae-one", "agreement_name": "Alpha Agreement"},
            {"council": "Beta", "agreement_id": "ae-two", "agreement_name": "Beta Agreement"},
        ],
        "profiles": [
            {
                "entitlement_id": "leave-test",
                "label": "Test Leave",
                "target_rows": [
                    {
                        "council": "Alpha",
                        "agreement_id": "ae-one",
                        "page_count": 12,
                        "state": "clause_found_value_missing",
                        "clause_cards": [
                            {
                                "source_container_type": "agreement_clause",
                                "process_rule_flags": ["quantification_or_amount_not_stated_review"],
                                "review_status": "needs_quantification_review",
                                "raw_clause_text": "10. Test Leave Employees may access leave.",
                            }
                        ],
                        "feature_cards": [],
                        "best_candidate": {"page": 10, "heading": "10. Test Leave"},
                    },
                    {
                        "council": "Beta",
                        "agreement_id": "ae-two",
                        "page_count": 0,
                        "state": "no_candidate_clause_found",
                        "clause_cards": [],
                        "feature_cards": [],
                    },
                ],
            }
        ],
    }


def test_spine_clause_improvement_pass_surfaces_spine_and_clause_queues(tmp_path: Path):
    maps = tmp_path / "document-maps"
    maps.mkdir()
    (maps / "ae-one.json").write_text(
        json.dumps({
            "agreement_id": "ae-one",
            "summary": {
                "pages_scanned": 12,
                "sections_detected": 4,
                "headings_detected": 4,
                "page_role_counts": {"agreement_text": 12},
            },
        }),
        encoding="utf-8",
    )

    payload = build_payload(
        _locator_payload(),
        document_map_dir=maps,
        rule_overrides_payload={"overrides": [{"entitlement_id": "leave-test", "research_applied": True}]},
        generated_at="2026-05-10T01:00:00+00:00",
        source_path=Path("locator.json"),
    )

    assert payload["summary"]["target_agreements"] == 2
    assert payload["summary"]["document_maps_ready"] == 1
    assert payload["summary"]["source_cache_repair_needed"] == 1
    assert payload["summary"]["clause_only_cells"] == 1
    assert payload["clause_process"]["clause_quantification_queue"][0]["agreement_id"] == "ae-one"
    assert payload["clause_process"]["entitlements"][0]["learned_rule_ready"] is True
