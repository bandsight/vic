from pathlib import Path

from scripts.build_entitlement_cards import build_payload


def _profile(row: dict, *, answer_kind: str = "quantitative") -> dict:
    return {
        "entitlement_id": "leave-test",
        "label": "Test Leave",
        "output_contract": {"answer_kind": answer_kind},
        "rule_contract": {
            "definition": "Paid test leave for standard employees.",
            "scope": "standard_employees",
            "taxonomy_path": ["Leave", "Test Leave"],
        },
        "target_rows": [row],
    }


def test_entitlement_card_emits_only_for_strong_source_backed_feature_row(tmp_path: Path):
    row = {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "agreement_name": "Test Agreement",
        "state": "clause_found_value_extracted",
        "normalised_values": [{"value": "4", "unit": "weeks", "condition": "per year"}],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "page_number_physical": 8,
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "raw_clause_text": "An employee is entitled to 4 weeks per year.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "clause_id": "clause-one",
                "page_number_physical": 8,
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "4",
                "unit": "weeks",
                "condition": "per year",
                "evidence_span_text": "An employee is entitled to 4 weeks per year.",
            }
        ],
    }
    locator_payload = {"artifact_id": "locator-test", "profiles": [_profile(row)]}

    payload = build_payload(locator_payload, generated_at="2026-05-12T00:00:00+00:00", source_path=tmp_path / "locator.json")

    assert payload["summary"]["entitlement_cards"] == 1
    card = payload["cards"][0]
    assert card["status"] == "proposed_governed"
    assert card["promotion"]["review_queue_policy"] == "if_review_needed_card_is_not_emitted"
    assert card["entitlement_definition"] == "Paid test leave for standard employees."
    assert card["council"] == "Ballarat"
    assert card["quantum"]["value_text"] == "4 weeks"
    assert card["quantum"]["fact_roles"] == ["entitlement_quantum"]
    assert card["quantum"]["fact_atoms"][0]["fact_role"] == "entitlement_quantum"
    assert card["simple_sentence"] == "4 weeks test leave per year."
    assert card["source_refs"]["clause_card_ids"] == ["clause-one"]
    assert card["source_refs"]["feature_card_ids"] == ["feature-one"]


def test_entitlement_card_attaches_report_learning_alignment(tmp_path: Path):
    row = {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [{"value": "4", "unit": "weeks", "condition": "per year"}],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "raw_clause_text": "An employee is entitled to 4 weeks per year.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "4",
                "unit": "weeks",
                "condition": "per year",
                "evidence_span_text": "An employee is entitled to 4 weeks per year.",
            }
        ],
    }
    report_learning = {
        "entitlements": [
            {
                "entitlement_key": "test-leave",
                "label": "Test Leave",
                "definition": "A paid leave entitlement used to test report learning.",
                "expected_answer_kind": "duration_or_time",
                "observed_value_kinds": {"duration_or_time": 10},
                "observed_conditions": ["for permanent employees"],
                "observed_timeframes": ["per_year"],
                "quantum_profile": {
                    "ranges": [
                        {"kind": "duration_or_time", "unit": "weeks", "basis": "", "min": 4, "median": 4, "max": 5}
                    ],
                    "conversion_hints": ["Preserve annual basis."],
                },
            }
        ]
    }

    payload = build_payload(
        {"artifact_id": "locator-test", "profiles": [_profile(row)]},
        generated_at="2026-05-12T00:00:00+00:00",
        source_path=tmp_path / "locator.json",
        report_learning_payload=report_learning,
    )

    card = payload["cards"][0]
    alignment = card["evidence_standard"]["report_learning_alignment"]
    assert alignment["status"] == "aligned"
    assert alignment["expected_answer_kind"] == "duration_or_time"
    assert alignment["report_definition"] == "A paid leave entitlement used to test report learning."
    assert alignment["observed_conditions"] == ["for permanent employees"]
    assert alignment["observed_value_kinds"] == {"duration_or_time": 10}
    assert alignment["conversion_hints"] == ["Preserve annual basis."]
    assert payload["summary"]["report_learning_matched_cards"] == 1


