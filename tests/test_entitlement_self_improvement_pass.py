from pathlib import Path

from scripts.build_entitlement_self_improvement_pass import build_payload


def test_self_improvement_payload_scores_green_feature_cards(tmp_path):
    locator_payload = {
        "artifact_id": "locator-test",
        "generated_at": "2026-05-10T00:00:00+00:00",
        "profiles": [
            {
                "entitlement_id": "annual-leave",
                "key": "annual_leave",
                "label": "Annual Leave",
                "rule_contract": {
                    "definition": "Annual leave for ordinary employees.",
                    "classification_boundary": {
                        "canonical_definition": "Annual leave for ordinary employees.",
                        "included": ["Ordinary annual leave."],
                        "excluded": ["Purchased leave."],
                        "needs_review": ["Ambiguous extra leave."],
                    },
                },
                "target_rows": [
                    {
                        "council": "Ballarat",
                        "agreement_id": "ae-test",
                        "page_count": 2,
                        "state": "clause_found_value_extracted",
                        "value_extracted": True,
                        "normalised_values": [{"value": "4", "unit": "weeks"}],
                        "feature_cards": [
                            {
                                "feature_id": "feature-one",
                                "page_number_physical": 5,
                                "value": "4",
                                "unit": "weeks",
                                "evidence_span_text": "12.1 An employee is entitled to 4 weeks annual leave.",
                            }
                        ],
                    }
                ],
            },
            {
                "entitlement_id": "new-benefit",
                "key": "new_benefit",
                "label": "New Benefit",
                "target_rows": [
                    {
                        "council": "Ballarat",
                        "agreement_id": "ae-test",
                        "page_count": 2,
                        "state": "no_candidate_clause_found",
                    }
                ],
            },
        ],
    }

    payload = build_payload(
        locator_payload,
        generated_at="2026-05-10T01:00:00+00:00",
        source_path=Path(tmp_path / "locator.json"),
    )

    rows_by_id = {row["entitlement_id"]: row for row in payload["rows"]}
    assert payload["summary"]["entitlements"] == 2
    assert payload["summary"]["green_feature_cells"] == 1
    assert rows_by_id["annual-leave"]["coverage"]["green_feature_cells"] == 1
    assert rows_by_id["annual-leave"]["observed_value_profile"]["common_values"]["4 weeks"] == 1
    assert rows_by_id["annual-leave"]["normal_value_hypothesis"].startswith("Most common observed value is 4 weeks")
    assert rows_by_id["annual-leave"]["sample_green_cards"][0]["feature_card_ids"] == ["feature-one"]
    assert rows_by_id["new-benefit"]["status"] == "needs_external_research"
    assert any(
        suggestion["type"] == "external_research"
        for suggestion in rows_by_id["new-benefit"]["improvement_suggestions"]
    )


def test_self_improvement_keeps_generic_taxonomy_contracts_as_unsolidified(tmp_path):
    locator_payload = {
        "artifact_id": "locator-test",
        "profiles": [
            {
                "entitlement_id": "generic-benefit",
                "key": "generic_benefit",
                "label": "Generic Benefit",
                "rule_contract": {
                    "rule_origin": "generic_taxonomy_fallback",
                    "definition": "Generic benefit.",
                    "classification_boundary": {
                        "canonical_definition": "Generic benefit.",
                        "included": ["Generic inclusion."],
                        "excluded": ["Generic exclusion."],
                        "needs_review": ["Generic review."],
                    },
                },
                "target_rows": [
                    {
                        "council": "Ballarat",
                        "agreement_id": "ae-test",
                        "page_count": 1,
                        "state": "clause_found_value_extracted",
                        "value_extracted": True,
                        "normalised_values": [{"value": "1", "unit": "day"}],
                        "feature_cards": [{"feature_id": "feature-one", "evidence_span_text": "One day."}],
                    }
                ],
            }
        ],
    }

    payload = build_payload(
        locator_payload,
        generated_at="2026-05-10T01:00:00+00:00",
        source_path=tmp_path / "locator.json",
    )

    row = payload["rows"][0]
    assert row["status"] == "needs_definition_solidification"
    assert row["improvement_suggestions"][0]["type"] == "definition_boundary"
