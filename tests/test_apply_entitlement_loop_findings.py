from pathlib import Path

from scripts.apply_entitlement_loop_findings import build_payload


def test_loop_findings_become_locator_rule_overrides(tmp_path):
    loop_payload = {
        "artifact_id": "loop-test",
        "generated_at": "2026-05-10T00:00:00+00:00",
        "rows": [
            {
                "entitlement_id": "conditions-call-out-minimum-engagement",
                "label": "Call Out Minimum Engagement",
                "loop_status": "split_or_normalise_values",
                "promotion_gate": "needs_loop_review",
                "entitlement_question": "For standard employees, does the agreement provide Call Out Minimum Engagement, and what duration applies?",
                "answer_shape": {
                    "kind": "duration_or_time",
                    "top_observed_value": "3 hours",
                    "expectation": "Expect 3 hours as the normal answer unless source context shows a subclass or exception.",
                },
                "rule_change_candidates": {
                    "include": ["Call-out clauses with a minimum engagement value."],
                    "exclude": ["Overtime clauses without call-out recall."],
                    "review_if": ["Observed value is unusual."],
                    "value_rules": ["Use 3 hours as the provisional normal value."],
                },
                "validation_queue": [{"council": "Ballarat"}],
                "next_loop_steps": ["Cluster observed values by unit and subclass."],
            }
        ],
    }

    payload = build_payload(
        loop_payload,
        generated_at="2026-05-10T02:00:00+00:00",
        source_path=Path(tmp_path / "loop.json"),
    )

    override = payload["overrides"][0]
    assert payload["summary"]["overrides"] == 1
    assert override["rule_origin"] == "learned_loop_override"
    assert override["classification_boundary"]["canonical_definition"].startswith("For standard employees")
    assert "Call-out clauses with a minimum engagement value." in override["classification_boundary"]["included"]
    assert "Overtime clauses without call-out recall." in override["classification_boundary"]["excluded"]
    assert override["value_rules"] == ["Use 3 hours as the provisional normal value."]
    assert override["accepted_subclasses"][0]["relationship"] == "learned_loop_answer_shape"
