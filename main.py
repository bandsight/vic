from __future__ import annotations

from collections import Counter
import json
import os
import ssl
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional local-dev helper
    load_dotenv = None

import requests

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".env"
if load_dotenv is not None:
    load_dotenv(ENV_FILE)

IMMUTABLE_DIR = ROOT / "documents" / "immutable"
REGISTRY_CSV = ROOT / "registers" / "source-document-register.csv"
VICTORIAN_COUNCILS_CSV = ROOT / "data" / "reference" / "victorian-councils.csv"
MULTI_COUNCIL_REGISTER = ROOT / "registers" / "multi-council-decisions.csv"
INTAKE_DECISIONS_JSON = ROOT / "registers" / "intake-decisions.json"
CANONICAL_DIR = ROOT / "canonical"
SCENARIO_OVERRIDES_DIR = ROOT / "scenario-overrides"
CACHE_DIR = ROOT / "cache"
CLEAR_RECORDS_DIR = ROOT / "var" / "clear-records"
STATIC_DIR = ROOT / "static"
ANALYSIS_ASSET_DIR = ROOT / "data" / "analysis"
DISTRIBUTION_POINT_ANALYSIS_JSON = ANALYSIS_ASSET_DIR / "distribution-point-analysis.json"
CANDIDATE_AGREEMENTS_JSON = ROOT / "data" / "bronze" / "phase1_source_build" / "candidate_agreements" / "candidate_agreements.json"

ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
CODEX_MODEL = "gpt-5.4"
PAGE_RENDER_DPI = 150

# Section picker regexes are defined in the uplift_rules subsystem and re-exported
# here so the rest of main.py (and tests importing `from main import ...`)
# continues to work unchanged.
from benchmarking_data_factory.uplift_rules.section_picker import (  # noqa: E402
    DOLLAR_PATTERN,
    PAY_KEYWORDS,
    UPLIFT_KEYWORDS,
    UPLIFT_STRONG_HEADINGS,
    rank_pay_table_pages as _rank_pay_table_pages,
    score_pages as _generic_score_pages,
)
from benchmarking_data_factory.workbench.source_documents import (  # noqa: E402
    SUSPECT_PDF_SIZE_BYTES,
)
from benchmarking_data_factory.workbench.review_sections import (  # noqa: E402
    REVIEW_SECTIONS,
    SECTION_LABELS,
    SECTIONS,
    VALID_SECTION_STATUSES,
    apply_section_status,
    derive_governed_set_status,
    done_count as review_done_count,
    section_statuses,
)
from benchmarking_data_factory.workbench import analysis_workspace as analysis_workspace_module  # noqa: E402
from benchmarking_data_factory.workbench import app_bootstrap as app_bootstrap_module  # noqa: E402
from benchmarking_data_factory.workbench import audit_report as audit_report_module  # noqa: E402
from benchmarking_data_factory.workbench import canonical_workflow as canonical_workflow_module  # noqa: E402
from benchmarking_data_factory.workbench import compatibility_exports as compatibility_exports_module  # noqa: E402
from benchmarking_data_factory.workbench import compatibility_wrappers as compatibility_wrappers_module  # noqa: E402
from benchmarking_data_factory.workbench import council_read_model as council_read_model_module  # noqa: E402
from benchmarking_data_factory.workbench import document_page_workflow as document_page_workflow_module  # noqa: E402
from benchmarking_data_factory.workbench import facade_bands as facade_bands_module  # noqa: E402
from benchmarking_data_factory.workbench import intake_workflow as intake_workflow_module  # noqa: E402
from benchmarking_data_factory.workbench import llm_service as llm_service_module  # noqa: E402
from benchmarking_data_factory.workbench import dependency_factories as dependency_factories_module  # noqa: E402
from benchmarking_data_factory.workbench import extraction_orchestration as extraction_orchestration_module  # noqa: E402
from benchmarking_data_factory.workbench import misc_facades as misc_facades_module  # noqa: E402
from benchmarking_data_factory.workbench import scenario_governance as scenario_governance_module  # noqa: E402
from benchmarking_data_factory.workbench import service_passthroughs as service_passthroughs_module  # noqa: E402
from benchmarking_data_factory.workbench import source_document_intake as source_document_intake_module  # noqa: E402
from benchmarking_data_factory.workbench import uplift_rules_workflow as uplift_rules_workflow_module  # noqa: E402
from benchmarking_data_factory.workbench.canonical_store import CanonicalCache  # noqa: E402
from benchmarking_data_factory.workbench.intake_candidates import (  # noqa: E402
    candidate_date_ordinal,
    candidate_lgas,
    candidate_rank_key,
    normalise_candidate_date,
)
from benchmarking_data_factory.workbench.llm_boundary import is_llm_error  # noqa: E402
from benchmarking_data_factory.workbench.report_values import (  # noqa: E402
    agreement_report_values,
    pay_table_report_values,
)
from benchmarking_data_factory.reference.councils import (  # noqa: E402
    active_canonical_council_lookup,
    canonical_council_reference_payload,
    load_canonical_councils,
)
from benchmarking_data_factory.reference.council_master import (  # noqa: E402
    council_master_reference_payload,
)
from benchmarking_data_factory.reference.council_jobs import (  # noqa: E402
    council_job_source_registry_payload,
)
from benchmarking_data_factory.spatial.council_geography import (  # noqa: E402
    analysis_geography_fields,
    build_council_geography_payload,
    geography_for_lga,
)
from benchmarking_data_factory.phase1.pipeline import run_phase1  # noqa: E402

