from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator

from benchmarking_data_factory.workbench import analysis_spatial_routes as analysis_spatial_routes_module
from benchmarking_data_factory.workbench import analysis_workspace as analysis_workspace_module
from benchmarking_data_factory.workbench import audit_report as audit_report_module
from benchmarking_data_factory.workbench import canonical_workflow as canonical_workflow_module
from benchmarking_data_factory.workbench import council_action_routes as council_action_routes_module
from benchmarking_data_factory.workbench import council_read_model as council_read_model_module
from benchmarking_data_factory.workbench import document_page_workflow as document_page_workflow_module
from benchmarking_data_factory.workbench import document_routes as document_routes_module
from benchmarking_data_factory.workbench import extraction_orchestration as extraction_orchestration_module
from benchmarking_data_factory.workbench import intake_audit_reference_routes as intake_audit_reference_routes_module
from benchmarking_data_factory.workbench import intake_workflow as intake_workflow_module
from benchmarking_data_factory.workbench import llm_connection_routes as llm_connection_routes_module
from benchmarking_data_factory.workbench import llm_service as llm_service_module
from benchmarking_data_factory.workbench import scenario_governance as scenario_governance_module
from benchmarking_data_factory.workbench import source_document_intake as source_document_intake_module
from benchmarking_data_factory.workbench import uplift_rules_workflow as uplift_rules_workflow_module
from benchmarking_data_factory.workbench.application_core import (
    ReportAssetService,
    ReportExportService,
    WorkbenchPathService,
)
from benchmarking_data_factory.workbench.pay_horizon_explorer import PayHorizonCurveStore


