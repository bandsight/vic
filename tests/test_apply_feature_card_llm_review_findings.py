from scripts.apply_feature_card_llm_review_findings import build_payload


def test_feature_card_llm_review_updates_definition_and_quantum_rules():
    overrides_payload = {
        "schema_version": "wiki.entitlement_loop_rule_overrides.v2",
        "summary": {"overrides": 1},
        "overrides": [
            {
                "entitlement_id": "leave-test",
                "label": "Test Leave",
                "classification_boundary": {
                    "canonical_definition": "Old definition.",
                    "included": ["Existing include."],
                    "excluded": ["Existing exclude."],
                    "needs_review": ["Existing review."],
                },
                "accepted_subclasses": [],
                "value_rules": ["Existing value rule."],
            }
        ],
    }
    review_payload = {
        "artifact_id": "feature-card-llm-review-test",
        "generated_at": "2026-05-11T01:00:00+00:00",
        "rows": [
            {
                "entitlement_id": "leave-test",
                "green_feature_cards": 3,
                "llm_status": "parsed",
                "context_flag_counts": {"timeframe_or_basis_missing": 2},
                "llm_review": {
                    "definition_review": {
                        "status": "tighten",
                        "industry_standard_definition": "Industry standard definition.",
                        "inclusions": ["New include."],
                        "exclusions": ["New exclude."],
                        "review_if": ["New review trigger."],
                    },
                    "quantum_review": {
                        "normal_value_model": "Expect days per year.",
                        "required_context_fields": ["timeframe", "cohort"],
                        "timeframe_rules": ["Days must state annual or occasion basis."],
                        "unit_normalisation_rules": ["Separate available from numeric days."],
                        "cohort_scope_rules": ["Specialist-only clauses need scope review."],
                    },
                    "alignment_review": {
                        "overall_status": "mixed",
                        "suspicious_patterns": ["Unusual value."],
                        "missing_context_patterns": ["No timeframe."],
                    },
                    "feature_card_decisions": [
                        {
                            "feature_id": "feature-one",
                            "decision": "needs_timeframe_or_basis",
                            "required_fix": "Find the annual basis.",
                        }
                    ],
                    "rule_updates": {
                        "definition_updates": ["Definition update note."],
                        "value_rules": ["Promotion requires source clause context."],
                        "subclass_splits": ["Per-year quantified leave"],
                        "promotion_gate": "requires_definition_quantum_alignment",
                    },
                },
            }
        ],
    }

    payload = build_payload(overrides_payload, review_payload, generated_at="2026-05-11T02:00:00+00:00")

    override = payload["overrides"][0]
    assert payload["schema_version"] == "wiki.entitlement_loop_rule_overrides.v3"
    assert payload["summary"]["feature_card_llm_review_applied"] == 1
    assert override["classification_boundary"]["canonical_definition"] == "Industry standard definition."
    assert "New include." in override["classification_boundary"]["included"]
    assert "New exclude." in override["classification_boundary"]["excluded"]
    assert "New review trigger." in override["classification_boundary"]["needs_review"]
    assert "Days must state annual or occasion basis." in override["value_rules"]
    assert override["accepted_subclasses"][0]["relationship"] == "feature_card_llm_subclass_split"
    assert override["feature_card_promotion_gate"] == "requires_definition_quantum_alignment"
    assert override["feature_card_llm_review"]["alignment_status"] == "mixed"
