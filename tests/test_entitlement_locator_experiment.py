from scripts import build_standard_entitlement_profile_evidence as standard
from scripts.build_entitlement_locator_experiment import (
    LOCATOR_SPECS,
    LocatorSpec,
    locate_in_agreement,
    process_rule_flags_for_candidate,
    review_status_for_candidate,
    serialisable_rule_contract,
    taxonomy_value_noise_reasons,
)


def _spec(entitlement_id: str):
    for item in LOCATOR_SPECS:
        if item.entitlement_id == entitlement_id:
            return item
    raise AssertionError(f"missing locator spec: {entitlement_id}")


def test_locator_records_clause_found_when_value_extractor_misses():
    spec = _spec(standard.EMERGENCY_SERVICES_PROFILE["entitlement_id"])
    row = locate_in_agreement(spec, "Monash", "ae531166")

    assert row["clause_found"] is True
    assert row["value_extracted"] is False
    assert row["state"] == "clause_found_value_missing"
    assert "emergency_services_context" in row["best_candidate"]["matched_terms"]


def test_locator_preserves_value_extracted_state():
    spec = _spec(standard.FAMILY_DOMESTIC_VIOLENCE_PROFILE["entitlement_id"])
    row = locate_in_agreement(spec, "Alpine", "ae524168")

    assert row["clause_found"] is True
    assert row["value_extracted"] is True
    assert row["state"] == "clause_found_value_extracted"
    assert "20 days" in row["value_signals"]


def test_locator_emits_span_level_clause_cards():
    spec = _spec(standard.FAMILY_DOMESTIC_VIOLENCE_PROFILE["entitlement_id"])
    row = locate_in_agreement(spec, "Colac Otway", "ae518862")
    card = row["clause_cards"][0]

    assert card["clause_id"].startswith("clause-")
    assert card["agreement_id"] == "ae518862"
    assert card["council_id"] == "Colac Otway"
    assert card["clause_family"] == standard.FAMILY_DOMESTIC_VIOLENCE_PROFILE["entitlement_id"]
    assert card["benefit_label"] == standard.FAMILY_DOMESTIC_VIOLENCE_PROFILE["label"]
    assert card["matched_span_start"] < card["matched_span_end"]
    assert card["matched_span_text"]
    assert card["raw_clause_text"]
    assert card["source_container_type"]
    assert "feature_value_extracted" in card["process_rule_flags"]
    assert card["interpretation_status"] == "candidate_features_found"
    assert len(card["raw_clause_text_hash"]) == 64
    assert card["parser_used"] == "cached_page_text"
    assert card["page_number_physical"] == card["page_ref"]["page"]
    assert card["feature_cards"]
    feature = card["feature_cards"][0]
    assert feature["feature_id"].startswith("feature-")
    assert feature["clause_id"] == card["clause_id"]
    assert feature["measure_id"] == standard.FAMILY_DOMESTIC_VIOLENCE_PROFILE["entitlement_id"]
    assert feature["evidence_span_text"]
    assert feature["source_container_type"] == card["source_container_type"]
    assert feature["process_rule_flags"] == card["process_rule_flags"]
    assert len(feature["evidence_span_text_hash"]) == 64
    assert feature["answer_builder_status"] in {
        "ready_for_deterministic_promotion_gate",
        "llm_answer_builder_required",
    }
    assert feature["answer_builder"]["schema_version"] == "wiki.feature_answer_builder_contract.v1"
    assert feature["answer_builder"]["candidate_answer"]["source_feature_id"] == feature["feature_id"]
    assert feature["answer_builder"]["candidate_answer"]["source_clause_id"] == card["clause_id"]
    assert "Is this feature actually answering the target entitlement?" in feature["answer_builder"]["semantic_questions"]
    assert feature["answer_builder"]["deterministic_gate_policy"]["feature_card_is_not_final_answer"] is True
    assert row["feature_cards"]
    assert card["page_ref"]["agreement_id"] == "ae518862"
    assert card["extraction_method"] == "alias_window_span_locator_v1"
    assert card["governance_status"] == "ungoverned_experiment"
    assert card["review_status"] == "auto_extracted_benchmark_value"


