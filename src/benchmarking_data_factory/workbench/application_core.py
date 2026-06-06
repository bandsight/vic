from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import platform
from pathlib import Path
import re
from typing import Any, Callable

from benchmarking_data_factory.workbench.agreement_workspace import AgreementWorkspaceService
from benchmarking_data_factory.workbench import intake_workflow as intake_workflow_module
from benchmarking_data_factory.workbench import scenario_governance as scenario_governance_module
from benchmarking_data_factory.workbench.operator_commands import OperatorCommandService
from benchmarking_data_factory.workbench.package_profiles import PackageProfileService, PackagingService
from benchmarking_data_factory.workbench.portable_validation import PortableValidationService
from benchmarking_data_factory.workbench.report_assets import ReportAssetService, ReportExportService

def read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "error": "invalid_json",
            "path": path.name,
        }


def entitlement_definition_overrides(root: Path) -> dict[str, str]:
    payload = read_json_file(root / "data" / "review" / "entitlement_definition_overrides.json") or {}
    raw_overrides = payload.get("overrides") if isinstance(payload, dict) else {}
    if not isinstance(raw_overrides, dict):
        return {}
    definitions: dict[str, str] = {}
    for entitlement_id, value in raw_overrides.items():
        definition = value.get("definition") if isinstance(value, dict) else value
        text = str(definition or "").strip()
        if text:
            definitions[str(entitlement_id)] = text
    return definitions


def file_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
        }
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "bytes": stat.st_size,
        "last_modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def file_count(path: Path, pattern: str = "*") -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.glob(pattern) if item.is_file())


def governed_data_layer_entries(
    layer_dir: Path,
    *,
    kind: str,
    id_key: str,
    id_prefix: str,
    layer_label: str,
) -> list[dict[str, Any]]:
    if not layer_dir.exists():
        return []
    entries: list[dict[str, Any]] = []
    for status_path in sorted(layer_dir.glob("*_status.json")):
        payload = read_json_file(status_path) or {}
        if not isinstance(payload, dict) or payload.get("error"):
            continue
        item_id = str(payload.get(id_key) or status_path.name.removesuffix("_status.json"))
        if status_path.name != f"{item_id}_status.json":
            continue
        output_files = payload.get("output_files")
        if not isinstance(output_files, list):
            output_files = []
        entries.append(
            {
                "id": f"{id_prefix}:{item_id}",
                id_key: item_id,
                "label": display_code_label(item_id),
                "kind": kind,
                "layer": layer_label,
                "directory": str(layer_dir),
                "status": payload.get("status") or "unknown",
                "row_count": payload.get("row_count"),
                "generated_at": payload.get("generated_at"),
                "schema_version": payload.get("schema_version"),
                "contract": payload.get("contract"),
                "inputs": payload.get("inputs") if isinstance(payload.get("inputs"), list) else [],
                "caveats": payload.get("caveats") if isinstance(payload.get("caveats"), list) else [],
                "blockers": payload.get("blockers") if isinstance(payload.get("blockers"), list) else [],
                "recommended_next_action": payload.get("recommended_next_action"),
                "status_file": file_info(status_path),
                "file": file_info(layer_dir / f"{item_id}.json"),
                "csv_file": file_info(layer_dir / f"{item_id}.csv"),
                "sqlite_file": file_info(layer_dir / f"{item_id}.sqlite"),
                "output_files": [str(item) for item in output_files],
            }
        )
    return entries


def display_code_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"[_-]+", " ", text).strip().title()


def parse_artifact_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def path_modified_datetime(path: Path) -> datetime | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)


def route_catalog(app: Any) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for route in getattr(app, "routes", []):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        visible_methods = sorted(method for method in methods if method != "HEAD")
        if not visible_methods:
            continue
        routes.append(
            {
                "path": path,
                "methods": visible_methods,
                "name": getattr(route, "name", None),
            }
        )
    return sorted(routes, key=lambda item: (item["path"], ",".join(item["methods"])))


@dataclass(frozen=True)
class WorkbenchPathService:
    root: Path
    canonical_dir: Path
    immutable_dir: Path
    registers_dir: Path
    scenario_overrides_dir: Path
    cache_dir: Path
    analysis_asset_dir: Path
    exports_dir: Path
    var_dir: Path
    static_dir: Path
    src_dir: Path
    scripts_dir: Path
    tests_dir: Path
    candidate_agreements_json: Path
    distribution_point_analysis_json: Path
    wiki_dir: Path | None = None
    reference_documents_dir: Path | None = None

    @classmethod
    def from_context(cls, ctx: Any) -> WorkbenchPathService:
        root = ctx.ROOT
        return cls(
            root=root,
            canonical_dir=ctx.CANONICAL_DIR,
            immutable_dir=ctx.IMMUTABLE_DIR,
            registers_dir=root / "registers",
            scenario_overrides_dir=ctx.SCENARIO_OVERRIDES_DIR,
            cache_dir=ctx.CACHE_DIR,
            analysis_asset_dir=ctx.ANALYSIS_ASSET_DIR,
            exports_dir=root / "exports",
            var_dir=root / "var",
            static_dir=ctx.STATIC_DIR,
            src_dir=root / "src",
            scripts_dir=root / "scripts",
            tests_dir=root / "tests",
            candidate_agreements_json=ctx.CANDIDATE_AGREEMENTS_JSON,
            distribution_point_analysis_json=ctx.DISTRIBUTION_POINT_ANALYSIS_JSON,
            wiki_dir=getattr(ctx, "WIKI_DIR", root / "wiki"),
            reference_documents_dir=getattr(ctx, "REFERENCE_DOCUMENTS_DIR", root / "documents" / "reference"),
        )

    def directories(self) -> list[dict[str, Any]]:
        wiki_dir = self.wiki_dir or (self.root / "wiki")
        reference_documents_dir = self.reference_documents_dir or (self.root / "documents" / "reference")
        entries = [
            ("canonical", self.canonical_dir, "reviewed per-agreement workspace state", "read_write"),
            ("documents_immutable", self.immutable_dir, "frozen source PDFs", "read_write_governed"),
            ("documents_reference", reference_documents_dir, "operator-provided reference PDFs used by the wiki", "read_write_governed"),
            ("registers", self.registers_dir, "audit and source registers", "read_write_governed"),
            ("wiki", wiki_dir, "document maps, reference inputs, language maps, questions, runs, and support artifacts", "read_write_governed"),
            ("scenario_overrides", self.scenario_overrides_dir, "scenario overrides and notes", "read_write_governed"),
            ("cache", self.cache_dir, "runtime page and extraction cache", "generated"),
            ("analysis", self.analysis_asset_dir, "materialised analysis assets", "generated_read_write"),
            ("exports", self.exports_dir, "operator exports", "generated_read_write"),
            ("var", self.var_dir, "runtime records and clear-record archives", "generated_read_write"),
            ("static", self.static_dir, "frontend assets", "source"),
            ("src", self.src_dir, "backend/domain source code", "source"),
            ("scripts", self.scripts_dir, "operator and portability scripts", "source"),
            ("tests", self.tests_dir, "test suite", "source"),
        ]
        return [
            {
                "id": key,
                "path": str(path),
                "exists": path.exists(),
                "purpose": purpose,
                "access": access,
            }
            for key, path, purpose, access in entries
        ]

    def datasets(self) -> list[dict[str, Any]]:
        wiki_dir = self.wiki_dir or (self.root / "wiki")
        reference_documents_dir = self.reference_documents_dir or (self.root / "documents" / "reference")
        governed_canonical_dir = self.root / "data" / "governed_canonical"
        datamarts_dir = self.root / "data" / "datamarts"
        datasets = [
            {
                "id": "intake_candidates",
                "label": "Source Intake Candidates",
                "kind": "source_stage",
                "endpoint": "/api/intake/candidates",
                "source": str(self.candidate_agreements_json),
                "file": file_info(self.candidate_agreements_json),
            },
            {
                "id": "canonical_agreements",
                "label": "Canonical Agreement Workspace Files",
                "kind": "workspace_state",
                "directory": str(self.canonical_dir),
                "file_count": file_count(self.canonical_dir, "*.yaml"),
            },
            {
                "id": "source_pdfs",
                "label": "Immutable Source PDFs",
                "kind": "source_evidence",
                "directory": str(self.immutable_dir),
                "file_count": file_count(self.immutable_dir, "*.pdf"),
            },
            {
                "id": "reference_pdfs",
                "label": "Reference PDFs",
                "kind": "reference_evidence",
                "directory": str(reference_documents_dir),
                "file_count": file_count(reference_documents_dir, "*.pdf"),
            },
            {
                "id": "uplift_rules",
                "label": "Governed Uplift Rules",
                "kind": "governed_entity_set",
                "endpoint": "/api/analysis/uplift-rules",
            },
            {
                "id": "pay_tables",
                "label": "Governed Pay Tables",
                "kind": "governed_entity_set",
                "endpoint": "/api/analysis/pay-tables",
            },
            {
                "id": "end_of_band_dollars",
                "label": "Governed End of Band Dollars",
                "kind": "governed_entity_set",
                "endpoint": "/api/analysis/end-of-band-dollars",
            },
            {
                "id": "distribution_point_analysis",
                "label": "Distribution Point Analysis",
                "kind": "report_asset_source",
                "endpoint": "/api/analysis/distribution-point-analysis",
                "file": file_info(self.distribution_point_analysis_json),
            },
            {
                "id": "distribution_point_analysis_asset",
                "label": "Distribution Point Analysis Asset Contract",
                "kind": "report_asset_manifest",
                "file": file_info(self.analysis_asset_dir / "distribution-point-analysis.asset.json"),
            },
            {
                "id": "council_master",
                "label": "Council Master Reference",
                "kind": "reference",
                "endpoint": "/api/reference/council-master",
            },
            {
                "id": "council_job_sources",
                "label": "Council Jobs Source Registry",
                "kind": "reference",
                "endpoint": "/api/reference/council-job-sources",
            },
            {
                "id": "council_geography",
                "label": "Council Geography",
                "kind": "reference",
                "endpoint": "/api/spatial/council-geography",
            },
            {
                "id": "wiki_layer",
                "label": "Wiki Layer",
                "kind": "knowledge_layer",
                "directory": str(wiki_dir),
                "manifest": file_info(wiki_dir / "wiki-manifest.json"),
                "document_map_count": file_count(wiki_dir / "document-maps", "*.json"),
                "reference_input_count": file_count(wiki_dir / "reference-inputs", "*.json"),
                "run_count": file_count(wiki_dir / "runs", "*.json"),
            },
        ]
        datasets.extend(
            [
                {
                    "id": "governed_canonical_layer",
                    "label": "Governed Canonical Layer",
                    "kind": "governed_canonical_layer",
                    "directory": str(governed_canonical_dir),
                    "summary": file_info(governed_canonical_dir / "governed_canonical_build_summary.md"),
                    "dataset_count": file_count(governed_canonical_dir, "*_status.json"),
                },
                {
                    "id": "datamart_layer",
                    "label": "Analytical Datamart Layer",
                    "kind": "datamart_layer",
                    "directory": str(datamarts_dir),
                    "summary": file_info(datamarts_dir / "datamart_build_summary.md"),
                    "mart_count": file_count(datamarts_dir, "*_status.json"),
                },
            ]
        )
        datasets.extend(
            governed_data_layer_entries(
                governed_canonical_dir,
                kind="governed_canonical_dataset",
                id_key="dataset_id",
                id_prefix="governed_canonical",
                layer_label="data/governed_canonical",
            )
        )
        datasets.extend(
            governed_data_layer_entries(
                datamarts_dir,
                kind="analytical_datamart",
                id_key="mart_id",
                id_prefix="datamart",
                layer_label="data/datamarts",
            )
        )
        return datasets


def agent_actions() -> list[dict[str, Any]]:
    return [
        {
            "id": "fetch_registry",
            "label": "Fetch Fair Work registry",
            "method": "POST",
            "endpoint": "/api/intake/fetch-registry",
            "governance": "operator_review_required",
        },
        {
            "id": "freeze_source_pdf",
            "label": "Freeze source PDF",
            "method": "POST",
            "endpoint": "/api/intake/candidates/{ae_id}/freeze",
            "governance": "source_register_event",
        },
        {
            "id": "record_intake_decision",
            "label": "Record intake decision",
            "method": "POST",
            "endpoint": "/api/intake/candidates/{ae_id}/decision",
            "governance": "decision_event",
        },
        {
            "id": "extract_pay_tables",
            "label": "Extract pay tables",
            "method": "POST",
            "endpoint": "/api/councils/{ae_id}/pay-tables/extract-range",
            "governance": "draft_until_accepted",
        },
        {
            "id": "accept_uplift_rules",
            "label": "Accept uplift rules",
            "method": "POST",
            "endpoint": "/api/councils/{ae_id}/uplift-rules/accept",
            "governance": "accepted_workspace_state",
        },
        {
            "id": "run_scenarios",
            "label": "Run uplift scenarios",
            "method": "POST",
            "endpoint": "/api/councils/{ae_id}/uplift-rules/scenarios",
            "governance": "scenario_validation",
        },
        {
            "id": "promote_governed_set",
            "label": "Promote governed set",
            "method": "POST",
            "endpoint": "/api/councils/{ae_id}/governed-set/promote",
            "governance": "promotion_event",
        },
        {
            "id": "unwind_governed_set",
            "label": "Unwind governed set",
            "method": "POST",
            "endpoint": "/api/councils/{ae_id}/governed-set/unwind",
            "governance": "unwind_event",
        },
        {
            "id": "rebuild_analysis",
            "label": "Rebuild analysis dataset",
            "method": "POST",
            "endpoint": "/api/analysis/{data_set}/rebuild",
            "governance": "derived_asset_refresh",
        },
    ]


SAFE_WIKI_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")

