from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from benchmarking_data_factory.workbench import review_sections as review_sections_module


HUMAN_QA_WORKFLOW_SECTIONS = tuple(review_sections_module.REVIEW_SECTIONS)


@dataclass(frozen=True)
class HumanQaTransitionResult:
    section: str
    enabled: bool
    status: str | None
    completed_at: str | None
    downstream_cleared: list[str]
    clear_scenario_overrides: bool


class HumanQaTransitionBlocked(ValueError):
    def __init__(self, *, section: str, blocker: str) -> None:
        self.section = section
        self.blocker = blocker
        super().__init__(f"Cannot accept {section}; {blocker} must be accepted first")


def section_has_working_data(section_data: dict[str, Any]) -> bool:
    if not isinstance(section_data, dict):
        return False
    data = section_data.get("data")
    if data not in (None, "", [], {}):
        return True
    tables = section_data.get("tables")
    if isinstance(tables, list) and tables:
        return True
    return bool(section_data.get("source_ref") or section_data.get("notes"))


def downstream_human_qa_sections(section: str) -> list[str]:
    if section not in HUMAN_QA_WORKFLOW_SECTIONS:
        return []
    index = HUMAN_QA_WORKFLOW_SECTIONS.index(section)
    return list(HUMAN_QA_WORKFLOW_SECTIONS[index + 1 :])


def upstream_human_qa_blocker(sections: dict[str, Any], section: str) -> str | None:
    if section not in HUMAN_QA_WORKFLOW_SECTIONS:
        return None
    index = HUMAN_QA_WORKFLOW_SECTIONS.index(section)
    for upstream_section in HUMAN_QA_WORKFLOW_SECTIONS[:index]:
        upstream = sections.get(upstream_section)
        qa_record = upstream.get("human_qa") if isinstance(upstream, dict) else None
        if not isinstance(qa_record, dict) or qa_record.get("enabled") is not True:
            return upstream_section
        if qa_record.get("invalidated_by"):
            return upstream_section
    return None


def apply_human_qa_transition(
    canonical: dict[str, Any],
    section: str,
    *,
    enabled: bool,
    timestamp: str,
    notes: str = "",
    summary: str = "",
    apply_section_status: Callable[[dict[str, Any], str, str | None], Any],
) -> HumanQaTransitionResult:
    sections = canonical.setdefault("sections", {})
    section_data = sections.setdefault(section, {})
    downstream = downstream_human_qa_sections(section)
    upstream_blocker = upstream_human_qa_blocker(sections, section)
    if enabled and upstream_blocker:
        raise HumanQaTransitionBlocked(section=section, blocker=upstream_blocker)

    if enabled:
        apply_section_status(section_data, "done", timestamp)
    else:
        next_status = "in_progress" if section_has_working_data(section_data) else "not_started"
        apply_section_status(section_data, next_status, None)

    qa_record = section_data.get("human_qa") if isinstance(section_data.get("human_qa"), dict) else {}
    qa_record = {
        **qa_record,
        "enabled": enabled,
        "updated_at": timestamp,
        "summary": summary,
        "notes": notes,
    }
    qa_record.pop("invalidated_by", None)
    qa_record.pop("invalidated_at", None)
    if enabled:
        qa_record.pop("downstream_cleared", None)
    else:
        qa_record["downstream_cleared"] = downstream
    section_data["human_qa"] = qa_record

    if not enabled:
        defaults = review_sections_module.default_sections()
        for downstream_section in downstream:
            default_section = defaults.get(downstream_section, {}).copy()
            default_section["human_qa"] = {
                "enabled": False,
                "invalidated_by": section,
                "invalidated_at": timestamp,
                "summary": f"Cleared because Human QA was switched off for {section}.",
                "notes": "",
            }
            sections[downstream_section] = default_section
    else:
        for downstream_section in downstream:
            downstream_data = sections.get(downstream_section)
            if not isinstance(downstream_data, dict):
                continue
            downstream_qa = (
                downstream_data.get("human_qa")
                if isinstance(downstream_data.get("human_qa"), dict)
                else {}
            )
            if downstream_qa.get("invalidated_by") != section:
                continue
            downstream_qa["enabled"] = False
            downstream_qa.pop("invalidated_by", None)
            downstream_qa.pop("invalidated_at", None)
            downstream_qa["summary"] = f"Ready for editing after Human QA was accepted for {section}."
            downstream_data["human_qa"] = downstream_qa

    return HumanQaTransitionResult(
        section=section,
        enabled=enabled,
        status=section_data.get("status"),
        completed_at=section_data.get("completed_at"),
        downstream_cleared=downstream if not enabled else [],
        clear_scenario_overrides=not enabled and "scenarios" in downstream,
    )
