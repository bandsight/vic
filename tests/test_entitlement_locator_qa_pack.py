from pathlib import Path

from scripts.build_entitlement_locator_qa_pack import build_qa_payload, guardrail_errors


def _row(
    council: str,
    *,
    state: str,
    clause_found: bool,
    value_extracted: bool,
    blockers: list[str] | None = None,
    feature: dict | None = None,
) -> dict:
    card = {
        "clause_id": f"clause-{council}",
        "agreement_id": f"ae-{council}",
        "council_id": council,
        "page_number_physical": 12,
        "block_id": f"block-{council}",
        "parser_used": "cached_page_text",
        "parser_version": "workbench_pages_json_v1",
        "raw_clause_text_hash": "a" * 64,
        "locator_span_text": "Family violence leave",
        "locator_span_text_hash": "b" * 64,
        "interpretation_status": "candidate_features_found" if value_extracted else "source_container_only",
        "review_status": "auto_extracted_benchmark_value" if value_extracted else "needs_quantification_review",
        "governance_status": "ungoverned_experiment",
        "reference_links": [],
    }
    features = [feature] if feature else []
    return {
        "council": council,
        "agreement_id": f"ae-{council}",
        "agreement_name": f"{council} Agreement",
        "state": state,
        "clause_found": clause_found,
        "value_extracted": value_extracted,
        "candidate_count": 1,
        "locator_confidence": 88,
        "clause_cards": [card],
        "feature_cards": features,
        "reference_links": [],
        "candidate_pages": [
            {
                "state": state,
                "page": 12,
                "heading": "Leave",
                "blocker_signals": blockers or [],
                "matched_terms": ["leave"],
                "excerpt": "candidate excerpt",
            }
        ],
    }


def _feature(governance_status: str = "ungoverned_experiment") -> dict:
    return {
        "feature_id": "feature-1",
        "clause_id": "clause-clean",
        "normalised_value": {"value": "20", "unit": "days"},
        "evidence_span_text": "20 days paid leave",
        "evidence_span_text_hash": "c" * 64,
        "evidence_span_start": 10,
        "evidence_span_end": 28,
        "span_basis": "normalised_value_window",
        "governance_status": governance_status,
        "review_status": "auto_extracted_benchmark_value",
    }


def _locator_payload(rows_by_profile: list[tuple[str, str, list[dict]]]) -> dict:
    return {
        "schema_version": "wiki.entitlement_locator_experiment.v2",
        "artifact_id": "fixture",
        "generated_at": "2026-05-09T00:00:00+00:00",
        "profiles": [
            {
                "key": key,
                "entitlement_id": key.replace("_", "-"),
                "label": label,
                "target_rows": rows,
            }
            for key, label, rows in rows_by_profile
        ],
    }


def test_qa_pack_keeps_clause_found_and_value_found_separate():
    payload = _locator_payload([
        (
            "family_domestic_violence_leave",
            "Family and Domestic Violence Leave",
            [
                _row(
                    "Clean",
                    state="clause_found_value_extracted",
                    clause_found=True,
                    value_extracted=True,
                    feature=_feature(),
                ),
                _row(
                    "NeedsValue",
                    state="clause_found_value_missing",
                    clause_found=True,
                    value_extracted=False,
                ),
            ],
        )
    ])

    qa = build_qa_payload(payload, generated_at="2026-05-09T00:00:00+00:00", source_path=Path("fixture.json"))
    summary = qa["profiles"][0]["summary"]

    assert summary["clause_found"] == 2
    assert summary["value_found"] == 1
    assert qa["profiles"][0]["details"][0]["provision_present"] is True
    assert qa["profiles"][0]["details"][0]["quantified_value_found"] is True
    assert qa["profiles"][0]["details"][1]["provision_present"] is True
    assert qa["profiles"][0]["details"][1]["quantified_value_found"] is False
    assert qa["summary_matrix"][0]["statuses"]["family_domestic_violence_leave"]["status"] == "clause_value"
    assert qa["summary_matrix"][1]["statuses"]["family_domestic_violence_leave"]["status"] == "clause_only"


