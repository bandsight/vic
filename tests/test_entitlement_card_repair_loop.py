from pathlib import Path

from scripts.build_entitlement_card_repair_loop import build_payload, profile_context


def _profile(rows: list[dict]) -> dict:
    return {
        "entitlement_id": "leave-test",
        "label": "Test Leave",
        "output_contract": {"answer_kind": "quantitative"},
        "rule_contract": {
            "definition": "Paid test leave for standard employees.",
            "scope": "standard_employees",
            "classification_boundary": {
                "included": ["Operative paid test leave clauses."],
                "excluded": ["Policy references only."],
                "needs_review": ["Unclear timeframe."],
            },
        },
        "target_rows": rows,
    }


def _blocked_row() -> dict:
    return {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [
            {"value": "5", "unit": "days", "condition": ""},
            {"value": "available", "unit": "candidate provision", "condition": ""},
        ],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "page_number_physical": 4,
                "review_status": "needs_feature_card_llm_review",
                "process_rule_flags": ["feature_value_extracted", "feature_llm_timeframe_or_basis_review"],
                "raw_clause_text": "Employees may access 5 days. The provision is available by agreement.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "review_status": "needs_feature_card_llm_review",
                "process_rule_flags": ["feature_value_extracted", "feature_llm_timeframe_or_basis_review"],
                "value": "5",
                "unit": "days",
                "evidence_span_text": "Employees may access 5 days.",
            }
        ],
    }


def test_profile_context_keeps_blocked_reason_and_source_samples():
    context = profile_context(_profile([_blocked_row()]), {"cards": []}, sample_limit=3)

    assert context["blocked_rows"] == 1
    assert context["blocked_value_rows"] == 1
    assert context["failure_counts"]["blocking_process_rule_flags"] == 1
    assert context["failure_counts"]["review_status_not_strong"] == 1
    assert context["blocked_samples"][0]["council"] == "Ballarat"
    assert context["blocked_samples"][0]["feature_samples"][0]["feature_id"] == "feature-one"


def test_offline_repair_payload_summarises_blocked_entitlement_rows(tmp_path: Path):
    locator_payload = {"artifact_id": "locator-test", "profiles": [_profile([_blocked_row()])]}
    cards_payload = {"artifact_id": "cards-test", "cards": []}

    payload = build_payload(
        locator_payload,
        cards_payload,
        generated_at="2026-05-12T00:00:00+00:00",
        source_path=tmp_path / "locator.json",
        cards_path=tmp_path / "cards.json",
        env={},
        model="test-model",
        max_tokens=100,
        offline=True,
        sample_limit=3,
    )

    row = payload["rows"][0]
    assert payload["summary"]["entitlements_reviewed"] == 1
    assert payload["summary"]["blocked_value_rows_reviewed"] == 1
    assert payload["summary"]["llm_statuses"] == {"offline_deterministic": 1}
    assert row["repair_review"]["row_decisions"][0]["decision"] == "repairable_by_context_extraction"