_source_register_cache: dict[str, dict[str, str]] | None = None
_canonical_cache: CanonicalCache = {}
ALTERATION_KEYWORDS = extraction_orchestration_module.ALTERATION_KEYWORDS


def _score_pages(page_texts: list[str], pattern: Any) -> list[int]:
    if pattern is PAY_KEYWORDS:
        return _rank_pay_table_pages(page_texts)
    return _generic_score_pages(page_texts, pattern)


def _dependency_factories() -> dependency_factories_module.WorkbenchDependencyFactories:
    return dependency_factories_module.WorkbenchDependencyFactories(sys.modules[__name__])


def _source_document_intake_dependencies() -> source_document_intake_module.SourceDocumentIntakeDependencies:
    return _dependency_factories().source_document_intake_dependencies()


def _document_page_workflow_dependencies() -> document_page_workflow_module.DocumentPageWorkflowDependencies:
    return _dependency_factories().document_page_workflow_dependencies()


def _canonical_workflow_dependencies() -> canonical_workflow_module.CanonicalWorkflowDependencies:
    return _dependency_factories().canonical_workflow_dependencies()


def _llm_service_config() -> llm_service_module.LlmServiceConfig:
    return _dependency_factories().llm_service_config()


from benchmarking_data_factory.scenario_testing import run_scenarios  # noqa: E402
from benchmarking_data_factory.scenario_testing.normalise import (  # noqa: E402
    is_standard_band_level_row,
    standard_band_level_metadata,
)
from benchmarking_data_factory.scenario_testing.projector import construct_table, extract_rules_for_projection  # noqa: E402
from benchmarking_data_factory.uplift_rules.rate_cap.resolver import (  # noqa: E402
    RATE_CAP_DATA_DIR,
    get_year_status_row,
    invalidate_caches as invalidate_rate_cap_caches,
)
from benchmarking_data_factory.uplift_rules.suggest import suggest as run_uplift_suggest  # noqa: E402















_candidate_agreement_rows_cache: list[dict[str, Any]] | None = None
_candidate_agreements_cache: dict[str, dict[str, Any]] | None = None
_intake_decisions_cache: dict[str, dict[str, Any]] | None = None


_normalise_candidate_date = normalise_candidate_date
_candidate_date_ordinal = candidate_date_ordinal
_candidate_rank_key = candidate_rank_key
_candidate_lgas = candidate_lgas


service_passthroughs_module.bind_intake_state_passthroughs(globals(), sys.modules[__name__])


def _intake_workflow_dependencies() -> intake_workflow_module.IntakeWorkflowDependencies:
    return _dependency_factories().intake_workflow_dependencies()


