from scripts.build_entitlement_locator_gold_seed import (
    gold_records_from_qa_pack,
    validate_gold_record,
    validate_gold_records,
)


def _detail(council: str, entitlement_key: str, *, value_status: str = "quantified") -> dict:
    return {
        "council": council,
        "agreement_id": f"ae-{council}",
        "entitlement_key": entitlement_key,
        "entitlement_id": entitlement_key.replace("_", "-"),
        "entitlement_label": entitlement_key.replace("_", " ").title(),
        "cell_status": "clause_value" if value_status == "quantified" else "clause_only",
        "clause_found": True,
        "value_found": value_status == "quantified",
        "provision_present": True,
        "quantified_value_found": value_status == "quantified",
        "machine_presence_status": "present_candidate",
        "machine_value_status": value_status,
        "failure_reason": "" if value_status == "quantified" else "clause_found_but_no_normalised_value",
        "clause_card_id": f"clause-{council}-{entitlement_key}",
        "feature_card_ids": [f"feature-{council}-{entitlement_key}"] if value_status == "quantified" else [],
        "evidence_span": {
            "text": "20 days paid leave",
            "text_hash": "a" * 64,
        },
        "raw_clause_text_hash": "b" * 64,
        "parser_used": "cached_page_text",
        "parser_version": "workbench_pages_json_v1",
        "page": 10,
        "block_id": "block-1",
        "reference_links": [],
    }


def _qa_pack() -> dict:
    return {
        "artifact_id": "locator-qa-review-fixture",
        "source_artifact": {"artifact_id": "locator-fixture"},
        "recommended_review_sample": [{"council": "Loddon", "reason": "clean_high_value_extraction"}],
        "profiles": [
            {
                "key": "leave_parental_leave_primary_carer",
                "label": "Parental Leave Primary Carer",
                "details": [_detail("Loddon", "leave_parental_leave_primary_carer")],
            },
            {
                "key": "leave_emergency_services_leave",
                "label": "Emergency Services Leave",
                "details": [_detail("Loddon", "leave_emergency_services_leave", value_status="needs_value_review")],
            },
        ],
    }


def test_gold_seed_records_are_not_reviewed_truth_by_default():
    records = gold_records_from_qa_pack(_qa_pack(), generated_at="2026-05-09T00:00:00+00:00")

    assert len(records) == 2
    assert {record["review_status"] for record in records} == {"not_reviewed"}
    assert {record["review_decision"] for record in records} == {None}
    assert {record["reviewed_by"] for record in records} == {None}
    assert {record["review_scope"] for record in records} == {None}
    assert {record["expected_presence"] for record in records} == {"not_reviewed"}
    assert {record["expected_value_status"] for record in records} == {"not_reviewed"}
    assert {record["expected_provision_present"] for record in records} == {None}
    assert {record["expected_quantified_value_found"] for record in records} == {None}
    assert all(record["eligible_for_governance"] is False for record in records)
    assert all(record["promote_to_governed"] is False for record in records)
    assert validate_gold_records(records) == []


def test_amount_not_stated_presence_is_not_a_quantified_value_success():
    record = gold_records_from_qa_pack(_qa_pack(), generated_at="2026-05-09T00:00:00+00:00")[1]
    record.update({
        "review_status": "amount_not_stated_confirmed",
        "review_decision": "amount_not_stated_but_presence_correct",
        "reviewed_by": "analyst",
        "reviewed_at": "2026-05-09T00:00:00+00:00",
        "review_scope": "standard_staff_emergency_services_presence",
        "expected_presence": "present",
        "expected_provision_present": True,
        "expected_quantified_value_found": False,
        "expected_value_status": "amount_not_stated",
        "cross_reference_review": "not_required",
        "cross_reference_status": "not_required",
        "expected_value": None,
        "expected_unit": None,
    })

    assert record["machine_provision_present"] is True
    assert record["machine_quantified_value_found"] is False
    assert validate_gold_record(record) == []


def test_cross_reference_missing_enters_follow_up_queue():
    record = gold_records_from_qa_pack(_qa_pack(), generated_at="2026-05-09T00:00:00+00:00")[0]
    record.update({
        "review_status": "cross_reference_required",
        "review_decision": "cross_reference_missing",
        "reviewed_by": "analyst",
        "reviewed_at": "2026-05-09T00:00:00+00:00",
        "review_scope": "standard_staff_parental_leave_reference_edges",
        "expected_presence": "present",
        "expected_provision_present": True,
        "expected_quantified_value_found": False,
        "expected_value_status": "cross_reference_required",
        "cross_reference_review": "missing",
        "cross_reference_status": "missing",
        "follow_up_required": True,
    })

    assert validate_gold_record(record) == []

    record["follow_up_required"] = False
    assert any(error["code"] == "cross_reference_missing_requires_follow_up" for error in validate_gold_record(record))


