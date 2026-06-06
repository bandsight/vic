from scripts.build_entitlement_locator_human_review_worksheet import (
    HUMAN_REVIEW_COLUMNS,
    validate_worksheet,
    worksheet_rows,
)


def _gold(review_id: str, council: str, key: str, *, machine_cell_status: str = "clause_value") -> dict:
    return {
        "review_id": review_id,
        "council": council,
        "agreement_id": f"ae-{council}",
        "entitlement_key": key,
        "entitlement_label": key.replace("_", " ").title(),
        "sample_reason": "fixture",
        "machine_cell_status": machine_cell_status,
        "machine_clause_found": machine_cell_status in {"clause_value", "clause_only"},
        "machine_feature_found": machine_cell_status == "clause_value",
        "machine_provision_present": machine_cell_status in {"clause_value", "clause_only"},
        "machine_quantified_value_found": machine_cell_status == "clause_value",
        "machine_presence_status": "present_candidate" if machine_cell_status != "not_found" else "not_found_not_reviewed",
        "machine_value_status": "quantified" if machine_cell_status == "clause_value" else "not_applicable",
        "machine_failure_reason": "" if machine_cell_status == "clause_value" else "no_candidate_clause_found",
        "clause_card_id": "clause-1" if machine_cell_status != "not_found" else "",
        "feature_card_id": "feature-1" if machine_cell_status == "clause_value" else "",
        "feature_card_ids": ["feature-1"] if machine_cell_status == "clause_value" else [],
        "page": 7 if machine_cell_status != "not_found" else None,
        "block_id": "block-1" if machine_cell_status != "not_found" else "",
        "parser_used": "cached_page_text" if machine_cell_status != "not_found" else "",
        "parser_version": "workbench_pages_json_v1" if machine_cell_status != "not_found" else "",
        "raw_clause_text_hash": "a" * 64 if machine_cell_status != "not_found" else "",
        "evidence_span_text": "20 weeks paid leave" if machine_cell_status in {"clause_value", "clause_only"} else "",
        "evidence_span_text_hash": "b" * 64 if machine_cell_status in {"clause_value", "clause_only"} else "",
        "reference_link_count": 0,
        "reference_links": [],
    }


def _qa(council: str, key: str, *, blockers=None, failure_reason="") -> dict:
    return {
        "profiles": [
            {
                "key": key,
                "details": [
                    {
                        "council": council,
                        "entitlement_key": key,
                        "blocker_signals": blockers or [],
                        "failure_reason": failure_reason,
                        "reference_links": [],
                    }
                ],
            }
        ]
    }


def _suggestion(review_id: str) -> dict:
    return {
        "gold_review_id": review_id,
        "suggestion_id": "suggestion-1",
        "suggestion_source": "codex_simulation",
        "requires_human_confirmation": True,
        "suggested_review_decision": "correct",
        "suggested_expected_provision_present": True,
        "suggested_expected_quantified_value_found": True,
        "suggested_value": "20",
        "suggested_unit": "weeks",
        "suggested_scope": "primary_carer",
        "suggested_cross_reference_review": "not_required",
        "confidence": "high",
        "reasons": ["Evidence span states the quantum."],
        "risk_flags": [],
    }


def test_worksheet_includes_all_gold_rows_and_keeps_human_fields_blank():
    gold_rows = [
        _gold("r1", "Loddon", "leave_parental_leave_primary_carer"),
        _gold("r2", "Yarra", "leave_emergency_services_leave", machine_cell_status="clause_only"),
    ]
    qa_pack = {
        "profiles": [
            {
                "key": "leave_parental_leave_primary_carer",
                "details": [{"council": "Loddon", "entitlement_key": "leave_parental_leave_primary_carer"}],
            },
            {
                "key": "leave_emergency_services_leave",
                "details": [{"council": "Yarra", "entitlement_key": "leave_emergency_services_leave"}],
            },
        ]
    }
    suggestions = [_suggestion("r1"), _suggestion("r2")]

    rows = worksheet_rows(gold_rows, qa_pack, suggestions)

    assert len(rows) == 2
    assert validate_worksheet(rows, gold_rows, suggestions) == []
    for row in rows:
        assert row["codex_advisory_label"] == "advisory_only_human_confirmation_required"
        for column in HUMAN_REVIEW_COLUMNS:
            assert row[column] == ""


def test_worksheet_preserves_evidence_and_provenance_when_available():
    gold_rows = [_gold("r1", "Loddon", "leave_parental_leave_primary_carer")]
    rows = worksheet_rows(gold_rows, _qa("Loddon", "leave_parental_leave_primary_carer"), [_suggestion("r1")])
    row = rows[0]

    assert row["evidence_span_text"] == "20 weeks paid leave"
    assert row["evidence_span_text_hash"] == "b" * 64
    assert row["parser_used"] == "cached_page_text"
    assert row["page"] == 7
    assert row["block_id"] == "block-1"


def test_additional_annual_rows_remain_non_promoted_review_targets():
    gold_rows = [
        _gold(
            "r1",
            "Benalla",
            "additional_annual_leave",
            machine_cell_status="blocked",
        )
    ]
    qa_pack = _qa("Benalla", "additional_annual_leave", blockers=["purchased_leave"], failure_reason="candidate_blocked")
    suggestions = [_suggestion("r1")]

    rows = worksheet_rows(gold_rows, qa_pack, suggestions)

    assert validate_worksheet(rows, gold_rows, suggestions) == []
    assert rows[0]["entitlement_key"] == "additional_annual_leave"
    assert rows[0]["machine_cell_status"] == "blocked"
    assert rows[0]["human_governance_result"] == ""


def test_missing_codex_suggestion_is_rejected():
    gold_rows = [_gold("r1", "Loddon", "leave_parental_leave_primary_carer")]
    rows = worksheet_rows(gold_rows, _qa("Loddon", "leave_parental_leave_primary_carer"), [])

    assert any(error["code"] == "suggestions_missing_gold_rows" for error in validate_worksheet(rows, gold_rows, []))
    assert any(error["code"] == "codex_suggestion_not_marked_advisory" for error in validate_worksheet(rows, gold_rows, []))


def test_prefilled_human_field_is_rejected():
    gold_rows = [_gold("r1", "Loddon", "leave_parental_leave_primary_carer")]
    rows = worksheet_rows(gold_rows, _qa("Loddon", "leave_parental_leave_primary_carer"), [_suggestion("r1")])
    rows[0]["human_review_decision"] = "correct"

    assert any(error["code"] == "human_review_field_prefilled" for error in validate_worksheet(rows, gold_rows, [_suggestion("r1")]))
