from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import main

    canonical_dir = tmp_path / "canonical"
    overrides_dir = tmp_path / "scenario-overrides"
    canonical_dir.mkdir()
    overrides_dir.mkdir()
    monkeypatch.setattr(main, "CANONICAL_DIR", canonical_dir)
    monkeypatch.setattr(main, "SCENARIO_OVERRIDES_DIR", overrides_dir)
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Test Council"})
    monkeypatch.setattr(main, "fetch_metadata_for_ae_id", lambda *args, **kwargs: {})
    monkeypatch.setattr(main, "resolve_canonical_lga_short_name", lambda *args, **kwargs: None)
    if hasattr(main, "_canonical_cache"):
        main._canonical_cache.clear()

    (canonical_dir / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Test Council\n"
        "sections:\n"
        "  pay_tables:\n"
        "    status: in_progress\n"
        "    source_ref: old source\n"
        "    notes: old note\n"
        "    tables:\n"
        "      - table_title: Existing weekly rates\n"
        "        rate_kind: weekly\n"
        "        effective_from: '2026-07-01'\n"
        "        rows:\n"
        "          - band: 1\n"
        "            level: A\n"
        "            weekly_rate: 1000\n"
        "  uplift_rules:\n"
        "    status: in_progress\n"
        "    data: {}\n",
        encoding="utf-8",
    )
    return TestClient(main.app)


def test_scenario_override_audit_records_cells_groups_notes_and_clear(client):
    first = client.post(
        "/api/councils/aetest01/uplift-rules/scenarios/overrides",
        json={
            "overrides": {
                "2026-07-01": {
                    "1:A": {"action": "use_computed", "weekly": 1030},
                },
            },
            "change_context": {"scope": "cell", "action": "use_computed", "period": "2026-07-01"},
        },
    )
    assert first.status_code == 200, first.text
    first_events = first.json()["audit_events"]
    assert any(event["event_type"] == "scenario_cell_override_added" for event in first_events)

    grouped = client.post(
        "/api/councils/aetest01/uplift-rules/scenarios/overrides",
        json={
            "overrides": {
                "2026-07-01": {
                    "1:A": {"action": "use_computed", "weekly": 1040},
                    "1:B": {"action": "use_computed", "weekly": 1050},
                },
            },
            "change_context": {
                "scope": "group",
                "action": "use_computed_all",
                "period": "2026-07-01",
                "affected_cells": 2,
            },
        },
    )
    assert grouped.status_code == 200, grouped.text
    grouped_events = grouped.json()["audit_events"]
    group_event = next(event for event in grouped_events if event["event_type"] == "scenario_group_override_applied")
    assert group_event["scope"] == "group"
    assert group_event["affected_count"] == 2
    assert any(event["event_type"] == "scenario_cell_override_changed" for event in grouped_events)

    noted = client.post(
        "/api/councils/aetest01/uplift-rules/scenarios/note",
        json={
            "notes": "Reviewed computed rates for Year 2.",
            "change_context": {"scope": "note", "action": "save_note"},
        },
    )
    assert noted.status_code == 200, noted.text
    assert any(event["event_type"] == "scenario_note_updated" for event in noted.json()["audit_events"])

    cleared = client.delete("/api/councils/aetest01/uplift-rules/scenarios/overrides")
    assert cleared.status_code == 200, cleared.text
    cleared_body = cleared.json()
    assert cleared_body["cleared"] is True
    assert cleared_body["overrides"] == {}
    clear_types = {event["event_type"] for event in cleared_body["audit_events"]}
    assert "scenario_overrides_cleared" in clear_types
    assert "scenario_cell_override_removed" in clear_types

    reloaded = client.get("/api/councils/aetest01/uplift-rules/scenarios/overrides")
    assert reloaded.status_code == 200, reloaded.text
    assert reloaded.json()["overrides"] == {}
    assert reloaded.json()["audit_events"]


def test_scenario_runner_uses_saved_overrides_by_default(client, monkeypatch):
    from benchmarking_data_factory.workbench import scenario_governance as scenario_governance_module

    saved = client.post(
        "/api/councils/aetest01/uplift-rules/scenarios/overrides",
        json={
            "overrides": {
                "2026-07-01": {
                    "1:A": {"action": "use_computed", "weekly": 1030},
                },
            },
            "change_context": {"scope": "cell", "action": "use_computed", "period": "2026-07-01"},
        },
    )
    assert saved.status_code == 200, saved.text

    captured: dict[str, object] = {}

    def fake_run_scenarios(canonical, overrides=None, lga_short_name=None):
        del canonical, lga_short_name
        captured["overrides"] = overrides
        return ()

    monkeypatch.setattr(scenario_governance_module, "run_scenarios", fake_run_scenarios)

    response = client.post("/api/councils/aetest01/uplift-rules/scenarios", json={})

    assert response.status_code == 200, response.text
    assert captured["overrides"] == {
        "2026-07-01": {
            "1:A": {"action": "use_computed", "weekly": 1030.0},
        },
    }