def test_quantified_gold_value_requires_value_unit_and_feature_card():
    record = gold_records_from_qa_pack(_qa_pack(), generated_at="2026-05-09T00:00:00+00:00")[0]
    record.update({
        "review_status": "reviewed_correct",
        "review_decision": "correct",
        "reviewed_by": "analyst",
        "reviewed_at": "2026-05-09T00:00:00+00:00",
        "review_scope": "standard_staff_parental_primary",
        "expected_presence": "present",
        "expected_provision_present": True,
        "expected_quantified_value_found": True,
        "expected_value_status": "quantified",
        "expected_value": None,
        "expected_unit": None,
    })

    errors = validate_gold_record(record)

    assert any(error["code"] == "quantified_value_requires_value_and_unit" for error in errors)


def test_additional_annual_conservative_candidate_cannot_be_promoted():
    record = gold_records_from_qa_pack(_qa_pack(), generated_at="2026-05-09T00:00:00+00:00")[0]
    record.update({
        "entitlement_key": "additional_annual_leave",
        "machine_cell_status": "blocked",
        "review_status": "not_reviewed",
        "review_decision": None,
        "expected_presence": "not_reviewed",
        "expected_value_status": "not_reviewed",
        "eligible_for_governance": False,
        "promote_to_governed": True,
    })

    errors = validate_gold_record(record)

    assert any(error["code"] == "not_reviewed_cannot_promote" for error in errors)
    assert any(error["code"] == "additional_annual_conservative_candidate_cannot_promote" for error in errors)


def test_reviewed_correct_can_only_become_eligible_with_evidence_span():
    record = gold_records_from_qa_pack(_qa_pack(), generated_at="2026-05-09T00:00:00+00:00")[0]
    record.update({
        "review_status": "eligible_for_governance",
        "review_decision": "correct",
        "reviewed_by": "analyst",
        "reviewed_at": "2026-05-09T00:00:00+00:00",
        "review_scope": "standard_staff_parental_primary",
        "expected_presence": "present",
        "expected_provision_present": True,
        "expected_quantified_value_found": True,
        "expected_value_status": "quantified",
        "expected_value": "20",
        "expected_unit": "weeks",
        "eligible_for_governance": True,
    })

    assert validate_gold_record(record) == []

    record["evidence_span_text"] = ""
    assert any(error["code"] == "eligible_for_governance_requires_evidence_span" for error in validate_gold_record(record))


def test_reviewed_corrected_requires_corrected_evidence_fields():
    record = gold_records_from_qa_pack(_qa_pack(), generated_at="2026-05-09T00:00:00+00:00")[0]
    record.update({
        "review_status": "reviewed_corrected",
        "review_decision": "right_span_wrong_value",
        "reviewed_by": "analyst",
        "reviewed_at": "2026-05-09T00:00:00+00:00",
        "review_scope": "standard_staff_parental_primary",
        "expected_presence": "present",
        "expected_provision_present": True,
        "expected_quantified_value_found": True,
        "expected_value_status": "quantified",
        "expected_value": "18",
        "expected_unit": "weeks",
    })

    assert any(error["code"] == "reviewed_corrected_requires_corrected_evidence" for error in validate_gold_record(record))

    record["corrected_evidence_span"] = "Corrected source sentence."
    assert validate_gold_record(record) == []


def test_reviewed_rejected_cannot_count_toward_governance_success():
    record = gold_records_from_qa_pack(_qa_pack(), generated_at="2026-05-09T00:00:00+00:00")[0]
    record.update({
        "review_status": "reviewed_rejected",
        "review_decision": "wrong_clause",
        "reviewed_by": "analyst",
        "reviewed_at": "2026-05-09T00:00:00+00:00",
        "review_scope": "standard_staff_parental_primary",
        "eligible_for_governance": True,
        "promote_to_governed": True,
    })

    errors = validate_gold_record(record)

    assert any(error["code"] == "reviewed_rejected_cannot_promote" for error in errors)
    assert any(error["code"] == "eligible_for_governance_requires_lifecycle_status" for error in errors)


def test_reviewed_absent_requires_scope_or_notes_and_false_presence():
    record = gold_records_from_qa_pack(_qa_pack(), generated_at="2026-05-09T00:00:00+00:00")[0]
    record.update({
        "review_status": "reviewed_absent",
        "review_decision": "true_absence",
        "reviewed_by": "analyst",
        "reviewed_at": "2026-05-09T00:00:00+00:00",
        "review_scope": None,
        "review_notes": None,
        "expected_presence": "absent_reviewed",
        "expected_provision_present": False,
        "expected_quantified_value_found": False,
        "expected_value_status": "not_applicable",
    })

    assert any(error["code"] == "reviewed_status_requires_scope" for error in validate_gold_record(record))

    record["review_scope"] = "standard_staff_additional_annual_leave"
    assert validate_gold_record(record) == []
