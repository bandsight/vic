from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from benchmarking_data_factory.conditions.prompt import build_conditions_extraction_prompt
from benchmarking_data_factory.conditions.schema import empty_conditions_data, validate_conditions_payload
from benchmarking_data_factory.conditions.section_picker import score_condition_pages
from benchmarking_data_factory.extraction.overview import parse_overview_response as extraction_parse_overview_response
from benchmarking_data_factory.extraction.prompts import (
    ALTERATION_KEYWORDS,
    OVERVIEW_SYSTEM,
    PAY_TABLE_EXTRACT_SYSTEM,
    PAY_TABLE_RANGE_EXTRACT_SYSTEM,
)
from benchmarking_data_factory.workbench import agreement_extraction as agreement_extraction_module
from benchmarking_data_factory.workbench import pay_table_workflow as pay_table_workflow_module


@dataclass(frozen=True)
class ExtractionOrchestrationDependencies:
    pay_keywords: Any
    uplift_keywords: Any
    page_render_dpi: int
    valid_section_statuses: set[str]
    find_candidate_pages: Callable[..., Any]
    require_vision_llm: Callable[..., Any]
    render_page_png: Callable[..., Any]
    extract_page_text: Callable[..., Any]
    extract_all_page_texts: Callable[..., Any]
    get_page_count: Callable[..., Any]
    call_llm: Callable[..., Any]
    is_llm_error: Callable[..., Any]
    llm_http_failure: Callable[..., Any]
    strip_fences: Callable[..., Any]
    strip_json_preamble: Callable[..., Any]
    normalise_extracted_pay_table_candidates: Callable[..., Any]
    get_canonical: Callable[..., Any]
    fetch_metadata_for_ae_id: Callable[..., Any]
    build_provenance_stamp: Callable[..., Any]
    apply_section_status: Callable[..., Any]
    now_iso: Callable[..., Any]
    get_nominated_expiry: Callable[..., Any]
    get_uplift_rule_dates: Callable[..., Any]
    apply_timeline_policy_to_tables: Callable[..., Any]
    recalc_to_dates: Callable[..., Any]
    validate_pay_tables: Callable[..., Any]
    pay_table_qa_events: Callable[..., Any]
    append_qa_events: Callable[..., Any]
    save_canonical: Callable[..., Any]
    find_pdf: Callable[..., Any]
    anthropic_client: Callable[..., Any]
    collect_uplift_pages_text: Callable[..., Any]
    resolve_fwc: Callable[..., Any]
    split_ae_id: Callable[..., Any]
    load_registry: Callable[..., Any]
    resolve_canonical_lga_short_name: Callable[..., Any]


def parse_overview_response(
    raw: str,
    page_count: int,
    pay_pages: list[int],
    uplift_pages: list[int],
    alteration_pages: list[int],
    *,
    strip_json_preamble: Callable[[str], str],
) -> dict[str, Any]:
    return extraction_parse_overview_response(
        raw,
        page_count,
        pay_pages,
        uplift_pages,
        alteration_pages,
        strip_json_preamble=strip_json_preamble,
    )


