from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Container

from fastapi import HTTPException

from benchmarking_data_factory.workbench import agreement_extraction as agreement_extraction_module
from benchmarking_data_factory.workbench import human_qa_workflow
from benchmarking_data_factory.workbench import intake_workflow as intake_workflow_module
from benchmarking_data_factory.workbench import pay_table_workflow as pay_table_workflow_module
from benchmarking_data_factory.workbench import review_advice as review_advice_module
from benchmarking_data_factory.workbench import scenario_governance as scenario_governance_module
from benchmarking_data_factory.workbench import uplift_rules_workflow as uplift_rules_workflow_module

HUMAN_QA_WORKFLOW_SECTIONS = human_qa_workflow.HUMAN_QA_WORKFLOW_SECTIONS


@dataclass(frozen=True)
class AgreementWorkspaceService:
    clear_review_record: Callable[..., dict[str, Any]]
    list_councils: Callable[[bool], list[dict[str, Any]]]
    get_council: Callable[[str], dict[str, Any]]
    intake_workflow_dependencies: Callable[[], intake_workflow_module.IntakeWorkflowDependencies]
    sections: Container[str]
    valid_section_statuses: Container[str]
    get_canonical: Callable[[str], dict[str, Any]]
    apply_section_status: Callable[..., Any]
    now_iso: Callable[[], str]
    save_canonical: Callable[[str, dict[str, Any]], None]
    uplift_workflow_dependencies: Callable[[], uplift_rules_workflow_module.UpliftRulesWorkflowDependencies]
    fetch_metadata_for_ae_id: Callable[..., dict[str, Any] | None]
    find_pdf: Callable[[str], Path | None]
    extract_page_text: Callable[[str, int], str]
    render_page_png: Callable[[str, int], bytes]
    agreement_dependencies: Callable[[], agreement_extraction_module.AgreementExtractionDependencies]
    pay_table_dependencies: Callable[[], pay_table_workflow_module.PayTableWorkflowDependencies]
    scenario_governance_dependencies: Callable[
        [],
        scenario_governance_module.ScenarioGovernanceDependencies,
    ]

    @classmethod
    def from_context(cls, ctx: Any) -> AgreementWorkspaceService:
        return cls(
            clear_review_record=lambda *args, **kwargs: ctx.clear_review_record(*args, **kwargs),
            list_councils=lambda include_split_parents=False: ctx.api_councils(include_split_parents),
            get_council=lambda ae_id: ctx.api_council(ae_id),
            intake_workflow_dependencies=lambda: ctx._intake_workflow_dependencies(),
            sections=ctx.SECTIONS,
            valid_section_statuses=ctx.VALID_SECTION_STATUSES,
            get_canonical=lambda ae_id: ctx.get_canonical(ae_id),
            apply_section_status=lambda *args, **kwargs: ctx.apply_section_status(*args, **kwargs),
            now_iso=lambda: ctx.now_iso(),
            save_canonical=lambda ae_id, canonical: ctx.save_canonical(ae_id, canonical),
            uplift_workflow_dependencies=lambda: ctx._uplift_workflow_dependencies(),
            fetch_metadata_for_ae_id=lambda ae_id, *args, **kwargs: ctx.fetch_metadata_for_ae_id(
                ae_id,
                *args,
                **kwargs,
            ),
            find_pdf=lambda ae_id: ctx.find_pdf(ae_id),
            extract_page_text=lambda ae_id, page_num: ctx.extract_page_text(ae_id, page_num),
            render_page_png=lambda ae_id, page_num: ctx.render_page_png(ae_id, page_num),
            agreement_dependencies=lambda: ctx._agreement_extraction_dependencies(),
            pay_table_dependencies=lambda: ctx._pay_table_workflow_dependencies(),
            scenario_governance_dependencies=lambda: ctx._scenario_governance_dependencies(),
        )

    def clear_review(
        self,
        ae_id: str,
        *,
        reason: str = "",
        include_related: bool = True,
    ) -> dict[str, Any]:
        return self.clear_review_record(ae_id, reason=reason, include_related=include_related)

    def councils(self, include_split_parents: bool = False) -> list[dict[str, Any]]:
        return self.list_councils(include_split_parents)

    def pipeline_matrix(self) -> list[dict[str, Any]]:
        return self.list_councils(False)

    def council(self, ae_id: str) -> dict[str, Any]:
        return self.get_council(ae_id)

    def split_council(self, ae_id: str, request: Any) -> dict[str, Any]:
        return intake_workflow_module.split_council(ae_id, request, self.intake_workflow_dependencies())

    def confirm_single_council(self, ae_id: str, request: Any) -> dict[str, Any]:
        return intake_workflow_module.confirm_single_council(
            ae_id,
            request,
            self.intake_workflow_dependencies(),
        )

    def unsplit_council(self, ae_id: str) -> dict[str, Any]:
        return intake_workflow_module.unsplit_council(ae_id, self.intake_workflow_dependencies())

    def update_section_status(self, ae_id: str, section: str, status: str) -> dict[str, Any]:
        if section not in self.sections:
            raise HTTPException(status_code=404, detail="Unknown section")
        if status not in self.valid_section_statuses:
            raise HTTPException(status_code=400, detail="Invalid status")
        canonical = self.get_canonical(ae_id)
        section_data = canonical["sections"][section]
        self.apply_section_status(section_data, status, self.now_iso() if status == "done" else None)
        self.save_canonical(ae_id, canonical)
        return {
            "ok": True,
            "section": section,
            "status": status,
            "completed_at": section_data["completed_at"],
        }

    def update_section_human_qa(
        self,
        ae_id: str,
        section: str,
        *,
        enabled: bool,
        notes: str = "",
        summary: str = "",
    ) -> dict[str, Any]:
        if section not in self.sections:
            raise HTTPException(status_code=404, detail="Unknown section")

        canonical = self.get_canonical(ae_id)
        timestamp = self.now_iso()
        try:
            transition = human_qa_workflow.apply_human_qa_transition(
                canonical,
                section,
                enabled=enabled,
                timestamp=timestamp,
                notes=notes,
                summary=summary,
                apply_section_status=self.apply_section_status,
            )
        except human_qa_workflow.HumanQaTransitionBlocked as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            ) from exc

        if transition.clear_scenario_overrides:
            scenario_governance_module.delete_uplift_rule_scenario_overrides(
                ae_id,
                self.scenario_governance_dependencies(),
            )

        self.save_canonical(ae_id, canonical)
        return {
            "ok": True,
            "section": section,
            "enabled": transition.enabled,
            "status": transition.status,
            "completed_at": transition.completed_at,
            "downstream_cleared": transition.downstream_cleared,
            "canonical": self.get_council(ae_id),
        }

    def suggest_uplift_rules(self, ae_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
        return uplift_rules_workflow_module.suggest_uplift_rules(
            ae_id,
            force_refresh=force_refresh,
            deps=self.uplift_workflow_dependencies(),
        )

    def uplift_rule_suggestion(self, ae_id: str) -> dict[str, Any]:
        return uplift_rules_workflow_module.get_uplift_rule_suggestion(
            ae_id,
            self.uplift_workflow_dependencies(),
        )

    def accept_uplift_rules(self, ae_id: str, rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return uplift_rules_workflow_module.accept_uplift_rules(
            ae_id,
            self.uplift_workflow_dependencies(),
            rules=rules,
        )

    def discard_uplift_rule_suggestion(self, ae_id: str) -> dict[str, Any]:
        return uplift_rules_workflow_module.discard_uplift_rule_suggestion(
            ae_id,
            self.uplift_workflow_dependencies(),
        )

    def update_accepted_uplift_rules(self, ae_id: str, rules: list[dict[str, Any]]) -> dict[str, Any]:
        return uplift_rules_workflow_module.update_accepted_uplift_rules(
            ae_id,
            rules,
            self.uplift_workflow_dependencies(),
        )

    def fetch_metadata(self, ae_id: str) -> dict[str, Any]:
        metadata = self.fetch_metadata_for_ae_id(ae_id)
        if metadata is None:
            raise HTTPException(status_code=404, detail="Fetch metadata not found")
        return metadata

    def pdf_path(self, ae_id: str) -> Path:
        pdf_path = self.find_pdf(ae_id)
        if pdf_path is None:
            raise HTTPException(status_code=404, detail="PDF not found")
        return pdf_path

    def page_text(self, ae_id: str, page_num: int) -> dict[str, Any]:
        return {"page": page_num, "text": self.extract_page_text(ae_id, page_num)}

    def page_image(self, ae_id: str, page_num: int) -> bytes:
        return self.render_page_png(ae_id, page_num)

    def generate_overview(self, ae_id: str) -> dict[str, Any]:
        return agreement_extraction_module.generate_overview(ae_id, self.agreement_dependencies())

    def pay_table_candidate_pages(self, ae_id: str) -> dict[str, Any]:
        return pay_table_workflow_module.find_pay_table_candidate_pages(ae_id, self.pay_table_dependencies())

    def extract_pay_table_page(self, ae_id: str, request: Any) -> dict[str, Any]:
        return pay_table_workflow_module.extract_pay_table_page(ae_id, request, self.pay_table_dependencies())

    def extract_pay_table_range(self, ae_id: str, request: Any) -> dict[str, Any]:
        return pay_table_workflow_module.extract_pay_table_range(ae_id, request, self.pay_table_dependencies())

    def extract_entitlements(self, ae_id: str) -> dict[str, Any]:
        return agreement_extraction_module.extract_entitlements(ae_id, self.agreement_dependencies())

    def save_pay_tables(self, ae_id: str, request: Any) -> dict[str, Any]:
        return pay_table_workflow_module.save_pay_tables(ae_id, request, self.pay_table_dependencies())

    def validate_pay_tables(self, ae_id: str) -> dict[str, Any]:
        return pay_table_workflow_module.validate_pay_table_section(ae_id, self.pay_table_dependencies())

    def recalc_pay_table_dates(self, ae_id: str, request: Any | None) -> dict[str, Any]:
        return pay_table_workflow_module.recalc_pay_table_dates(ae_id, request, self.pay_table_dependencies())

    def suggest_effective_dates(self, ae_id: str, request: Any) -> dict[str, Any]:
        return pay_table_workflow_module.suggest_effective_dates(ae_id, request, self.pay_table_dependencies())

    def pay_table_review_hints(self, ae_id: str, request: Any) -> dict[str, Any]:
        deps = self.pay_table_dependencies()
        canonical = deps.get_canonical(ae_id)
        overview_data = (((canonical.get("sections") or {}).get("overview") or {}).get("data") or {})
        candidate_pages = request.candidate_pages or overview_data.get("likely_pay_table_pages") or []
        hints = review_advice_module.build_pay_table_review_hints(
            canonical,
            request.tables,
            suggestions=request.suggestions,
            candidate_pages=candidate_pages,
        )
        return {"ae_id": ae_id, "hints": hints}
