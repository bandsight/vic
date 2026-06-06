from scripts.build_exemplar_accuracy_evaluation import evaluate


def _exemplar() -> dict:
    return {
        "artifact_id": "fixture-exemplar",
        "gold_comparator_target": {"can_disagree_with_gold": True},
        "categories": [
            {
                "label": "Conditions",
                "entitlements": [
                    {
                        "entitlement_id": "conditions-work-from-home-protections",
                        "entitlement_label": "Work From Home Protections",
                        "semantic_mapping": {
                            "quantification_semantics": {"quantification_type": "binary_presence_or_absence"},
                            "comparator_semantics": {
                                "entries": [
                                    {
                                        "council": "Ballarat",
                                        "presence": "no_specific_provision_identified",
                                        "finding": "No specific provision identified.",
                                        "quantum_signals": [],
                                    },
                                    {
                                        "council": "Bendigo",
                                        "presence": "provided",
                                        "finding": "Available under flexible working arrangements.",
                                        "quantum_signals": [],
                                    },
                                ]
                            },
                        },
                    }
                ],
            }
        ],
    }


def test_evaluation_scores_boolean_presence_and_absence():
    locator = {
        "artifact_id": "fixture-locator",
        "run_scope": "gold_exemplar_v2",
        "profiles": [
            {
                "entitlement_id": "conditions-work-from-home-protections",
                "target_rows": [
                    {"council": "Ballarat", "state": "no_candidate_clause_found", "normalised_values": []},
                    {"council": "Bendigo", "state": "clause_found_value_missing", "clause_cards": [{"clause_id": "c1"}]},
                ],
            }
        ],
    }

    payload = evaluate(_exemplar(), locator, target=0.9)

    assert payload["passes_target"] is True
    assert payload["summary"]["operational_accuracy"] == 1.0
    assert payload["by_answer_kind"]["boolean"]["operational_accuracy"] == 1.0


def test_evaluation_records_supported_disagreement_separately_from_strict_match():
    locator = {
        "artifact_id": "fixture-locator",
        "run_scope": "gold_exemplar_v2",
        "profiles": [
            {
                "entitlement_id": "conditions-work-from-home-protections",
                "target_rows": [
                    {
                        "council": "Ballarat",
                        "state": "clause_found_value_extracted",
                        "normalised_values": [{"value": "available", "unit": "candidate provision"}],
                        "feature_cards": [{"feature_id": "f1"}],
                    },
                    {"council": "Bendigo", "state": "clause_found_value_missing", "clause_cards": [{"clause_id": "c1"}]},
                ],
            }
        ],
    }

    payload = evaluate(_exemplar(), locator, target=0.9)

    assert payload["passes_target"] is True
    assert payload["summary"]["operational_accuracy"] == 1.0
    assert payload["summary"]["strict_reference_accuracy"] == 0.5
    assert payload["summary"]["supported_disagreements"] == 1
