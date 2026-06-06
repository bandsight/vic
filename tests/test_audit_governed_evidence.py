from benchmarking_data_factory.workbench.audit_governed_evidence import audit_governed_events


def test_scenario_override_timeline_event_summarises_bulk_computed_notes():
    notes = (
        "Used computed for 1:A (2023-07-01) - 1158.8481. "
        "Used computed for 1:B (2023-07-01) - 1169.0739. "
        "Used computed for 1:A (2024-07-01) - 1190.7164.\n"
        "---\n"
        "RATE CAP ADJUSTMENTS NEEDED USED COMPUTED VALUES"
    )

    events = audit_governed_events(
        "ae518094",
        {
            "scenario_saved_at": "2026-04-29T08:53:05+00:00",
            "scenario_notes": notes,
        },
        get_canonical=lambda ae_id: {"sections": {"uplifts": {"data": {"periods": []}}}},
    )

    event = next(item for item in events if item["label"] == "Scenario overrides saved")
    assert event["detail"] == (
        "3 computed-rate selections across 2 periods (2023-07-01, 2024-07-01). "
        "Reviewer note: RATE CAP ADJUSTMENTS NEEDED USED COMPUTED VALUES"
    )
    assert event["detail_full"] == notes
    assert len(event["detail"]) < 180