def test_locator_emits_reference_links_for_external_dependencies():
    spec = _spec(standard.FAMILY_DOMESTIC_VIOLENCE_PROFILE["entitlement_id"])
    row = locate_in_agreement(spec, "Ballarat", "ae526078")

    assert any(
        link.get("to_external", "").lower() in {"nes", "national employment standards"}
        for link in row["reference_links"]
    )


def test_locator_extracts_unquantified_paid_emergency_services_support():
    spec = _spec(standard.EMERGENCY_SERVICES_PROFILE["entitlement_id"])
    row = locate_in_agreement(spec, "Alpine", "ae524168")

    assert row["clause_found"] is True
    assert row["value_extracted"] is True
    assert row["state"] == "clause_found_value_extracted"
    assert any(
        value["subclass_id"] == "leave-emergency-services.paid-unquantified"
        for value in row["normalised_values"]
    )


def test_locator_extracts_parental_table_quantums():
    primary = _spec(standard.PARENTAL_PRIMARY_PROFILE["entitlement_id"])
    non_primary = _spec(standard.PARENTAL_NON_PRIMARY_PROFILE["entitlement_id"])

    primary_row = locate_in_agreement(primary, "Colac Otway", "ae518862")
    non_primary_row = locate_in_agreement(non_primary, "Colac Otway", "ae518862")

    assert primary_row["state"] == "clause_found_value_extracted"
    assert "16 weeks" in primary_row["value_signals"]
    assert non_primary_row["state"] == "clause_found_value_extracted"
    assert "4 weeks" in non_primary_row["value_signals"]


def test_locator_extracts_parental_alias_quantums():
    primary = _spec(standard.PARENTAL_PRIMARY_PROFILE["entitlement_id"])
    non_primary = _spec(standard.PARENTAL_NON_PRIMARY_PROFILE["entitlement_id"])

    primary_row = locate_in_agreement(primary, "Whitehorse", "ae529964")
    non_primary_row = locate_in_agreement(non_primary, "Whitehorse", "ae529964")

    assert primary_row["state"] == "clause_found_value_extracted"
    assert "18 weeks" in primary_row["value_signals"]
    assert non_primary_row["state"] == "clause_found_value_extracted"
    assert "5 weeks" in non_primary_row["value_signals"]


def test_locator_rule_contract_serialises_definition_boundary():
    spec = _spec(standard.FAMILY_DOMESTIC_VIOLENCE_PROFILE["entitlement_id"])
    contract = serialisable_rule_contract(spec)

    assert contract["definition"]
    assert contract["classification_boundary"]["included"]
    assert contract["classification_boundary"]["excluded"]
    assert contract["accepted_subclasses"]
    assert "What is this entitlement really asking us to identify?" in contract["ai_improvement_questions"]


def test_locator_rule_contract_gives_taxonomy_profiles_review_rules():
    spec = _spec("leave-pet-leave")
    contract = serialisable_rule_contract(spec)

    assert contract["definition"]
    assert contract["classification_boundary"]["included"]
    assert contract["classification_boundary"]["excluded"]
    assert contract["classification_boundary"]["needs_review"]
    assert contract["rule_origin"] in {"generic_taxonomy_fallback", "learned_loop_override"}


def test_locator_rule_contract_carries_loop_override_when_available():
    spec = _spec("conditions-call-out-minimum-engagement")
    contract = serialisable_rule_contract(spec)

    assert contract["rule_origin"] == "learned_loop_override"
    assert contract["definition"].startswith("For standard employees")
    assert contract["learned_loop_rules"]["promotion_gate"]
    assert contract["learned_loop_rules"]["value_rules"]
    assert "research_status" in contract["learned_loop_rules"]["research_findings"]


def test_locator_rule_contract_carries_exemplar_answer_contract():
    spec = _spec("conditions-work-from-home-protections")
    contract = serialisable_rule_contract(spec)

    assert contract["output_contract"]["answer_kind"] == "boolean"
    assert contract["output_contract"]["quantification_type"] == "binary_presence_or_absence"
    assert "presence/absence state" in contract["output_contract"]["supportable_output_requires"]


