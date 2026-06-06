import pytest

from benchmarking_data_factory.workbench import human_qa_workflow
from benchmarking_data_factory.workbench import review_sections as review_sections_module


def test_human_qa_off_transition_resets_downstream_sections():
    timestamp = "2026-05-02T00:00:00+00:00"
    canonical = {
        "agreement_id": "ae1",
        "sections": review_sections_module.default_sections(),
    }
    for name in review_sections_module.REVIEW_SECTIONS:
        section = canonical["sections"][name]
        section["status"] = "done"
        section["completed_at"] = "2026-05-01T00:00:00+00:00"
        section["source_ref"] = f"{name}-source"
        section["notes"] = f"{name}-notes"
        section["human_qa"] = {"enabled": True}
    canonical["sections"]["pay_tables"]["tables"] = [{"title": "Accepted rates"}]
    canonical["sections"]["scenarios"]["data"] = {"runs": [{"id": "scenario-1"}]}
    canonical["sections"]["uplifts"]["data"] = {"governed": True}

    result = human_qa_workflow.apply_human_qa_transition(
        canonical,
        "pay_tables",
        enabled=False,
        timestamp=timestamp,
        summary="Pay Tables Human QA switched off.",
        notes="Reviewer found the pay table is not accepted.",
        apply_section_status=review_sections_module.apply_section_status,
    )

    assert result.downstream_cleared == ["scenarios", "end_of_band_dollars", "uplifts", "clauses"]
    assert result.clear_scenario_overrides is True
    assert canonical["sections"]["pay_tables"]["status"] == "in_progress"
    assert canonical["sections"]["pay_tables"]["human_qa"]["downstream_cleared"] == [
        "scenarios",
        "end_of_band_dollars",
        "uplifts",
        "clauses",
    ]
    assert canonical["sections"]["uplift_rules"]["human_qa"]["enabled"] is True
    for name in ("scenarios", "end_of_band_dollars", "uplifts", "clauses"):
        section = canonical["sections"][name]
        assert section["status"] == "not_started"
        assert section["source_ref"] == ""
        assert section["human_qa"]["invalidated_by"] == "pay_tables"
        assert section["human_qa"]["invalidated_at"] == timestamp


def test_human_qa_on_transition_requires_upstream_acceptance():
    canonical = {
        "agreement_id": "ae1",
        "sections": review_sections_module.default_sections(),
    }

    with pytest.raises(human_qa_workflow.HumanQaTransitionBlocked) as excinfo:
        human_qa_workflow.apply_human_qa_transition(
            canonical,
            "pay_tables",
            enabled=True,
            timestamp="2026-05-02T00:00:00+00:00",
            apply_section_status=review_sections_module.apply_section_status,
        )

    assert excinfo.value.section == "pay_tables"
    assert excinfo.value.blocker == "overview"


def test_human_qa_on_transition_reopens_downstream_invalidated_by_section():
    timestamp = "2026-05-02T00:00:00+00:00"
    canonical = {
        "agreement_id": "ae1",
        "sections": review_sections_module.default_sections(),
    }
    for name in ("overview", "uplift_rules"):
        section = canonical["sections"][name]
        section["status"] = "done"
        section["completed_at"] = "2026-05-01T00:00:00+00:00"
        section["human_qa"] = {"enabled": True}
    pay_tables = canonical["sections"]["pay_tables"]
    pay_tables["status"] = "in_progress"
    pay_tables["tables"] = [{"title": "Reviewed rates"}]
    scenarios = canonical["sections"]["scenarios"]
    scenarios["human_qa"] = {
        "enabled": False,
        "invalidated_by": "pay_tables",
        "invalidated_at": "2026-05-01T00:00:00+00:00",
    }

    result = human_qa_workflow.apply_human_qa_transition(
        canonical,
        "pay_tables",
        enabled=True,
        timestamp=timestamp,
        summary="Pay tables accepted.",
        notes="Accept pay tables.",
        apply_section_status=review_sections_module.apply_section_status,
    )

    assert result.downstream_cleared == []
    assert result.clear_scenario_overrides is False
    assert pay_tables["status"] == "done"
    assert pay_tables["completed_at"] == timestamp
    assert pay_tables["human_qa"]["enabled"] is True
    assert scenarios["human_qa"]["enabled"] is False
    assert "invalidated_by" not in scenarios["human_qa"]
    assert "invalidated_at" not in scenarios["human_qa"]