def test_additional_annual_adjacent_candidate_is_not_a_true_clause():
    payload = _locator_payload([
        (
            "additional_annual_leave",
            "Additional Annual Leave",
            [
                _row(
                    "Blocked",
                    state="adjacent_or_blocked_clause_found",
                    clause_found=False,
                    value_extracted=False,
                    blockers=["purchased_leave"],
                )
            ],
        )
    ])

    qa = build_qa_payload(payload, generated_at="2026-05-09T00:00:00+00:00", source_path=Path("fixture.json"))

    assert qa["profiles"][0]["summary"]["clause_found"] == 0
    assert qa["summary_matrix"][0]["statuses"]["additional_annual_leave"]["status"] == "blocked"
    assert guardrail_errors(qa) == []


def test_additional_annual_true_clause_can_enter_review():
    payload = _locator_payload([
        (
            "additional_annual_leave",
            "Additional Annual Leave",
            [
                _row(
                    "Clean",
                    state="clause_found_value_extracted",
                    clause_found=True,
                    value_extracted=True,
                    feature=_feature(),
                )
            ],
        )
    ])

    qa = build_qa_payload(payload, generated_at="2026-05-09T00:00:00+00:00", source_path=Path("fixture.json"))

    assert qa["profiles"][0]["summary"]["clause_found"] == 1
    assert qa["summary_matrix"][0]["statuses"]["additional_annual_leave"]["status"] == "clause_value"
    assert guardrail_errors(qa) == []


def test_value_found_requires_feature_card_and_evidence_span():
    payload = _locator_payload([
        (
            "family_domestic_violence_leave",
            "Family and Domestic Violence Leave",
            [
                _row(
                    "Invalid",
                    state="clause_found_value_extracted",
                    clause_found=True,
                    value_extracted=True,
                    feature=None,
                )
            ],
        )
    ])

    qa = build_qa_payload(payload, generated_at="2026-05-09T00:00:00+00:00", source_path=Path("fixture.json"))

    assert any(error["code"] == "value_found_without_feature_card" for error in qa["guardrail_errors"])
    assert qa["guardrail_status"] == "failed"


def test_governed_for_scope_requires_review_metadata():
    payload = _locator_payload([
        (
            "family_domestic_violence_leave",
            "Family and Domestic Violence Leave",
            [
                _row(
                    "InvalidGovernance",
                    state="clause_found_value_extracted",
                    clause_found=True,
                    value_extracted=True,
                    feature=_feature(governance_status="governed_for_scope"),
                )
            ],
        )
    ])

    qa = build_qa_payload(payload, generated_at="2026-05-09T00:00:00+00:00", source_path=Path("fixture.json"))

    assert any(error["code"] == "governed_without_review_metadata" for error in qa["guardrail_errors"])


def test_review_sample_returns_five_distinct_councils_when_available():
    payload = _locator_payload([
        (
            "additional_annual_leave",
            "Additional Annual Leave",
            [
                _row("A", state="no_candidate_clause_found", clause_found=False, value_extracted=False),
                _row("B", state="no_candidate_clause_found", clause_found=False, value_extracted=False),
                _row("C", state="no_candidate_clause_found", clause_found=False, value_extracted=False),
                _row("D", state="no_candidate_clause_found", clause_found=False, value_extracted=False),
                _row("E", state="no_candidate_clause_found", clause_found=False, value_extracted=False),
            ],
        )
    ])

    qa = build_qa_payload(payload, generated_at="2026-05-09T00:00:00+00:00", source_path=Path("fixture.json"))
    councils = [item["council"] for item in qa["recommended_review_sample"]]

    assert len(councils) == 5
    assert len(set(councils)) == 5