def test_gold_exemplar_scope_uses_report_comparator_councils():
    from scripts.build_entitlement_locator_experiment import target_agreement_pool

    councils = [row["council"] for row in target_agreement_pool("gold_exemplar_v2")]

    assert councils == [
        "Ararat",
        "Ballarat",
        "Central Goldfields",
        "Golden Plains",
        "Greater Bendigo",
        "Hepburn",
        "Moorabool",
        "Mount Alexander",
        "Pyrenees",
        "Wyndham",
    ]


def test_feature_card_llm_rules_gate_context_light_quantum_values():
    spec = LocatorSpec(
        key="test",
        entitlement_id="leave-test",
        label="Test Leave",
        family="taxonomy",
        profile={
            "learned_loop_rules": {
                "feature_card_llm_review": {
                    "alignment_status": "mixed",
                    "required_context_fields": ["timeframe", "cohort", "unit_basis", "condition"],
                    "decision_counts": {"wrong_entitlement_or_noise": 3, "promote_candidate": 1},
                }
            }
        },
    )

    flags = process_rule_flags_for_candidate(
        spec=spec,
        state="clause_found_value_extracted",
        values=[{"value": "5", "unit": "days", "condition": ""}],
        blockers=[],
        page_role="agreement_text",
        source_text="MCH nurses may access 5 days subject to the NES.",
        excerpt="MCH nurses may access 5 days subject to the NES.",
    )

    assert "feature_llm_timeframe_or_basis_review" in flags
    assert "feature_llm_scope_or_cohort_review" in flags
    assert "feature_llm_reference_context_review" in flags
    assert "feature_llm_definition_noise_gate" in flags
    assert review_status_for_candidate("clause_found_value_extracted", [{"value": "5"}], [], flags) == "needs_feature_card_llm_review"


def test_feature_card_llm_definition_noise_gate_allows_clear_local_entitlement_language():
    spec = LocatorSpec(
        key="test",
        entitlement_id="leave-test",
        label="Test Leave",
        family="taxonomy",
        profile={
            "learned_loop_rules": {
                "feature_card_llm_review": {
                    "alignment_status": "mixed",
                    "required_context_fields": ["timeframe", "cohort", "unit_basis", "condition"],
                    "decision_counts": {"wrong_entitlement_or_noise": 5, "promote_candidate": 0},
                }
            }
        },
    )

    flags = process_rule_flags_for_candidate(
        spec=spec,
        state="clause_found_value_extracted",
        values=[{"value": "10", "unit": "days", "condition": "over two years"}],
        blockers=[],
        page_role="agreement_text",
        source_text="Workplace delegates are entitled to 10 days paid leave over two years to attend union training courses.",
        excerpt="Workplace delegates are entitled to 10 days paid leave over two years to attend union training courses.",
    )

    assert "feature_llm_definition_noise_gate" not in flags


def test_taxonomy_value_noise_rules_filter_admin_timeframes_not_union_leave():
    spec = _spec("leave-union-training-leave")

    assert "administrative_timeframe_not_leave_quantum" in taxonomy_value_noise_reasons(
        spec,
        "The delegate must provide 5 weeks notice and evidence within 7 days after completion.",
        value="5",
        unit="weeks",
    )
    assert not taxonomy_value_noise_reasons(
        spec,
        "Union delegates are entitled to 10 days paid union training leave over two years.",
        value="10",
        unit="days",
    )


def test_taxonomy_value_noise_rules_filter_shutdown_and_purchased_leave_noise():
    shutdown_spec = _spec("leave-paid-shutdown-days-christmas-to-new-year")
    purchased_spec = _spec("leave-purchased-leave-scheme")

    assert "not_shutdown_day_quantum" in taxonomy_value_noise_reasons(
        shutdown_spec,
        "Personal leave accrues at 121 hours near the annual leave section.",
        value="121",
        unit="hours",
    )
    assert not taxonomy_value_noise_reasons(
        shutdown_spec,
        "Employees receive 3 days paid leave during the Christmas closedown.",
        value="3",
        unit="days",
    )
    assert "salary_calculation_not_scheme_duration" in taxonomy_value_noise_reasons(
        purchased_spec,
        "Purchased leave salary calculation is shown as 80 percent of ordinary pay.",
        value="80",
        unit="percent",
    )
