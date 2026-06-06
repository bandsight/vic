from __future__ import annotations

from fastapi.testclient import TestClient

from benchmarking_data_factory.workbench.review_learning import (
    build_review_learning_snapshot,
    evaluate_rule_promotions,
    extract_review_decision_events,
)


def _canonical_with_pay_events() -> dict:
    return {
        "agreement_id": "aetest01",
        "source_name": "Test Council Agreement",
        "canonical_lga_short_name": "Test",
        "sections": {
            "pay_tables": {
                "qa_events": [
                    {
                        "changed_at": "2026-05-01T00:00:00Z",
                        "changed_by": "local analyst",
                        "event_type": "pay_table_date_changed",
                        "table_label": "Weekly rates",
                        "field": "effective_from",
                        "previous": "2026-07-02",
                        "next": "2026-07-01",
                    },
                    {
                        "changed_at": "2026-05-01T00:01:00Z",
                        "changed_by": "local analyst",
                        "event_type": "pay_table_cell_value_changed",
                        "table_label": "Weekly rates",
                        "row_key": "1:A",
                        "field": "weekly_rate",
                        "previous": 1000,
                        "next": 1030,
                    },
                    {
                        "changed_at": "2026-05-01T00:02:00Z",
                        "changed_by": "local analyst",
                        "event_type": "pay_table_row_removed",
                        "table_label": "Weekly rates",
                        "row_key": "base",
                    },
                ],
            },
        },
    }


def test_review_learning_normalises_pay_and_scenario_decisions():
    scenario_state = {
        "audit_events": [
            {
                "changed_at": "2026-05-01T00:03:00Z",
                "changed_by": "local analyst",
                "event_type": "scenario_cell_override_added",
                "period_effective_from": "2026-07-01",
                "cell_key": "1:A",
                "band": "1",
                "level": "A",
                "change_context": {"action": "use_computed", "period": "2026-07-01"},
            },
            {
                "changed_at": "2026-05-01T00:04:00Z",
                "changed_by": "local analyst",
                "event_type": "scenario_group_override_applied",
                "period_effective_from": "2026-07-01",
                "affected_count": 12,
                "change_context": {"action": "use_computed_all", "period": "2026-07-01"},
            },
        ],
    }

    events = extract_review_decision_events("aetest01", _canonical_with_pay_events(), scenario_state=scenario_state)

    assert {event["pattern"] for event in events} >= {
        "pay_table_effective_date_adjusted",
        "pay_table_value_adjusted",
        "pay_table_row_removed",
        "scenario_cell_use_computed",
        "scenario_group_use_computed",
    }
    date_event = next(event for event in events if event["pattern"] == "pay_table_effective_date_adjusted")
    assert date_event["decision_type"] == "effective_date"
    assert date_event["period"] == "2026-07-01"
    assert "previous=2026-07-02" in date_event["evidence"]


def test_review_learning_snapshot_groups_patterns_and_policy_suggestions():
    snapshot = build_review_learning_snapshot(
        [
            ("aetest01", _canonical_with_pay_events()),
            ("aetest02", _canonical_with_pay_events()),
        ],
        scenario_states={
            "aetest01": {
                "audit_events": [
                    {
                        "event_type": "scenario_cell_override_added",
                        "period_effective_from": "2026-07-01",
                        "cell_key": "1:A",
                        "change_context": {"action": "use_computed"},
                    }
                ]
            }
        },
    )

    assert snapshot["schema_version"] == "review_learning.v1"
    assert snapshot["learning_mode"] == "invisible"
    assert snapshot["summary"]["decision_events"] == 7
    patterns = {item["pattern"]: item for item in snapshot["learned_patterns"]}
    assert patterns["pay_table_effective_date_adjusted"]["count"] == 2
    assert patterns["pay_table_effective_date_adjusted"]["confidence"] == "medium"
    rules = {item["rule"] for item in snapshot["policy_suggestions"]}
    assert "reinforce_effective_date_suggestion" in rules
    assert "reinforce_computed_value_decision" in rules
    assert "allow_pragmatic_row_drop_reason" in rules
    assert snapshot["rule_promotions"] == []
    assert all(item["promotion_gate"]["required_suite"] == "full" for item in snapshot["policy_suggestions"])


