from copy import deepcopy

from scripts.build_entitlement_locator_codex_suggestions import (
    suggestions_from_gold,
    validate_suggestion,
    validate_suggestions,
)


def _gold_row(**overrides) -> dict:
    row = {
        "review_id": "locator_gold_v1_loddon_parental_primary",
        "source_artifact": "entitlement-locator-experiment-next-52-offset-0",
        "qa_pack": "locator-qa-review-entitlement-locator-experiment-next-52-offset-0",
        "council": "Loddon",
        "agreement_id": "ae532192",
        "entitlement_key": "leave_parental_leave_primary_carer",
        "entitlement_label": "Parental Leave Primary Carer",
        "clause_card_id": "clause-1",
        "feature_card_id": "feature-1",
        "feature_card_ids": ["feature-1"],
        "machine_cell_status": "clause_value",
        "machine_presence_status": "present_candidate",
        "machine_value_status": "quantified",
        "machine_failure_reason": "",
        "machine_provision_present": True,
        "machine_quantified_value_found": True,
        "evidence_span_text": "The primary carer is entitled to 20 weeks paid leave.",
        "evidence_span_text_hash": "a" * 64,
        "reference_link_count": 0,
    }
    row.update(overrides)
    return row


def _qa_pack() -> dict:
    return {
        "profiles": [
            {
                "key": "leave_parental_leave_primary_carer",
                "details": [
                    {
                        "council": "Loddon",
                        "entitlement_key": "leave_parental_leave_primary_carer",
                        "feature_card_ids": ["feature-1"],
                        "evidence_span": {"text": "The primary carer is entitled to 20 weeks paid leave."},
                    }
                ],
            }
        ]
    }


def test_codex_suggestions_reference_gold_rows_and_require_human_confirmation():
    gold_rows = [_gold_row()]
    suggestions = suggestions_from_gold(gold_rows, _qa_pack(), generated_at="2026-05-09T00:00:00+00:00")

    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion["gold_review_id"] == "locator_gold_v1_loddon_parental_primary"
    assert suggestion["suggestion_source"] == "codex_simulation"
    assert suggestion["requires_human_confirmation"] is True
    assert suggestion["suggested_review_decision"] == "correct"
    assert suggestion["suggested_expected_quantified_value_found"] is True
    assert validate_suggestions(suggestions, gold_rows) == []


def test_suggestions_cannot_contain_review_or_governance_authority_fields():
    gold_rows = [_gold_row()]
    suggestion = suggestions_from_gold(gold_rows, _qa_pack(), generated_at="2026-05-09T00:00:00+00:00")[0]
    suggestion["review_status"] = "reviewed_correct"
    suggestion["eligible_for_governance"] = True
    suggestion["promote_to_governed"] = True

    errors = validate_suggestion(suggestion, {gold_rows[0]["review_id"]})

    assert sum(error["code"] == "forbidden_authority_field" for error in errors) == 3


def test_quantified_suggestion_requires_value_unit_feature_and_span():
    gold_rows = [_gold_row(feature_card_id="", feature_card_ids=[], evidence_span_text="")]
    suggestion = suggestions_from_gold(gold_rows, _qa_pack(), generated_at="2026-05-09T00:00:00+00:00")[0]
    suggestion["suggested_expected_quantified_value_found"] = True
    suggestion["suggested_value"] = "20"
    suggestion["suggested_unit"] = "weeks"
    suggestion["evidence_summary"]["feature_card_id"] = ""
    suggestion["evidence_summary"]["evidence_span_text"] = ""

    errors = validate_suggestion(suggestion, {gold_rows[0]["review_id"]})

    assert any(error["code"] == "quantified_suggestion_requires_feature_card" for error in errors)
    assert any(error["code"] == "quantified_suggestion_requires_evidence_span" for error in errors)


def test_amount_not_stated_suggestion_is_not_quantified_success():
    gold_rows = [
        _gold_row(
            machine_value_status="discretionary_or_amount_not_stated",
            machine_quantified_value_found=False,
            evidence_span_text="Paid leave may be granted as approved.",
            feature_card_id="feature-1",
            feature_card_ids=["feature-1"],
        )
    ]

    suggestion = suggestions_from_gold(gold_rows, _qa_pack(), generated_at="2026-05-09T00:00:00+00:00")[0]

    assert suggestion["suggested_review_decision"] == "amount_not_stated_but_presence_correct"
    assert suggestion["suggested_expected_provision_present"] is True
    assert suggestion["suggested_expected_quantified_value_found"] is False
    assert suggestion["suggested_value"] is None
    assert suggestion["suggested_unit"] is None
    assert validate_suggestions([suggestion], gold_rows) == []


def test_suggestion_generation_does_not_mutate_gold_rows():
    gold_row = _gold_row()
    original = deepcopy(gold_row)

    suggestions_from_gold([gold_row], _qa_pack(), generated_at="2026-05-09T00:00:00+00:00")

    assert gold_row == original


def test_invalid_gold_reference_is_rejected():
    gold_rows = [_gold_row()]
    suggestion = suggestions_from_gold(gold_rows, _qa_pack(), generated_at="2026-05-09T00:00:00+00:00")[0]
    suggestion["gold_review_id"] = "missing"

    assert any(
        error["code"] == "invalid_gold_review_id"
        for error in validate_suggestions([suggestion], gold_rows)
    )