def test_report_learning_alignment_prefers_matching_timeframe(tmp_path: Path):
    row = {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [{"value": "20", "unit": "days per annum"}],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "raw_clause_text": "An employee is entitled to 20 days per annum.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "20",
                "unit": "days per annum",
                "evidence_span_text": "An employee is entitled to 20 days per annum.",
            }
        ],
    }
    report_learning = {
        "entitlements": [
            {
                "entitlement_key": "test-leave",
                "label": "Test Leave",
                "expected_answer_kind": "duration_or_time",
                "quantum_profile": {
                    "ranges": [
                        {"kind": "duration_or_time", "unit": "days", "basis": "", "min": 5, "median": 5, "max": 5},
                        {"kind": "duration_or_time", "unit": "days", "basis": "per year", "min": 10, "median": 20, "max": 20},
                    ],
                    "conversion_hints": [],
                },
            }
        ]
    }

    payload = build_payload(
        {"artifact_id": "locator-test", "profiles": [_profile(row)]},
        generated_at="2026-05-12T00:00:00+00:00",
        source_path=tmp_path / "locator.json",
        report_learning_payload=report_learning,
    )

    assert payload["cards"][0]["evidence_standard"]["report_learning_alignment"]["status"] == "aligned"


def test_report_learning_alignment_uses_upper_bounds_and_duration_conversion(tmp_path: Path):
    row = {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [{"value": "5", "unit": "paid days"}],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "raw_clause_text": "An employee may access five paid days of emergency leave.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "5",
                "unit": "paid days",
                "evidence_span_text": "An employee may access five paid days of emergency leave.",
            }
        ],
    }
    report_learning = {
        "entitlements": [
            {
                "entitlement_key": "test-leave",
                "label": "Test Leave",
                "expected_answer_kind": "duration_or_time",
                "quantum_profile": {
                    "ranges": [
                        {
                            "kind": "duration_or_time",
                            "unit": "weeks",
                            "basis": "",
                            "bound": "upper",
                            "min": 2,
                            "median": 2,
                            "max": 2,
                        }
                    ],
                    "conversion_hints": ["Time values may need working-day conversion."],
                },
            }
        ]
    }

    payload = build_payload(
        {"artifact_id": "locator-test", "profiles": [_profile(row)]},
        generated_at="2026-05-12T00:00:00+00:00",
        source_path=tmp_path / "locator.json",
        report_learning_payload=report_learning,
    )

    alignment = payload["cards"][0]["evidence_standard"]["report_learning_alignment"]
    assert alignment["status"] == "aligned"
    assert alignment["conversion_hints"] == ["Time values may need working-day conversion."]


def test_entitlement_card_blocks_rows_that_need_review(tmp_path: Path):
    row = {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [{"value": "5", "unit": "days"}],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "review_status": "needs_feature_card_llm_review",
                "process_rule_flags": ["feature_value_extracted", "feature_llm_timeframe_or_basis_review"],
                "raw_clause_text": "Employees may receive 5 days.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "review_status": "needs_feature_card_llm_review",
                "process_rule_flags": ["feature_value_extracted", "feature_llm_timeframe_or_basis_review"],
                "value": "5",
                "unit": "days",
            }
        ],
    }
    locator_payload = {"artifact_id": "locator-test", "profiles": [_profile(row)]}

    payload = build_payload(locator_payload, generated_at="2026-05-12T00:00:00+00:00", source_path=tmp_path / "locator.json")

    assert payload["summary"]["entitlement_cards"] == 0
    assert payload["summary"]["blocked_value_cells"] == 1
    assert payload["summary"]["gate_failure_counts"]["review_status_not_strong"] == 1
    assert payload["summary"]["gate_failure_counts"]["blocking_process_rule_flags"] == 1
    assert payload["blocked_samples"][0]["gate_failures"] == [
        "blocking_process_rule_flags",
        "review_status_not_strong",
    ]


def test_entitlement_card_ignores_availability_placeholder_when_quantum_has_strong_feature(tmp_path: Path):
    row = {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [
            {"value": "5", "unit": "days", "condition": "per year"},
            {"value": "available", "unit": "candidate provision", "condition": ""},
        ],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "raw_clause_text": "Employees may cash out 5 days. Cash out is available by agreement.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "5",
                "unit": "days",
            }
        ],
    }

    payload = build_payload({"artifact_id": "locator-test", "profiles": [_profile(row)]}, generated_at="2026-05-12T00:00:00+00:00", source_path=tmp_path / "locator.json")

    assert payload["summary"]["entitlement_cards"] == 1
    card = payload["cards"][0]
    assert card["quantum"]["value_text"] == "5 days"
    assert card["source_refs"]["feature_card_ids"] == ["feature-one"]


