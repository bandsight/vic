from __future__ import annotations

from copy import deepcopy
from typing import Any

from benchmarking_data_factory.conditions.schema import empty_conditions_data

SECTIONS = [
    "overview",
    "pay_tables",
    "uplift_rules",
    "scenarios",
    "end_of_band_dollars",
    "uplifts",
    "front_matter",
    "clauses",
]
WORKFLOW_SECTIONS = ["overview", "uplift_rules", "pay_tables", "scenarios", "end_of_band_dollars", "uplifts"]
OPTIONAL_REVIEW_SECTIONS = ["clauses"]
REVIEW_SECTIONS = [*WORKFLOW_SECTIONS, *OPTIONAL_REVIEW_SECTIONS]
SECTION_LABELS = {
    "overview": "Overview",
    "pay_tables": "Pay Tables",
    "uplift_rules": "Uplift Rules",
    "scenarios": "Scenarios",
    "end_of_band_dollars": "End of Band Dollars",
    "uplifts": "Governed Set",
    "front_matter": "Front Matter",
    "clauses": "Entitlements",
}
VALID_SECTION_STATUSES = {"not_started", "in_progress", "done", "flagged"}


_DEFAULT_SECTIONS: dict[str, dict[str, Any]] = {
    "overview": {
        "status": "not_started",
        "completed_at": None,
        "source_ref": "",
        "data": None,
        "notes": "",
    },
    "pay_tables": {
        "status": "not_started",
        "completed_at": None,
        "source_ref": "",
        "tables": [],
        "validations": [],
        "notes": "",
    },
    "uplift_rules": {
        "status": "not_started",
        "completed_at": None,
        "source_ref": "",
        "data": None,
        "notes": "",
    },
    "scenarios": {
        "status": "not_started",
        "completed_at": None,
        "source_ref": "",
        "data": None,
        "notes": "",
    },
    "end_of_band_dollars": {
        "status": "not_started",
        "completed_at": None,
        "source_ref": "",
        "data": None,
        "notes": "",
    },
    "uplifts": {
        "status": "not_started",
        "completed_at": None,
        "source_ref": "",
        "data": None,
        "notes": "",
    },
    "front_matter": {
        "status": "not_started",
        "completed_at": None,
        "source_ref": "",
        "data": None,
        "notes": "",
    },
    "clauses": {
        "status": "not_started",
        "completed_at": None,
        "source_ref": "",
        "data": empty_conditions_data(),
        "notes": "",
    },
}


def default_sections() -> dict[str, dict[str, Any]]:
    return deepcopy(_DEFAULT_SECTIONS)


def merge_section_defaults(incoming_sections: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    sections = default_sections()
    incoming_sections = incoming_sections or {}
    for section in SECTIONS:
        incoming = incoming_sections.get(section)
        if isinstance(incoming, dict):
            sections[section].update(incoming)
            if section == "clauses":
                incoming_data = sections[section].get("data")
                if isinstance(incoming_data, dict):
                    merged_data = empty_conditions_data()
                    merged_data.update(incoming_data)
                    sections[section]["data"] = merged_data
                else:
                    sections[section]["data"] = empty_conditions_data()
    return sections


def section_statuses(sections: dict[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for section in REVIEW_SECTIONS:
        section_data = sections.get(section)
        status = section_data.get("status") if isinstance(section_data, dict) else None
        statuses[section] = status if isinstance(status, str) else "not_started"
    return statuses


def done_count(statuses: dict[str, str]) -> int:
    return sum(1 for value in statuses.values() if value == "done")


def apply_section_status(section_data: dict[str, Any], status: str, timestamp: str | None) -> None:
    if status not in VALID_SECTION_STATUSES:
        raise ValueError(f"Invalid section status: {status}")
    section_data["status"] = status
    section_data["completed_at"] = timestamp if status == "done" else None


def _section_status(sections: dict[str, Any], section: str) -> str:
    section_data = sections.get(section)
    if not isinstance(section_data, dict):
        return "not_started"
    status = section_data.get("status")
    return status if isinstance(status, str) else "not_started"


def _set_derived_status(section_data: dict[str, Any], status: str) -> None:
    if status not in VALID_SECTION_STATUSES:
        raise ValueError(f"Invalid section status: {status}")
    section_data["status"] = status
    if status != "done":
        section_data["completed_at"] = None


def _governed_period_has_promoted_work(period: dict[str, Any]) -> bool:
    return period.get("pay_table") is not None or period.get("uplift_rule") is not None


def _governed_set_is_human_accepted(section_data: dict[str, Any]) -> bool:
    return section_data.get("status") == "done" and bool(section_data.get("completed_at"))


def derive_governed_set_status(canonical: dict[str, Any]) -> None:
    """Derive Governed Set status from the governed workflow dependency chain.

    The operational workflow is:
    Overview -> Uplift Rules -> Pay Tables -> Scenarios -> Governed Set.
    The Governed Set can contain rule-only or baseline pay-only periods. Those
    remain visible to the reviewer, but green requires the human Save & Accept
    action rather than automatic completion.
    """
    sections = canonical.get("sections") or {}
    uplifts = sections.get("uplifts")
    if not isinstance(uplifts, dict):
        return
    data = uplifts.get("data")
    periods = (data or {}).get("periods") if isinstance(data, dict) else None
    valid_periods = [period for period in periods if isinstance(period, dict)] if isinstance(periods, list) else []
    has_promoted = any(_governed_period_has_promoted_work(period) for period in valid_periods)

    upstream_sections = WORKFLOW_SECTIONS[:-1]
    upstream_done = all(_section_status(sections, section) == "done" for section in upstream_sections)
    if not upstream_done:
        _set_derived_status(uplifts, "in_progress" if has_promoted else "not_started")
        return

    if not has_promoted:
        _set_derived_status(uplifts, "not_started")
        return

    _set_derived_status(
        uplifts,
        "done" if _governed_set_is_human_accepted(uplifts) else "in_progress",
    )