def build_pay_table_workflow_dependencies(
    deps: ExtractionOrchestrationDependencies,
) -> pay_table_workflow_module.PayTableWorkflowDependencies:
    return pay_table_workflow_module.PayTableWorkflowDependencies(
        pay_keywords=deps.pay_keywords,
        uplift_keywords=deps.uplift_keywords,
        page_render_dpi=deps.page_render_dpi,
        pay_table_extract_system=PAY_TABLE_EXTRACT_SYSTEM,
        pay_table_range_extract_system=PAY_TABLE_RANGE_EXTRACT_SYSTEM,
        valid_section_statuses=deps.valid_section_statuses,
        find_candidate_pages=deps.find_candidate_pages,
        require_vision_llm=deps.require_vision_llm,
        render_page_png=deps.render_page_png,
        extract_page_text=deps.extract_page_text,
        get_page_count=deps.get_page_count,
        call_llm=deps.call_llm,
        is_llm_error=deps.is_llm_error,
        llm_http_failure=deps.llm_http_failure,
        strip_fences=deps.strip_fences,
        strip_json_preamble=deps.strip_json_preamble,
        normalise_extracted_pay_table_candidates=deps.normalise_extracted_pay_table_candidates,
        get_canonical=deps.get_canonical,
        fetch_metadata_for_ae_id=deps.fetch_metadata_for_ae_id,
        build_provenance_stamp=deps.build_provenance_stamp,
        apply_section_status=deps.apply_section_status,
        now_iso=deps.now_iso,
        get_nominated_expiry=deps.get_nominated_expiry,
        get_uplift_rule_dates=deps.get_uplift_rule_dates,
        apply_timeline_policy_to_tables=deps.apply_timeline_policy_to_tables,
        recalc_to_dates=deps.recalc_to_dates,
        validate_pay_tables=deps.validate_pay_tables,
        pay_table_qa_events=deps.pay_table_qa_events,
        append_qa_events=deps.append_qa_events,
        save_canonical=deps.save_canonical,
        find_pdf=deps.find_pdf,
        anthropic_client=deps.anthropic_client,
        collect_uplift_pages_text=deps.collect_uplift_pages_text,
    )


def build_agreement_extraction_dependencies(
    deps: ExtractionOrchestrationDependencies,
) -> agreement_extraction_module.AgreementExtractionDependencies:
    return agreement_extraction_module.AgreementExtractionDependencies(
        pay_keywords=deps.pay_keywords,
        uplift_keywords=deps.uplift_keywords,
        alteration_keywords=ALTERATION_KEYWORDS,
        overview_system=OVERVIEW_SYSTEM,
        get_page_count=deps.get_page_count,
        find_candidate_pages=deps.find_candidate_pages,
        extract_page_text=deps.extract_page_text,
        extract_all_page_texts=deps.extract_all_page_texts,
        call_llm=deps.call_llm,
        is_llm_error=deps.is_llm_error,
        llm_http_failure=deps.llm_http_failure,
        parse_overview_response=lambda raw, page_count, pay_pages, uplift_pages, alteration_pages: parse_overview_response(
            raw,
            page_count,
            pay_pages,
            uplift_pages,
            alteration_pages,
            strip_json_preamble=deps.strip_json_preamble,
        ),
        now_iso=deps.now_iso,
        get_canonical=deps.get_canonical,
        apply_section_status=deps.apply_section_status,
        save_canonical=deps.save_canonical,
        resolve_fwc=deps.resolve_fwc,
        fetch_metadata_for_ae_id=deps.fetch_metadata_for_ae_id,
        split_ae_id=deps.split_ae_id,
        find_pdf=deps.find_pdf,
        load_registry=deps.load_registry,
        resolve_canonical_lga_short_name=deps.resolve_canonical_lga_short_name,
        score_condition_pages=score_condition_pages,
        empty_conditions_data=empty_conditions_data,
        validate_conditions_payload=validate_conditions_payload,
        build_conditions_extraction_prompt=build_conditions_extraction_prompt,
        strip_json_preamble=deps.strip_json_preamble,
    )


def conditions_candidate_page_blocks(
    ae_id: str,
    *,
    max_pages: int = 28,
    deps: ExtractionOrchestrationDependencies,
) -> tuple[list[dict[str, Any]], list[int]]:
    return agreement_extraction_module.conditions_candidate_page_blocks(
        ae_id,
        max_pages=max_pages,
        deps=build_agreement_extraction_dependencies(deps),
    )


def normalise_conditions_extraction_payload(
    parsed: Any,
    *,
    ae_id: str,
    council_name: str,
    candidate_pages: list[int],
    deps: ExtractionOrchestrationDependencies,
) -> dict[str, Any]:
    return agreement_extraction_module.normalise_conditions_extraction_payload(
        parsed,
        ae_id=ae_id,
        council_name=council_name,
        candidate_pages=candidate_pages,
        deps=build_agreement_extraction_dependencies(deps),
    )