misc_facades_module.bind_intake_workflow_facades(globals(), sys.modules[__name__])


def _audit_dependencies() -> audit_report_module.AuditReportDependencies:
    return _dependency_factories().audit_dependencies()


def _with_audit_dependencies(callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return _dependency_factories().with_audit_dependencies(callback, *args, **kwargs)


compatibility_exports_module.bind_audit_exports(globals())
compatibility_wrappers_module.bind_audit_wrappers(globals(), sys.modules[__name__])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


FWC_REQUEST_HEADERS = source_document_intake_module.FWC_REQUEST_HEADERS


service_passthroughs_module.bind_source_document_passthroughs(globals(), sys.modules[__name__])




_multi_council_cache: dict[str, dict[str, Any]] | None = None


service_passthroughs_module.bind_multi_council_passthroughs(globals(), sys.modules[__name__])

service_passthroughs_module.bind_document_page_passthroughs(globals(), sys.modules[__name__])
service_passthroughs_module.bind_canonical_passthroughs(globals(), sys.modules[__name__])


_anthropic_ssl_context: ssl.SSLContext | None = None


facade_bands_module.bind_llm_facade(globals(), sys.modules[__name__])


misc_facades_module.bind_uplift_facades(globals(), sys.modules[__name__])


def _uplift_workflow_dependencies() -> uplift_rules_workflow_module.UpliftRulesWorkflowDependencies:
    return _dependency_factories().uplift_workflow_dependencies()


facade_bands_module.bind_pay_table_utility_facade(globals(), sys.modules[__name__])


misc_facades_module.bind_council_api_facades(globals(), sys.modules[__name__])


def _council_read_model_dependencies() -> council_read_model_module.CouncilReadModelDependencies:
    return _dependency_factories().council_read_model_dependencies()


def _analysis_dependencies() -> analysis_workspace_module.AnalysisWorkspaceDependencies:
    return _dependency_factories().analysis_dependencies()


def _with_analysis_dependencies(callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return _dependency_factories().with_analysis_dependencies(callback, *args, **kwargs)


compatibility_exports_module.bind_analysis_exports(globals())
compatibility_wrappers_module.bind_analysis_wrappers(globals(), sys.modules[__name__])
misc_facades_module.bind_extraction_facades(globals(), sys.modules[__name__])


def _extraction_orchestration_dependencies() -> extraction_orchestration_module.ExtractionOrchestrationDependencies:
    return _dependency_factories().extraction_orchestration_dependencies()


ASSET_FILES = [
    "app.js",
    "style.css",
    "pdf-viewer.js",
    "display-values.js",
    "api-client.js",
    "report-export-state.js",
    "workbench-tree.js",
]


misc_facades_module.bind_app_facades(globals(), sys.modules[__name__])


def _pay_table_workflow_dependencies():
    return _dependency_factories().pay_table_workflow_dependencies()


def _agreement_extraction_dependencies():
    return _dependency_factories().agreement_extraction_dependencies()


def _document_routes_dependencies():
    return _dependency_factories().document_routes_dependencies()


def _intake_audit_reference_routes_dependencies():
    return _dependency_factories().intake_audit_reference_routes_dependencies()


def _analysis_spatial_routes_dependencies():
    return _dependency_factories().analysis_spatial_routes_dependencies()


misc_facades_module.bind_review_learning_facade(globals(), sys.modules[__name__])


def _council_action_routes_dependencies():
    return _dependency_factories().council_action_routes_dependencies()


def _llm_connection_routes_dependencies():
    return _dependency_factories().llm_connection_routes_dependencies()


def _scenario_governance_dependencies() -> scenario_governance_module.ScenarioGovernanceDependencies:
    return _dependency_factories().scenario_governance_dependencies()


def _with_scenario_governance_dependencies(callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return _dependency_factories().with_scenario_governance_dependencies(callback, *args, **kwargs)


compatibility_exports_module.bind_scenario_exports(globals())
compatibility_wrappers_module.bind_scenario_wrappers(globals(), sys.modules[__name__])


app = app_bootstrap_module.create_bootstrapped_app(sys.modules[__name__])