class WorkbenchDependencyFactories:
    def __init__(self, ctx: Any):
        self.ctx = ctx

    def source_document_intake_dependencies(self) -> source_document_intake_module.SourceDocumentIntakeDependencies:
        ctx = self.ctx
        return source_document_intake_module.SourceDocumentIntakeDependencies(
            registry_csv=lambda: ctx.REGISTRY_CSV,
            find_pdf=ctx.find_pdf,
            now_iso=ctx.now_iso,
        )

    def document_page_workflow_dependencies(self) -> document_page_workflow_module.DocumentPageWorkflowDependencies:
        ctx = self.ctx
        return document_page_workflow_module.DocumentPageWorkflowDependencies(
            immutable_dir=lambda: ctx.IMMUTABLE_DIR,
            cache_dir=lambda: ctx.CACHE_DIR,
            page_render_dpi=lambda: ctx.PAGE_RENDER_DPI,
            score_pages=ctx._score_pages,
            uplift_keywords=ctx.UPLIFT_KEYWORDS,
        )

    def canonical_workflow_dependencies(self) -> canonical_workflow_module.CanonicalWorkflowDependencies:
        ctx = self.ctx
        return canonical_workflow_module.CanonicalWorkflowDependencies(
            canonical_dir=lambda: ctx.CANONICAL_DIR,
            load_registry=ctx.load_registry,
            split_ae_id=ctx.split_ae_id,
            derive_governed_set_status=ctx.derive_governed_set_status,
        )

    def llm_service_config(self) -> llm_service_module.LlmServiceConfig:
        ctx = self.ctx
        return llm_service_module.LlmServiceConfig(
            env=ctx.os.environ,
            env_file=ctx.ENV_FILE,
            default_anthropic_model=ctx.ANTHROPIC_MODEL,
            default_codex_model=ctx.CODEX_MODEL,
            ssl_module=ctx.ssl,
        )

    def intake_workflow_dependencies(self) -> intake_workflow_module.IntakeWorkflowDependencies:
        ctx = self.ctx
        return intake_workflow_module.IntakeWorkflowDependencies(
            candidate_agreements_json=lambda: ctx.CANDIDATE_AGREEMENTS_JSON,
            root_path=lambda: ctx.ROOT,
            immutable_dir=lambda: ctx.IMMUTABLE_DIR,
            canonical_dir=lambda: ctx.CANONICAL_DIR,
            scenario_overrides_dir=lambda: ctx.SCENARIO_OVERRIDES_DIR,
            cache_dir=lambda: ctx.CACHE_DIR,
            clear_records_dir=lambda: ctx.CLEAR_RECORDS_DIR,
            distribution_point_analysis_json=lambda: ctx.DISTRIBUTION_POINT_ANALYSIS_JSON,
            load_candidate_agreement_rows=ctx.load_candidate_agreement_rows,
            load_candidate_agreements=ctx.load_candidate_agreements,
            load_intake_decisions=ctx.load_intake_decisions,
            load_registry=ctx.load_registry,
            list_pdfs=ctx.list_pdfs,
            api_councils=ctx.api_councils,
            pdf_source_metadata=ctx.pdf_source_metadata,
            run_phase1=ctx.run_phase1,
            clear_intake_source_caches=ctx.clear_intake_source_caches,
            record_intake_decision=ctx.record_intake_decision,
            find_pdf=ctx.find_pdf,
            sha256_file=ctx.sha256_file,
            record_frozen_source_document=ctx.record_frozen_source_document,
            find_fwc_document_download_url=ctx.find_fwc_document_download_url,
            download_pdf_to_path=ctx.download_pdf_to_path,
            load_multi_council_decisions=ctx.load_multi_council_decisions,
            write_multi_council_decisions=ctx.write_multi_council_decisions,
            record_multi_council_decision=ctx.record_multi_council_decision,
            split_ae_id=ctx.split_ae_id,
            lga_slug=ctx.lga_slug,
            active_canonical_council_lookup=ctx.active_canonical_council_lookup,
            fresh_canonical=ctx.fresh_canonical,
            save_canonical=ctx.save_canonical,
            fetch_metadata_for_ae_id=ctx.fetch_metadata_for_ae_id,
            now_iso=ctx.now_iso,
        )

    def audit_dependencies(self) -> audit_report_module.AuditReportDependencies:
        ctx = self.ctx
        return audit_report_module.AuditReportDependencies(
            load_canonical_councils=ctx.load_canonical_councils,
            candidate_lgas=ctx._candidate_lgas,
            candidate_date_ordinal=ctx.candidate_date_ordinal,
            pdf_source_metadata=ctx.pdf_source_metadata,
            load_registry=ctx.load_registry,
            load_multi_council_decisions=ctx.load_multi_council_decisions,
            split_ae_ids_from_decisions=ctx.split_ae_ids_from_decisions,
            list_pdfs=ctx.list_pdfs,
            fetch_metadata_for_ae_id=ctx.fetch_metadata_for_ae_id,
            resolve_canonical_lga_short_name=ctx.resolve_canonical_lga_short_name,
            get_canonical=ctx.get_canonical,
            read_scenario_override_state=ctx._read_scenario_override_state,
            is_standard_band_level_row=ctx.is_standard_band_level_row,
            load_candidate_agreement_rows=ctx.load_candidate_agreement_rows,
            build_intake_candidate_rows=ctx.build_intake_candidate_rows,
            load_source_register_by_ae_id=ctx.load_source_register_by_ae_id,
            build_council_summary=lambda *args, **kwargs: ctx.build_council_summary(*args, **kwargs),
            now_iso=ctx.now_iso,
            geography_for_lga=ctx.geography_for_lga,
            workspace_ae_ids=lambda *args, **kwargs: ctx._audit_workspace_ae_ids(*args, **kwargs),
            workspace_matches_council=lambda *args, **kwargs: ctx._audit_workspace_matches_council(*args, **kwargs),
            workspace_snapshot=lambda *args, **kwargs: ctx._audit_workspace_snapshot(*args, **kwargs),
            governed_events=lambda *args, **kwargs: ctx._audit_governed_events(*args, **kwargs),
        )

    def uplift_workflow_dependencies(self) -> uplift_rules_workflow_module.UpliftRulesWorkflowDependencies:
        ctx = self.ctx
        return uplift_rules_workflow_module.UpliftRulesWorkflowDependencies(
            pdf_path_for=ctx.pdf_path_for,
            get_page_count=ctx.get_page_count,
            extract_page_text=ctx.extract_page_text,
            extract_all_page_texts=ctx.extract_all_page_texts,
            call_llm=ctx.call_llm,
            configured_llm_model=ctx.configured_llm_model,
            run_uplift_suggest=ctx.run_uplift_suggest,
            get_canonical=ctx.get_canonical,
            now_iso=ctx.now_iso,
            apply_section_status=ctx.apply_section_status,
            save_canonical=ctx.save_canonical,
        )

    def council_read_model_dependencies(self) -> council_read_model_module.CouncilReadModelDependencies:
        ctx = self.ctx
        return council_read_model_module.CouncilReadModelDependencies(
            get_canonical=ctx.get_canonical,
            section_statuses=ctx.section_statuses,
            done_count=ctx.review_done_count,
            load_multi_council_decisions=ctx.load_multi_council_decisions,
            split_ae_id=ctx.split_ae_id,
            load_source_register_by_ae_id=ctx.load_source_register_by_ae_id,
            pdf_source_metadata=ctx.pdf_source_metadata,
            fetch_metadata_for_ae_id=ctx.fetch_metadata_for_ae_id,
            resolve_assigned_lga=ctx.resolve_assigned_lga,
            resolve_canonical_lga_short_name=ctx.resolve_canonical_lga_short_name,
            resolve_fwc=ctx.resolve_fwc,
            geography_for_lga=ctx.geography_for_lga,
            pay_table_report_values=ctx.pay_table_report_values,
            agreement_report_values=ctx.agreement_report_values,
            review_sections=ctx.REVIEW_SECTIONS,
            load_registry=ctx.load_registry,
            split_ae_ids_from_decisions=ctx.split_ae_ids_from_decisions,
            list_pdfs=ctx.list_pdfs,
            find_pdf=ctx.find_pdf,
            recalc_to_dates=ctx.recalc_to_dates,
            get_nominated_expiry=ctx.get_nominated_expiry,
            get_uplift_rule_dates=ctx.get_uplift_rule_dates,
        )

    def analysis_dependencies(self) -> analysis_workspace_module.AnalysisWorkspaceDependencies:
        ctx = self.ctx
        return analysis_workspace_module.AnalysisWorkspaceDependencies(
            load_registry=ctx.load_registry,
            load_multi_council_decisions=ctx.load_multi_council_decisions,
            split_ae_ids_from_decisions=ctx.split_ae_ids_from_decisions,
            list_pdfs=ctx.list_pdfs,
            get_canonical=ctx.get_canonical,
            fetch_metadata_for_ae_id=ctx.fetch_metadata_for_ae_id,
            resolve_canonical_lga_short_name=ctx.resolve_canonical_lga_short_name,
            scenario_cell_overrides_for_period=ctx._scenario_cell_overrides_for_period,
            save_canonical=ctx.save_canonical,
            now_iso=ctx.now_iso,
            analysis_geography_fields=ctx.analysis_geography_fields,
            standard_band_level_metadata=ctx.standard_band_level_metadata,
            parse_iso_date=ctx._parse_iso_date,
            root_path=lambda: ctx.ROOT,
            distribution_point_analysis_json=lambda: ctx.DISTRIBUTION_POINT_ANALYSIS_JSON,
            extract_page_text=ctx.extract_page_text,
        )

    def extraction_orchestration_dependencies(
        self,
    ) -> extraction_orchestration_module.ExtractionOrchestrationDependencies:
        ctx = self.ctx
        return extraction_orchestration_module.ExtractionOrchestrationDependencies(
            pay_keywords=ctx.PAY_KEYWORDS,
            uplift_keywords=ctx.UPLIFT_KEYWORDS,
            page_render_dpi=ctx.PAGE_RENDER_DPI,
            valid_section_statuses=set(ctx.VALID_SECTION_STATUSES),
            find_candidate_pages=ctx.find_candidate_pages,
            require_vision_llm=ctx.require_vision_llm,
            render_page_png=ctx.render_page_png,
            extract_page_text=ctx.extract_page_text,
            extract_all_page_texts=ctx.extract_all_page_texts,
            get_page_count=ctx.get_page_count,
            call_llm=ctx.call_llm,
            is_llm_error=ctx.is_llm_error,
            llm_http_failure=ctx.llm_http_failure,
            strip_fences=ctx.strip_fences,
            strip_json_preamble=ctx.strip_json_preamble,
            normalise_extracted_pay_table_candidates=ctx.normalise_extracted_pay_table_candidates,
            get_canonical=ctx.get_canonical,
            fetch_metadata_for_ae_id=ctx.fetch_metadata_for_ae_id,
            build_provenance_stamp=ctx.build_provenance_stamp,
            apply_section_status=ctx.apply_section_status,
            now_iso=ctx.now_iso,
            get_nominated_expiry=ctx.get_nominated_expiry,
            get_uplift_rule_dates=ctx.get_uplift_rule_dates,
            apply_timeline_policy_to_tables=ctx.apply_timeline_policy_to_tables,
            recalc_to_dates=ctx.recalc_to_dates,
            validate_pay_tables=ctx.validate_pay_tables,
            pay_table_qa_events=ctx._pay_table_qa_events,
            append_qa_events=ctx._append_qa_events,
            save_canonical=ctx.save_canonical,
            find_pdf=ctx.find_pdf,
            anthropic_client=ctx.anthropic_client,
            collect_uplift_pages_text=ctx.collect_uplift_pages_text,
            resolve_fwc=ctx.resolve_fwc,
            split_ae_id=ctx.split_ae_id,
            load_registry=ctx.load_registry,
            resolve_canonical_lga_short_name=ctx.resolve_canonical_lga_short_name,
        )

    def pay_table_workflow_dependencies(self) -> Any:
        return extraction_orchestration_module.build_pay_table_workflow_dependencies(
            self.extraction_orchestration_dependencies()
        )

    def agreement_extraction_dependencies(self) -> Any:
        return extraction_orchestration_module.build_agreement_extraction_dependencies(
            self.extraction_orchestration_dependencies()
        )

    def document_routes_dependencies(self) -> document_routes_module.DocumentRoutesDependencies:
        ctx = self.ctx
        return document_routes_module.DocumentRoutesDependencies(
            fetch_metadata_for_ae_id=ctx.fetch_metadata_for_ae_id,
            find_pdf=ctx.find_pdf,
            extract_page_text=ctx.extract_page_text,
            render_page_png=ctx.render_page_png,
        )

    def intake_audit_reference_routes_dependencies(
        self,
    ) -> intake_audit_reference_routes_module.IntakeAuditReferenceRoutesDependencies:
        ctx = self.ctx
        return intake_audit_reference_routes_module.IntakeAuditReferenceRoutesDependencies(
            load_canonical_councils=ctx.load_canonical_councils,
            canonical_council_reference_payload=ctx.canonical_council_reference_payload,
            council_master_reference_payload=ctx.council_master_reference_payload,
            council_job_source_registry_payload=ctx.council_job_source_registry_payload,
            build_intake_quality_summary=ctx.build_intake_quality_summary,
            build_pay_tables_analysis=ctx.build_pay_tables_analysis,
            build_intake_candidate_rows=ctx.build_intake_candidate_rows,
            build_council_audit_report=ctx.build_council_audit_report,
            fetch_fair_work_registry_intake=ctx.fetch_fair_work_registry_intake,
            load_intake_decisions=ctx.load_intake_decisions,
            intake_workflow_dependencies=ctx._intake_workflow_dependencies,
        )

    def analysis_spatial_routes_dependencies(self) -> analysis_spatial_routes_module.AnalysisSpatialRoutesDependencies:
        ctx = self.ctx
        paths = WorkbenchPathService.from_context(ctx)
        report_assets = ReportAssetService(paths=paths, now=ctx.now_iso)
        return analysis_spatial_routes_module.AnalysisSpatialRoutesDependencies(
            build_uplift_rules_analysis=ctx.build_uplift_rules_analysis,
            build_pay_tables_analysis=ctx.build_pay_tables_analysis,
            build_end_of_band_dollars_analysis=ctx.build_end_of_band_dollars_analysis,
            build_review_learning_snapshot=ctx.build_review_learning_snapshot,
            load_distribution_point_analysis_asset=ctx.load_distribution_point_analysis_asset,
            materialize_distribution_point_analysis=ctx.materialize_distribution_point_analysis,
            rebuild_analysis_data_set=ctx.rebuild_analysis_data_set,
            build_council_geography_payload=ctx.build_council_geography_payload,
            pay_horizon_curve_store=PayHorizonCurveStore(ctx.ROOT),
            report_assets=report_assets,
            report_exports=ReportExportService(paths=paths, report_assets=report_assets, now=ctx.now_iso),
        )

    def council_action_routes_dependencies(self) -> council_action_routes_module.CouncilActionRoutesDependencies:
        ctx = self.ctx
        return council_action_routes_module.CouncilActionRoutesDependencies(
            clear_review_record=ctx.clear_review_record,
            list_councils=lambda include_split_parents=False: ctx.api_councils(include_split_parents),
            get_council=lambda ae_id: ctx.api_council(ae_id),
            intake_workflow_dependencies=ctx._intake_workflow_dependencies,
            sections=ctx.SECTIONS,
            valid_section_statuses=ctx.VALID_SECTION_STATUSES,
            get_canonical=ctx.get_canonical,
            apply_section_status=ctx.apply_section_status,
            now_iso=ctx.now_iso,
            save_canonical=ctx.save_canonical,
            uplift_workflow_dependencies=ctx._uplift_workflow_dependencies,
            scenario_governance_dependencies=ctx._scenario_governance_dependencies,
        )

    def llm_connection_routes_dependencies(self) -> llm_connection_routes_module.LlmConnectionRoutesDependencies:
        ctx = self.ctx
        return llm_connection_routes_module.LlmConnectionRoutesDependencies(
            llm_provider_status=ctx.api_llm_status,
            llm_connections_status=ctx.api_connections,
            update_llm_connection=ctx.api_update_llm_connection,
        )

    def scenario_governance_dependencies(self) -> scenario_governance_module.ScenarioGovernanceDependencies:
        ctx = self.ctx
        return scenario_governance_module.ScenarioGovernanceDependencies(
            scenario_overrides_dir=lambda: ctx.SCENARIO_OVERRIDES_DIR,
            split_ae_id=ctx.split_ae_id,
            find_pdf=ctx.find_pdf,
            load_registry=ctx.load_registry,
            get_canonical=ctx.get_canonical,
            recalc_to_dates=ctx.recalc_to_dates,
            get_nominated_expiry=ctx.get_nominated_expiry,
            get_uplift_rule_dates=ctx.get_uplift_rule_dates,
            fetch_metadata_for_ae_id=ctx.fetch_metadata_for_ae_id,
            resolve_canonical_lga_short_name=ctx.resolve_canonical_lga_short_name,
            run_scenarios=ctx.run_scenarios,
            now_iso=ctx.now_iso,
            apply_section_status=ctx.apply_section_status,
            save_canonical=ctx.save_canonical,
            construct_table=ctx.construct_table,
            normalised_governed_payload_for_response=ctx.normalised_governed_payload_for_response,
            rate_cap_data_dir=lambda: ctx.RATE_CAP_DATA_DIR,
            invalidate_rate_cap_caches=ctx.invalidate_rate_cap_caches,
        )

    def with_audit_dependencies(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        with audit_report_module.audit_report_dependencies(self.audit_dependencies()):
            return callback(*args, **kwargs)

    def with_analysis_dependencies(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        with analysis_workspace_module.analysis_workspace_dependencies(self.analysis_dependencies()):
            return callback(*args, **kwargs)

    def with_scenario_governance_dependencies(
        self,
        callback: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        with scenario_governance_module.scenario_governance_dependencies(self.scenario_governance_dependencies()):
            return callback(*args, **kwargs)

    @contextmanager
    def audit_dependency_context(self) -> Iterator[None]:
        with audit_report_module.audit_report_dependencies(self.audit_dependencies()):
            yield

    @contextmanager
    def analysis_dependency_context(self) -> Iterator[None]:
        with analysis_workspace_module.analysis_workspace_dependencies(self.analysis_dependencies()):
            yield

    @contextmanager
    def scenario_governance_dependency_context(self) -> Iterator[None]:
        with scenario_governance_module.scenario_governance_dependencies(self.scenario_governance_dependencies()):
            yield