def test_entitlement_card_blocks_availability_only_quantitative_rows(tmp_path: Path):
    row = {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [{"value": "available", "unit": "candidate provision", "condition": ""}],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "review_status": "auto_extracted_non_benchmark_support",
                "process_rule_flags": ["feature_value_extracted"],
                "raw_clause_text": "Study leave is available by agreement.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "clause_id": "clause-one",
                "review_status": "auto_extracted_non_benchmark_support",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "available",
                "unit": "candidate provision",
            }
        ],
    }

    payload = build_payload({"artifact_id": "locator-test", "profiles": [_profile(row)]}, generated_at="2026-05-12T00:00:00+00:00", source_path=tmp_path / "locator.json")

    assert payload["summary"]["entitlement_cards"] == 0
    assert "availability_candidate_not_reportable_quantum" in payload["blocked_samples"][0]["gate_failures"]


def test_entitlement_card_uses_strong_duplicate_feature_and_ignores_weak_sibling(tmp_path: Path):
    row = {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [{"value": "5", "unit": "days", "condition": "per occasion"}],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "review_status": "needs_feature_card_llm_review",
                "process_rule_flags": ["feature_value_extracted", "feature_llm_scope_or_cohort_review"],
                "raw_clause_text": "Employees receive 5 days per occasion. A specialist note follows.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-weak",
                "clause_id": "clause-one",
                "review_status": "needs_feature_card_llm_review",
                "process_rule_flags": ["feature_value_extracted", "feature_llm_scope_or_cohort_review"],
                "value": "5",
                "unit": "days",
                "condition": "per occasion",
            },
            {
                "feature_id": "feature-strong",
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "5",
                "unit": "days",
                "condition": "per occasion",
            },
        ],
    }

    payload = build_payload({"artifact_id": "locator-test", "profiles": [_profile(row)]}, generated_at="2026-05-12T00:00:00+00:00", source_path=tmp_path / "locator.json")

    assert payload["summary"]["entitlement_cards"] == 1
    card = payload["cards"][0]
    assert card["source_refs"]["feature_card_ids"] == ["feature-strong"]
    assert card["evidence_standard"]["process_rule_flags"] == ["feature_value_extracted"]


def test_entitlement_card_sentence_names_measurement_for_multi_value_leave_rows(tmp_path: Path):
    row = {
        "council": "Maribyrnong",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [
            {"value": "1", "unit": "non-cumulative service recognition leave day(s) per annum", "condition": "3 years continuous service"},
            {"value": "4", "unit": "non-cumulative service recognition leave day(s) per annum", "condition": "15 years continuous service"},
        ],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "raw_clause_text": "Employees receive between 1 and 4 non-cumulative service recognition leave days per annum depending on service.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "1",
                "unit": "non-cumulative service recognition leave day(s) per annum",
                "condition": "3 years continuous service",
                "subclass_label": "Service / End-of-Band Recognition Leave",
            },
            {
                "feature_id": "feature-two",
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "4",
                "unit": "non-cumulative service recognition leave day(s) per annum",
                "condition": "15 years continuous service",
                "subclass_label": "Service / End-of-Band Recognition Leave",
            },
        ],
    }

    payload = build_payload({"artifact_id": "locator-test", "profiles": [_profile(row)]}, generated_at="2026-05-12T00:00:00+00:00", source_path=tmp_path / "locator.json")

    assert payload["summary"]["entitlement_cards"] == 1
    assert payload["cards"][0]["simple_sentence"] == "1 to 4 non-cumulative service recognition leave days per annum."


def test_entitlement_card_blocks_ambiguous_multi_value_rows_instead_of_inventing_range(tmp_path: Path):
    row = {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [
            {"value": "4", "unit": "weeks", "condition": "minimum retained annual leave balance"},
            {"value": "52", "unit": "weeks", "condition": "scheme application period"},
        ],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "raw_clause_text": "An employee may cash out annual leave if 4 weeks is retained. The scheme may run over 52 weeks.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "4",
                "unit": "weeks",
                "condition": "minimum retained annual leave balance",
                "evidence_span_text": "An employee may cash out annual leave if 4 weeks is retained.",
            },
            {
                "feature_id": "feature-two",
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "52",
                "unit": "weeks",
                "condition": "scheme application period",
                "evidence_span_text": "The scheme may run over 52 weeks.",
            },
        ],
    }

    payload = build_payload({"artifact_id": "locator-test", "profiles": [_profile(row)]}, generated_at="2026-05-12T00:00:00+00:00", source_path=tmp_path / "locator.json")

    assert payload["summary"]["entitlement_cards"] == 0
    assert "missing_reportable_fact_atom" in payload["blocked_samples"][0]["gate_failures"]
    assert {atom["fact_role"] for atom in payload["blocked_samples"][0]["fact_atoms"]} == {"rule_parameter"}


