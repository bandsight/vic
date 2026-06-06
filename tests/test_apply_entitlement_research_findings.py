from scripts.apply_entitlement_research_findings import build_payload


def test_research_findings_enrich_rule_overrides():
    overrides_payload = {
        "schema_version": "wiki.entitlement_loop_rule_overrides.v1",
        "summary": {"overrides": 1},
        "overrides": [
            {
                "entitlement_id": "leave-family-and-domestic-violence-leave",
                "classification_boundary": {"needs_review": ["Existing review rule."]},
                "value_rules": ["Existing value rule."],
            }
        ],
    }
    research_payload = {
        "artifact_id": "research-test",
        "generated_at": "2026-05-10T04:00:00+00:00",
        "rows": [
            {
                "entitlement_id": "leave-family-and-domestic-violence-leave",
                "research_status": "official_minimum_floor_attached",
                "definition_candidate": "Definition candidate.",
                "official_sources": [{"title": "Family and domestic violence leave - Fair Work Ombudsman"}],
                "cross_council_value_model": {"interpretation": "Compare agreement value against external floor."},
                "feedback_actions": {
                    "append_value_rules": ["Compare agreement value against external floor."],
                    "append_review_if": ["Feature-card value conflicts with official floor."],
                },
            }
        ],
    }

    payload = build_payload(overrides_payload, research_payload, generated_at="2026-05-10T05:00:00+00:00")

    override = payload["overrides"][0]
    assert payload["schema_version"] == "wiki.entitlement_loop_rule_overrides.v2"
    assert payload["summary"]["research_applied"] == 1
    assert payload["summary"]["with_official_sources"] == 1
    assert "Compare agreement value against external floor." in override["value_rules"]
    assert "Feature-card value conflicts with official floor." in override["classification_boundary"]["needs_review"]
    assert override["research_findings"]["research_status"] == "official_minimum_floor_attached"
