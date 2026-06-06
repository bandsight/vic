from benchmarking_data_factory.conditions.schema import (
    BIG_TICKET_CONDITION_CATEGORIES,
    CONDITION_CATEGORY_DEFINITIONS,
    ClauseReference,
    ConditionItem,
    ConditionValue,
    ConditionsDocument,
    empty_conditions_data,
    validate_conditions_payload,
)


def test_prompt_excludes_wage_rules_and_requires_clause_text():
    from benchmarking_data_factory.conditions.prompt import build_conditions_extraction_prompt

    prompt = build_conditions_extraction_prompt("ae527533", "Buloke Shire Council")

    assert "Do not extract wage uplift/pay-table rules" in prompt
    assert "Target scope: standard_general_employees" in prompt
    assert "Exclude specialised cohort-only clauses" in prompt
    assert "clauses[]" in prompt
    assert "Preserve the exact associated clause text" in prompt


def test_empty_conditions_data_includes_big_ticket_and_storage_slots():
    data = empty_conditions_data()

    assert data["schema_version"] == "conditions_v1"
    assert data["target_scope"] == "standard_general_employees"
    assert data["multi_employer"] is False
    assert data["covered_councils"] == []
    assert "maternal_and_child_health_nurses" in data["excluded_specialised_cohorts"]
    assert data["big_ticket_categories"] == list(BIG_TICKET_CONDITION_CATEGORIES)
    assert "paid_parental_family_leave" in data["category_definitions"]
    assert data["category_definitions"]["paid_parental_family_leave"]["required_comparison_keys"]
    assert data["items"] == []
    assert "overtime_penalties_rosters" in data["categories"]
    assert "redundancy_redeployment" in data["categories"]


def test_each_category_definition_has_incoming_data_contract():
    for category, definition in CONDITION_CATEGORY_DEFINITIONS.items():
        assert definition.category == category
        assert definition.definition
        assert definition.include_when
        assert definition.exclude_when
        assert definition.required_comparison_keys
        assert definition.allowed_value_types


def test_condition_item_stores_clause_text_and_quantified_values():
    clause = ClauseReference(
        clause_id="56.2",
        heading="Redundancy Payments",
        page_start=25,
        page_end=26,
        text="Severance pay is two weeks for each completed year to a maximum of 48 weeks.",
    )
    value = ConditionValue(
        value_id="56.2.max_severance",
        label="Maximum severance",
        value_type="weeks",
        raw_value="48 weeks",
        numeric_value=48,
        unit="weeks",
        role="cap",
        source_clause_ids=("56.2",),
        confidence=0.95,
    )
    item = ConditionItem(
        item_id="redundancy.severance",
        category="redundancy_redeployment",
        title="Redundancy severance",
        summary="Two weeks per completed year, capped at 48 weeks.",
        clauses=(clause,),
        values=(value,),
        materiality="big_ticket",
        extraction_status="extracted",
    )
    document = ConditionsDocument(ae_id="ae527533", council="Buloke Shire Council", items=(item,))

    assert document.items[0].clauses[0].text.startswith("Severance pay")
    assert document.items[0].values[0].numeric_value == 48
    assert document.items[0].values[0].source_clause_ids == ("56.2",)


def test_validate_conditions_payload_accepts_clause_backed_comparable_item():
    payload = empty_conditions_data()
    payload["items"] = [
        {
            "category": "paid_parental_family_leave",
            "title": "Paid parental leave",
            "clauses": [{"clause_id": "18.3", "text": "Primary carer leave is 20 weeks."}],
            "council_applicability": {"mode": "single_council", "applies_to_councils": [], "excluded_councils": []},
            "comparison_keys": ["primary_carer_paid_weeks"],
            "values": [
                {
                    "value_id": "primary_carer_paid_weeks",
                    "value_type": "weeks",
                    "raw_value": "20 weeks",
                    "source_clause_ids": ["18.3"],
                    "council_applicability": {"mode": "single_council", "applies_to_councils": [], "excluded_councils": []},
                }
            ],
        }
    ]

    assert validate_conditions_payload(payload) == []


def test_validate_conditions_payload_rejects_missing_clause_and_wrong_value_type():
    payload = empty_conditions_data()
    payload["items"] = [
        {
            "category": "redundancy_redeployment",
            "comparison_keys": [],
            "clauses": [],
            "values": [
                {
                    "value_id": "max_severance_weeks",
                    "value_type": "percentage",
                    "raw_value": "48 weeks",
                    "source_clause_ids": [],
                }
            ],
        }
    ]

    errors = validate_conditions_payload(payload)

    assert any("at least one source clause is required" in error for error in errors)
    assert any("value_type 'percentage' is not allowed" in error for error in errors)
    assert any("source_clause_ids is required" in error for error in errors)


def test_validate_conditions_payload_requires_named_applicability_for_split_agreements():
    payload = empty_conditions_data()
    payload["multi_employer"] = True
    payload["covered_councils"] = ["Ararat Rural City Council", "Central Goldfields Shire Council"]
    payload["items"] = [
        {
            "category": "redundancy_redeployment",
            "title": "Redundancy severance",
            "clauses": [{"clause_id": "98.2", "text": "This redundancy clause applies to Ararat only."}],
            "council_applicability": {
                "mode": "named_councils_only",
                "applies_to_councils": ["Ararat Rural City Council"],
                "excluded_councils": [],
            },
            "comparison_keys": ["max_severance_weeks"],
            "values": [
                {
                    "value_id": "max_severance_weeks",
                    "value_type": "weeks",
                    "raw_value": "48 weeks",
                    "source_clause_ids": ["98.2"],
                    "council_applicability": {
                        "mode": "named_councils_only",
                        "applies_to_councils": ["Ararat Rural City Council"],
                        "excluded_councils": [],
                    },
                }
            ],
        }
    ]

    assert validate_conditions_payload(payload) == []


def test_validate_conditions_payload_rejects_unknown_split_applicability():
    payload = empty_conditions_data()
    payload["multi_employer"] = True
    payload["covered_councils"] = ["Ararat Rural City Council", "Central Goldfields Shire Council"]
    payload["items"] = [
        {
            "category": "redundancy_redeployment",
            "clauses": [{"clause_id": "98.2", "text": "Redundancy applies."}],
            "council_applicability": {"mode": "unknown", "applies_to_councils": [], "excluded_councils": []},
            "comparison_keys": ["max_severance_weeks"],
            "values": [
                {
                    "value_id": "max_severance_weeks",
                    "value_type": "weeks",
                    "raw_value": "48 weeks",
                    "source_clause_ids": ["98.2"],
                    "council_applicability": {
                        "mode": "named_councils_only",
                        "applies_to_councils": ["Wrong Council"],
                        "excluded_councils": [],
                    },
                }
            ],
        }
    ]

    errors = validate_conditions_payload(payload)

    assert any("split agreement applicability cannot be unknown" in error for error in errors)
    assert any("applies_to_councils not in covered_councils" in error for error in errors)