def test_entitlement_card_allows_genuine_yes_no_availability_for_descriptive_measures(tmp_path: Path):
    row = {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [{"value": "available", "unit": "candidate provision", "condition": ""}],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "review_status": "auto_extracted_non_benchmark_support",
                "process_rule_flags": ["feature_value_extracted"],
                "raw_clause_text": "Employees may access the employee assistance program.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "clause_id": "clause-one",
                "review_status": "auto_extracted_non_benchmark_support",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "available",
                "unit": "candidate provision",
            }
        ],
    }

    profile = _profile(row, answer_kind="descriptive")
    profile["label"] = "Employee Assistance Program"
    payload = build_payload({"artifact_id": "locator-test", "profiles": [profile]}, generated_at="2026-05-12T00:00:00+00:00", source_path=tmp_path / "locator.json")

    assert payload["summary"]["entitlement_cards"] == 1
    card = payload["cards"][0]
    assert card["quantum"]["fact_roles"] == ["availability"]
    assert card["simple_sentence"] == "Employee assistance program provision available."


def test_entitlement_card_allows_amount_not_stated_when_clause_creates_entitlement(tmp_path: Path):
    row = {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [{"value": "amount not stated", "unit": "", "condition": "paid time off"}],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "review_status": "auto_extracted_non_benchmark_support",
                "process_rule_flags": ["feature_value_extracted"],
                "raw_clause_text": "Employees affected by natural disaster may access paid time off, amount not stated.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "clause_id": "clause-one",
                "review_status": "auto_extracted_non_benchmark_support",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "amount not stated",
                "unit": "",
                "condition": "paid time off",
                "evidence_span_text": "Employees affected by natural disaster may access paid time off, amount not stated.",
            }
        ],
    }

    payload = build_payload({"artifact_id": "locator-test", "profiles": [_profile(row)]}, generated_at="2026-05-12T00:00:00+00:00", source_path=tmp_path / "locator.json")

    assert payload["summary"]["entitlement_cards"] == 1
    card = payload["cards"][0]
    assert card["quantum"]["fact_roles"] == ["amount_not_stated"]
    assert card["simple_sentence"] == "Amount unstated for test leave."


def test_entitlement_card_allows_distinct_values_for_different_operative_periods(tmp_path: Path):
    row = {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [
            {"value": "4", "unit": "weeks", "condition": "from 1 July 2024"},
            {"value": "5", "unit": "weeks", "condition": "from 1 July 2025"},
        ],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "raw_clause_text": "Employees receive 4 weeks from 1 July 2024 and 5 weeks from 1 July 2025.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "4",
                "unit": "weeks",
                "condition": "from 1 July 2024",
                "evidence_span_text": "Employees receive 4 weeks from 1 July 2024.",
            },
            {
                "feature_id": "feature-two",
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted"],
                "value": "5",
                "unit": "weeks",
                "condition": "from 1 July 2025",
                "evidence_span_text": "Employees receive 5 weeks from 1 July 2025.",
            },
        ],
    }

    payload = build_payload({"artifact_id": "locator-test", "profiles": [_profile(row)]}, generated_at="2026-05-12T00:00:00+00:00", source_path=tmp_path / "locator.json")

    assert payload["summary"]["entitlement_cards"] == 1
    card = payload["cards"][0]
    assert card["simple_sentence"] == "4 weeks test leave from 1 july 2024 and 5 weeks test leave from 1 july 2025."
    assert [atom["operative_period"] for atom in card["quantum"]["fact_atoms"]] == ["from 1 July 2024", "from 1 July 2025"]


def test_entitlement_card_blocks_reference_only_quantum_values(tmp_path: Path):
    row = {
        "council": "Ballarat",
        "agreement_id": "ae-test",
        "state": "clause_found_value_extracted",
        "normalised_values": [{"value": "NES paid compassionate leave cross-reference", "unit": "", "condition": ""}],
        "clause_cards": [
            {
                "clause_id": "clause-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted", "reference_heavy_context"],
                "raw_clause_text": "Compassionate leave is provided in accordance with the NES.",
            }
        ],
        "feature_cards": [
            {
                "feature_id": "feature-one",
                "review_status": "auto_extracted_benchmark_value",
                "process_rule_flags": ["feature_value_extracted", "reference_heavy_context"],
                "value": "NES paid compassionate leave cross-reference",
            }
        ],
    }

    payload = build_payload({"artifact_id": "locator-test", "profiles": [_profile(row)]}, generated_at="2026-05-12T00:00:00+00:00", source_path=tmp_path / "locator.json")

    assert payload["summary"]["entitlement_cards"] == 0
    assert "reference_only_value_not_reportable_quantum" in payload["blocked_samples"][0]["gate_failures"]
