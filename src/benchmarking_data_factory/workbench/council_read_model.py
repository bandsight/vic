from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import HTTPException


@dataclass(frozen=True)
class CouncilReadModelDependencies:
    get_canonical: Callable[[str], dict[str, Any]]
    section_statuses: Callable[[dict[str, Any]], dict[str, str]]
    done_count: Callable[[dict[str, str]], int]
    load_multi_council_decisions: Callable[[], dict[str, dict[str, Any]]]
    split_ae_id: Callable[[str], tuple[str, str | None]]
    load_source_register_by_ae_id: Callable[[], dict[str, dict[str, str]]]
    pdf_source_metadata: Callable[[str], dict[str, Any]]
    fetch_metadata_for_ae_id: Callable[..., dict[str, Any] | None]
    resolve_assigned_lga: Callable[[str, dict[str, Any] | None], str | None]
    resolve_canonical_lga_short_name: Callable[..., str | None]
    resolve_fwc: Callable[[dict[str, Any], dict[str, Any] | None], dict[str, Any]]
    geography_for_lga: Callable[[str | None], dict[str, Any] | None]
    pay_table_report_values: Callable[[dict[str, Any]], dict[str, Any]]
    agreement_report_values: Callable[..., dict[str, Any]]
    review_sections: list[str]
    load_registry: Callable[[], dict[str, str]]
    split_ae_ids_from_decisions: Callable[[dict[str, dict[str, Any]]], set[str]]
    list_pdfs: Callable[[], list[str]]
    find_pdf: Callable[[str], Any]
    recalc_to_dates: Callable[..., Any]
    get_nominated_expiry: Callable[[dict[str, Any]], str | None]
    get_uplift_rule_dates: Callable[[dict[str, Any]], list[str]]


