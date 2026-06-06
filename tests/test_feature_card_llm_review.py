from pathlib import Path

from scripts.build_feature_card_llm_review import (
    build_payload,
    choose_review_samples,
    context_flags,
    infer_timeframes,
)


def test_context_flags_require_timeframe_and_scope_for_quantum_values():
    value = {"value": "5", "unit": "days", "condition": ""}
    flags = context_flags(
        evidence="MCH nurses may access 5 days. This is subject to the NES.",
        value=value,
        common_values={"10 days"},
    )

    assert infer_timeframes("5 days per year", value) == ["per_year"]
    assert "timeframe_or_basis_missing" in flags
    assert "condition_missing" in flags
    assert "specialist_cohort_signal" in flags
    assert "reference_heavy_context" in flags
    assert "uncommon_against_feature_set" in flags


def test_choose_review_samples_prioritises_risky_unique_feature_cards():
    samples = [
        {"feature_id": "safe", "council": "Alpha", "context_flags": []},
        {"feature_id": "risk", "council": "Beta", "context_flags": ["timeframe_or_basis_missing"]},
        {"feature_id": "risk", "council": "Gamma", "context_flags": ["timeframe_or_basis_missing"]},
        {"feature_id": "cohort", "council": "Delta", "context_flags": ["specialist_cohort_signal"]},
    ]

    chosen = choose_review_samples(samples, limit=2)

    assert [item["feature_id"] for item in chosen] == ["risk", "cohort"]


def test_offline_payload_reviews_feature_cards_for_definition_and_quantum_context(tmp_path: Path):
    locator_payload = {
        "artifact_id": "locator-test",
        "generated_at": "2026-05-11T00:00:00+00:00",
        "profiles": [
            {
                "entitlement_id": "leave-test",
                "label": "Test Leave",
                "rule_contract": {
                    "definition": "Does the agreement provide test leave?",
                    "classification_boundary": {
                        "included": ["Operative test leave clauses."],
                        "excluded": ["Headings only."],
                        "needs_review": ["Unclear scope."],
                    },
                },
                "target_rows": [
                    {
                        "council": "Alpha",
                        "agreement_id": "ae-one",
                        "value_extracted": True,
                        "best_candidate": {"page": 4, "excerpt": "Test leave 2 days amount not stated."},
                        "normalised_values": [{"value": "2", "unit": "days", "condition": ""}],
                        "feature_cards": [
                            {
                                "feature_id": "feature-one",
                                "evidence_span_text": "Test leave 2 days amount not stated.",
                            }
                        ],
                    }
                ],
            }
        ],
    }

    payload = build_payload(
        locator_payload,
        {},
        generated_at="2026-05-11T01:00:00+00:00",
        source_path=tmp_path / "locator.json",
        env={},
        model="test-model",
        max_tokens=100,
        offline=True,
    )

    row = payload["rows"][0]
    assert payload["summary"]["entitlements_reviewed"] == 1
    assert payload["summary"]["green_feature_cards_in_scope"] == 1
    assert row["llm_status"] == "offline_deterministic"
    assert "timeframe_or_basis_missing" in row["context_flag_counts"]
    assert row["llm_review"]["quantum_review"]["required_context_fields"]
