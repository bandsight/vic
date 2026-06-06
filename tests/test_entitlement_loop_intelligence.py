from pathlib import Path

from scripts.build_entitlement_loop_intelligence import build_payload


def test_loop_intelligence_turns_diagnosis_into_review_actions(tmp_path):
    locator_payload = {
        "artifact_id": "locator-test",
        "profiles": [
            {
                "entitlement_id": "annual-leave",
                "label": "Annual Leave",
                "target_rows": [
                    {
                        "council": "Ballarat",
                        "agreement_id": "ae-test",
                        "value_extracted": True,
                        "normalised_values": [{"value": "4", "unit": "weeks"}],
                        "feature_cards": [
                            {
                                "feature_id": "feature-one",
                                "page_number_physical": 3,
                                "evidence_span_text": "12.1 An employee receives 4 weeks annual leave.",
                            }
                        ],
                        "best_candidate": {"excerpt": "12.1 An employee receives 4 weeks annual leave."},
                    }
                ],
            }
        ],
    }
    self_improvement_payload = {
        "artifact_id": "self-test",
        "rows": [
            {
                "entitlement_id": "annual-leave",
                "label": "Annual Leave",
                "coverage": {"green_feature_cells": 12, "clause_only_cells": 0, "blocked_or_adjacent_cells": 0},
                "observed_value_profile": {
                    "feature_values": 12,
                    "common_values": {"4 weeks": 10},
                    "units": {"weeks": 10},
                    "numeric_distinct_count": 1,
                },
                "normal_value_hypothesis": "Most common observed value is 4 weeks.",
                "improvement_suggestions": [],
            }
        ],
    }

    payload = build_payload(
        locator_payload,
        self_improvement_payload,
        generated_at="2026-05-10T03:00:00+00:00",
        source_path=Path(tmp_path / "self.json"),
    )

    row = payload["rows"][0]
    assert payload["summary"]["entitlements"] == 1
    assert payload["summary"]["promotion_gates"]["candidate_for_human_validation"] == 1
    assert row["loop_status"] == "ready_for_validation"
    assert row["promotion_gate"] == "candidate_for_human_validation"
    assert "Annual Leave" in row["entitlement_question"]
    assert row["answer_shape"]["expectation"].startswith("Expect 4 weeks")
    assert row["rule_change_candidates"]["value_rules"][0].startswith("Use 4 weeks")
    assert row["validation_queue"][0]["feature_card_ids"] == ["feature-one"]


def test_loop_intelligence_blocks_generic_boundaries(tmp_path):
    locator_payload = {
        "artifact_id": "locator-test",
        "profiles": [{"entitlement_id": "allowance", "label": "Allowance", "target_rows": []}],
    }
    self_improvement_payload = {
        "artifact_id": "self-test",
        "rows": [
            {
                "entitlement_id": "allowance",
                "label": "Allowance",
                "coverage": {"green_feature_cells": 3},
                "observed_value_profile": {"common_values": {}, "units": {}},
                "improvement_suggestions": [{"type": "definition_boundary", "priority": "high"}],
            }
        ],
    }

    payload = build_payload(
        locator_payload,
        self_improvement_payload,
        generated_at="2026-05-10T03:00:00+00:00",
        source_path=Path(tmp_path / "self.json"),
    )

    row = payload["rows"][0]
    assert row["loop_status"] == "define_boundary"
    assert row["promotion_gate"] == "blocked_until_definition_research"
    assert row["next_loop_steps"][0].startswith("Write the inclusion")