def human_qa_statuses(sections: dict[str, Any], review_sections: list[str]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for section in review_sections:
        section_data = sections.get(section)
        section_status = section_data.get("status") if isinstance(section_data, dict) else None
        qa_record = section_data.get("human_qa") if isinstance(section_data, dict) else None
        if isinstance(qa_record, dict):
            if qa_record.get("enabled") is True and not qa_record.get("invalidated_by"):
                statuses[section] = "accepted"
            elif qa_record.get("invalidated_by"):
                statuses[section] = "invalidated"
            elif qa_record.get("enabled") is False:
                statuses[section] = "open"
            else:
                statuses[section] = "missing" if section_status != "not_started" else "not_started"
        else:
            statuses[section] = "missing" if section_status != "not_started" else "not_started"
    return statuses


def build_council_summary(
    ae_id: str,
    *,
    registry: dict[str, str] | None = None,
    decisions: dict[str, dict[str, Any]] | None = None,
    deps: CouncilReadModelDependencies,
) -> dict[str, Any]:
    canonical = deps.get_canonical(ae_id)
    statuses = deps.section_statuses(canonical["sections"])
    done_count = deps.done_count(statuses)
    decisions = decisions or deps.load_multi_council_decisions()
    parent_ae_id, split_slug = deps.split_ae_id(ae_id)
    source_register = deps.load_source_register_by_ae_id()
    register_key = parent_ae_id if split_slug else ae_id
    register_entry = source_register.get(register_key)
    landed_at = (register_entry.get("fetched_at") or None) if register_entry else None
    pdf_source = deps.pdf_source_metadata(register_key)
    decision = decisions.get(parent_ae_id)
    fetch_metadata = deps.fetch_metadata_for_ae_id(ae_id, decisions)
    assigned_lga = deps.resolve_assigned_lga(ae_id, decision)
    is_split_row = split_slug is not None
    decision_pending = bool(
        fetch_metadata
        and fetch_metadata.get("possible_multi_council_flag")
        and decision is None
        and not is_split_row
    )
    canonical_lga_short_name = deps.resolve_canonical_lga_short_name(ae_id, fetch_metadata, decisions)
    fwc_resolved = deps.resolve_fwc(canonical, fetch_metadata)
    geography = deps.geography_for_lga(canonical_lga_short_name)
    raw_tables = canonical.get("sections", {}).get("pay_tables", {}).get("tables") or []
    pay_table_summary = []
    for table in raw_tables:
        table_summary = {
            "table_title": table.get("table_title"),
            "source_clause": table.get("source_clause"),
            "source_pages": table.get("source_pages"),
            "effective_from": table.get("effective_from"),
            "to_date": table.get("to_date"),
            "rate_kind": table.get("rate_kind"),
        }
        table_summary["report_values"] = deps.pay_table_report_values(table_summary)
        pay_table_summary.append(table_summary)
    summary = {
        "ae_id": ae_id,
        "source_name": next(
            (
                source
                for source in [
                    canonical.get("source_name"),
                    (registry or {}).get(ae_id),
                    fetch_metadata.get("Agreement Title") if fetch_metadata else None,
                ]
                if source and source != ae_id
            ),
            ae_id,
        ),
        "section_statuses": statuses,
        "human_qa_statuses": human_qa_statuses(canonical["sections"], deps.review_sections),
        "done_count": done_count,
        "total_sections": len(deps.review_sections),
        "has_overview": bool(canonical.get("overview", {}).get("generated_at")),
        "fetch_metadata": fetch_metadata,
        "canonical_lga_short_name": canonical_lga_short_name,
        "processing_gated": decision_pending,
        "is_split_row": is_split_row,
        "parent_ae_id": parent_ae_id if is_split_row else None,
        "multi_council_decision": {
            "is_multi": True if is_split_row else bool(decision and decision.get("is_multi")),
            "parent_ae_id": parent_ae_id if is_split_row else None,
            "assigned_lga": assigned_lga,
            "decision_pending": decision_pending,
        },
        "landed_at": landed_at,
        "pdf_frozen": pdf_source["frozen"],
        "pdf_source": pdf_source,
        "last_clear_record": (
            (canonical.get("review_clear_records") or [])[-1]
            if isinstance(canonical.get("review_clear_records"), list)
            and canonical.get("review_clear_records")
            else None
        ),
        "fwc": fwc_resolved,
        "geography": geography,
        "pay_table_summary": pay_table_summary,
    }
    summary["report_values"] = deps.agreement_report_values(
        canonical={**canonical, "fwc": fwc_resolved},
        fetch_metadata=fetch_metadata,
        pdf_source=pdf_source,
        landed_at=landed_at,
        pay_table_summary=pay_table_summary,
    )
    return summary


def list_councils(include_split_parents: bool, deps: CouncilReadModelDependencies) -> list[dict[str, Any]]:
    registry = deps.load_registry()
    decisions = deps.load_multi_council_decisions()
    split_ae_ids = deps.split_ae_ids_from_decisions(decisions)
    ae_ids = sorted(set(registry.keys()) | set(deps.list_pdfs()) | split_ae_ids)
    hidden_parents = {
        decision_ae_id
        for decision_ae_id, decision in decisions.items()
        if decision.get("is_multi")
        and not include_split_parents
        and (decision.get("split_files") or any(split_id.startswith(f"{decision_ae_id}__") for split_id in split_ae_ids))
    }
    visible_ae_ids = [ae_id for ae_id in ae_ids if ae_id not in hidden_parents]
    rows = [
        build_council_summary(ae_id, registry=registry, decisions=decisions, deps=deps)
        for ae_id in visible_ae_ids
    ]
    rows.sort(key=lambda item: (item["source_name"] or item["ae_id"]).lower())
    return rows


def get_council(ae_id: str, deps: CouncilReadModelDependencies) -> dict[str, Any]:
    parent_ae_id, _ = deps.split_ae_id(ae_id)
    registry = deps.load_registry()
    if deps.find_pdf(ae_id) is None and ae_id.lower() not in registry and parent_ae_id not in registry:
        raise HTTPException(status_code=404, detail="Council not found")
    canonical = deps.get_canonical(ae_id)
    decisions = deps.load_multi_council_decisions()
    fetch_metadata = deps.fetch_metadata_for_ae_id(ae_id, decisions)
    canonical_lga_short_name = deps.resolve_canonical_lga_short_name(ae_id, fetch_metadata, decisions)
    canonical["canonical_lga_short_name"] = canonical_lga_short_name
    canonical["geography"] = deps.geography_for_lga(canonical_lga_short_name)
    canonical["fwc"] = deps.resolve_fwc(canonical, fetch_metadata)
    tables = canonical.get("sections", {}).get("pay_tables", {}).get("tables") or []
    if tables:
        deps.recalc_to_dates(
            tables,
            deps.get_nominated_expiry(canonical),
            deps.get_uplift_rule_dates(canonical),
        )
    canonical["report_values"] = deps.agreement_report_values(
        canonical=canonical,
        fetch_metadata=fetch_metadata,
        pdf_source=deps.pdf_source_metadata(parent_ae_id),
        pay_table_summary=[
            {
                "table_title": table.get("table_title"),
                "source_clause": table.get("source_clause"),
                "source_pages": table.get("source_pages"),
                "effective_from": table.get("effective_from"),
                "to_date": table.get("to_date"),
                "rate_kind": table.get("rate_kind"),
            }
            for table in tables
            if isinstance(table, dict)
        ],
    )
    return canonical