def test_pay_table_save_audit_records_date_number_note_and_source_changes(client):
    payload = {
        "action": "replace",
        "status": "in_progress",
        "timeline_policy": "current",
        "source_ref": "new source",
        "notes": "Updated after QA review.",
        "tables": [
            {
                "table_title": "Existing weekly rates",
                "rate_kind": "weekly",
                "effective_from": "2026-07-02",
                "rows": [
                    {"band": 1, "level": "A", "weekly_rate": 1010},
                ],
            }
        ],
    }

    response = client.post("/api/councils/aetest01/pay-tables/save", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    event_types = {event["event_type"] for event in body["qa_events"]}

    assert "pay_table_date_changed" in event_types
    assert "pay_table_cell_value_changed" in event_types
    assert "pay_table_note_updated" in event_types
    assert "pay_table_source_ref_updated" in event_types

    import main

    saved = main.get_canonical("aetest01")
    qa_events = saved["sections"]["pay_tables"]["qa_events"]
    assert {event["event_type"] for event in qa_events} >= {
        "pay_table_date_changed",
        "pay_table_cell_value_changed",
        "pay_table_note_updated",
    }


def test_audit_report_includes_qa_governance_changes(client, monkeypatch):
    import main

    monkeypatch.setattr(main, "load_candidate_agreement_rows", lambda: [])
    monkeypatch.setattr(main, "load_multi_council_decisions", lambda: {})
    monkeypatch.setattr(main, "load_source_register_by_ae_id", lambda: {})
    monkeypatch.setattr(main, "list_pdfs", lambda: ["aetest01"])
    monkeypatch.setattr(main, "_audit_workspace_ae_ids", lambda target_keys, lineage_ids: ["aetest01"])
    monkeypatch.setattr(main, "_audit_workspace_matches_council", lambda row, target_keys: True)
    monkeypatch.setattr(
        main,
        "build_council_summary",
        lambda ae_id, registry=None, decisions=None: {
            "ae_id": ae_id,
            "source_name": "Test Council Agreement",
            "canonical_lga_short_name": "Test",
            "fetch_metadata": {},
            "geography": {"short_name": "Test"},
            "done_count": 2,
            "total_sections": 6,
            "pay_table_summary": [],
        },
    )

    pay_response = client.post(
        "/api/councils/aetest01/pay-tables/save",
        json={
            "action": "replace",
            "status": "in_progress",
            "timeline_policy": "current",
            "source_ref": "QA source",
            "notes": "QA note",
            "tables": [
                {
                    "table_title": "Existing weekly rates",
                    "rate_kind": "weekly",
                    "effective_from": "2026-07-02",
                    "rows": [
                        {"band": 1, "level": "A", "weekly_rate": 1010},
                        {"title": "Maternal and Child Health Nurse Year 1", "weekly_rate": 2000},
                    ],
                }
            ],
        },
    )
    assert pay_response.status_code == 200, pay_response.text

    scenario_response = client.post(
        "/api/councils/aetest01/uplift-rules/scenarios/overrides",
        json={
            "overrides": {
                "2026-07-01": {
                    "1:A": {"action": "use_computed", "weekly": 1030},
                },
            },
            "change_context": {"scope": "cell", "action": "use_computed", "period": "2026-07-01"},
        },
    )
    assert scenario_response.status_code == 200, scenario_response.text

    report_response = client.get("/api/audit/councils/Test")
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()

    assert report["summary"]["qa_governance_events"] >= 2
    assert report["summary"]["qa_brief_items"] >= 3
    qa_event_types = {change["event_type"] for change in report["qa_changes"]}
    assert "pay_table_cell_value_changed" in qa_event_types
    assert "scenario_cell_override_added" in qa_event_types
    qa_brief_categories = {item["category"] for item in report["qa_brief"]}
    assert {"pay_tables", "scenarios", "row_level_treatment"} <= qa_brief_categories
    scenario_brief = next(item for item in report["qa_brief"] if item["category"] == "scenarios")
    assert "cell decision" in scenario_brief["body"]
    assert scenario_brief["impact"]
    assert any(event["kind"] == "qa" and event["source"] == "Pay-table review" for event in report["events"])
    assert any(event["kind"] == "qa" and event["source"] == "Scenario review" for event in report["events"])
    assert report["summary"]["has_non_standard_row_level_treatment"] is True
    assert report["summary"]["non_standard_row_level_count"] == 1
    assert report["row_level_treatment"]["status"] == "present"
    assert report["row_level_treatment"]["examples"][0]["title"] == "Maternal and Child Health Nurse Year 1"
    quality = report["quality_standard"]
    assert 0 <= quality["score"] <= 1000
    assert quality["max_score"] == 1000
    assert quality["agreement_count"] == 1
    assert quality["agreements"][0]["ae_id"] == "aetest01"
    assert {measure["key"] for measure in quality["agreements"][0]["measures"]} >= {
        "confidence_numbers",
        "source_structure",
        "table_rule_agreement",
        "qa_change_burden",
        "date_alignment",
        "governed_pipeline",
    }
    assert report["summary"]["quality_standard_score"] == quality["score"]
