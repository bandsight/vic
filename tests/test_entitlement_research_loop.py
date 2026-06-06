from scripts.build_entitlement_research_loop import build_payload


def test_research_loop_attaches_official_floor_and_value_model(tmp_path):
    locator_payload = {
        "artifact_id": "locator-test",
        "profiles": [
            {
                "entitlement_id": "leave-family-and-domestic-violence-leave",
                "target_rows": [
                    {
                        "value_extracted": True,
                        "feature_cards": [{"feature_id": "f1"}],
                        "normalised_values": [{"value": "20", "unit": "days per annum"}],
                    }
                ],
            }
        ],
    }
    loop_payload = {
        "artifact_id": "loop-test",
        "rows": [
            {
                "entitlement_id": "leave-family-and-domestic-violence-leave",
                "label": "Family and Domestic Violence Leave",
                "loop_status": "repair_value_extraction",
                "promotion_gate": "needs_loop_review",
                "entitlement_question": "For standard employees, does the agreement provide Family and Domestic Violence Leave, and what duration applies?",
                "answer_shape": {"top_observed_value": "20 days per annum"},
                "validation_queue": [{"council": "Ballarat", "value_labels": ["20 days per annum"]}],
                "rule_change_candidates": {"value_rules": ["Use 20 days as the provisional normal value."]},
            }
        ],
    }

    payload = build_payload(
        locator_payload,
        loop_payload,
        generated_at="2026-05-10T04:00:00+00:00",
        source_path=tmp_path / "loop.json",
    )

    row = payload["rows"][0]
    assert payload["summary"]["official_source_links"] == 1
    assert row["research_status"] == "official_minimum_floor_attached"
    assert row["official_sources"][0]["source_id"] == "fwo_fdv_leave"
    assert "10 days paid leave" in row["official_sources"][0]["baseline_value"]
    assert row["cross_council_value_model"]["top_observed_value"] == "20 days per annum"
    assert row["feedback_actions"]["append_value_rules"][0].startswith("Compare agreement value")


def test_research_loop_marks_enterprise_only_entitlements(tmp_path):
    locator_payload = {
        "artifact_id": "locator-test",
        "profiles": [
            {
                "entitlement_id": "wellbeing-and-support-wellbeing-days",
                "target_rows": [
                    {
                        "value_extracted": True,
                        "feature_cards": [{"feature_id": "f1"}],
                        "normalised_values": [{"value": "1", "unit": "day"}],
                    }
                ],
            }
        ],
    }
    loop_payload = {
        "artifact_id": "loop-test",
        "rows": [
            {
                "entitlement_id": "wellbeing-and-support-wellbeing-days",
                "label": "Wellbeing Days",
                "loop_status": "split_or_normalise_values",
                "promotion_gate": "needs_loop_review",
                "entitlement_question": "For standard employees, does the agreement provide Wellbeing Days?",
                "answer_shape": {"top_observed_value": "1 day"},
            }
        ],
    }

    payload = build_payload(
        locator_payload,
        loop_payload,
        generated_at="2026-05-10T04:00:00+00:00",
        source_path=tmp_path / "loop.json",
    )

    row = payload["rows"][0]
    assert row["research_status"] == "enterprise_agreement_pattern_only"
    assert row["official_sources"] == []
    assert any("No external official anchor" in risk for risk in row["research_risks"])


def test_research_loop_blocks_superannuation_leave_duration_as_normal_value(tmp_path):
    locator_payload = {
        "artifact_id": "locator-test",
        "profiles": [
            {
                "entitlement_id": "superannuation-superannuation-on-paid-parental-leave",
                "target_rows": [
                    {
                        "value_extracted": True,
                        "feature_cards": [{"feature_id": "f1"}],
                        "normalised_values": [{"value": "34", "unit": "weeks"}],
                    }
                ],
            }
        ],
    }
    loop_payload = {
        "artifact_id": "loop-test",
        "rows": [
            {
                "entitlement_id": "superannuation-superannuation-on-paid-parental-leave",
                "label": "Superannuation on Paid Parental Leave",
                "loop_status": "split_or_normalise_values",
                "promotion_gate": "needs_loop_review",
                "entitlement_question": "For standard employees, does the agreement provide Superannuation on Paid Parental Leave?",
                "answer_shape": {"top_observed_value": "34 weeks"},
                "rule_change_candidates": {"value_rules": ["Use 34 weeks as the provisional normal value."]},
            }
        ],
    }

    payload = build_payload(
        locator_payload,
        loop_payload,
        generated_at="2026-05-10T04:00:00+00:00",
        source_path=tmp_path / "loop.json",
    )

    row = payload["rows"][0]
    model = row["cross_council_value_model"]
    assert model["value_conflict_with_official_anchor"] is True
    assert "12% superannuation contribution" in model["official_expected_value"]
    assert not any("Use 34 weeks" in rule for rule in row["feedback_actions"]["append_value_rules"])
    assert any("Official expected value" in rule for rule in row["feedback_actions"]["append_value_rules"])