CLAUSE_LIBRARY_SCHEMA_VERSION = "wiki.clause_library.v1"
TAG_REGISTRY_SCHEMA_VERSION = "wiki.tag_registry.v1"
TAGGED_EVIDENCE_SCHEMA_VERSION = "wiki.tagged_evidence.v1"
TAGGABLE_DIMENSIONS_SCHEMA_VERSION = "wiki.taggable_dimensions.v1"
TAG_FAMILY_LABELS = {
    "clause_function": "Clause Function",
    "context_scope": "Context Scope",
    "cohort_scope": "Cohort Scope",
}
TAGGABLE_DIMENSION_LABELS = {
    "source_type": "Source Type",
    "source_kind": "Source Kind",
    "record_type": "Record Type",
    "page_role": "Page Role",
    "source_container_type": "Source Container Type",
    "clause_context_relevance": "Clause/Context Relevance",
    "text_quality": "Text Quality",
    "review_state": "Review State",
}
TAG_DISCOVERY_BACKLOG_CODES = {
    "untagged_heading",
    "untagged_reference_heading",
    "tagged_page_without_heading",
    "tagged_reference_page_without_heading",
}
CLAUSE_LIBRARY_TREE = [
    {
        "id": "pay-classification",
        "label": "Pay, Classification and Progression",
        "description": "Classification structures, minimum rates, progression, annualised salaries and pay architecture.",
        "children": [
            {
                "id": "classification-structure",
                "label": "Classification Structure",
                "description": "Band, level, increment and position-description architecture.",
                "tags": ["classification_context"],
                "terms": ["classification_structure"],
            },
            {
                "id": "band-responsibilities-descriptors",
                "label": "Band Responsibilities and Descriptors",
                "description": "Band-specific accountability, judgement, skills, duties, supervision and qualification descriptors.",
                "tags": ["band_responsibility_context"],
                "terms": ["band_responsibilities", "position_descriptions"],
            },
            {
                "id": "pay-rates-and-salary",
                "label": "Rates, Salary and Annualised Pay",
                "description": "Rates of pay, salary packaging, annualised salary and pay-table signals.",
                "tags": ["implementation_context", "agreement_coverage"],
                "terms": ["pay_increase"],
            },
            {
                "id": "superannuation",
                "label": "Superannuation",
                "description": "Employer superannuation contributions and related benefit language.",
                "tags": ["superannuation"],
                "terms": ["superannuation"],
            },
        ],
    },
    {
        "id": "hours-work-patterns",
        "label": "Hours and Work Patterns",
        "description": "Ordinary hours, rosters, overtime, penalties, on-call, standby and availability arrangements.",
        "children": [
            {
                "id": "ordinary-hours",
                "label": "Ordinary Hours",
                "description": "Ordinary hours, spans of hours and rostered-hour structures.",
                "tags": ["hours"],
                "terms": ["ordinary_hours"],
            },
            {
                "id": "overtime-penalties",
                "label": "Overtime and Penalties",
                "description": "Overtime triggers, penalty rates and time-and-a-half/double-time language.",
                "tags": ["overtime_penalties"],
                "terms": ["overtime_penalties"],
            },
            {
                "id": "on-call-standby",
                "label": "On-Call, Standby and Availability",
                "description": "On-call, standby duty, availability duty and related operational payments.",
                "tags": ["on_call_standby"],
                "terms": ["on_call_standby"],
            },
            {
                "id": "rostering-shiftwork",
                "label": "Rostering and Shiftwork",
                "description": "Roster change, shift work and shiftworker condition signals.",
                "tags": ["rostering", "employment_type_context"],
                "terms": ["rostering"],
            },
        ],
    },
    {
        "id": "allowances-expenses",
        "label": "Allowances and Expenses",
        "description": "Allowances, reimbursements, accident make-up pay and expense-related entitlements.",
        "children": [
            {
                "id": "allowances",
                "label": "Allowances",
                "description": "Tool, travel, first-aid and other allowance clauses.",
                "tags": ["allowances"],
                "terms": ["allowances"],
            },
            {
                "id": "accident-makeup-pay",
                "label": "Accident Make-Up Pay",
                "description": "Accident pay and workers compensation top-up arrangements.",
                "tags": ["accident_makeup_pay"],
                "terms": ["accident_makeup_pay"],
            },
        ],
    },
    {
        "id": "leave-holidays",
        "label": "Leave and Holidays",
        "description": "Annual, personal, carer's, parental, family violence, long service leave and public holidays.",
        "children": [
            {
                "id": "annual-leave-loading",
                "label": "Annual Leave and Loading",
                "description": "Annual leave, loading and related cash-out or accrual language.",
                "tags": ["leave_annual"],
                "terms": ["annual_leave"],
            },
            {
                "id": "personal-carers-sick-leave",
                "label": "Personal, Carer's and Sick Leave",
                "description": "Personal leave, carer's leave and sick leave conditions.",
                "tags": ["leave_personal_carers"],
                "terms": ["personal_carers_leave"],
            },
            {
                "id": "parental-family-leave",
                "label": "Parental and Family Leave",
                "description": "Parental, partner and family leave arrangements.",
                "tags": ["leave_parental_family"],
                "terms": ["parental_family_leave"],
            },
            {
                "id": "long-service-leave",
                "label": "Long Service Leave",
                "description": "Long service leave and LSL cross-references.",
                "tags": ["leave_long_service"],
                "terms": ["long_service_leave"],
            },
            {
                "id": "family-violence-leave",
                "label": "Family and Domestic Violence Leave",
                "description": "Family violence and domestic violence leave protections.",
                "tags": ["family_violence"],
                "terms": ["family_violence"],
            },
            {
                "id": "public-holidays",
                "label": "Public Holidays",
                "description": "Public holiday entitlements, substitution and penalty interactions.",
                "tags": ["public_holidays"],
                "terms": ["public_holidays"],
            },
        ],
    },
    {
        "id": "employment-security-change",
        "label": "Employment Security and Change",
        "description": "Redundancy, redeployment, termination, consultation, dispute resolution and flexibility.",
        "children": [
            {
                "id": "redundancy-redeployment",
                "label": "Redundancy and Redeployment",
                "description": "Redundancy, redeployment, severance and change-management protections.",
                "tags": ["redundancy_redeployment"],
                "terms": ["redundancy_redeployment"],
            },
            {
                "id": "termination-notice",
                "label": "Termination and Notice",
                "description": "Notice of termination, abandonment and dismissal language.",
                "tags": ["termination"],
                "terms": ["termination_notice"],
            },
            {
                "id": "consultation-change",
                "label": "Consultation and Change",
                "description": "Major change, workplace change and consultation obligations.",
                "tags": ["consultation"],
                "terms": ["consultation"],
            },
            {
                "id": "dispute-resolution",
                "label": "Dispute Resolution",
                "description": "Dispute, grievance and Fair Work escalation pathways.",
                "tags": ["dispute_resolution"],
                "terms": ["dispute_resolution"],
            },
            {
                "id": "flexibility",
                "label": "Flexibility",
                "description": "Individual flexibility and flexible work arrangements.",
                "tags": ["flexibility", "remote_work"],
                "terms": ["remote_work"],
            },
        ],
    },
    {
        "id": "development-representation",
        "label": "Development, Representation and Workload",
        "description": "Training, professional development, union rights, workload and higher duties signals.",
        "children": [
            {
                "id": "training-development",
                "label": "Training and Professional Development",
                "description": "Training, study assistance and staff development schemes.",
                "tags": ["training_development"],
                "terms": ["training_development"],
            },
            {
                "id": "higher-duties",
                "label": "Higher Duties",
                "description": "Higher duties, acting allowance and relieving allowance arrangements.",
                "tags": ["higher_duties"],
                "terms": ["higher_duties"],
            },
            {
                "id": "union-rights",
                "label": "Union Rights",
                "description": "Union, delegate and right-of-entry provisions.",
                "tags": ["union_rights"],
                "terms": ["union_rights"],
            },
            {
                "id": "workload",
                "label": "Workload",
                "description": "Workload, staffing and work-intensity language.",
                "tags": ["workload"],
                "terms": ["workload"],
            },
        ],
    },
    {
        "id": "scope-controls",
        "label": "Scope Controls and Specialist Lanes",
        "description": "Coverage, exclusions, specialist schedules and service-area context that should govern filtering.",
        "children": [
            {
                "id": "coverage-all-employees",
                "label": "Coverage and All-Employee Context",
                "description": "Coverage, parties bound and all-employee signals.",
                "tags": ["agreement_coverage", "all_employee_context"],
                "terms": [],
            },
            {
                "id": "specialist-schedules",
                "label": "Specialist Schedules",
                "description": "Nurses, early years, aquatic, senior officer and other specialist-lane signals.",
                "tags": ["specialist_occupation_context", "schedule_context"],
                "terms": [],
            },
            {
                "id": "external-exclusions",
                "label": "External Awards and Exclusions",
                "description": "Excluded occupations, external award dependencies and out-of-scope clauses.",
                "tags": ["external_or_excluded_context"],
                "terms": [],
            },
            {
                "id": "service-area-context",
                "label": "Service-Area Context",
                "description": "Library, waste, parking, recreation and other service-area language used as a filter.",
                "tags": ["service_area_context"],
                "terms": [],
            },
        ],
    },
]


def _normalise_wiki_ref(source_ref: Any) -> tuple[str, str, int | None]:
    if not isinstance(source_ref, dict):
        return ("unknown", "", None)
    source_type = "reference" if source_ref.get("source_id") else "agreement"
    source_id = str(source_ref.get("source_id") or source_ref.get("agreement_id") or "").lower()
    page = source_ref.get("page")
    try:
        page_value = int(page) if page is not None else None
    except (TypeError, ValueError):
        page_value = None
    return (source_type, source_id, page_value)


def safe_wiki_token(value: str, *, label: str) -> str:
    token = str(value or "").strip()
    if not token or Path(token).name != token or not SAFE_WIKI_TOKEN_PATTERN.match(token):
        raise ValueError(f"Invalid wiki {label}: {value}")
    return token


