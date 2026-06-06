from benchmarking_data_factory.workbench.review_sections import (
    REVIEW_SECTIONS,
    apply_section_status,
    default_sections,
    derive_governed_set_status,
    done_count,
    merge_section_defaults,
    section_statuses,
)


def test_default_sections_are_independent():
    first = default_sections()
    second = default_sections()

    first["pay_tables"]["tables"].append({"effective_from": "2026-07-01"})

    assert second["pay_tables"]["tables"] == []


def test_merge_section_defaults_preserves_known_data_and_fills_missing_sections():
    sections = merge_section_defaults(
        {
            "pay_tables": {
                "status": "done",
                "tables": [{"table_title": "Schedule A"}],
            }
        }
    )

    assert sections["pay_tables"]["status"] == "done"
    assert sections["pay_tables"]["tables"] == [{"table_title": "Schedule A"}]
    assert sections["overview"]["status"] == "not_started"
    assert set(REVIEW_SECTIONS).issubset(sections)


def test_merge_section_defaults_merges_clause_data_with_conditions_contract():
    sections = merge_section_defaults(
        {
            "clauses": {
                "data": {
                    "items": [{"item_id": "item-1", "category": "allowances_reimbursements"}],
                    "covered_councils": ["East Gippsland"],
                }
            }
        }
    )

    data = sections["clauses"]["data"]

    assert data["schema_version"] == "conditions_v1"
    assert data["target_scope"] == "standard_general_employees"
    assert data["covered_councils"] == ["East Gippsland"]
    assert data["items"] == [{"item_id": "item-1", "category": "allowances_reimbursements"}]
    assert "allowances_reimbursements" in data["category_definitions"]


def test_section_statuses_and_done_count_are_review_scope_only():
    sections = default_sections()
    apply_section_status(sections["overview"], "done", "2026-04-27T00:00:00Z")
    apply_section_status(sections["front_matter"], "done", "2026-04-27T00:00:00Z")

    statuses = section_statuses(sections)

    assert "front_matter" not in statuses
    assert statuses["overview"] == "done"
    assert done_count(statuses) == 1


def test_derive_governed_set_status_tracks_promoted_periods():
    canonical = {
        "sections": {
            "uplifts": {
                "status": "not_started",
                "data": {"periods": [{"pay_table": {"rows": []}, "uplift_rule": None}]},
            }
        }
    }

    derive_governed_set_status(canonical)

    assert canonical["sections"]["uplifts"]["status"] == "in_progress"


def test_derive_governed_set_status_requires_dependency_chain():
    sections = default_sections()
    for section in ("overview", "uplift_rules", "pay_tables"):
        apply_section_status(sections[section], "done", "2026-04-27T00:00:00Z")
    sections["scenarios"]["status"] = "in_progress"
    sections["uplifts"] = {
        "status": "done",
        "completed_at": "2026-04-27T00:00:00Z",
        "data": {
            "periods": [
                {"effective_from": "2026-07-01", "pay_table": {"rows": []}, "uplift_rule": {"source_rule_id": "r1"}}
            ]
        },
    }

    derive_governed_set_status({"sections": sections})

    assert sections["uplifts"]["status"] == "in_progress"
    assert sections["uplifts"]["completed_at"] is None


def test_derive_governed_set_status_ready_periods_wait_for_human_acceptance():
    sections = default_sections()
    for section in ("overview", "uplift_rules", "pay_tables", "scenarios", "end_of_band_dollars"):
        apply_section_status(sections[section], "done", "2026-04-27T00:00:00Z")
    sections["scenarios"]["data"] = {
        "future_triggers": [
            {"period_effective_from": "2027-07-01", "trigger_date": "2027-07-01"}
        ]
    }
    sections["uplifts"] = {
        "status": "in_progress",
        "completed_at": None,
        "data": {
            "periods": [
                {"effective_from": "2026-07-01", "pay_table": {"rows": []}, "uplift_rule": {"source_rule_id": "r1"}},
                {"effective_from": "2027-07-01", "pay_table": None, "uplift_rule": {"source_rule_id": "r2"}},
            ]
        },
    }

    derive_governed_set_status({"sections": sections})

    assert sections["uplifts"]["status"] == "in_progress"
    assert sections["uplifts"]["completed_at"] is None


def test_derive_governed_set_status_preserves_human_acceptance_when_ready():
    sections = default_sections()
    for section in ("overview", "uplift_rules", "pay_tables", "scenarios", "end_of_band_dollars"):
        apply_section_status(sections[section], "done", "2026-04-27T00:00:00Z")
    sections["scenarios"]["data"] = {
        "future_triggers": [
            {"period_effective_from": "2027-07-01", "trigger_date": "2027-07-01"}
        ]
    }
    sections["uplifts"] = {
        "status": "done",
        "completed_at": "2026-04-27T00:30:00Z",
        "data": {
            "periods": [
                {"effective_from": "2026-07-01", "pay_table": {"rows": []}, "uplift_rule": {"source_rule_id": "r1"}},
                {"effective_from": "2027-07-01", "pay_table": None, "uplift_rule": {"source_rule_id": "r2"}},
            ]
        },
    }

    derive_governed_set_status({"sections": sections})

    assert sections["uplifts"]["status"] == "done"
    assert sections["uplifts"]["completed_at"] == "2026-04-27T00:30:00Z"