def test_review_learning_captures_uplift_rule_table_binding_conflict():
    canonical = {
        "agreement_id": "aetest03",
        "source_name": "Test Council Agreement",
        "canonical_lga_short_name": "Test",
        "sections": {
            "uplift_rules": {
                "data": {
                    "table_alignment_issues": [
                        {
                            "code": "uplift_rule_table_binding_conflict",
                            "period_effective_from": "2023-11-07",
                            "rule_quantum": "2.00% or $28.00 per week",
                            "affected_cells": 28,
                            "covered_cells": 30,
                            "mechanised_weekly_increase": 28.0,
                            "implied_weekly_increase": 32.63,
                            "table_names": ["Indoor benchmark"],
                        }
                    ]
                }
            }
        },
    }

    snapshot = build_review_learning_snapshot([("aetest03", canonical)])

    assert snapshot["summary"]["decision_events"] == 1
    event = snapshot["decision_events"][0]
    assert event["pattern"] == "uplift_rule_table_binding_conflict"
    assert event["decision_type"] == "uplift_extraction_binding"
    assert "implied_weekly_increase=32.63" in event["evidence"]
    rules = {item["rule"] for item in snapshot["policy_suggestions"]}
    assert "stop_at_uplift_rule_table_binding_conflict" in rules


def test_review_learning_promotes_rules_only_after_full_regression_pass():
    snapshot = build_review_learning_snapshot(
        [
            ("aetest01", _canonical_with_pay_events()),
            ("aetest02", _canonical_with_pay_events()),
        ],
        regression_result={"suite": "full", "passed": True, "test_count": 424},
    )

    assert snapshot["summary"]["rule_promotions"] >= 2
    promotions = {item["rule"]: item for item in snapshot["rule_promotions"]}
    assert promotions["reinforce_effective_date_suggestion"]["promotion_status"] == "addable_after_full_regression"
    assert promotions["reinforce_effective_date_suggestion"]["regression"]["test_count"] == 424

    assert evaluate_rule_promotions(
        snapshot["policy_suggestions"],
        regression_result={"suite": "focused", "passed": True, "test_count": 35},
    ) == []
    assert evaluate_rule_promotions(
        snapshot["policy_suggestions"],
        regression_result={"suite": "full", "passed": False, "test_count": 424},
    ) == []


def test_review_learning_endpoint_is_available_without_frontend(monkeypatch, tmp_path):
    import main

    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir()
    monkeypatch.setattr(main, "CANONICAL_DIR", canonical_dir)
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Test Council Agreement"})
    monkeypatch.setattr(main, "load_multi_council_decisions", lambda: {})
    monkeypatch.setattr(main, "list_pdfs", lambda: ["aetest01"])
    monkeypatch.setattr(main, "_read_scenario_override_state", lambda ae_id: {
        "audit_events": [
            {
                "event_type": "scenario_cell_override_added",
                "period_effective_from": "2026-07-01",
                "cell_key": "1:A",
                "change_context": {"action": "use_computed"},
            }
        ]
    })
    if hasattr(main, "_canonical_cache"):
        main._canonical_cache.clear()
    (canonical_dir / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Test Council Agreement\n"
        "sections:\n"
        "  pay_tables:\n"
        "    qa_events:\n"
        "      - event_type: pay_table_date_changed\n"
        "        table_label: Weekly rates\n"
        "        field: effective_from\n"
        "        previous: '2026-07-02'\n"
        "        next: '2026-07-01'\n",
        encoding="utf-8",
    )

    response = TestClient(main.app).get("/api/analysis/review-learning")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["learning_mode"] == "invisible"
    assert body["summary"]["decision_events"] == 2
    assert {item["pattern"] for item in body["learned_patterns"]} >= {
        "pay_table_effective_date_adjusted",
        "scenario_cell_use_computed",
    }