def wikiAsList(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def wiki_evidence_agreement_id(row: dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return ""
    source_ref = row.get("source_ref") if isinstance(row.get("source_ref"), dict) else {}
    source_evidence = row.get("source_evidence") if isinstance(row.get("source_evidence"), dict) else {}
    nested_ref = source_evidence.get("source_ref") if isinstance(source_evidence.get("source_ref"), dict) else {}
    for candidate in (
        row.get("agreement_id"),
        row.get("ae_id"),
        source_ref.get("agreement_id"),
        source_ref.get("ae_id"),
        source_evidence.get("agreement_id"),
        source_evidence.get("ae_id"),
        nested_ref.get("agreement_id"),
    ):
        if str(candidate or "").strip():
            return str(candidate).strip().lower()
    return ""


def wiki_source_evidence_projection(source_row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(source_row, dict):
        return {}
    source_evidence = source_row.get("source_evidence") if isinstance(source_row.get("source_evidence"), dict) else {}
    agreement_id = wiki_evidence_agreement_id(source_row)
    return {
        "agreement_id": agreement_id,
        "agreement_name": source_row.get("agreement_name") or source_evidence.get("agreement_name"),
        "support_status": source_row.get("support_status") or source_evidence.get("support_status"),
        "page_count": source_row.get("page_count") or source_evidence.get("page_count"),
        "candidate_page_count": source_row.get("candidate_page_count") or source_evidence.get("candidate_page_count"),
        "source_clause_page_count": source_row.get("source_clause_page_count") or source_evidence.get("source_clause_page_count"),
        "out_of_scope_candidate_page_count": source_row.get("out_of_scope_candidate_page_count")
        or source_evidence.get("out_of_scope_candidate_page_count"),
        "observed_subclasses": wikiAsList(source_row.get("observed_subclasses") or source_evidence.get("observed_subclasses")),
        "source_excerpts": wikiAsList(source_row.get("source_excerpts") or source_evidence.get("source_excerpts")),
        "candidate_pages": wikiAsList(source_row.get("candidate_pages") or source_evidence.get("candidate_pages")),
    }


def _wiki_record_has_any_tag(record: dict[str, Any], tags: set[str]) -> bool:
    if not tags:
        return False
    tag_payload = record.get("tags") if isinstance(record.get("tags"), dict) else {}
    entries = [
        *wikiAsList(tag_payload.get("clause_function")),
        *wikiAsList(tag_payload.get("context_scope")),
        *wikiAsList(tag_payload.get("cohort_scope")),
    ]
    return any(isinstance(entry, dict) and entry.get("tag") in tags for entry in entries)


def _wiki_record_tag_entries(record: dict[str, Any]) -> list[dict[str, Any]]:
    tag_payload = record.get("tags") if isinstance(record.get("tags"), dict) else {}
    entries: list[dict[str, Any]] = []
    for family, raw_items in tag_payload.items():
        family_id = str(family or "").strip()
        if not family_id:
            continue
        for raw_item in wikiAsList(raw_items):
            if isinstance(raw_item, dict):
                tag = str(raw_item.get("tag") or "").strip()
                if not tag:
                    continue
                entries.append(
                    {
                        "family": family_id,
                        "tag": tag,
                        "score": raw_item.get("score"),
                        "evidence_terms": wikiAsList(raw_item.get("evidence_terms")),
                    }
                )
            else:
                tag = str(raw_item or "").strip()
                if tag:
                    entries.append({"family": family_id, "tag": tag})
    return entries


def _wiki_record_has_tag(record: dict[str, Any], *, tag: str = "", family: str = "") -> bool:
    entries = _wiki_record_tag_entries(record)
    if tag and not any(entry["tag"] == tag for entry in entries):
        return False
    if family and not any(entry["family"] == family for entry in entries):
        return False
    return bool(entries)


def _wiki_record_relevance(record: dict[str, Any]) -> str:
    return str(record.get("clause_context_relevance") or record.get("standard_band_relevance") or "").strip()


def _normalise_wiki_filter(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"", "all", "none"} else text


@dataclass(frozen=True)
class WikiLayerService:
    paths: WorkbenchPathService

    @property
    def wiki_root(self) -> Path:
        return self.paths.wiki_dir or (self.paths.root / "wiki")

    def directory(self, key: str) -> Path:
        directories = {
            "document_maps": self.wiki_root / "document-maps",
            "reference_inputs": self.wiki_root / "reference-inputs",
            "language_maps": self.wiki_root / "language-maps",
            "questions": self.wiki_root / "questions",
            "learning_backlog": self.wiki_root / "learning-backlog",
            "runs": self.wiki_root / "runs",
            "artifacts": self.wiki_root / "artifacts",
            "pages": self.wiki_root / "pages",
            "patterns": self.wiki_root / "patterns",
            "issues": self.wiki_root / "issues",
        }
        return directories[key]

    def manifest_path(self) -> Path:
        return self.wiki_root / "wiki-manifest.json"

    def manifest(self) -> dict[str, Any] | None:
        return read_json_file(self.manifest_path())

    def _json_files(self, key: str) -> list[Path]:
        directory = self.directory(key)
        if not directory.exists():
            return []
        return sorted(
            (path for path in directory.glob("*.json") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def _latest_artifact_file(self, artifact_dir: str, pattern: str, fallback_name: str) -> Path:
        directory = self.directory("artifacts") / artifact_dir
        if directory.exists():
            files = sorted(
                (path for path in directory.glob(pattern) if path.is_file()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if files:
                return files[0]
        return directory / fallback_name

    def _locator_answer_builder_coverage(self, payload: dict[str, Any]) -> dict[str, Any]:
        feature_cards = 0
        with_contract = 0
        ready = 0
        for profile in wikiAsList(payload.get("profiles")):
            if not isinstance(profile, dict):
                continue
            for row in wikiAsList(profile.get("target_rows")):
                if not isinstance(row, dict):
                    continue
                for feature in wikiAsList(row.get("feature_cards")):
                    if not isinstance(feature, dict):
                        continue
                    feature_cards += 1
                    if isinstance(feature.get("answer_builder"), dict):
                        with_contract += 1
                    if feature.get("answer_builder_status") == "ready_for_deterministic_promotion_gate":
                        ready += 1
        return {
            "feature_cards": feature_cards,
            "with_answer_builder_contract": with_contract,
            "ready_for_deterministic_promotion_gate": ready,
            "coverage_ratio": round(with_contract / feature_cards, 4) if feature_cards else None,
        }

    def _artifact_generated_at(self, payload: dict[str, Any], path: Path) -> datetime | None:
        return parse_artifact_datetime(payload.get("generated_at")) or path_modified_datetime(path)

    def _script_freshness_reason(
        self,
        *,
        artifact_generated_at: datetime | None,
        script_name: str,
        reason: str,
    ) -> tuple[list[str], dict[str, Any]]:
        script_path = self.paths.scripts_dir / script_name
        script_modified = path_modified_datetime(script_path)
        code = {
            "path": str(script_path),
            "last_modified": script_modified.isoformat() if script_modified else None,
        }
        # Code mtimes are displayed for operator context, but they are not a
        # semantic staleness gate. Small CLI/progress edits should not invalidate
        # a freshly rebuilt evidence artifact.
        return [], code

    def _clause_pipeline_freshness(
        self,
        locator_payload: dict[str, Any],
        locator_path: Path,
        cards_payload: dict[str, Any],
        cards_path: Path,
        repair_payload: dict[str, Any],
        repair_path: Path,
    ) -> dict[str, Any]:
        locator_generated = self._artifact_generated_at(locator_payload, locator_path)
        cards_generated = self._artifact_generated_at(cards_payload, cards_path)
        repair_generated = self._artifact_generated_at(repair_payload, repair_path)
        locator_id = locator_payload.get("artifact_id")
        cards_id = cards_payload.get("artifact_id")
        coverage = self._locator_answer_builder_coverage(locator_payload)

        locator_reasons: list[str] = []
        if not locator_path.exists() or not locator_payload:
            locator_reasons.append("locator_artifact_missing")
        if locator_path.exists() and not locator_payload.get("generated_at"):
            locator_reasons.append("generated_at_missing")
        script_reasons, locator_code = self._script_freshness_reason(
            artifact_generated_at=locator_generated,
            script_name="build_entitlement_locator_experiment.py",
            reason="artifact_predates_locator_builder_code",
        )
        locator_reasons.extend(script_reasons)
        if coverage["feature_cards"] and not coverage["with_answer_builder_contract"]:
            locator_reasons.append("answer_builder_contracts_missing")
        elif coverage["feature_cards"] and coverage["with_answer_builder_contract"] < coverage["feature_cards"]:
            locator_reasons.append("answer_builder_contracts_partial")

        cards_source = cards_payload.get("source_artifact") if isinstance(cards_payload.get("source_artifact"), dict) else {}
        cards_reasons: list[str] = []
        if not cards_path.exists() or not cards_payload:
            cards_reasons.append("entitlement_cards_artifact_missing")
        if cards_path.exists() and not cards_payload.get("generated_at"):
            cards_reasons.append("generated_at_missing")
        if locator_id and cards_payload and cards_source.get("locator_artifact_id") != locator_id:
            cards_reasons.append("locator_source_artifact_mismatch")
        if locator_payload.get("generated_at") and cards_source and cards_source.get("generated_at") != locator_payload.get("generated_at"):
            cards_reasons.append("locator_source_timestamp_mismatch")
        if locator_generated and cards_generated and cards_generated < locator_generated:
            cards_reasons.append("artifact_predates_locator_artifact")
        script_reasons, cards_code = self._script_freshness_reason(
            artifact_generated_at=cards_generated,
            script_name="build_entitlement_cards.py",
            reason="artifact_predates_entitlement_card_builder_code",
        )
        cards_reasons.extend(script_reasons)
        if locator_reasons:
            cards_reasons.append("upstream_locator_needs_refresh")

        repair_source = repair_payload.get("source_artifact") if isinstance(repair_payload.get("source_artifact"), dict) else {}
        repair_reasons: list[str] = []
        if not repair_path.exists() or not repair_payload:
            repair_reasons.append("repair_loop_artifact_missing")
        if repair_path.exists() and not repair_payload.get("generated_at"):
            repair_reasons.append("generated_at_missing")
        if locator_id and repair_payload and repair_source.get("locator_artifact_id") != locator_id:
            repair_reasons.append("locator_source_artifact_mismatch")
        if cards_id and repair_payload and repair_source.get("entitlement_cards_artifact_id") != cards_id:
            repair_reasons.append("entitlement_cards_source_artifact_mismatch")
        if locator_generated and repair_generated and repair_generated < locator_generated:
            repair_reasons.append("artifact_predates_locator_artifact")
        if cards_generated and repair_generated and repair_generated < cards_generated:
            repair_reasons.append("artifact_predates_entitlement_cards")
        script_reasons, repair_code = self._script_freshness_reason(
            artifact_generated_at=repair_generated,
            script_name="build_entitlement_card_repair_loop.py",
            reason="artifact_predates_repair_loop_builder_code",
        )
        repair_reasons.extend(script_reasons)
        if locator_reasons:
            repair_reasons.append("upstream_locator_needs_refresh")
        if cards_reasons:
            repair_reasons.append("upstream_entitlement_cards_need_refresh")

        def stage(
            *,
            stage_id: str,
            label: str,
            path: Path,
            payload: dict[str, Any],
            generated_at: datetime | None,
            reasons: list[str],
            code: dict[str, Any],
            refresh_command: str,
            extra: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            missing = any(
                reason in {
                    "locator_artifact_missing",
                    "entitlement_cards_artifact_missing",
                    "repair_loop_artifact_missing",
                }
                for reason in reasons
            )
            status = "missing" if missing else ("stale" if reasons else "current")
            return {
                "stage": stage_id,
                "label": label,
                "status": status,
                "artifact_id": payload.get("artifact_id"),
                "generated_at": payload.get("generated_at"),
                "effective_generated_at": generated_at.isoformat() if generated_at else None,
                "source": file_info(path),
                "code": code,
                "reasons": sorted(set(reasons)),
                "refresh_command": refresh_command,
                **(extra or {}),
            }

        checks = [
            stage(
                stage_id="entitlement_locator",
                label="Locator and Feature Cards",
                path=locator_path,
                payload=locator_payload,
                generated_at=locator_generated,
                reasons=locator_reasons,
                code=locator_code,
                refresh_command=r".\.venv-win\Scripts\python.exe scripts\build_entitlement_locator_experiment.py --all-cached --offset 0",
                extra={"answer_builder_coverage": coverage},
            ),
            stage(
                stage_id="entitlement_cards",
                label="Entitlement Cards",
                path=cards_path,
                payload=cards_payload,
                generated_at=cards_generated,
                reasons=cards_reasons,
                code=cards_code,
                refresh_command=(
                    rf".\.venv-win\Scripts\python.exe scripts\build_entitlement_cards.py "
                    rf"--input ""{locator_path}"""
                ),
            ),
            stage(
                stage_id="entitlement_card_repair_loop",
                label="Blocked Value Repair Loop",
                path=repair_path,
                payload=repair_payload,
                generated_at=repair_generated,
                reasons=repair_reasons,
                code=repair_code,
                refresh_command=(
                    rf".\.venv-win\Scripts\python.exe scripts\build_entitlement_card_repair_loop.py "
                    rf"--locator-input ""{locator_path}"" --cards-input ""{cards_path}"""
                ),
            ),
        ]
        stale = [check for check in checks if check["status"] != "current"]
        return {
            "schema_version": "wiki.clause_pipeline_freshness.v1",
            "status": "current" if not stale else "stale",
            "stale_stages": len(stale),
            "run_order": [check["stage"] for check in checks],
            "checks": checks,
            "blocking_reasons": sorted({
                reason
                for check in checks
                for reason in wikiAsList(check.get("reasons"))
            }),
        }

    def _read_required_json(self, path: Path, *, label: str) -> dict[str, Any]:
        payload = read_json_file(path)
        if payload is None:
            raise FileNotFoundError(f"Wiki {label} not found: {path.name}")
        return payload

    def latest_run_id(self) -> str | None:
        manifest = self.manifest() or {}
        run_id = manifest.get("latest_run_id")
        if isinstance(run_id, str) and run_id:
            return run_id
        run_files = self._json_files("runs")
        if not run_files:
            return None
        return run_files[0].stem

    def status(self) -> dict[str, Any]:
        manifest = self.manifest() or {}
        return {
            "service": "WikiLayerService",
            "root": str(self.wiki_root),
            "manifest": file_info(self.manifest_path()),
            "latest_run_id": self.latest_run_id(),
            "document_map_count": file_count(self.directory("document_maps"), "*.json"),
            "reference_input_count": file_count(self.directory("reference_inputs"), "*.json"),
            "run_count": file_count(self.directory("runs"), "*.json"),
            "question_file_count": file_count(self.directory("questions"), "*.json"),
            "learning_backlog_file_count": file_count(self.directory("learning_backlog"), "*.json"),
            "language_map_count": file_count(self.directory("language_maps"), "*.json"),
            "artifact_count": len(self.artifacts()["artifacts"]),
            "scope_focus": manifest.get("scope_focus"),
            "schema_version": manifest.get("schema_version"),
        }

    def catalog(self) -> dict[str, Any]:
        return {
            "service": "WikiLayerService",
            "status": self.status(),
            "endpoints": [
                {"id": "wiki_status", "method": "GET", "endpoint": "/api/wiki/status"},
                {"id": "wiki_runs", "method": "GET", "endpoint": "/api/wiki/runs"},
                {"id": "wiki_latest_run", "method": "GET", "endpoint": "/api/wiki/runs/latest"},
                {"id": "wiki_run", "method": "GET", "endpoint": "/api/wiki/runs/{run_id}"},
                {"id": "wiki_document_maps", "method": "GET", "endpoint": "/api/wiki/document-maps"},
                {"id": "wiki_document_map", "method": "GET", "endpoint": "/api/wiki/document-maps/{ae_id}"},
                {"id": "wiki_reference_inputs", "method": "GET", "endpoint": "/api/wiki/reference-inputs"},
                {"id": "wiki_reference_input", "method": "GET", "endpoint": "/api/wiki/reference-inputs/{source_id}"},
                {"id": "wiki_clause_library", "method": "GET", "endpoint": "/api/wiki/clause-library"},
                {"id": "wiki_tag_registry", "method": "GET", "endpoint": "/api/wiki/tag-registry"},
                {"id": "wiki_tagged_evidence", "method": "GET", "endpoint": "/api/wiki/tagged-evidence"},
                {"id": "wiki_questions", "method": "GET", "endpoint": "/api/wiki/questions"},
                {"id": "wiki_learning_backlog", "method": "GET", "endpoint": "/api/wiki/learning-backlog"},
                {"id": "wiki_language_map", "method": "GET", "endpoint": "/api/wiki/language-map"},
                {"id": "wiki_artifacts", "method": "GET", "endpoint": "/api/wiki/artifacts"},
                {"id": "wiki_clause_cards", "method": "GET", "endpoint": "/api/wiki/clause-cards"},
            ],
            "document_maps": self.document_maps()["document_maps"],
            "reference_inputs": self.reference_inputs()["reference_inputs"],
            "runs": self.runs(limit=5)["runs"],
        }

    def actions(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "read_wiki_status",
                "label": "Read wiki layer status",
                "method": "GET",
                "endpoint": "/api/wiki/status",
                "governance": "read_only",
            },
            {
                "id": "review_wiki_questions",
                "label": "Review wiki direction questions",
                "method": "GET",
                "endpoint": "/api/wiki/questions",
                "governance": "operator_review_surface",
            },
            {
                "id": "inspect_document_map",
                "label": "Inspect agreement document map",
                "method": "GET",
                "endpoint": "/api/wiki/document-maps/{ae_id}",
                "governance": "read_only",
            },
            {
                "id": "inspect_reference_input",
                "label": "Inspect reference input map",
                "method": "GET",
                "endpoint": "/api/wiki/reference-inputs/{source_id}",
                "governance": "read_only",
            },
        ]

    def io(self) -> dict[str, Any]:
        return {
            "root": str(self.wiki_root),
            "manifest": file_info(self.manifest_path()),
            "directories": {
                key: {
                    "path": str(self.directory(key)),
                    "exists": self.directory(key).exists(),
                }
                for key in [
                    "document_maps",
                    "reference_inputs",
                    "language_maps",
                    "questions",
                    "learning_backlog",
                    "runs",
                    "artifacts",
                    "pages",
                    "patterns",
                    "issues",
                ]
            },
            "write_policy": "governed_wiki_records_only",
        }

    def runs(self, *, limit: int | None = None) -> dict[str, Any]:
        files = self._json_files("runs")
        if limit is not None:
            files = files[: max(0, limit)]
        runs: list[dict[str, Any]] = []
        for path in files:
            payload = read_json_file(path) or {}
            runs.append({
                "run_id": payload.get("run_id") or path.stem,
                "generated_at": payload.get("generated_at"),
                "scope_focus": payload.get("scope_focus"),
                "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
                "file": file_info(path),
            })
        return {
            "runs": runs,
            "latest_run_id": self.latest_run_id(),
            "count": len(self._json_files("runs")),
        }

    def latest_run(self) -> dict[str, Any]:
        run_id = self.latest_run_id()
        if not run_id:
            raise FileNotFoundError("Wiki latest run not found")
        return self.run(run_id)

    def run(self, run_id: str) -> dict[str, Any]:
        token = safe_wiki_token(run_id, label="run id")
        return self._read_required_json(self.directory("runs") / f"{token}.json", label="run")

    def document_maps(self) -> dict[str, Any]:
        maps: list[dict[str, Any]] = []
        for path in sorted(self._json_files("document_maps"), key=lambda item: item.stem):
            payload = read_json_file(path) or {}
            maps.append({
                "agreement_id": payload.get("agreement_id") or path.stem,
                "agreement_name": payload.get("agreement_name"),
                "generated_at": payload.get("generated_at"),
                "review_state": payload.get("review_state"),
                "scope_focus": payload.get("scope_focus"),
                "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
                "file": file_info(path),
            })
        return {
            "document_maps": maps,
            "count": len(maps),
        }

    def document_map(self, ae_id: str) -> dict[str, Any]:
        token = safe_wiki_token(ae_id.lower().removesuffix(".pdf"), label="agreement id")
        return self._read_required_json(self.directory("document_maps") / f"{token}.json", label="document map")

    def _source_records_for_tagging(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(self._json_files("document_maps"), key=lambda item: item.stem):
            payload = read_json_file(path) or {}
            source_id = str(payload.get("agreement_id") or path.stem).lower()
            records.append(
                {
                    "source_type": "agreement",
                    "source_id": source_id,
                    "source_name": payload.get("agreement_name") or source_id,
                    "source_kind": "enterprise_agreement",
                    "payload": payload,
                }
            )
        for path in sorted(self._json_files("reference_inputs"), key=lambda item: item.stem):
            payload = read_json_file(path) or {}
            source_id = str(payload.get("source_id") or path.stem).lower()
            records.append(
                {
                    "source_type": "reference",
                    "source_id": source_id,
                    "source_name": payload.get("source_name") or source_id,
                    "source_kind": payload.get("source_kind") or "reference_material",
                    "payload": payload,
                }
            )
        return records

    def _tagged_evidence_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for source in self._source_records_for_tagging():
            payload = source["payload"]
            review_state = str(payload.get("review_state") or "proposed")
            source_ref_key = "source_id" if source["source_type"] == "reference" else "agreement_id"
            for page in wikiAsList(payload.get("pages")):
                if not isinstance(page, dict) or not _wiki_record_tag_entries(page):
                    continue
                page_number = page.get("page")
                rows.append(
                    {
                        "row_id": f"{source['source_type']}:{source['source_id']}:page:{page_number}",
                        "record_type": "page",
                        "source_type": source["source_type"],
                        "source_id": source["source_id"],
                        "source_name": source["source_name"],
                        "source_kind": source["source_kind"],
                        "page": page_number,
                        "source_ref": {source_ref_key: source["source_id"], "page": page_number},
                        "title": f"Page {page_number}" if page_number is not None else "Page",
                        "page_role": page.get("page_role"),
                        "source_container_type": page.get("source_container_type"),
                        "text_quality": page.get("text_quality"),
                        "char_count": page.get("char_count"),
                        "heading_count": page.get("heading_count"),
                        "clause_context_relevance": _wiki_record_relevance(page),
                        "review_state": review_state,
                        "tags": page.get("tags") if isinstance(page.get("tags"), dict) else {},
                        "tag_entries": _wiki_record_tag_entries(page),
                        "evidence_excerpt": "",
                    }
                )
            for section in wikiAsList(payload.get("sections")):
                if not isinstance(section, dict) or not _wiki_record_tag_entries(section):
                    continue
                source_ref = section.get("source_ref") if isinstance(section.get("source_ref"), dict) else {}
                page_number = source_ref.get("page")
                rows.append(
                    {
                        "row_id": section.get("section_id")
                        or f"{source['source_type']}:{source['source_id']}:section:{page_number}:{len(rows)}",
                        "record_type": "section",
                        "source_type": source["source_type"],
                        "source_id": source["source_id"],
                        "source_name": source["source_name"],
                        "source_kind": source["source_kind"],
                        "page": page_number,
                        "line_index": source_ref.get("line_index"),
                        "source_ref": source_ref or {source_ref_key: source["source_id"], "page": page_number},
                        "title": section.get("title") or section.get("heading") or "Detected Section",
                        "heading": section.get("heading"),
                        "page_role": section.get("page_role"),
                        "source_container_type": section.get("source_container_type"),
                        "text_quality": section.get("text_quality"),
                        "clause_context_relevance": _wiki_record_relevance(section),
                        "review_state": section.get("review_state") or review_state,
                        "tags": section.get("tags") if isinstance(section.get("tags"), dict) else {},
                        "tag_entries": _wiki_record_tag_entries(section),
                        "evidence_excerpt": section.get("evidence_excerpt") or "",
                    }
                )
        return sorted(
            rows,
            key=lambda item: (
                str(item.get("source_type") or ""),
                str(item.get("source_name") or item.get("source_id") or ""),
                int(item.get("page") or 0),
                str(item.get("record_type") or ""),
                str(item.get("title") or ""),
            ),
        )

    @staticmethod
    def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return min(max(parsed, minimum), maximum)

    def tag_registry(self) -> dict[str, Any]:
        rows = self._tagged_evidence_rows()
        tag_stats: dict[tuple[str, str], dict[str, Any]] = {}
        dimension_counts: dict[str, Counter[str]] = {
            key: Counter()
            for key in TAGGABLE_DIMENSION_LABELS
        }
        for row in rows:
            source_key = (row["source_type"], row["source_id"])
            for entry in wikiAsList(row.get("tag_entries")):
                family = str(entry.get("family") or "").strip()
                tag = str(entry.get("tag") or "").strip()
                if not family or not tag:
                    continue
                stat = tag_stats.setdefault(
                    (family, tag),
                    {
                        "family": family,
                        "tag": tag,
                        "label": display_code_label(tag),
                        "record_count": 0,
                        "page_records": 0,
                        "section_records": 0,
                        "source_refs": set(),
                        "source_count": 0,
                        "score": 0,
                        "evidence_terms": Counter(),
                        "review_state": "observed",
                    },
                )
                stat["record_count"] += 1
                if row.get("record_type") == "page":
                    stat["page_records"] += 1
                if row.get("record_type") == "section":
                    stat["section_records"] += 1
                stat["source_refs"].add(source_key)
                try:
                    stat["score"] += int(entry.get("score") or 0)
                except (TypeError, ValueError):
                    pass
                stat["evidence_terms"].update(str(term) for term in wikiAsList(entry.get("evidence_terms")) if str(term).strip())
            for dimension in dimension_counts:
                value = str(row.get(dimension) or "").strip()
                if value:
                    dimension_counts[dimension][value] += 1
        families: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for stat in tag_stats.values():
            source_refs = stat.pop("source_refs")
            stat["source_count"] = len(source_refs)
            stat["evidence_terms"] = [
                {"term": term, "count": count}
                for term, count in stat["evidence_terms"].most_common(8)
            ]
            families[stat["family"]].append(stat)
        family_rows = []
        for family, tags in sorted(families.items(), key=lambda item: item[0]):
            ordered_tags = sorted(tags, key=lambda item: (-int(item["record_count"]), str(item["tag"])))
            family_rows.append(
                {
                    "family": family,
                    "label": TAG_FAMILY_LABELS.get(family, display_code_label(family)),
                    "tag_count": len(ordered_tags),
                    "record_count": sum(int(item["record_count"]) for item in ordered_tags),
                    "tags": ordered_tags,
                }
            )
        dimensions = []
        for dimension, counter in dimension_counts.items():
            dimensions.append(
                {
                    "dimension": dimension,
                    "label": TAGGABLE_DIMENSION_LABELS.get(dimension, display_code_label(dimension)),
                    "value_count": len(counter),
                    "values": [
                        {"value": value, "label": display_code_label(value), "record_count": count}
                        for value, count in counter.most_common(40)
                    ],
                }
            )
        proposals = self._tag_discovery_proposals()
        return {
            "schema_version": TAG_REGISTRY_SCHEMA_VERSION,
            "scope_role": "source_knowledge_tagging",
            "governance_note": "Tags describe source structure, topic and routing context. They are not benchmark or entitlement findings.",
            "summary": {
                "source_records": len(self._source_records_for_tagging()),
                "tagged_records": len(rows),
                "tag_families": len(family_rows),
                "tags": sum(len(item["tags"]) for item in family_rows),
                "tag_assignments": sum(int(item["record_count"]) for item in tag_stats.values()),
                "taggable_dimensions": len(dimensions),
                "discovery_proposals": len(proposals),
            },
            "families": family_rows,
            "taggable_dimensions": {
                "schema_version": TAGGABLE_DIMENSIONS_SCHEMA_VERSION,
                "dimensions": dimensions,
            },
            "discovery_proposals": proposals,
        }

    def _tag_discovery_proposals(self) -> list[dict[str, Any]]:
        if not self.latest_run_id():
            return []
        try:
            backlog_items = wikiAsList(self.learning_backlog().get("items"))
        except FileNotFoundError:
            backlog_items = []
        proposals: list[dict[str, Any]] = []
        for item in backlog_items:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            if code not in TAG_DISCOVERY_BACKLOG_CODES:
                continue
            proposals.append(
                {
                    "proposal_id": item.get("item_id") or f"tag-proposal-{len(proposals) + 1}",
                    "proposal_type": "tagging_rule_research",
                    "code": code,
                    "description": item.get("description"),
                    "source_ref": item.get("source_ref"),
                    "priority": item.get("priority") or "medium",
                    "status": item.get("status") or "observed",
                    "next_review_action": "review_as_tag_alias_rule_or_document_structure_rule",
                }
            )
        return proposals

    def tagged_evidence(
        self,
        *,
        tag: str | None = None,
        family: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        record_type: str | None = None,
        relevance: str | None = None,
        page_role: str | None = None,
        review_state: str | None = None,
        q: str | None = None,
        limit: int = 160,
        offset: int = 0,
    ) -> dict[str, Any]:
        tag_filter = _normalise_wiki_filter(tag)
        family_filter = _normalise_wiki_filter(family)
        source_type_filter = _normalise_wiki_filter(source_type)
        source_id_filter = _normalise_wiki_filter(source_id).lower()
        record_type_filter = _normalise_wiki_filter(record_type)
        relevance_filter = _normalise_wiki_filter(relevance)
        page_role_filter = _normalise_wiki_filter(page_role)
        review_state_filter = _normalise_wiki_filter(review_state)
        query = str(q or "").strip().casefold()
        bounded_limit = self._bounded_int(limit, default=160, minimum=1, maximum=1000)
        bounded_offset = self._bounded_int(offset, default=0, minimum=0, maximum=1_000_000)

        rows = []
        facets = {
            "tags": Counter(),
            "families": Counter(),
            "source_types": Counter(),
            "record_types": Counter(),
            "relevance": Counter(),
            "page_roles": Counter(),
            "review_states": Counter(),
            "sources": Counter(),
        }
        for row in self._tagged_evidence_rows():
            if tag_filter and not _wiki_record_has_tag(row, tag=tag_filter):
                continue
            if family_filter and not _wiki_record_has_tag(row, family=family_filter):
                continue
            if source_type_filter and row.get("source_type") != source_type_filter:
                continue
            if source_id_filter and str(row.get("source_id") or "").lower() != source_id_filter:
                continue
            if record_type_filter and row.get("record_type") != record_type_filter:
                continue
            if relevance_filter and row.get("clause_context_relevance") != relevance_filter:
                continue
            if page_role_filter and row.get("page_role") != page_role_filter:
                continue
            if review_state_filter and row.get("review_state") != review_state_filter:
                continue
            if query:
                haystack = " ".join(
                    str(value or "")
                    for value in (
                        row.get("source_name"),
                        row.get("title"),
                        row.get("heading"),
                        row.get("evidence_excerpt"),
                        " ".join(entry.get("tag", "") for entry in wikiAsList(row.get("tag_entries")) if isinstance(entry, dict)),
                    )
                ).casefold()
                if query not in haystack:
                    continue
            rows.append(row)
            facets["source_types"][str(row.get("source_type") or "unknown")] += 1
            facets["record_types"][str(row.get("record_type") or "unknown")] += 1
            if row.get("clause_context_relevance"):
                facets["relevance"][str(row.get("clause_context_relevance"))] += 1
            if row.get("page_role"):
                facets["page_roles"][str(row.get("page_role"))] += 1
            if row.get("review_state"):
                facets["review_states"][str(row.get("review_state"))] += 1
            source_key = f"{row.get('source_type')}:{row.get('source_id')}"
            facets["sources"][source_key] += 1
            for entry in wikiAsList(row.get("tag_entries")):
                if not isinstance(entry, dict):
                    continue
                tag_value = str(entry.get("tag") or "")
                family_value = str(entry.get("family") or "")
                if tag_value:
                    facets["tags"][tag_value] += 1
                if family_value:
                    facets["families"][family_value] += 1

        total = len(rows)
        page_rows = rows[bounded_offset:bounded_offset + bounded_limit]
        facet_payload = {
            key: [
                {"value": value, "label": display_code_label(value), "record_count": count}
                for value, count in counter.most_common(60)
            ]
            for key, counter in facets.items()
        }
        return {
            "schema_version": TAGGED_EVIDENCE_SCHEMA_VERSION,
            "scope_role": "source_knowledge_tagging",
            "governance_note": "Rows are source index evidence only. A tag does not assert a benchmark fact or entitlement outcome.",
            "filters": {
                "tag": tag_filter,
                "family": family_filter,
                "source_type": source_type_filter,
                "source_id": source_id_filter,
                "record_type": record_type_filter,
                "relevance": relevance_filter,
                "page_role": page_role_filter,
                "review_state": review_state_filter,
                "q": q or "",
                "limit": bounded_limit,
                "offset": bounded_offset,
            },
            "summary": {
                "total": total,
                "returned": len(page_rows),
                "offset": bounded_offset,
                "limit": bounded_limit,
                "has_more": bounded_offset + bounded_limit < total,
            },
            "facets": facet_payload,
            "rows": page_rows,
        }

    @staticmethod
    def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                rows.append({"error": "invalid_jsonl_row", "line": index})
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    @staticmethod
    def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    @staticmethod
    def _count_values(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for row in rows:
            value = str(row.get(key) or "").strip() or "blank"
            counts[value] += 1
        return dict(sorted(counts.items()))

    @staticmethod
    def _int_value(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _locator_gold_rows(self) -> tuple[Path, list[dict[str, Any]]]:
        path = self.paths.root / "data" / "review" / "entitlement_locator_gold_v1.jsonl"
        return path, self._read_jsonl_rows(path)

    def clause_cards(self) -> dict[str, Any]:
        path, rows = self._locator_gold_rows()
        cards: dict[str, dict[str, Any]] = {}
        feature_card_ids: set[str] = set()
        no_clause_found = 0
        for row in rows:
            clause_card_id = str(row.get("clause_card_id") or "").strip()
            if not clause_card_id:
                no_clause_found += 1
                continue
            card = cards.setdefault(
                clause_card_id,
                {
                    "clause_card_id": clause_card_id,
                    "agreement_id": row.get("agreement_id"),
                    "council": row.get("council"),
                    "pages": set(),
                    "entitlements": [],
                    "feature_card_ids": set(),
                    "raw_clause_text_hashes": set(),
                    "evidence_span_text_hashes": set(),
                    "reference_link_count": 0,
                    "review_statuses": Counter(),
                    "machine_cell_statuses": Counter(),
                    "evidence_spans": [],
                    "reference_links": [],
                },
            )
            page = row.get("page")
            if page is not None:
                card["pages"].add(page)
            entitlement_label = row.get("entitlement_label") or row.get("entitlement_id")
            if entitlement_label:
                card["entitlements"].append(
                    {
                        "entitlement_id": row.get("entitlement_id"),
                        "entitlement_key": row.get("entitlement_key"),
                        "label": entitlement_label,
                        "review_id": row.get("review_id"),
                        "machine_value_status": row.get("machine_value_status"),
                        "machine_presence_status": row.get("machine_presence_status"),
                    }
                )
            for feature_id in wikiAsList(row.get("feature_card_ids")):
                if feature_id:
                    card["feature_card_ids"].add(str(feature_id))
                    feature_card_ids.add(str(feature_id))
            feature_id = str(row.get("feature_card_id") or "").strip()
            if feature_id:
                card["feature_card_ids"].add(feature_id)
                feature_card_ids.add(feature_id)
            raw_hash = str(row.get("raw_clause_text_hash") or "").strip()
            if raw_hash:
                card["raw_clause_text_hashes"].add(raw_hash)
            span_hash = str(row.get("evidence_span_text_hash") or "").strip()
            if span_hash:
                card["evidence_span_text_hashes"].add(span_hash)
            card["reference_link_count"] += self._int_value(row.get("reference_link_count"))
            card["review_statuses"][str(row.get("review_status") or "not_reviewed")] += 1
            card["machine_cell_statuses"][str(row.get("machine_cell_status") or "unknown")] += 1
            evidence_span = str(row.get("evidence_span_text") or "").strip()
            if evidence_span and len(card["evidence_spans"]) < 4:
                card["evidence_spans"].append(
                    {
                        "entitlement_label": entitlement_label,
                        "text": evidence_span,
                        "text_hash": span_hash,
                    }
                )
            for reference in wikiAsList(row.get("reference_links")):
                if isinstance(reference, dict) and len(card["reference_links"]) < 6:
                    card["reference_links"].append(
                        {
                            "relationship": reference.get("relationship"),
                            "to_clause": reference.get("to_clause"),
                            "to_schedule": reference.get("to_schedule"),
                            "to_external": reference.get("to_external"),
                            "text_hash": reference.get("text_hash"),
                        }
                    )
        card_rows = []
        for card in cards.values():
            card_rows.append(
                {
                    **card,
                    "pages": sorted(card["pages"], key=lambda item: str(item)),
                    "entitlements": card["entitlements"],
                    "feature_card_ids": sorted(card["feature_card_ids"]),
                    "raw_clause_text_hashes": sorted(card["raw_clause_text_hashes"]),
                    "evidence_span_text_hashes": sorted(card["evidence_span_text_hashes"]),
                    "review_statuses": dict(sorted(card["review_statuses"].items())),
                    "machine_cell_statuses": dict(sorted(card["machine_cell_statuses"].items())),
                }
            )
        card_rows.sort(key=lambda item: (str(item.get("agreement_id") or ""), str(item.get("clause_card_id") or "")))
        return {
            "schema_version": "wiki.clause_cards.v1",
            "source": file_info(path),
            "summary": {
                "review_rows": len(rows),
                "clause_cards": len(card_rows),
                "feature_cards": len(feature_card_ids),
                "rows_without_clause_card": no_clause_found,
                "cards_with_reference_links": sum(1 for item in card_rows if int(item.get("reference_link_count") or 0) > 0),
            },
            "cards": card_rows,
        }

    def clause_intelligence_review(self) -> dict[str, Any]:
        gold_path, gold_rows = self._locator_gold_rows()
        suggestions_path = self.paths.root / "data" / "review" / "entitlement_locator_codex_suggestions_v1.jsonl"
        suggestions = self._read_jsonl_rows(suggestions_path)
        qa_path = self._latest_artifact_file(
            "entitlement-locator-qa-review",
            "locator-qa-review-entitlement-locator-experiment-*.json",
            "locator-qa-review-entitlement-locator-experiment-next-52-offset-0.json",
        )
        qa_payload = read_json_file(qa_path) or {}
        worksheet_csv_path = self._latest_artifact_file(
            "entitlement-locator-human-review",
            "locator-human-review-worksheet-v1*.csv",
            "locator-human-review-worksheet-v1.csv",
        )
        worksheet_md_path = self._latest_artifact_file(
            "entitlement-locator-human-review",
            "locator-human-review-worksheet-v1*.md",
            "locator-human-review-worksheet-v1.md",
        )
        worksheet_rows = self._read_csv_rows(worksheet_csv_path)
        governed_path = self.paths.root / "data" / "governed_canonical" / "entitlement_items.json"
        governed_payload = read_json_file(governed_path) or {}
        summary_mart_path = self.paths.root / "data" / "datamarts" / "entitlement_summary_mart.json"
        summary_mart = read_json_file(summary_mart_path) or {}
        governed_rows = wikiAsList(governed_payload.get("rows"))
        entitlement_test_path = self._latest_artifact_file(
            "entitlement-locator-experiment",
            "entitlement-locator-experiment-*.json",
            "entitlement-locator-experiment-next-10-offset-0.json",
        )
        entitlement_test_payload = read_json_file(entitlement_test_path) or {}
        entitlement_test_matrix = self._entitlement_test_matrix_projection(
            entitlement_test_payload,
            entitlement_test_path,
            governed_rows,
        )
        self_improvement_path = self._latest_artifact_file(
            "entitlement-self-improvement",
            "entitlement-self-improvement-pass-*.json",
            "entitlement-self-improvement-pass-entitlement-locator-experiment-all-cached-79-offset-0.json",
        )
        self_improvement = self._entitlement_self_improvement_projection(
            read_json_file(self_improvement_path) or {},
            self_improvement_path,
        )
        loop_intelligence_path = self._latest_artifact_file(
            "entitlement-loop-intelligence",
            "entitlement-loop-intelligence-*.json",
            "entitlement-loop-intelligence-entitlement-locator-experiment-all-cached-79-offset-0.json",
        )
        loop_intelligence = self._entitlement_loop_intelligence_projection(
            read_json_file(loop_intelligence_path) or {},
            loop_intelligence_path,
        )
        spine_clause_improvement_path = self._latest_artifact_file(
            "spine-clause-improvement",
            "spine-clause-improvement-*.json",
            "spine-clause-improvement-entitlement-locator-experiment-all-cached-79-offset-0.json",
        )
        spine_clause_improvement = self._spine_clause_improvement_projection(
            read_json_file(spine_clause_improvement_path) or {},
            spine_clause_improvement_path,
        )
        spine_clause_rules_path = self.paths.root / "data" / "review" / "spine_clause_process_rules.json"
        spine_clause_process_rules = self._spine_clause_rules_projection(
            read_json_file(spine_clause_rules_path) or {},
            spine_clause_rules_path,
        )
        entitlement_cards_path = self._latest_artifact_file(
            "entitlement-cards",
            "entitlement-cards-*.json",
            "entitlement-cards-entitlement-locator-experiment-all-cached-79-offset-0.json",
        )
        entitlement_cards_payload = read_json_file(entitlement_cards_path) or {}
        entitlement_cards = self._entitlement_cards_projection(
            entitlement_cards_payload,
            entitlement_cards_path,
        )
        entitlement_card_repair_path = self._latest_artifact_file(
            "entitlement-card-repair-loop",
            "entitlement-card-repair-loop-*.json",
            "entitlement-card-repair-loop-entitlement-locator-experiment-all-cached-79-offset-0.json",
        )
        entitlement_card_repair_payload = read_json_file(entitlement_card_repair_path) or {}
        entitlement_card_repair_loop = self._entitlement_card_repair_loop_projection(
            entitlement_card_repair_payload,
            entitlement_card_repair_path,
        )
        pipeline_freshness = self._clause_pipeline_freshness(
            entitlement_test_payload,
            entitlement_test_path,
            entitlement_cards_payload,
            entitlement_cards_path,
            entitlement_card_repair_payload,
            entitlement_card_repair_path,
        )
        clause_cards = self.clause_cards()
        feature_cards = self._feature_cards_from_locator_rows(gold_rows)
        reference_edges = self._reference_edges_from_locator_rows(gold_rows)
        qa_profiles = wikiAsList(qa_payload.get("profiles"))
        qa_details = [
            detail
            for profile in qa_profiles
            for detail in wikiAsList(profile.get("details"))
            if isinstance(detail, dict)
        ]
        human_blank_fields = [
            "human_clause_locator_result",
            "human_span_result",
            "human_presence_result",
            "human_value_result",
            "human_expected_value",
            "human_expected_unit",
            "human_expected_scope",
            "human_cross_reference_result",
            "human_review_decision",
            "human_review_notes",
            "human_governance_result",
        ]
        return {
            "schema_version": "wiki.clause_intelligence_review.v1",
            "summary": {
                "document_maps": file_count(self.directory("document_maps"), "*.json"),
                "locator_profiles": len(qa_profiles),
                "locator_rows": len(qa_details),
                "gold_seed_rows": len(gold_rows),
                "codex_suggestions": len(suggestions),
                "human_review_rows": len(worksheet_rows),
                "clause_cards": clause_cards.get("summary", {}).get("clause_cards", 0),
                "feature_cards": feature_cards["summary"]["feature_cards"],
                "entitlement_cards": entitlement_cards["summary"]["entitlement_cards"],
                "entitlement_card_repair_entitlements": entitlement_card_repair_loop["summary"]["entitlements_reviewed"],
                "reference_edges": reference_edges["summary"]["reference_edges"],
                "governed_entitlement_rows": len(governed_rows),
                "final_entitlements": entitlement_test_matrix["summary"]["final_entitlements"],
                "target_test_councils": entitlement_test_matrix["summary"]["target_councils"],
                "entitlement_test_cells": entitlement_test_matrix["summary"]["test_cells"],
                "feature_card_test_cells": entitlement_test_matrix["summary"]["feature_card_ready"],
                "self_improvement_entitlements": self_improvement["summary"]["entitlements"],
                "definition_solidification_needed": self_improvement["summary"]["definition_solidification_needed"],
                "loop_intelligence_entitlements": loop_intelligence["summary"]["entitlements"],
                "loop_validation_queue_items": loop_intelligence["summary"]["validation_queue_items"],
                "spine_clause_backfill_needed": spine_clause_improvement["summary"].get("document_map_backfill_needed", 0),
                "spine_clause_quantification_queue_items": spine_clause_process_rules["summary"].get("quantification_queue_items", 0),
                "pipeline_freshness_status": pipeline_freshness["status"],
                "pipeline_stale_stages": pipeline_freshness["stale_stages"],
            },
            "pipeline_freshness": pipeline_freshness,
            "entitlement_test_matrix": entitlement_test_matrix,
            "entitlement_self_improvement": self_improvement,
            "entitlement_loop_intelligence": loop_intelligence,
            "spine_clause_improvement": spine_clause_improvement,
            "spine_clause_process_rules": spine_clause_process_rules,
            "qa_review_pack": self._qa_review_pack_projection(qa_payload, qa_path, qa_details),
            "gold_seed_rows": {
                "source": file_info(gold_path),
                "summary": {
                    "rows": len(gold_rows),
                    "review_statuses": self._count_values(gold_rows, "review_status"),
                    "governance_statuses": self._count_values(gold_rows, "governance_status"),
                    "machine_cell_statuses": self._count_values(gold_rows, "machine_cell_status"),
                    "follow_up_required": sum(1 for row in gold_rows if row.get("follow_up_required") is True),
                    "eligible_for_governance": sum(1 for row in gold_rows if row.get("eligible_for_governance") is True),
                },
                "rows": gold_rows[:40],
            },
            "codex_suggestions": {
                "source": file_info(suggestions_path),
                "summary": {
                    "rows": len(suggestions),
                    "confidence": self._count_values(suggestions, "confidence"),
                    "suggested_review_decisions": self._count_values(suggestions, "suggested_review_decision"),
                    "requires_human_confirmation": sum(1 for row in suggestions if row.get("requires_human_confirmation") is True),
                    "risk_flags": dict(sorted(Counter(
                        str(flag)
                        for row in suggestions
                        for flag in wikiAsList(row.get("risk_flags"))
                    ).items())),
                },
                "rows": suggestions[:40],
            },
            "human_review_worksheet": {
                "source": file_info(worksheet_csv_path),
                "markdown": file_info(worksheet_md_path),
                "summary": {
                    "rows": len(worksheet_rows),
                    "machine_cell_statuses": self._count_values(worksheet_rows, "machine_cell_status"),
                    "codex_confidence": self._count_values(worksheet_rows, "codex_confidence"),
                    "blank_human_fields": {
                        field: sum(1 for row in worksheet_rows if not str(row.get(field) or "").strip())
                        for field in human_blank_fields
                    },
                },
                "columns": list(worksheet_rows[0].keys()) if worksheet_rows else [],
                "rows": worksheet_rows,
            },
            "feature_cards": feature_cards,
            "entitlement_cards": entitlement_cards,
            "entitlement_card_repair_loop": entitlement_card_repair_loop,
            "reference_edges": reference_edges,
            "clause_cards": clause_cards,
            "governed_entitlement_measures": {
                "source": file_info(governed_path),
                "summary_mart": file_info(summary_mart_path),
                "summary": {
                    "rows": len(governed_rows),
                    "review_governance_statuses": self._count_values(governed_rows, "review_governance_status"),
                    "governed_canonical_statuses": self._count_values(governed_rows, "governed_canonical_status"),
                    "value_statuses": self._count_values(governed_rows, "value_status"),
                    "mart_rows": self._int_value(summary_mart.get("row_count")),
                    "mart_id": summary_mart.get("mart_id"),
                },
                "rows": governed_rows[:60],
            },
        }

    def _entitlement_card_repair_loop_projection(self, payload: dict[str, Any], path: Path) -> dict[str, Any]:
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        rows = [
            {
                "entitlement_id": row.get("entitlement_id"),
                "label": row.get("label"),
                "blocked_rows": row.get("blocked_rows"),
                "blocked_value_rows": row.get("blocked_value_rows"),
                "failure_counts": row.get("failure_counts") if isinstance(row.get("failure_counts"), dict) else {},
                "repair_review": row.get("repair_review") if isinstance(row.get("repair_review"), dict) else {},
                "llm_status": row.get("llm_status"),
                "blocked_samples": wikiAsList(row.get("blocked_samples"))[:5],
            }
            for row in wikiAsList(payload.get("rows"))[:80]
            if isinstance(row, dict)
        ]
        return {
            "schema_version": payload.get("schema_version") or "wiki.entitlement_card_repair_loop.v1",
            "source": file_info(path),
            "artifact_id": payload.get("artifact_id"),
            "generated_at": payload.get("generated_at"),
            "method": payload.get("method") if isinstance(payload.get("method"), dict) else {},
            "summary": {
                "entitlements_reviewed": self._int_value(summary.get("entitlements_reviewed")),
                "blocked_rows_reviewed": self._int_value(summary.get("blocked_rows_reviewed")),
                "blocked_value_rows_reviewed": self._int_value(summary.get("blocked_value_rows_reviewed")),
                "llm_statuses": summary.get("llm_statuses") if isinstance(summary.get("llm_statuses"), dict) else {},
                "sample_decisions": summary.get("sample_decisions") if isinstance(summary.get("sample_decisions"), dict) else {},
                "failure_counts": summary.get("failure_counts") if isinstance(summary.get("failure_counts"), dict) else {},
            },
            "rows": rows,
        }

    def _entitlement_cards_projection(self, payload: dict[str, Any], path: Path) -> dict[str, Any]:
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        cards = wikiAsList(payload.get("cards"))
        blocked_samples = wikiAsList(payload.get("blocked_samples"))
        return {
            "schema_version": payload.get("schema_version") or "wiki.entitlement_cards.v1",
            "source": file_info(path),
            "artifact_id": payload.get("artifact_id"),
            "generated_at": payload.get("generated_at"),
            "method": payload.get("method") if isinstance(payload.get("method"), dict) else {},
            "summary": {
                "source_cells": self._int_value(summary.get("source_cells")),
                "value_extracted_cells": self._int_value(summary.get("value_extracted_cells")),
                "entitlement_cards": self._int_value(summary.get("entitlement_cards")),
                "blocked_cells": self._int_value(summary.get("blocked_cells")),
                "blocked_value_cells": self._int_value(summary.get("blocked_value_cells")),
                "status_counts": summary.get("status_counts") if isinstance(summary.get("status_counts"), dict) else {},
                "gate_failure_counts": summary.get("gate_failure_counts") if isinstance(summary.get("gate_failure_counts"), dict) else {},
            },
            "cards": cards,
            "blocked_samples": blocked_samples[:60],
        }

    def _spine_clause_improvement_projection(self, payload: dict[str, Any], path: Path) -> dict[str, Any]:
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        spine = payload.get("document_spine") if isinstance(payload.get("document_spine"), dict) else {}
        clause = payload.get("clause_process") if isinstance(payload.get("clause_process"), dict) else {}
        return {
            "schema_version": payload.get("schema_version") or "wiki.spine_clause_improvement_pass.v1",
            "source": file_info(path),
            "artifact_id": payload.get("artifact_id"),
            "generated_at": payload.get("generated_at"),
            "summary": {
                "target_agreements": self._int_value(summary.get("target_agreements")),
                "source_spines_ready": self._int_value(summary.get("source_spines_ready")),
                "document_maps_ready": self._int_value(summary.get("document_maps_ready")),
                "document_map_backfill_needed": self._int_value(summary.get("document_map_backfill_needed")),
                "source_cache_repair_needed": self._int_value(summary.get("source_cache_repair_needed")),
                "entitlements": self._int_value(summary.get("entitlements")),
                "clause_only_cells": self._int_value(summary.get("clause_only_cells")),
                "blocked_or_adjacent_cells": self._int_value(summary.get("blocked_or_adjacent_cells")),
                "feature_card_cells": self._int_value(summary.get("feature_card_cells")),
            },
            "document_spine": {
                "document_map_backfill_queue": wikiAsList(spine.get("document_map_backfill_queue"))[:40],
                "source_cache_repair_queue": wikiAsList(spine.get("source_cache_repair_queue"))[:40],
                "agreements": wikiAsList(spine.get("agreements"))[:90],
            },
            "clause_process": {
                "source_container_type_counts": clause.get("source_container_type_counts") if isinstance(clause.get("source_container_type_counts"), dict) else {},
                "process_rule_flag_counts": clause.get("process_rule_flag_counts") if isinstance(clause.get("process_rule_flag_counts"), dict) else {},
                "clause_quantification_queue": wikiAsList(clause.get("clause_quantification_queue"))[:30],
                "blocked_clause_review_queue": wikiAsList(clause.get("blocked_clause_review_queue"))[:30],
                "routing_or_front_matter_review_queue": wikiAsList(clause.get("routing_or_front_matter_review_queue"))[:24],
                "entitlements": wikiAsList(clause.get("entitlements"))[:60],
            },
        }

    def _spine_clause_rules_projection(self, payload: dict[str, Any], path: Path) -> dict[str, Any]:
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        document_spine_rules = payload.get("document_spine_rules") if isinstance(payload.get("document_spine_rules"), dict) else {}
        clause_process_rules = payload.get("clause_process_rules") if isinstance(payload.get("clause_process_rules"), dict) else {}
        return {
            "schema_version": payload.get("schema_version") or "wiki.spine_clause_process_rules.v1",
            "source": file_info(path),
            "generated_at": payload.get("generated_at"),
            "summary": {
                "target_agreements": self._int_value(summary.get("target_agreements")),
                "document_maps_ready": self._int_value(summary.get("document_maps_ready")),
                "document_map_backfill_needed": self._int_value(summary.get("document_map_backfill_needed")),
                "source_cache_repair_needed": self._int_value(summary.get("source_cache_repair_needed")),
                "entitlements": self._int_value(summary.get("entitlements")),
                "clause_only_cells": self._int_value(summary.get("clause_only_cells")),
                "blocked_or_adjacent_cells": self._int_value(summary.get("blocked_or_adjacent_cells")),
                "feature_card_cells": self._int_value(summary.get("feature_card_cells")),
                "quantification_queue_items": self._int_value(summary.get("quantification_queue_items")),
                "blocked_review_queue_items": self._int_value(summary.get("blocked_review_queue_items")),
                "routing_or_front_matter_queue_items": self._int_value(summary.get("routing_or_front_matter_queue_items")),
            },
            "document_spine_rules": {
                "target_source_policy": document_spine_rules.get("target_source_policy"),
                "page_role_model": wikiAsList(document_spine_rules.get("page_role_model")),
                "routing_rules": wikiAsList(document_spine_rules.get("routing_rules")),
                "document_map_backfill_queue": wikiAsList(document_spine_rules.get("document_map_backfill_queue"))[:40],
                "source_cache_repair_queue": wikiAsList(document_spine_rules.get("source_cache_repair_queue"))[:40],
            },
            "clause_process_rules": {
                "promotion_gate": wikiAsList(clause_process_rules.get("promotion_gate")),
                "source_container_types": clause_process_rules.get("source_container_types") if isinstance(clause_process_rules.get("source_container_types"), dict) else {},
                "process_rule_flags": clause_process_rules.get("process_rule_flags") if isinstance(clause_process_rules.get("process_rule_flags"), dict) else {},
                "quantification_queue": wikiAsList(clause_process_rules.get("quantification_queue"))[:30],
                "blocked_clause_review_queue": wikiAsList(clause_process_rules.get("blocked_clause_review_queue"))[:30],
                "routing_or_front_matter_review_queue": wikiAsList(clause_process_rules.get("routing_or_front_matter_review_queue"))[:24],
            },
            "entitlement_process_actions": wikiAsList(payload.get("entitlement_process_actions"))[:60],
        }

    def _entitlement_self_improvement_projection(self, payload: dict[str, Any], path: Path) -> dict[str, Any]:
        rows = [row for row in wikiAsList(payload.get("rows")) if isinstance(row, dict)]
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        by_entitlement = {
            str(row.get("entitlement_id") or "").strip(): row
            for row in rows
            if str(row.get("entitlement_id") or "").strip()
        }
        return {
            "schema_version": payload.get("schema_version") or "wiki.entitlement_self_improvement_pass.v1",
            "source": file_info(path),
            "artifact_id": payload.get("artifact_id"),
            "generated_at": payload.get("generated_at"),
            "method": payload.get("method") if isinstance(payload.get("method"), dict) else {},
            "summary": {
                "entitlements": self._int_value(summary.get("entitlements")) if summary else len(rows),
                "green_feature_cells": self._int_value(summary.get("green_feature_cells")),
                "statuses": summary.get("statuses") if isinstance(summary.get("statuses"), dict) else {},
                "suggestion_types": summary.get("suggestion_types") if isinstance(summary.get("suggestion_types"), dict) else {},
                "definition_solidification_needed": self._int_value(summary.get("definition_solidification_needed")),
            },
            "rows": rows,
            "rows_by_entitlement": by_entitlement,
        }

    def _entitlement_loop_intelligence_projection(self, payload: dict[str, Any], path: Path) -> dict[str, Any]:
        rows = [row for row in wikiAsList(payload.get("rows")) if isinstance(row, dict)]
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        by_entitlement = {
            str(row.get("entitlement_id") or "").strip(): row
            for row in rows
            if str(row.get("entitlement_id") or "").strip()
        }
        return {
            "schema_version": payload.get("schema_version") or "wiki.entitlement_loop_intelligence.v1",
            "source": file_info(path),
            "artifact_id": payload.get("artifact_id"),
            "generated_at": payload.get("generated_at"),
            "method": payload.get("method") if isinstance(payload.get("method"), dict) else {},
            "summary": {
                "entitlements": self._int_value(summary.get("entitlements")) if summary else len(rows),
                "loop_statuses": summary.get("loop_statuses") if isinstance(summary.get("loop_statuses"), dict) else {},
                "promotion_gates": summary.get("promotion_gates") if isinstance(summary.get("promotion_gates"), dict) else {},
                "validation_queue_items": self._int_value(summary.get("validation_queue_items")),
            },
            "rows": rows,
            "rows_by_entitlement": by_entitlement,
        }

    def entitlement_test_matrix(self) -> dict[str, Any]:
        governed_path = self.paths.root / "data" / "governed_canonical" / "entitlement_items.json"
        governed_payload = read_json_file(governed_path) or {}
        path = self._latest_artifact_file(
            "entitlement-locator-experiment",
            "entitlement-locator-experiment-*.json",
            "entitlement-locator-experiment-next-10-offset-0.json",
        )
        payload = read_json_file(path) or {}
        return self._entitlement_test_matrix_projection(payload, path, wikiAsList(governed_payload.get("rows")))

    def _entitlement_test_matrix_projection(
        self,
        payload: dict[str, Any],
        path: Path,
        governed_rows: list[Any],
    ) -> dict[str, Any]:
        entitlement_rows = [
            row
            for row in governed_rows
            if isinstance(row, dict) and str(row.get("entitlement_id") or "").strip()
        ]
        profiles = [profile for profile in wikiAsList(payload.get("profiles")) if isinstance(profile, dict)]
        profile_by_id = {
            str(profile.get("entitlement_id") or "").strip(): profile
            for profile in profiles
            if str(profile.get("entitlement_id") or "").strip()
        }
        profile_contracts_by_id = {
            str(profile.get("entitlement_id") or "").strip(): profile.get("rule_contract")
            for profile in profiles
            if isinstance(profile.get("rule_contract"), dict) and str(profile.get("entitlement_id") or "").strip()
        }
        try:
            from scripts.build_entitlement_locator_experiment import LOCATOR_SPECS, serialisable_rule_contract

            profile_contracts_by_id.update({
                spec.entitlement_id: serialisable_rule_contract(spec)
                for spec in LOCATOR_SPECS
                if spec.entitlement_id not in profile_contracts_by_id
            })
        except Exception:
            pass
        targets = [row for row in wikiAsList(payload.get("target_comparator_set")) if isinstance(row, dict)]
        if not targets:
            for profile in profiles:
                targets = [row for row in wikiAsList(profile.get("target_rows")) if isinstance(row, dict)]
                if targets:
                    break
        target_count = len(targets)
        document_map_ids = {path.stem.lower() for path in self._json_files("document_maps")}
        categories: dict[str, dict[str, Any]] = {}
        matrix_cells: list[dict[str, Any]] = []
        matrix_entitlements: list[dict[str, Any]] = []
        status_counts: Counter[str] = Counter()
        stage_counts: Counter[str] = Counter()

        def ready_label(ready: bool) -> str:
            return "ready" if ready else "missing"

        def row_status(spine_ready: int, clause_ready: int, feature_ready: int) -> str:
            if target_count and feature_ready == target_count:
                return "complete_to_feature_card"
            if feature_ready:
                return "partial_feature_cards"
            if clause_ready:
                return "clause_cards_only"
            if spine_ready:
                return "document_spine_only"
            return "not_profiled"

        def compact_preview(value: Any, *, limit: int = 720) -> str:
            text = re.sub(r"\s+", " ", str(value or "")).strip()
            if len(text) <= limit:
                return text
            return f"{text[:limit].rstrip()}..."

        clause_marker = re.compile(r"(?<![\w])(\d{1,3}(?:\.\d{1,3}){1,6}\.?)\s+(?=[A-Z(])")

        def sentence_start_before(text: str, anchor: int) -> int:
            segment = text[: max(anchor, 0)]
            starts = [match.end() for match in re.finditer(r"(?<=[.!?])\s+(?=[A-Z(])", segment)]
            return starts[-1] if starts else 0

        def format_review_text(text: str) -> str:
            text = re.sub(r"\s+", " ", text).strip()
            text = re.sub(r"(?<!^)\s+(?=\d{1,3}(?:\.\d{1,3}){1,6}\.?\s+[A-Z(])", "\n\n", text)
            text = re.sub(r"\s+(\([a-z]\))\s+", r"\n  \1 ", text)
            text = re.sub(r"\s+(\([ivxlcdm]{1,6}\))\s+", r"\n    \1 ", text, flags=re.I)
            text = re.sub(r"\s+(Page\s*(?:\||\d+\s+of\s+\d+))", r"\n\n\1", text, flags=re.I)
            return re.sub(r"\n{3,}", "\n\n", text).strip()

        def reading_preview(value: Any, *, limit: int = 5200, anchor: int | None = None) -> str:
            text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
            text = re.sub(r"\s+", " ", text).strip()
            if anchor is not None and text:
                bounded_anchor = min(max(anchor, 0), len(text) - 1)
                clause_starts = [
                    match.start(1)
                    for match in clause_marker.finditer(text)
                    if match.start(1) <= bounded_anchor
                ]
                start = clause_starts[-1] if clause_starts else sentence_start_before(text, bounded_anchor)
                text = text[start:].lstrip()
            elif text:
                first_clause = clause_marker.search(text)
                if first_clause and first_clause.start(1) <= 900:
                    text = text[first_clause.start(1):].lstrip()
            text = format_review_text(text)
            if len(text) <= limit:
                return text
            return f"{text[:limit].rstrip()}..."

        def preview_clause_card(card: Any) -> dict[str, Any]:
            if not isinstance(card, dict):
                return {}
            anchor = self._int_value(card.get("matched_span_start")) if card.get("matched_span_start") is not None else None
            return {
                "clause_id": card.get("clause_id"),
                "heading": card.get("heading_path") or card.get("clause_number") or card.get("benefit_label"),
                "page": card.get("page_number_physical"),
                "confidence": card.get("confidence"),
                "review_status": card.get("review_status"),
                "governance_status": card.get("governance_status"),
                "text": compact_preview(card.get("raw_clause_text"), limit=160),
            }

        def preview_feature_card(card: Any) -> dict[str, Any]:
            if not isinstance(card, dict):
                return {}
            return {
                "feature_id": card.get("feature_id"),
                "clause_id": card.get("clause_id"),
                "page": card.get("page_number_physical"),
                "subclass_label": card.get("subclass_label"),
                "answer_kind": card.get("answer_kind"),
                "quantification_type": card.get("quantification_type"),
                "value": card.get("value"),
                "unit": card.get("unit"),
                "condition": card.get("condition"),
                "benchmark_value": card.get("benchmark_value"),
                "review_status": card.get("review_status"),
                "governance_status": card.get("governance_status"),
                "answer_builder_status": card.get("answer_builder_status") or (
                    card.get("answer_builder", {}).get("status")
                    if isinstance(card.get("answer_builder"), dict)
                    else None
                ),
                "evidence_span": compact_preview(card.get("evidence_span_text"), limit=160),
            }

        def preview_candidate_page(candidate: Any) -> dict[str, Any]:
            if not isinstance(candidate, dict):
                return {}
            return {
                "state": candidate.get("state"),
                "page": candidate.get("page"),
                "page_label": candidate.get("page_label"),
                "heading": candidate.get("heading"),
                "matched_terms": wikiAsList(candidate.get("matched_terms"))[:6],
                "blocker_signals": wikiAsList(candidate.get("blocker_signals"))[:6],
                "score": candidate.get("score"),
                "value_signals": wikiAsList(candidate.get("value_signals"))[:6],
                "excerpt": compact_preview(candidate.get("excerpt"), limit=220),
                "source_ref": candidate.get("source_ref") if isinstance(candidate.get("source_ref"), dict) else {},
            }

        for entitlement in entitlement_rows:
            entitlement_id = str(entitlement.get("entitlement_id") or "").strip()
            profile = profile_by_id.get(entitlement_id)
            target_rows = [
                row
                for row in wikiAsList(profile.get("target_rows") if profile else [])
                if isinstance(row, dict)
            ]
            rows_by_agreement = {
                str(row.get("agreement_id") or "").strip().lower(): row
                for row in target_rows
                if str(row.get("agreement_id") or "").strip()
            }
            value_rows = [
                {
                    "council": row.get("council"),
                    "value": value.get("value"),
                    "unit": value.get("unit"),
                    "condition": value.get("condition") or value.get("subclass_label"),
                    "subclass_label": value.get("subclass_label"),
                }
                for row in target_rows
                for value in wikiAsList(row.get("normalised_values"))
                if isinstance(value, dict) and (value.get("value") or value.get("unit") or value.get("condition") or value.get("subclass_label"))
            ]
            value_profile = {
                "feature_values": len(value_rows),
                "common_values": dict(Counter(
                    " ".join(str(part).strip() for part in (value.get("value"), value.get("unit")) if str(part or "").strip())
                    for value in value_rows
                    if " ".join(str(part).strip() for part in (value.get("value"), value.get("unit")) if str(part or "").strip())
                ).most_common(8)),
                "units": dict(Counter(str(value.get("unit") or "").strip() for value in value_rows if str(value.get("unit") or "").strip()).most_common(8)),
                "subclasses": dict(Counter(str(value.get("subclass_label") or "").strip() for value in value_rows if str(value.get("subclass_label") or "").strip()).most_common(8)),
                "examples": value_rows[:6],
            }
            spine_ready = 0
            clause_ready = 0
            feature_ready = 0
            document_map_ready = 0
            for target in targets:
                agreement_id = str(target.get("agreement_id") or "").strip().lower()
                cell = rows_by_agreement.get(agreement_id)
                source_pages_ready = bool(cell and self._int_value(cell.get("page_count")) > 0)
                clauses_ready = bool(cell and wikiAsList(cell.get("clause_cards")))
                features_ready = bool(cell and wikiAsList(cell.get("feature_cards")))
                has_document_map = agreement_id in document_map_ids
                spine_ready += int(source_pages_ready)
                clause_ready += int(clauses_ready)
                feature_ready += int(features_ready)
                document_map_ready += int(has_document_map)
                stage_counts["document_spine_ready"] += int(source_pages_ready)
                stage_counts["clause_card_ready"] += int(clauses_ready)
                stage_counts["feature_card_ready"] += int(features_ready)
                best_candidate = cell.get("best_candidate") if cell and isinstance(cell.get("best_candidate"), dict) else {}
                clause_card_rows = wikiAsList(cell.get("clause_cards")) if cell else []
                feature_card_rows = wikiAsList(cell.get("feature_cards")) if cell else []
                review_text = ""
                if clause_card_rows and isinstance(clause_card_rows[0], dict):
                    clause_anchor = (
                        self._int_value(clause_card_rows[0].get("matched_span_start"))
                        if clause_card_rows[0].get("matched_span_start") is not None
                        else None
                    )
                    review_text = reading_preview(
                        clause_card_rows[0].get("raw_clause_text"),
                        limit=700,
                        anchor=clause_anchor,
                    )
                if not review_text and best_candidate:
                    review_text = reading_preview(best_candidate.get("excerpt"), limit=520)
                if not review_text and feature_card_rows and isinstance(feature_card_rows[0], dict):
                    review_text = reading_preview(feature_card_rows[0].get("evidence_span_text"), limit=520)
                matrix_cells.append(
                    {
                        "entitlement_id": entitlement_id,
                        "entitlement_label": entitlement.get("entitlement_label") or entitlement_id,
                        "category": entitlement.get("category") or "Uncategorised",
                        "council": (target.get("council") or cell.get("council")) if cell else target.get("council"),
                        "agreement_id": agreement_id,
                        "agreement_name": (target.get("agreement_name") or cell.get("agreement_name")) if cell else target.get("agreement_name"),
                        "document_spine": ready_label(source_pages_ready),
                        "document_map": ready_label(has_document_map),
                        "clause_cards": ready_label(clauses_ready),
                        "feature_cards": ready_label(features_ready),
                        "machine_state": cell.get("state") if cell else "not_profiled",
                        "candidate_count": self._int_value(cell.get("candidate_count")) if cell else 0,
                        "clause_card_count": len(clause_card_rows),
                        "feature_card_count": len(feature_card_rows),
                        "reference_link_count": len(wikiAsList(cell.get("reference_links"))) if cell else 0,
                        "locator_confidence": cell.get("locator_confidence") if cell else 0,
                        "best_page": best_candidate.get("page"),
                        "best_heading": best_candidate.get("heading"),
                        "best_excerpt": compact_preview(best_candidate.get("excerpt"), limit=160),
                        "review_text": review_text,
                        "matched_terms": wikiAsList(best_candidate.get("matched_terms"))[:8],
                        "blocker_signals": wikiAsList(best_candidate.get("blocker_signals"))[:8],
                        "value_signals": wikiAsList(cell.get("value_signals"))[:8] if cell else [],
                        "normalised_values": wikiAsList(cell.get("normalised_values"))[:2] if cell else [],
                        "candidate_pages": [],
                        "clause_card_previews": [preview_clause_card(card) for card in clause_card_rows[:1]],
                        "feature_card_previews": [preview_feature_card(card) for card in feature_card_rows[:1]],
                    }
                )
            status = row_status(spine_ready, clause_ready, feature_ready)
            status_counts[status] += 1
            category_key = str(entitlement.get("category") or "Uncategorised")
            category_row = categories.setdefault(
                category_key,
                {
                    "category": category_key,
                    "entitlements": 0,
                    "test_cells": 0,
                    "document_spine_ready": 0,
                    "document_map_ready": 0,
                    "clause_card_ready": 0,
                    "feature_card_ready": 0,
                    "complete_to_feature_card": 0,
                },
            )
            category_row["entitlements"] += 1
            category_row["test_cells"] += target_count
            category_row["document_spine_ready"] += spine_ready
            category_row["document_map_ready"] += document_map_ready
            category_row["clause_card_ready"] += clause_ready
            category_row["feature_card_ready"] += feature_ready
            category_row["complete_to_feature_card"] += int(status == "complete_to_feature_card")
            matrix_entitlements.append(
                {
                    "entitlement_id": entitlement_id,
                    "entitlement_label": entitlement.get("entitlement_label") or entitlement_id,
                    "category": category_key,
                    "definition": entitlement.get("definition") or "",
                    "rule_contract": profile_contracts_by_id.get(entitlement_id) or {
                        "entitlement_id": entitlement_id,
                        "label": entitlement.get("entitlement_label") or entitlement_id,
                        "definition": entitlement.get("definition") or "",
                        "taxonomy_path": [category_key, entitlement.get("entitlement_label") or entitlement_id],
                        "scope": entitlement.get("scope") or "standard_employees",
                        "classification_boundary": {
                            "canonical_definition": entitlement.get("definition") or "",
                            "included": [],
                            "excluded": [],
                            "needs_review": [],
                        },
                        "accepted_subclasses": [],
                        "locator_signals": {},
                        "ai_improvement_questions": [],
                    },
                    "value_profile": value_profile,
                    "target_councils": target_count,
                    "document_spine_ready": spine_ready,
                    "document_map_ready": document_map_ready,
                    "clause_card_ready": clause_ready,
                    "feature_card_ready": feature_ready,
                    "missing_feature_cards": max(target_count - feature_ready, 0),
                    "status": status,
                    "profiled": profile is not None,
                }
            )

        total_cells = len(entitlement_rows) * target_count
        categories_sorted = sorted(categories.values(), key=lambda item: str(item.get("category") or ""))
        matrix_entitlements.sort(key=lambda item: (str(item.get("category") or ""), str(item.get("entitlement_label") or "")))
        return {
            "schema_version": "wiki.entitlement_test_matrix.v1",
            "source": file_info(path),
            "artifact_id": payload.get("artifact_id"),
            "generated_at": payload.get("generated_at"),
            "summary": {
                "final_entitlements": len(entitlement_rows),
                "locator_profiles": len(profiles),
                "target_councils": target_count,
                "test_cells": total_cells,
                "document_spine_ready": stage_counts["document_spine_ready"],
                "document_map_ready": sum(item["document_map_ready"] for item in categories_sorted),
                "clause_card_ready": stage_counts["clause_card_ready"],
                "feature_card_ready": stage_counts["feature_card_ready"],
                "complete_to_feature_card": status_counts["complete_to_feature_card"],
                "status_counts": dict(sorted(status_counts.items())),
            },
            "targets": targets,
            "categories": categories_sorted,
            "entitlements": matrix_entitlements,
            "cells": matrix_cells,
        }

    def _qa_review_pack_projection(
        self,
        payload: dict[str, Any],
        path: Path,
        details: list[dict[str, Any]],
    ) -> dict[str, Any]:
        profiles = wikiAsList(payload.get("profiles"))
        return {
            "source": file_info(path),
            "artifact_id": payload.get("artifact_id"),
            "generated_at": payload.get("generated_at"),
            "doctrine": payload.get("doctrine"),
            "review_questions": wikiAsList(payload.get("review_questions")),
            "guardrails": wikiAsList(payload.get("guardrails")),
            "semantic_status_model": payload.get("semantic_status_model") if isinstance(payload.get("semantic_status_model"), dict) else {},
            "summary": {
                "profiles": len(profiles),
                "details": len(details),
                "clause_found": sum(1 for row in details if row.get("clause_found") is True),
                "value_found": sum(1 for row in details if row.get("value_found") is True),
                "cell_statuses": self._count_values(details, "cell_status"),
                "row_states": self._count_values(details, "row_state"),
            },
            "profiles": [
                {
                    "key": profile.get("key"),
                    "entitlement_id": profile.get("entitlement_id"),
                    "label": profile.get("label"),
                    "summary": profile.get("summary") if isinstance(profile.get("summary"), dict) else {},
                    "details": wikiAsList(profile.get("details"))[:8],
                }
                for profile in profiles
                if isinstance(profile, dict)
            ],
        }

    def _feature_cards_from_locator_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        features: dict[str, dict[str, Any]] = {}
        for row in rows:
            feature_ids = [str(row.get("feature_card_id") or "").strip()]
            feature_ids.extend(str(item).strip() for item in wikiAsList(row.get("feature_card_ids")))
            for feature_id in sorted({item for item in feature_ids if item}):
                feature = features.setdefault(
                    feature_id,
                    {
                        "feature_card_id": feature_id,
                        "clause_card_id": row.get("clause_card_id"),
                        "agreement_id": row.get("agreement_id"),
                        "council": row.get("council"),
                        "page": row.get("page"),
                        "entitlements": [],
                        "evidence_spans": [],
                        "machine_value_statuses": Counter(),
                        "review_statuses": Counter(),
                        "governance_statuses": Counter(),
                        "answer_builder_statuses": Counter(),
                        "reference_link_count": 0,
                    },
                )
                entitlement = row.get("entitlement_label") or row.get("entitlement_id")
                if entitlement:
                    feature["entitlements"].append(entitlement)
                span_text = str(row.get("evidence_span_text") or "").strip()
                if span_text and len(feature["evidence_spans"]) < 3:
                    feature["evidence_spans"].append({
                        "text": span_text,
                        "text_hash": row.get("evidence_span_text_hash"),
                    })
                feature["machine_value_statuses"][str(row.get("machine_value_status") or "unknown")] += 1
                feature["review_statuses"][str(row.get("review_status") or "not_reviewed")] += 1
                feature["governance_statuses"][str(row.get("governance_status") or "not_eligible")] += 1
                feature["answer_builder_statuses"][str(row.get("answer_builder_status") or "not_available")] += 1
                feature["reference_link_count"] += self._int_value(row.get("reference_link_count"))
        feature_rows = [
            {
                **feature,
                "entitlements": sorted(set(feature["entitlements"])),
                "machine_value_statuses": dict(sorted(feature["machine_value_statuses"].items())),
                "review_statuses": dict(sorted(feature["review_statuses"].items())),
                "governance_statuses": dict(sorted(feature["governance_statuses"].items())),
                "answer_builder_statuses": dict(sorted(feature["answer_builder_statuses"].items())),
            }
            for feature in features.values()
        ]
        feature_rows.sort(key=lambda item: str(item.get("feature_card_id") or ""))
        return {
            "summary": {
                "feature_cards": len(feature_rows),
                "with_evidence_spans": sum(1 for item in feature_rows if item.get("evidence_spans")),
                "with_reference_links": sum(1 for item in feature_rows if self._int_value(item.get("reference_link_count")) > 0),
            },
            "features": feature_rows[:120],
        }

    def _reference_edges_from_locator_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        edges: dict[str, dict[str, Any]] = {}
        for row in rows:
            for reference in wikiAsList(row.get("reference_links")):
                if not isinstance(reference, dict):
                    continue
                edge_id = str(reference.get("reference_id") or "").strip()
                if not edge_id:
                    target = reference.get("to_clause") or reference.get("to_schedule") or reference.get("to_external") or "target"
                    edge_id = f"{row.get('review_id')}::{reference.get('relationship') or 'reference'}::{target}"
                edges[edge_id] = {
                    "reference_id": edge_id,
                    "agreement_id": row.get("agreement_id"),
                    "council": row.get("council"),
                    "entitlement_label": row.get("entitlement_label"),
                    "clause_card_id": row.get("clause_card_id"),
                    "from_clause_id": reference.get("from_clause_id"),
                    "relationship": reference.get("relationship"),
                    "to_clause": reference.get("to_clause"),
                    "to_schedule": reference.get("to_schedule"),
                    "to_external": reference.get("to_external"),
                    "text_hash": reference.get("text_hash"),
                }
        edge_rows = sorted(edges.values(), key=lambda item: str(item.get("reference_id") or ""))
        return {
            "summary": {
                "reference_edges": len(edge_rows),
                "relationships": self._count_values(edge_rows, "relationship"),
                "external_targets": sum(1 for item in edge_rows if item.get("to_external")),
                "clause_targets": sum(1 for item in edge_rows if item.get("to_clause")),
                "schedule_targets": sum(1 for item in edge_rows if item.get("to_schedule")),
            },
            "edges": edge_rows[:180],
        }

    def reference_inputs(self) -> dict[str, Any]:
        inputs: list[dict[str, Any]] = []
        for path in sorted(self._json_files("reference_inputs"), key=lambda item: item.stem):
            payload = read_json_file(path) or {}
            inputs.append({
                "source_id": payload.get("source_id") or path.stem,
                "source_name": payload.get("source_name"),
                "source_kind": payload.get("source_kind"),
                "knowledge_role": payload.get("knowledge_role"),
                "source_url": payload.get("source", {}).get("source_url") if isinstance(payload.get("source"), dict) else "",
                "generated_at": payload.get("generated_at"),
                "review_state": payload.get("review_state"),
                "scope_focus": payload.get("scope_focus"),
                "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
                "file": file_info(path),
            })
        return {
            "reference_inputs": inputs,
            "count": len(inputs),
        }

    def reference_input(self, source_id: str) -> dict[str, Any]:
        token = safe_wiki_token(source_id.lower().removesuffix(".pdf"), label="reference input id")
        return self._read_required_json(self.directory("reference_inputs") / f"{token}.json", label="reference input")

    def questions(self, *, run_id: str | None = None) -> dict[str, Any]:
        resolved_run_id = safe_wiki_token(run_id, label="run id") if run_id else self.latest_run_id()
        if not resolved_run_id:
            raise FileNotFoundError("Wiki questions not found")
        return self._read_required_json(self.directory("questions") / f"{resolved_run_id}.json", label="questions")

    def learning_backlog(self, *, run_id: str | None = None) -> dict[str, Any]:
        resolved_run_id = safe_wiki_token(run_id, label="run id") if run_id else self.latest_run_id()
        if not resolved_run_id:
            raise FileNotFoundError("Wiki learning backlog not found")
        return self._read_required_json(
            self.directory("learning_backlog") / f"{resolved_run_id}.json",
            label="learning backlog",
        )

    def language_map(self, *, map_id: str = "clause-context-terms") -> dict[str, Any]:
        token = safe_wiki_token(map_id, label="language map id")
        return self._read_required_json(self.directory("language_maps") / f"{token}.json", label="language map")

    def clause_library(self) -> dict[str, Any]:
        records = self._clause_library_source_records()
        language_map = self._optional_language_map()
        categories = self._build_clause_library_categories(records, language_map)
        category_count = len(categories)
        subcategory_count = sum(len(category["children"]) for category in categories)
        evidence_refs = sum(int(child["evidence_count"]) for category in categories for child in category["children"])
        language_terms = sum(int(child["language_term_count"]) for category in categories for child in category["children"])
        agreement_ids = {
            source["source_id"]
            for category in categories
            for child in category["children"]
            for source in child["sources"]
            if source["source_type"] == "agreement"
        }
        reference_ids = {
            source["source_id"]
            for category in categories
            for child in category["children"]
            for source in child["sources"]
            if source["source_type"] == "reference"
        }
        return {
            "schema_version": CLAUSE_LIBRARY_SCHEMA_VERSION,
            "scope_focus": (self.manifest() or {}).get("scope_focus"),
            "orientation": "global_clause_library",
            "filter_role": "Council and agreement selection are evidence filters, not the primary navigation.",
            "summary": {
                "categories": category_count,
                "subcategories": subcategory_count,
                "evidence_refs": evidence_refs,
                "language_terms": language_terms,
                "agreement_sources": len(agreement_ids),
                "reference_sources": len(reference_ids),
                "questions": len(wikiAsList(self.questions().get("questions"))) if self.latest_run_id() else 0,
                "learning_backlog_items": len(wikiAsList(self.learning_backlog().get("items"))) if self.latest_run_id() else 0,
            },
            "categories": categories,
        }

    def _optional_language_map(self) -> dict[str, Any]:
        try:
            return self.language_map()
        except FileNotFoundError:
            return {"terms": []}

    def _clause_library_source_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(self._json_files("document_maps"), key=lambda item: item.stem):
            payload = read_json_file(path) or {}
            records.append({
                "source_type": "agreement",
                "source_id": str(payload.get("agreement_id") or path.stem).lower(),
                "source_name": payload.get("agreement_name") or payload.get("agreement_id") or path.stem,
                "payload": payload,
            })
        for path in sorted(self._json_files("reference_inputs"), key=lambda item: item.stem):
            payload = read_json_file(path) or {}
            records.append({
                "source_type": "reference",
                "source_id": str(payload.get("source_id") or path.stem).lower(),
                "source_name": payload.get("source_name") or payload.get("source_id") or path.stem,
                "payload": payload,
            })
        return records

    def _build_clause_library_categories(
        self,
        records: list[dict[str, Any]],
        language_map: dict[str, Any],
    ) -> list[dict[str, Any]]:
        term_lookup = {
            str(term.get("canonical_term") or ""): term
            for term in wikiAsList(language_map.get("terms"))
            if isinstance(term, dict)
        }
        source_name_lookup = {
            (record["source_type"], record["source_id"]): str(record["source_name"] or record["source_id"])
            for record in records
        }
        categories: list[dict[str, Any]] = []
        for category_spec in CLAUSE_LIBRARY_TREE:
            children = [
                self._build_clause_library_child(child_spec, records, term_lookup, source_name_lookup)
                for child_spec in category_spec["children"]
            ]
            source_ids = {
                (source["source_type"], source["source_id"])
                for child in children
                for source in child["sources"]
            }
            review_states: Counter[str] = Counter()
            for child in children:
                review_states.update(child["review_state_counts"])
            categories.append({
                "id": category_spec["id"],
                "label": category_spec["label"],
                "description": category_spec["description"],
                "evidence_count": sum(int(child["evidence_count"]) for child in children),
                "section_count": sum(int(child["section_count"]) for child in children),
                "page_count": sum(int(child["page_count"]) for child in children),
                "language_term_count": sum(int(child["language_term_count"]) for child in children),
                "source_count": len(source_ids),
                "review_state_counts": dict(sorted(review_states.items())),
                "children": children,
            })
        return categories

    def _build_clause_library_child(
        self,
        child_spec: dict[str, Any],
        records: list[dict[str, Any]],
        term_lookup: dict[str, dict[str, Any]],
        source_name_lookup: dict[tuple[str, str], str],
    ) -> dict[str, Any]:
        tags = {str(tag) for tag in child_spec.get("tags") or []}
        terms = {str(term) for term in child_spec.get("terms") or []}
        pages: set[tuple[str, str, int | None]] = set()
        sections: list[dict[str, Any]] = []
        examples: list[dict[str, Any]] = []
        source_pages: dict[tuple[str, str], set[int | None]] = defaultdict(set)
        review_states: Counter[str] = Counter()
        for record in records:
            payload = record["payload"]
            for page in wikiAsList(payload.get("pages")):
                if not isinstance(page, dict) or not _wiki_record_has_any_tag(page, tags):
                    continue
                source_ref = {
                    "source_id" if record["source_type"] == "reference" else "agreement_id": record["source_id"],
                    "page": page.get("page"),
                }
                normal_ref = _normalise_wiki_ref(source_ref)
                pages.add(normal_ref)
                source_pages[(normal_ref[0], normal_ref[1])].add(normal_ref[2])
                review_states[str(payload.get("review_state") or "proposed")] += 1
            for section in wikiAsList(payload.get("sections")):
                if not isinstance(section, dict) or not _wiki_record_has_any_tag(section, tags):
                    continue
                source_ref = section.get("source_ref") if isinstance(section.get("source_ref"), dict) else {}
                normal_ref = _normalise_wiki_ref(source_ref)
                source_pages[(normal_ref[0], normal_ref[1])].add(normal_ref[2])
                sections.append(section)
                review_states[str(section.get("review_state") or payload.get("review_state") or "proposed")] += 1
                if len(examples) < 6:
                    examples.append({
                        "title": section.get("title") or section.get("heading") or "Detected section",
                        "excerpt": section.get("evidence_excerpt") or "",
                        "source_ref": source_ref,
                        "relevance": section.get("clause_context_relevance") or section.get("standard_band_relevance"),
                    })
        language_records = [term_lookup[term] for term in sorted(terms) if term in term_lookup]
        for term in language_records:
            for observed in wikiAsList(term.get("observed_terms")):
                if not isinstance(observed, dict):
                    continue
                for source_ref in wikiAsList(observed.get("source_refs")):
                    normal_ref = _normalise_wiki_ref(source_ref)
                    if normal_ref[1]:
                        source_pages[(normal_ref[0], normal_ref[1])].add(normal_ref[2])
        sources = []
        for (source_type, source_id), page_values in sorted(source_pages.items(), key=lambda item: (item[0][0], item[0][1])):
            if not source_id:
                continue
            pages_sorted = sorted(page for page in page_values if page is not None)
            sources.append({
                "source_type": source_type,
                "source_id": source_id,
                "source_name": source_name_lookup.get((source_type, source_id), source_id),
                "pages": pages_sorted[:8],
                "page_count": len(pages_sorted),
            })
        observed_terms = []
        for term in language_records:
            for observed in wikiAsList(term.get("observed_terms")):
                if isinstance(observed, dict):
                    observed_terms.append({
                        "canonical_term": term.get("canonical_term"),
                        "observed_term": observed.get("observed_term"),
                        "count": observed.get("count") or 0,
                    })
        return {
            "id": child_spec["id"],
            "label": child_spec["label"],
            "description": child_spec["description"],
            "tags": sorted(tags),
            "terms": sorted(terms),
            "evidence_count": len(pages) + len(sections) + sum(int(item.get("count") or 0) for item in observed_terms),
            "page_count": len(pages),
            "section_count": len(sections),
            "language_term_count": len(language_records),
            "observed_terms": sorted(observed_terms, key=lambda item: (-int(item["count"]), str(item["observed_term"])))[:8],
            "sources": sources[:12],
            "source_count": len(sources),
            "review_state_counts": dict(sorted(review_states.items())),
            "examples": examples,
        }

    def _artifact_metadata(self, path: Path) -> dict[str, Any]:
        if path.suffix.lower() != ".json":
            return {}
        payload = read_json_file(path)
        if not isinstance(payload, dict):
            return {}
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        return {
            "schema_version": payload.get("schema_version"),
            "artifact_id": payload.get("artifact_id") or payload.get("source_id"),
            "artifact_type": payload.get("artifact_type"),
            "title": payload.get("title") or payload.get("source_name") or payload.get("artifact_id"),
            "wiki_role": payload.get("wiki_role"),
            "scope_focus": payload.get("scope_focus"),
            "gold_comparator_target": payload.get("gold_comparator_target")
            if isinstance(payload.get("gold_comparator_target"), dict)
            else None,
            "summary": summary,
        }

    def _entitlement_clause_evidence(self) -> dict[str, dict[str, Any]]:
        evidence_dir = self.directory("artifacts") / "entitlement-clause-evidence"
        if not evidence_dir.exists():
            return {}
        records: dict[str, dict[str, Any]] = {}
        for path in sorted(evidence_dir.glob("*.json"), key=lambda item: item.stem):
            payload = read_json_file(path)
            if not isinstance(payload, dict):
                continue
            entitlement_id = str(payload.get("entitlement_id") or "").strip()
            if entitlement_id:
                records[entitlement_id] = payload
        return records

    @staticmethod
    def _source_evidence_by_council(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        if not isinstance(payload, dict):
            return {}
        rows: dict[str, dict[str, Any]] = {}
        for item in wikiAsList(payload.get("council_evidence")):
            if not isinstance(item, dict):
                continue
            council = str(item.get("council") or "").strip().casefold()
            if council:
                rows[council] = item
        return rows

    @staticmethod
    def _source_global_takeaway(payload: dict[str, Any] | None) -> str:
        if not isinstance(payload, dict):
            return ""
        explicit = str(payload.get("global_takeaway") or "").strip()
        if explicit:
            return explicit
        label = str(payload.get("label") or "This entitlement").strip()
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        councils = int(summary.get("councils") or 0)
        source_backed = int(summary.get("source_clause_observed") or 0)
        out_of_scope = int(summary.get("rows_with_only_out_of_scope_candidates") or 0)
        no_candidate = int(summary.get("rows_with_no_candidate_pages") or 0)
        needs_review = int((summary.get("candidate_subclass_counts") or {}).get("Needs Review") or 0)
        if not councils:
            return ""
        return (
            f"Across the current source evidence set, {label} is source-backed in {source_backed} of {councils} councils. "
            f"The remaining rows are not source-backed for this entitlement: {out_of_scope} have only outside-boundary "
            f"or lookalike candidates, {no_candidate} have no candidate text, and {needs_review} candidates need review."
        )

    def gold_comparator_target(self, *, artifact_id: str = "ballarat-entitlement-benchmark-exemplar") -> dict[str, Any]:
        token = safe_wiki_token(artifact_id, label="gold comparator artifact id")
        path = self.directory("artifacts") / "downstream-analysis-exemplars" / f"{token}.json"
        payload = self._read_required_json(path, label="gold comparator target")
        clause_evidence = self._entitlement_clause_evidence()
        definition_overrides = entitlement_definition_overrides(self.paths.root)
        categories = []
        for category in wikiAsList(payload.get("categories")):
            if not isinstance(category, dict):
                continue
            children = []
            for entitlement in wikiAsList(category.get("entitlements")):
                if not isinstance(entitlement, dict):
                    continue
                mapping = entitlement.get("semantic_mapping") if isinstance(entitlement.get("semantic_mapping"), dict) else {}
                concept = mapping.get("concept") if isinstance(mapping.get("concept"), dict) else {}
                comparator = mapping.get("comparator_semantics") if isinstance(mapping.get("comparator_semantics"), dict) else {}
                target = mapping.get("target_semantics") if isinstance(mapping.get("target_semantics"), dict) else {}
                quantification = (
                    mapping.get("quantification_semantics")
                    if isinstance(mapping.get("quantification_semantics"), dict)
                    else {}
                )
                supportability = (
                    mapping.get("supportability_semantics")
                    if isinstance(mapping.get("supportability_semantics"), dict)
                    else {}
                )
                review = mapping.get("review_semantics") if isinstance(mapping.get("review_semantics"), dict) else {}
                row_model = entitlement.get("row_model") if isinstance(entitlement.get("row_model"), dict) else {}
                entitlement_id = str(entitlement.get("entitlement_id") or "")
                source_payload = clause_evidence.get(entitlement_id)
                source_rows = self._source_evidence_by_council(source_payload)
                source_summary = source_payload.get("summary") if isinstance(source_payload, dict) and isinstance(source_payload.get("summary"), dict) else {}
                source_methodology = source_payload.get("methodology") if isinstance(source_payload, dict) and isinstance(source_payload.get("methodology"), dict) else {}
                source_ab_test = source_payload.get("ab_test") if isinstance(source_payload, dict) and isinstance(source_payload.get("ab_test"), dict) else {}
                source_boundary = source_payload.get("classification_boundary") if isinstance(source_payload, dict) and isinstance(source_payload.get("classification_boundary"), dict) else {}
                source_definition = source_payload.get("definition") if isinstance(source_payload, dict) else None
                override_definition = definition_overrides.get(entitlement_id)
                source_global_takeaway = self._source_global_takeaway(source_payload)
                source_status = "source_clause_evidence_enriched" if source_payload else "gold_exemplar_takeaway"
                source_next_state = "review_source_clause_normalisation" if source_payload else "recreate_from_source_clause_evidence"
                report_entries = [entry for entry in wikiAsList(comparator.get("entries")) if isinstance(entry, dict)]
                merged_council_evidence = []
                seen_councils: set[str] = set()
                seen_source_keys: set[str] = set()
                for entry in report_entries:
                    council_key = str(entry.get("council") or "").strip().casefold()
                    source_row = source_rows.get(council_key, {})
                    if council_key:
                        seen_councils.add(council_key)
                    if source_row:
                        seen_source_keys.add(
                            f"{str(source_row.get('council') or '').strip().casefold()}|{str(source_row.get('agreement_id') or '').strip().casefold()}"
                        )
                    merged_council_evidence.append({
                        "council": entry.get("council"),
                        "finding": source_row.get("finding") or entry.get("finding"),
                        "report_finding": entry.get("finding"),
                        "presence": source_row.get("presence") or entry.get("presence"),
                        **wiki_source_evidence_projection(source_row),
                        "quantum_signals": wikiAsList(source_row.get("quantum_signals") or entry.get("quantum_signals")),
                        "normalised_values": wikiAsList(source_row.get("normalised_values")),
                        "scope": entry.get("scope"),
                        "scope_signals": wikiAsList(entry.get("scope_signals")),
                        "source_ref": source_row.get("source_ref") or {
                            "source_type": "gold_exemplar_report",
                            "artifact_id": token,
                            "evidence_state": "pending_source_clause_link",
                        },
                        "source_evidence": source_row or None,
                    })
                if source_payload:
                    for source_row in wikiAsList(source_payload.get("council_evidence")):
                        if not isinstance(source_row, dict):
                            continue
                        council_key = str(source_row.get("council") or "").strip().casefold()
                        source_key = f"{council_key}|{str(source_row.get('agreement_id') or '').strip().casefold()}"
                        if not council_key or source_key in seen_source_keys:
                            continue
                        seen_source_keys.add(source_key)
                        merged_council_evidence.append({
                            "council": source_row.get("council"),
                            "finding": source_row.get("finding"),
                            "report_finding": None,
                            "presence": source_row.get("presence"),
                            **wiki_source_evidence_projection(source_row),
                            "quantum_signals": wikiAsList(source_row.get("quantum_signals")),
                            "normalised_values": wikiAsList(source_row.get("normalised_values")),
                            "scope": "standard_employees",
                            "scope_signals": wikiAsList(source_row.get("scope_signals")),
                            "source_ref": source_row.get("source_ref") or {},
                            "source_evidence": source_row,
                        })
                children.append({
                    "entitlement_id": entitlement_id,
                    "label": entitlement.get("entitlement_label"),
                    "definition": override_definition or source_definition or entitlement.get("definition"),
                    "classification_boundary": source_boundary,
                    "taxonomy_path": wikiAsList(concept.get("human_taxonomy_path")),
                    "category": entitlement.get("category"),
                    "scope": entitlement.get("scope") if isinstance(entitlement.get("scope"), dict) else {},
                    "clause_context_tags": wikiAsList(entitlement.get("clause_context_tags")),
                    "comparison_basis": concept.get("comparison_basis"),
                    "quantification": quantification,
                    "target": {
                        "council": target.get("target_council"),
                        "presence": target.get("presence"),
                        "comparator_posture": target.get("comparator_posture"),
                        "takeaway": target.get("takeaway") or row_model.get("target_takeaway"),
                    },
                    "supportability": {
                        **supportability,
                        **({
                            "current_support_level": "source_clause_evidence",
                            "production_support_status": "source_clause_search_partial",
                            "source_evidence_summary": source_summary,
                            "source_evidence_methodology": source_methodology,
                            "source_evidence_ab_test": source_ab_test,
                        } if source_payload else {}),
                    },
                    "review": review,
                    "council_evidence": merged_council_evidence,
                    "analysis": {
                        "status": source_status,
                        "quick_takeaway": source_global_takeaway or row_model.get("target_takeaway") or target.get("takeaway"),
                        "next_state": source_next_state,
                        "source_evidence_summary": source_summary,
                        "source_evidence_methodology": source_methodology,
                        "source_evidence_ab_test": source_ab_test,
                    },
                })
            categories.append({
                "category_id": category.get("category_id"),
                "label": category.get("label"),
                "description": category.get("description"),
                "row_count": len(children),
                "children": children,
            })
        return {
            "schema_version": "wiki.gold_comparator_target.v1",
            "artifact_id": payload.get("artifact_id") or token,
            "title": payload.get("title"),
            "scope_focus": payload.get("scope_focus"),
            "gold_comparator_target": payload.get("gold_comparator_target")
            if isinstance(payload.get("gold_comparator_target"), dict)
            else {},
            "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
            "categories": categories,
            "excluded_rows": wikiAsList(payload.get("excluded_rows")),
        }

    def artifacts(self) -> dict[str, Any]:
        artifact_dir = self.directory("artifacts")
        files: list[dict[str, Any]] = []
        if artifact_dir.exists():
            for path in sorted((item for item in artifact_dir.rglob("*") if item.is_file()), key=lambda item: str(item)):
                info = file_info(path)
                info["relative_path"] = path.relative_to(self.wiki_root).as_posix()
                info.update(self._artifact_metadata(path))
                files.append(info)
        return {
            "artifact_root": str(artifact_dir),
            "artifacts": files,
            "count": len(files),
        }


@dataclass(frozen=True)
class AgentDiscoveryService:
    paths: WorkbenchPathService
    app: Any
    llm_status: Callable[[], dict[str, Any]]
    package_profiles: PackagingService
    report_assets: ReportAssetService | None = None
    report_exports: ReportExportService | None = None
    operator_commands: OperatorCommandService | None = None
    portable_validation: PortableValidationService | None = None
    wiki_layer: WikiLayerService | None = None

    def _report_assets(self) -> ReportAssetService:
        return self.report_assets or ReportAssetService(paths=self.paths)

    def _report_exports(self) -> ReportExportService:
        return self.report_exports or ReportExportService(paths=self.paths, report_assets=self._report_assets())

    def _operator_commands(self) -> OperatorCommandService:
        return self.operator_commands or OperatorCommandService(paths=self.paths)

    def _portable_validation(self) -> PortableValidationService:
        return self.portable_validation or PortableValidationService(paths=self.paths)

    def _wiki_layer(self) -> WikiLayerService:
        return self.wiki_layer or WikiLayerService(paths=self.paths)

    def status(self) -> dict[str, Any]:
        manifest = read_json_file(self.paths.root / "workbench-agent.json")
        portable_manifest = read_json_file(self.paths.root / "PORTABLE_MANIFEST.json")
        try:
            llm_status = self.llm_status()
        except Exception as exc:  # pragma: no cover - defensive health surface
            llm_status = {
                "ready": False,
                "message": str(exc),
            }
        routes = route_catalog(self.app)
        return {
            "ok": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project": {
                "id": "municipal-benchmark-eba-workbench",
                "label": "Municipal Benchmark EBA Workbench",
                "root": str(self.paths.root),
                "platform": platform.platform(),
                "python": platform.python_version(),
            },
            "manifest": {
                "exists": manifest is not None,
                "version": (manifest or {}).get("version"),
                "schema_version": (manifest or {}).get("schema_version"),
            },
            "portable_manifest": {
                "exists": portable_manifest is not None,
                "schema_version": (portable_manifest or {}).get("schema_version"),
            },
            "llm": {
                "provider": llm_status.get("provider"),
                "model": llm_status.get("model"),
                "ready": llm_status.get("ready"),
                "text_capable": llm_status.get("text_capable"),
                "vision_capable": llm_status.get("vision_capable"),
            },
            "package_profile": self.package_profiles.status(),
            "report_assets": self._report_assets().status(),
            "report_exports": self._report_exports().status(),
            "operator_commands": self._operator_commands().status(),
            "portable_validation": self._portable_validation().status(),
            "wiki_layer": self._wiki_layer().status(),
            "routes": {
                "count": len(routes),
                "agent_routes": [route for route in routes if route["path"].startswith("/api/agent")],
            },
        }

    def catalog(self) -> dict[str, Any]:
        return {
            "project": "municipal-benchmark-eba-workbench",
            "datasets": self.paths.datasets(),
            "directories": self.paths.directories(),
            "packaging": self.package_profiles.status(),
            "report_assets": self._report_assets().catalog(),
            "report_exports": self._report_exports().catalog(),
            "operator_commands": self._operator_commands().catalog(),
            "portable_validation": self._portable_validation().catalog(),
            "wiki_layer": self._wiki_layer().catalog(),
            "routes": route_catalog(self.app),
        }

    def datasets_catalog(self) -> dict[str, Any]:
        return {
            "project": "municipal-benchmark-eba-workbench",
            "datasets": self.paths.datasets(),
        }

    def actions(self) -> dict[str, Any]:
        return {
            "project": "municipal-benchmark-eba-workbench",
            "default_policy": "Use UI-equivalent routes and preserve governance events.",
            "actions": agent_actions(),
            "package_actions": self.package_profiles.actions(),
            "report_export_actions": self._report_exports().actions(),
            "operator_actions": self._operator_commands().actions(),
            "portable_validation_actions": self._portable_validation().actions(),
            "wiki_actions": self._wiki_layer().actions(),
        }

    def io(self) -> dict[str, Any]:
        return {
            "project": "municipal-benchmark-eba-workbench",
            "root": str(self.paths.root),
            "safety": {
                "write_boundary": str(self.paths.root),
                "do_not_write_outside_root": True,
                "never_package_by_default": [
                    ".env",
                    ".venv",
                    ".venv-win",
                    "node_modules",
                    "vendor",
                    "__pycache__",
                ],
                "governance_note": "Agent actions should use the same API/services as the UI and must not bypass accept/promote/unwind rules.",
            },
            "directories": self.paths.directories(),
            "manifests": {
                "agent": file_info(self.paths.root / "workbench-agent.json"),
                "portable": file_info(self.paths.root / "PORTABLE_MANIFEST.json"),
            },
            "package_profile": self.package_profiles.status(),
            "packaging": self.package_profiles.package_plan(),
            "report_assets": self._report_assets().catalog(),
            "report_exports": self._report_exports().catalog(),
            "operator_commands": self._operator_commands().io(),
            "portable_validation": self._portable_validation().io(),
            "wiki_layer": self._wiki_layer().io(),
        }



@dataclass(frozen=True)
class AnalysisAssetService:
    build_uplift_rules_analysis: Callable[..., dict[str, Any]]
    build_pay_tables_analysis: Callable[..., dict[str, Any]]
    build_end_of_band_dollars_analysis: Callable[..., dict[str, Any]]
    build_review_learning_snapshot: Callable[..., dict[str, Any]]
    load_distribution_point_analysis_asset: Callable[[], dict[str, Any] | None]
    materialize_distribution_point_analysis: Callable[..., dict[str, Any]]
    rebuild_analysis_data_set: Callable[..., dict[str, Any]]
    report_assets: ReportAssetService | None = None

    def _attach_report_asset_manifest(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.report_assets is None:
            return payload
        manifest = self.report_assets.materialize_distribution_point_analysis_manifest(payload)
        payload["report_asset"] = self.report_assets.manifest_summary(manifest)
        return payload

    def uplift_rules(self, *, include_split_parents: bool = False) -> dict[str, Any]:
        return self.build_uplift_rules_analysis(include_split_parents=include_split_parents)

    def pay_tables(self, *, include_split_parents: bool = False) -> dict[str, Any]:
        return self.build_pay_tables_analysis(include_split_parents=include_split_parents)

    def end_of_band_dollars(self, *, include_split_parents: bool = False) -> dict[str, Any]:
        return self.build_end_of_band_dollars_analysis(include_split_parents=include_split_parents)

    def review_learning(self, *, include_split_parents: bool = False) -> dict[str, Any]:
        return self.build_review_learning_snapshot(include_split_parents=include_split_parents)

    def distribution_point_analysis(
        self,
        *,
        include_split_parents: bool = False,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        if not force_refresh:
            cached = self.load_distribution_point_analysis_asset()
            if cached is not None:
                return cached
        payload = self.materialize_distribution_point_analysis(include_split_parents=include_split_parents)
        return self._attach_report_asset_manifest(payload)

    def rebuild(
        self,
        data_set: str,
        *,
        include_split_parents: bool = False,
    ) -> dict[str, Any]:
        normalised = data_set.replace("-", "_")
        rebuild = self.rebuild_analysis_data_set(
            normalised,
            include_split_parents=include_split_parents,
        )
        if normalised == "pay_tables":
            analysis = self.pay_tables(include_split_parents=include_split_parents)
        elif normalised == "end_of_band_dollars":
            analysis = self.end_of_band_dollars(include_split_parents=include_split_parents)
        else:
            analysis = self.uplift_rules(include_split_parents=include_split_parents)
        derived_assets: dict[str, Any] = {}
        if normalised == "pay_tables":
            distribution_asset = self.materialize_distribution_point_analysis(
                include_split_parents=include_split_parents,
                pay_tables_analysis=analysis,
            )
            self._attach_report_asset_manifest(distribution_asset)
            derived_assets["distribution_point_analysis"] = {
                "asset_version": distribution_asset.get("asset_version"),
                "asset": distribution_asset.get("asset"),
                "report_asset": distribution_asset.get("report_asset"),
                "summary": distribution_asset.get("summary"),
            }
        return {
            "ok": True,
            "data_set": normalised,
            "rebuild": rebuild,
            "derived_assets": derived_assets,
            "analysis": analysis,
        }


@dataclass(frozen=True)
class IntakeService:
    load_canonical_councils: Callable[[], list[dict[str, str]]]
    canonical_council_reference_payload: Callable[[], dict[str, Any]]
    council_master_reference_payload: Callable[[], dict[str, Any]]
    council_job_source_registry_payload: Callable[[], dict[str, Any]]
    build_intake_quality_summary: Callable[..., dict[str, Any]]
    build_intake_candidate_rows: Callable[[], list[dict[str, Any]]]
    build_council_audit_report: Callable[[str], dict[str, Any]]
    fetch_fair_work_registry_intake: Callable[..., dict[str, Any]]
    load_intake_decisions: Callable[[], dict[str, dict[str, Any]]]
    intake_workflow_dependencies: Callable[[], intake_workflow_module.IntakeWorkflowDependencies]

    def active_canonical_councils(self) -> list[dict[str, str]]:
        return [row for row in self.load_canonical_councils() if row.get("status") == "active"]

    def canonical_council_reference(self) -> dict[str, Any]:
        return self.canonical_council_reference_payload()

    def council_master_reference(self) -> dict[str, Any]:
        return self.council_master_reference_payload()

    def council_job_source_registry(self) -> dict[str, Any]:
        return self.council_job_source_registry_payload()

    def canonical_council_count(self) -> dict[str, int]:
        return {"total": len(self.load_canonical_councils())}

    def intake_quality(self, *, force_refresh: bool = False) -> dict[str, Any]:
        return self.build_intake_quality_summary(force_refresh=force_refresh)

    def intake_candidates(self) -> list[dict[str, Any]]:
        return self.build_intake_candidate_rows()

    def council_audit(self, council_name: str) -> dict[str, Any]:
        return self.build_council_audit_report(council_name)

    def fetch_registry(
        self,
        *,
        force_refresh: bool = True,
        fetch_pdfs: bool = False,
        pdf_limit: int | None = None,
    ) -> dict[str, Any]:
        return self.fetch_fair_work_registry_intake(
            force_registry=force_refresh,
            fetch_pdfs=fetch_pdfs,
            pdf_limit=pdf_limit,
        )

    def intake_decisions(self) -> dict[str, dict[str, Any]]:
        return self.load_intake_decisions()

    def record_candidate_decision(
        self,
        ae_id: str,
        *,
        status: str,
        reason: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        return intake_workflow_module.intake_decision_response(
            ae_id,
            status=status,
            reason=reason,
            notes=notes,
            deps=self.intake_workflow_dependencies(),
        )

    def freeze_candidate(self, ae_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
        return intake_workflow_module.intake_freeze_candidate_response(
            ae_id,
            force_refresh=force_refresh,
            deps=self.intake_workflow_dependencies(),
        )



@dataclass(frozen=True)
class GovernanceEventService:
    scenario_governance_dependencies: Callable[[], scenario_governance_module.ScenarioGovernanceDependencies]

    @classmethod
    def from_context(cls, ctx: Any) -> GovernanceEventService:
        return cls(
            scenario_governance_dependencies=lambda: ctx._scenario_governance_dependencies(),
        )

    def run_uplift_rule_scenarios(self, ae_id: str, body: Any) -> dict[str, Any]:
        return scenario_governance_module.run_uplift_rule_scenarios(
            ae_id,
            body,
            self.scenario_governance_dependencies(),
        )

    def scenario_overrides(self, ae_id: str) -> dict[str, Any]:
        return scenario_governance_module.get_uplift_rule_scenario_overrides(
            ae_id,
            self.scenario_governance_dependencies(),
        )

    def save_scenario_overrides(self, ae_id: str, body: Any) -> dict[str, Any]:
        return scenario_governance_module.post_uplift_rule_scenario_overrides(
            ae_id,
            body,
            self.scenario_governance_dependencies(),
        )

    def save_scenario_note(self, ae_id: str, body: Any) -> dict[str, Any]:
        return scenario_governance_module.post_uplift_rule_scenario_note(
            ae_id,
            body,
            self.scenario_governance_dependencies(),
        )

    def clear_scenario_overrides(self, ae_id: str) -> dict[str, Any]:
        return scenario_governance_module.delete_uplift_rule_scenario_overrides(
            ae_id,
            self.scenario_governance_dependencies(),
        )

    def construct_pay_table(self, ae_id: str, body: Any) -> dict[str, Any]:
        return scenario_governance_module.construct_pay_table_for_period(
            ae_id,
            body,
            self.scenario_governance_dependencies(),
        )

    def promote_governed_set(self, ae_id: str, body: Any) -> dict[str, Any]:
        return scenario_governance_module.promote_governed_set(
            ae_id,
            body,
            self.scenario_governance_dependencies(),
        )

    def unwind_governed_set(self, ae_id: str, body: Any) -> dict[str, Any]:
        return scenario_governance_module.unwind_governed_set(
            ae_id,
            body,
            self.scenario_governance_dependencies(),
        )

    def governed_set(self, ae_id: str) -> dict[str, Any]:
        return scenario_governance_module.get_governed_set(
            ae_id,
            self.scenario_governance_dependencies(),
        )

    def rate_cap_status(self) -> dict[str, Any]:
        return scenario_governance_module.get_rate_cap_status(self.scenario_governance_dependencies())

    def confirm_rate_cap(self, body: Any) -> dict[str, Any]:
        return scenario_governance_module.post_rate_cap_confirm(
            body,
            self.scenario_governance_dependencies(),
        )


@dataclass(frozen=True)
class WorkbenchServices:
    paths: WorkbenchPathService
    packaging: PackagingService
    package_profiles: PackagingService
    report_assets: ReportAssetService
    report_exports: ReportExportService
    operator_commands: OperatorCommandService
    portable_validation: PortableValidationService
    wiki_layer: WikiLayerService
    agent_discovery: AgentDiscoveryService
    agreement_workspace: AgreementWorkspaceService
    governance_events: GovernanceEventService


def build_workbench_services(ctx: Any, app: Any) -> WorkbenchServices:
    paths = WorkbenchPathService.from_context(ctx)
    packaging = PackagingService(paths=paths)
    report_assets = ReportAssetService(paths=paths, now=ctx.now_iso)
    report_exports = ReportExportService(paths=paths, report_assets=report_assets, now=ctx.now_iso)
    operator_commands = OperatorCommandService(paths=paths)
    portable_validation = PortableValidationService(paths=paths, now=ctx.now_iso)
    wiki_layer = WikiLayerService(paths=paths)
    return WorkbenchServices(
        paths=paths,
        packaging=packaging,
        package_profiles=packaging,
        report_assets=report_assets,
        report_exports=report_exports,
        operator_commands=operator_commands,
        portable_validation=portable_validation,
        wiki_layer=wiki_layer,
        agent_discovery=AgentDiscoveryService(
            paths=paths,
            app=app,
            llm_status=ctx.api_llm_status,
            package_profiles=packaging,
            report_assets=report_assets,
            report_exports=report_exports,
            operator_commands=operator_commands,
            portable_validation=portable_validation,
            wiki_layer=wiki_layer,
        ),
        agreement_workspace=AgreementWorkspaceService.from_context(ctx),
        governance_events=GovernanceEventService.from_context(ctx),
    )
