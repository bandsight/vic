"""Static-asset smoke test: ensure Phase 4B frontend hooks are present."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "static" / "app.js"
STYLE_CSS = ROOT / "static" / "style.css"
INDEX_HTML = ROOT / "static" / "index.html"
DISPLAY_VALUES_JS = ROOT / "static" / "display-values.js"
API_CLIENT_JS = ROOT / "static" / "api-client.js"
REPORT_EXPORT_STATE_JS = ROOT / "static" / "report-export-state.js"
WORKBENCH_TREE_JS = ROOT / "static" / "workbench-tree.js"


def test_section_labels_uplifts_renamed():
    text = APP_JS.read_text(encoding="utf-8")
    assert 'uplifts: "Governed Set"' in text or "uplifts: 'Governed Set'" in text


def test_workspace_sections_follow_dependency_tree_order():
    text = APP_JS.read_text(encoding="utf-8")
    assert text.index('overview: "Overview"') < text.index('uplift_rules: "Uplift Rules"')
    assert text.index('uplift_rules: "Uplift Rules"') < text.index('pay_tables: "Pay Tables"')
    assert text.index('pay_tables: "Pay Tables"') < text.index('scenarios: "Scenarios"')
    assert text.index('scenarios: "Scenarios"') < text.index('uplifts: "Governed Set"')
    assert 'currentSection: "overview"' in text
    assert 'label: "Extraction"' in text
    assert 'label: "Validation"' in text
    assert 'label: "Governance"' in text


def test_workspace_clauses_page_is_removed():
    app_text = APP_JS.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert 'clauses: "Entitlements"' not in app_text
    assert 'SECTION_QA_WORKFLOW_ORDER = ["overview", "uplift_rules", "pay_tables", "scenarios", "end_of_band_dollars", "uplifts"]' in app_text
    assert 'section: SECTION_LABELS[extra] ? extra : "overview"' in app_text
    assert "renderEntitlementsPane" not in app_text
    assert "skipSyntheticHumanEntitlements" not in app_text
    assert "sections/clauses/status" not in app_text
    assert ".entitlements-workspace" not in style_text
    assert ".entitlement-panel" not in style_text


def test_frontend_uses_review_board_workspace_language():
    app_text = APP_JS.read_text(encoding="utf-8")
    index_text = INDEX_HTML.read_text(encoding="utf-8")
    visible_text = app_text + "\n" + index_text

    assert "Review Board" in visible_text
    assert "Agreement Workspace" in visible_text
    assert "Data Sets" in visible_text
    assert "Uplift Rules Entity Set" in visible_text
    assert "Settings" in visible_text
    assert "QA Matrix" not in visible_text
    assert "Module 01" not in visible_text
    assert "Module 02" not in visible_text
    assert "Module 03" not in visible_text
    assert "Module 04" not in visible_text
    assert "Analysis Workspace" not in visible_text
    assert "Review Workspace" not in visible_text


def test_analysis_workspace_frontend_hooks_present():
    app_text = APP_JS.read_text(encoding="utf-8")
    report_state_text = REPORT_EXPORT_STATE_JS.read_text(encoding="utf-8")
    index_text = INDEX_HTML.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")
    tree_text = WORKBENCH_TREE_JS.read_text(encoding="utf-8")

    assert '"navId": "nav-analysis"' in tree_text
    assert '"navId": "nav-analysis-pay-tables"' in tree_text
    assert 'id="view-analysis"' in index_text
    assert "/api/analysis/uplift-rules" in app_text
    assert "/api/analysis/pay-tables" in app_text
    assert "Pay Tables Data Asset" in app_text
    assert "hideSidePanel: true" in app_text
    assert "showCandidateDiagnostics: false" in app_text
    assert "renderAnalysisWorkspace" in app_text
    assert "analysis-data-table" in app_text
    assert "analysis-pay-table" in app_text
    assert ".analysis-shell" in style_text
    assert ".analysis-data-table" in style_text
    assert ".analysis-pay-table" in style_text
    assert ".analysis-rule-row" in style_text
    assert 'id="pay-candidate-quality-panel"' in index_text
    assert "renderPayCandidateQualityPanel" in app_text
    assert "candidate_quality" in app_text
    assert "Candidate false-positive analysis" in app_text
    assert "pay-candidate-quality-summary" in app_text
    assert "item.action || item.message || item.trigger" in app_text
    assert ".pay-candidate-quality-panel" in style_text
    assert ".pay-candidate-quality-summary" in style_text
    assert ".analysis-side-panel[hidden]" in style_text
    assert ".analysis-workbench-asset .analysis-rule-table" in style_text
    assert ".pay-candidate-reason-row" in style_text
    assert 'id="report-export-panel"' in index_text
    assert "/api/analysis/distribution-point-analysis/exports" in report_state_text
    assert "/api/analysis/distribution-point-analysis/report-asset/status" in report_state_text
    assert "renderReportExportPanel" in app_text
    assert "renderReportAssetLifecycle" in app_text
    assert "report-export-target-grid" in app_text
    assert "analysisChartRangeMode" in app_text
    assert "renderDistributionRangeToggle" in app_text
    assert "data-distribution-range" in app_text
    assert "distributionRangeOverlay" in app_text
    assert "CHART_BASE_DATE_SMOOTHED" in app_text
    assert "Date-smoothed" in app_text
    assert "dateSmoothedDistributionPointRows" in app_text
    assert "chart_smoothed_source_count" in app_text
    assert "selectedCouncilStatLabel" in app_text
    assert "selectedCouncilRawQuarterRow" in app_text
    assert "raw selected-quarter value" in app_text
    assert "Selected council date-smoothed" in app_text
    assert "comparatorCohortExtremeRows" in app_text
    assert "distribution-comparator-extreme-marker" in app_text
    assert "Trajectory date" in app_text
    assert "Local Government Victoria category" in app_text
    assert "Local Government Performance Reporting Framework group" in app_text
    assert "SEIFA means the ABS Socio-Economic Indexes for Areas" in app_text
    assert "analysisChartDistributionCohortKey" in app_text
    assert "selectedDistributionCohort" in app_text
    assert "setChartDistributionCohortKey" in app_text
    assert "renderReportingCohortExplainer" in app_text
    assert "Distribution curve" in app_text
    assert "Comparator marker" in app_text
    assert "distribution-cohort-badges" in app_text
    assert 'class="distribution-cohort-card distribution-cohort-${escapeHtml(cohort.key)}${selectedClass}${comparatorClass}"' in app_text
    assert 'data-analysis-distribution-cohort-key="${escapeHtml(cohort.key)}"' in app_text
    assert 'data-analysis-cohort-key="${escapeHtml(item.key)}"' in app_text
    assert 'aria-pressed="${pressed}"' in app_text
    assert "const distributionRows = distributionCohort?.rows?.length ? distributionCohort.rows : rows;" in app_text
    assert "const markerValues = [currentValue, cohortStats?.mean, ...comparatorExtremeValues].filter(Number.isFinite);" in app_text
    assert "const domainMin = Math.min(stats.min, stats.mean - (stats.stdDev * 3), ...markerValues);" in app_text
    assert "const pad = { left: 54, right: 26, top: 58, bottom: 42 };" in app_text
    assert "const markerLabelGap = 58;" in app_text
    assert "const leaderEndY = Math.min(curveY - 8, labelY + 10);" in app_text
    assert "const sidePosition = x <= stats.mean" in app_text
    assert "const boundaryTaper = Math.sin((Math.PI / 2) * sidePosition);" in app_text
    assert "const isBoundary = marker.percentileValue === 0 || marker.percentileValue === 100;" in app_text
    assert "salary boundary" in app_text
    assert "const curveMin = stats.min;" in app_text
    assert "const curveMax = stats.max;" in app_text
    assert "stats.mean," in app_text
    assert 'yScale(salaryDensity(value)).toFixed(1)' in app_text
    assert "boundaryPoint" not in app_text
    assert "Comparator Cohort" in app_text
    assert "Curve ${escapeHtml(distributionCohort?.label || \"Selected cohort\")} range" in app_text
    assert "Comparator ${escapeHtml(comparatorCohort?.label || \"Selected cohort\")} average" in app_text
    assert ".report-export-panel" in style_text
    assert ".report-export-lifecycle" in style_text
    assert ".report-export-target" in style_text
    assert ".distribution-range-toggle" in style_text
    assert ".distribution-range-overlay" in style_text
    assert ".distribution-comparator-extreme-marker line" in style_text
    assert "stroke: #2563eb;" in style_text
    assert "appearance: none;" in style_text
    assert ".distribution-cohort-card:hover" in style_text
    assert ".distribution-cohort-badges" in style_text
    assert ".distribution-cohort-explainer" in style_text
    assert ".distribution-percentile-boundary" in style_text


def test_audit_report_quality_standard_frontend_hooks_present():
    app_text = APP_JS.read_text(encoding="utf-8")
    index_text = INDEX_HTML.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert 'id="audit-quality-score"' in index_text
    assert 'id="audit-council-select"' in index_text
    assert 'id="audit-refresh"' in index_text
    assert "state.councilReference?.rows" in app_text
    assert "Quality Standard Score" in app_text
    assert "renderAuditQualityAgreementScore" in app_text
    assert "quality_standard" in app_text
    assert ".audit-quality-scorecard" in style_text
    assert ".audit-quality-agreement" in style_text


def test_wiki_cockpit_frontend_hooks_present():
    app_text = APP_JS.read_text(encoding="utf-8")
    index_text = INDEX_HTML.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")
    tree_text = WORKBENCH_TREE_JS.read_text(encoding="utf-8")

    assert '"navId": "nav-wiki"' in tree_text
    assert 'id="view-wiki"' in index_text
    assert 'id="wiki-document-maps"' in index_text
    assert 'id="wiki-map-detail"' in index_text
    assert 'id="wiki-reference-list"' in index_text
    assert "/api/wiki/status" in app_text
    assert "/api/wiki/document-maps" in app_text
    assert "/api/wiki/reference-inputs" in app_text
    assert "clause context" in app_text
    assert "renderWikiCockpit" in app_text
    assert "renderWikiMapDetail" in app_text
    assert "renderWikiReferenceList" in app_text
    assert "wikiArtifactSummaryLine" in app_text
    assert "entitlement rows" in app_text
    assert "recreate target" in app_text
    assert "specialist excluded" in app_text
    assert 'id="wiki-entitlement-detail"' in index_text
    assert "renderWikiEntitlementDetail" in app_text
    assert "Council Summary" in app_text
    assert "Global Takeaway" in app_text
    assert "Automation Coverage" in app_text
    assert "Outside boundary" in app_text
    assert "No candidate text" in app_text
    assert "not source-backed for this entitlement" in app_text
    assert "Evidence Method" in app_text
    assert "Evidence clauses" in app_text
    assert "Candidate context" in app_text
    assert "Source-backed evidence" in app_text
    assert "clause_segments" in app_text
    assert "Learned Patterns" in app_text
    assert "Included" in app_text
    assert "Excluded" in app_text
    assert "Needs Review" in app_text
    assert "rows_needing_absence_or_scope_automation" in app_text
    assert "source_evidence" in app_text
    assert "source_evidence_methodology" in app_text
    assert "source_evidence_ab_test" in app_text
    assert "learned_pattern_retest" in app_text
    assert "candidate_subclass_counts" in app_text
    assert "observed_subclasses" in app_text
    assert "classification_boundary" in app_text
    assert "normalised_values" in app_text
    assert "Comparator Lens" in app_text
    assert "Benchmark cohort" in app_text
    assert "wikiComparatorCouncilKey" in app_text
    assert "wikiComparatorCohortKey" in app_text
    assert "wikiLatestCouncilEvidenceRows" in app_text
    assert "wikiLatestAvailableEvidenceRow" in app_text
    assert "wikiPendingLatestEvidenceRow" in app_text
    assert "wikiEvidenceAgreementId" in app_text
    assert "source_ref?.agreement_id" in app_text
    assert "source_evidence?.agreement_id" in app_text
    assert "wikiSourceEvidenceSummaryForRows" in app_text
    assert "wikiEntitlementLandscapeDataset" in app_text
    assert "wiki.entitlement_landscape_dataset.v1" in app_text
    assert "plain_english_conclusions" in app_text
    assert "latest_agreement_not_searched" in app_text
    assert "rows_with_pending_latest_search" in app_text
    assert "latest council agreements" in app_text
    assert "buildWikiEntitlementCohorts" in app_text
    assert "wikiBenchmarkStats" in app_text
    assert "data-wiki-cohort-key" in app_text
    assert "data-wiki-comparator-council" in app_text
    assert "data-evidence-kind" in app_text
    assert "loadCouncilContext(nextAeId" in app_text
    assert "data-wiki-open-map" in app_text
    assert ".wiki-shell" in style_text
    assert ".wiki-reference-card" in style_text
    assert ".wiki-artifact-head" in style_text
    assert ".wiki-panel" in style_text
    assert ".wiki-map-table" in style_text
    assert ".wiki-source-excerpts" in style_text
    assert ".wiki-evidence-clause" in style_text
    assert ".wiki-evidence-clause-head" in style_text
    assert ".wiki-evidence-clause-text" in style_text
    assert ".wiki-evidence-segment-list" in style_text
    assert ".wiki-evidence-segment" in style_text
    assert ".wiki-source-values" in style_text
    assert ".wiki-automation-measurement" in style_text
    assert ".wiki-automation-metrics" in style_text
    assert ".wiki-evidence-method" in style_text
    assert ".wiki-method-chips" in style_text
    assert ".wiki-method-subblock" in style_text
    assert ".wiki-method-steps" in style_text
    assert ".wiki-boundary-grid" in style_text
    assert ".wiki-comparator-infographic" in style_text
    assert ".wiki-landscape-conclusions" in style_text
    assert ".wiki-cohort-selector" in style_text
    assert ".wiki-infographic-rail" in style_text
    assert ".wiki-benchmark-dot-source-backed" in style_text
    assert ".wiki-benchmark-dot-pending-latest" in style_text
    assert "--dot-fill" in style_text
    assert "--dot-image" in style_text
    assert "filter: none !important;" in style_text
    assert 'body[data-view="wiki"] #view-wiki.active' in style_text
    wiki_scroll_block = style_text.split('body[data-view="wiki"] #view-wiki.active', 1)[1].split("}", 1)[0]
    assert "overflow-y: auto;" in wiki_scroll_block
    assert "overflow-x: hidden;" in wiki_scroll_block
    wiki_main_block = style_text.split(".wiki-main-panel {", 1)[1].split("}", 1)[0]
    assert "overflow: visible;" in wiki_main_block


def test_global_status_rail_removed_for_clean_page_templates():
    app_text = APP_JS.read_text(encoding="utf-8")
    index_text = INDEX_HTML.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert 'class="top-status-bar"' not in index_text
    assert 'id="stage-rail"' not in index_text
    assert 'id="header-stats"' not in index_text
    assert "updateStageRail" in app_text
    assert ".top-status-bar" in style_text
    assert ".stage-badge" in style_text

    assert "renderEmptyState" in app_text
    assert "data-intake-empty-clear" in app_text
    assert "data-analysis-empty-clear" in app_text
    assert ".workbench-empty-state" in style_text


def test_frontend_supports_hash_routes_for_views_and_data_sets():
    text = APP_JS.read_text(encoding="utf-8")

    assert "parseWorkbenchRoute" in text
    assert "applyWorkbenchRouteFromHash" in text
    assert "syncWorkbenchRoute" in text
    assert "window.addEventListener(\"hashchange\"" in text
    assert "#data/" in text
    assert "#workspace/" in text
    assert 'encodeURIComponent(aeId)' in text
    assert "route.aeId" in text
    assert "openCouncil(route.aeId" in text


def test_quick_switch_shell_removed_for_clean_page_templates():
    app_text = APP_JS.read_text(encoding="utf-8")
    index_text = INDEX_HTML.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert 'id="quick-switch-open"' not in index_text
    assert 'id="quick-switch-dialog"' not in index_text
    assert "quickSwitchItems" in app_text
    assert "filterQuickSwitchItems" in app_text
    assert "RECENT_WORKBENCH_DESTINATIONS_KEY" in app_text
    assert "readRecentWorkbenchDestinations" in app_text
    assert "recordRecentWorkbenchDestination" in app_text
    assert "openWorkbenchRoute" in app_text
    assert "renderQuickSwitchResultRows" in app_text
    assert "quick-switch-section-heading" in app_text
    assert 'group: "Recent"' in app_text
    assert "wireQuickSwitch" in app_text
    assert 'key.toLowerCase() === "k"' in app_text
    assert ".quick-switch-panel" in style_text
    assert ".quick-switch-result" in style_text
    assert ".quick-switch-section-heading" in style_text


def test_current_view_link_copy_trigger_removed_for_clean_page_templates():
    app_text = APP_JS.read_text(encoding="utf-8")
    index_text = INDEX_HTML.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert 'id="current-link-copy"' not in index_text
    assert "currentWorkbenchUrl" in app_text
    assert "copyCurrentWorkbenchLink" in app_text
    assert "writeClipboardText" in app_text
    assert "window.navigator.clipboard.writeText" in app_text
    assert ".copy-link-trigger" in style_text
    assert ".top-status-actions" in style_text


def test_scenario_row_emits_dep_chips():
    text = APP_JS.read_text(encoding="utf-8")
    assert "scenario-dep-chip" in text
    assert "external_deps" in text
    assert "scenario-story-block" in text
    assert "renderScenarioCalculationStory" in text
    assert "Rule to test" in text
    assert "Source table" in text
    assert "Result" in text


def test_rule_expression_infers_rate_cap_value_from_accepted_rule_text():
    text = APP_JS.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")
    assert "extractRateCapPercentFromText" in text
    assert "rateCapDisplayFromRule" in text
    assert "raw.quantum_external_definition" in text
    assert 'addRuleDisplayField(fields, "rate cap"' in text
    assert 'rateCapDisplay ? "" : raw.quantum_external_ref' in text
    assert "rateCapValueFromStatus(dep.financial_year)" in text
    assert "rateCapDisplayValueForDep" in text
    assert "rule-expression-field-rate-cap" in style_text


def test_scenario_table_shows_prior_to_new_diff_columns():
    text = APP_JS.read_text(encoding="utf-8")
    assert "<th>↑ $</th>" in text
    assert "<th>↑ %</th>" in text
    assert "priorToNewDelta" in text
    assert "priorToNewPct" in text


def test_css_has_new_status_classes():
    text = STYLE_CSS.read_text(encoding="utf-8")
    assert ".scenario-row-table_resolved" in text
    assert ".scenario-row-needs_review" in text
    assert ".scenario-status-table_resolved" in text
    assert ".scenario-status-needs_review" in text
    assert ".scenario-dep-chip-confirmed" in text
    assert ".scenario-dep-chip-pending" in text


def test_rate_cap_admin_function_present():
    text = APP_JS.read_text(encoding="utf-8")
    assert "renderRateCapAdminPane" in text
    assert "/api/rate-caps/status" in text
    assert "/api/rate-caps/confirm" in text


def test_index_has_rate_cap_container():
    text = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="rate-cap-admin-container"' in text


def test_display_values_module_is_shared():
    app_text = APP_JS.read_text(encoding="utf-8")
    display_text = DISPLAY_VALUES_JS.read_text(encoding="utf-8")
    main_text = (ROOT / "main.py").read_text(encoding="utf-8")

    assert 'from "/static/display-values.js"' in app_text
    assert "displayDateRange" in display_text
    assert "displayCurrencyDelta" in display_text
    assert "display-values.js" in main_text


def test_api_client_module_is_shared():
    app_text = APP_JS.read_text(encoding="utf-8")
    api_client_text = API_CLIENT_JS.read_text(encoding="utf-8")
    main_text = (ROOT / "main.py").read_text(encoding="utf-8")

    assert 'from "/static/api-client.js"' in app_text
    assert "export async function api" in api_client_text
    assert "export function apiErrorMessage" in api_client_text
    assert "api-client.js" in main_text


def test_report_export_state_module_is_shared():
    app_text = APP_JS.read_text(encoding="utf-8")
    report_state_text = REPORT_EXPORT_STATE_JS.read_text(encoding="utf-8")
    main_text = (ROOT / "main.py").read_text(encoding="utf-8")

    assert 'from "/static/report-export-state.js"' in app_text
    assert "createReportExportState" in report_state_text
    assert "ensureReportExportCatalog" in report_state_text
    assert "updateReportAssetStatus" in report_state_text
    assert "report-export-state.js" in main_text


def test_module_three_buttons_use_neutral_workspace_style():
    text = STYLE_CSS.read_text(encoding="utf-8")

    assert "#view-workspace button" in text
    assert "#view-workspace button.primary" in text
    assert "#view-workspace .scenario-action-btn.accept" in text
    assert "#view-workspace .btn-promote-governed" in text
    assert "#view-workspace .btn-governed-undo" in text
    assert "background: #fff;" in text


def test_mb_application_report_theme_present():
    style_text = STYLE_CSS.read_text(encoding="utf-8")
    index_text = INDEX_HTML.read_text(encoding="utf-8")
    app_text = APP_JS.read_text(encoding="utf-8")

    assert "brand-mark-mb" in index_text
    assert "--mb-ocean-gradient" in style_text
    assert "section-report-brand" in app_text
    assert "var(--mb-deep-gradient)" in style_text


def test_workspace_header_prioritises_current_section_panel():
    style_text = STYLE_CSS.read_text(encoding="utf-8")
    app_text = APP_JS.read_text(encoding="utf-8")

    assert "section-work-visual" not in app_text
    assert "section-app-icon" not in app_text
    assert "grid-template-columns: minmax(280px, 1fr) minmax(160px, 1fr) minmax(280px, 1fr);" in style_text
    assert "section-card-scroll" in app_text


def test_intake_keeps_source_fetch_language_without_headline_metrics():
    app_text = APP_JS.read_text(encoding="utf-8")
    index_text = INDEX_HTML.read_text(encoding="utf-8")

    visible_text = app_text + "\n" + index_text
    assert 'id="intake-status-filter"' not in index_text
    assert 'id="intake-pdfs"' not in index_text
    assert "Fetch PDF" in visible_text
    assert "Fetched source" in visible_text
    assert "Frozen PDF" not in visible_text
    assert "Freeze PDF" not in visible_text


def test_governed_set_uses_save_accept_final_action():
    text = APP_JS.read_text(encoding="utf-8")

    assert "Governed set acceptance" in text
    assert 'buttonId: "governed-save"' in text
    assert "/sections/uplifts/status" in text
    assert 'body: JSON.stringify({ status: "done" })' in text


def test_uplift_rules_section_omits_provenance_card():
    app_text = APP_JS.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert "renderUpliftProvenance" not in app_text
    assert "uplift-provenance" not in app_text
    assert "uplift-provenance" not in style_text
    assert "mb-provenance" not in style_text


def test_uplift_rules_complete_state_keeps_human_qa_toggle_enabled():
    app_text = APP_JS.read_text(encoding="utf-8")

    complete_state = app_text.index('title: "Section complete"')
    state_end = app_text.index("};", complete_state)
    assert 'detail: "Uplift rules have been saved and accepted."' in app_text[complete_state:state_end]
    assert "disabled: false" in app_text[complete_state:state_end]


def test_uplift_rerun_candidates_stay_visible_and_reviewable():
    app_text = APP_JS.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert "upliftSuggestionIsPendingReview" in app_text
    assert "Candidate extraction run" in app_text
    assert "Extracted uplift rule candidates" in app_text
    assert "All extracted rules stay visible here" in app_text
    assert "toggle-uplift-candidate-rule" in app_text
    assert "includedUpliftSuggestionRules(suggestion)" in app_text
    assert "filterToCurrentCouncil: false" in app_text
    assert "/uplift-rules/suggestion" in app_text
    assert "Discard candidate run" in app_text
    assert ".uplift-rule-excluded" in style_text


def test_workspace_qa_gate_blocks_downstream_sections_until_upstream_acceptance():
    app_text = APP_JS.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert "function sectionQaGateBlocker" in app_text
    assert "openableWorkspaceSection(section, { notify: true })" in app_text
    assert "section-tab-locked" in app_text
    assert "section-pane-confirm-mode" in app_text
    assert "Accepted" in app_text
    assert "Edit mode" in app_text
    assert ".section-tab-locked" in style_text
    assert ".section-pane-confirm-mode" in style_text


def test_pay_tables_omits_legacy_extraction_review_panel():
    app_text = APP_JS.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert "Extraction review" not in app_text
    assert "No extraction yet" not in app_text
    assert "Add reviewed table to draft" not in app_text
    assert "pay-add-draft" not in app_text
    assert "renderExtractionPreview" not in app_text
    assert "addReviewedTableToDraft" not in app_text
    assert "pay-review-actions" not in style_text


def test_scenario_promote_uses_single_governed_action_and_undo_icon():
    app_text = APP_JS.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert "data-promote-governed" in app_text
    assert "data-promote-kinds" in app_text
    assert "data-governed-undo" in app_text
    assert "btn-promote-governed" in style_text
    assert "btn-governed-undo" in style_text
    assert "Promote pay table to Governed Set" not in app_text
    assert "Promote uplift rule to Governed Set" not in app_text
    assert "data-promote-kind=" not in app_text
    assert "data-unwind-kind=" not in app_text
    assert "btn-unwind" not in style_text


def test_review_board_progress_moves_left_of_action_grid():
    app_text = APP_JS.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert 'class="matrix-progress-readout"' in app_text
    assert app_text.index('class="matrix-card-progress ${showNextActionHint ? "" : "matrix-card-progress-compact"}"') < app_text.index('class="matrix-section-grid"')
    assert "matrix-status-chip-row" in app_text
    assert "MATRIX_SECTION_LABELS" in app_text
    assert "class=\"matrix-section-label\"" in app_text
    assert "MATRIX_CORE_REVIEW_SECTIONS" in app_text
    assert "matrixCoreProgress" in app_text
    assert "Core review complete" in app_text
    assert "All core workspace sections reviewed" in app_text
    assert "grid-template-columns: minmax(0, 0.92fr) minmax(500px, 660px);" in style_text
    assert "grid-template-columns: repeat(5, minmax(0, 1fr));" in style_text
    assert "matrix-card-progress-compact" in app_text
    assert "Decision required before modules" not in app_text
    assert ".matrix-progress-track" in style_text


def test_review_board_has_synthetic_human_completion_runner():
    app_text = APP_JS.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert "Run reviewer QA" in app_text
    assert "data-review-human-run" in app_text
    assert "queueSyntheticHumanReview" in app_text
    assert "saveSyntheticSectionHumanQa" in app_text
    assert "run.jobs[key].status = fallback.status" in app_text
    assert 'setSyntheticHumanJob(aeId, key, "queued", "Waiting for earlier review steps")' in app_text
    assert "Reviewer decisions" in app_text
    assert "syntheticHumanDecisionSummary" in app_text
    assert "Process was unremarkable" in app_text
    assert "/api/analysis/review-learning" in app_text
    assert "matrix-improvement-log" in app_text
    assert "matrix-decision-summary" in app_text
    assert "System improvement requested" in app_text
    assert "Continue after implementation" in app_text
    assert "SyntheticHumanSystemImprovementPause" in app_text
    assert "requestSyntheticSystemImprovement" in app_text
    assert "awaitingSystemImprovement" in app_text
    assert "Reviewer commentary" in app_text
    assert "addSyntheticHumanComment" in app_text
    assert "toggleMatrixAutomationDetails" in app_text
    assert "setMatrixAutomationDetailsOpen" in app_text
    assert 'event.key !== "Enter" && event.key !== " "' in app_text
    assert "I am still running" in app_text
    assert "confidently wrong in a suit" in app_text
    assert "numbers in the furniture" in app_text
    assert "Scenario QA is the argument room" in app_text
    assert "ritual paperwork in a tiny hat" in app_text
    assert "holdSyntheticHumanStepForImpact" in app_text
    assert "syntheticHumanStepMinimumMs" in app_text
    assert "matrix-reviewer-commentary" in style_text
    assert "matrix-system-improvement-request" in style_text


def test_synthetic_human_pay_qa_checks_table_cohorts():
    app_text = APP_JS.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert "resolveSyntheticPayTableCohorts" in app_text
    assert "syntheticPayTableCohort" in app_text
    assert "Duplicate pay tables need cohort review" in app_text
    assert "dropped specialised" in app_text
    assert "retained the general benchmark table set" in app_text
    assert "applySyntheticRuleAnchoredDatesToDraftTables" in app_text
    assert "post-snap duplicate resolution" in app_text
    assert "183-day snap guard" in app_text
    assert "loaded allowance rates" in app_text
    assert "standard indoor benchmark bandings" in app_text
    assert "standard technical/professional benchmark bandings" in app_text
    assert "general classification benchmark table" in app_text
    assert "multi-band standard rates" in app_text
    assert "standard rates" in app_text
    assert "single-band standard continuation" in app_text
    assert "syntheticPayTableBandNumbers" in app_text
    assert "syntheticPayTablePageNumbers" in app_text
    assert "syntheticPayTablePagesTouch" in app_text
    assert "syntheticPayTableOverlapProfile" in app_text
    assert "syntheticTablesCompatibleForContinuation" in app_text
    assert "syntheticUnknownTableCanMergeAsContinuation" in app_text
    assert "syntheticTableIsAbsorbedByKeeper" in app_text
    assert "Merged split-page standard rate continuation" in app_text
    assert "Removed partial duplicate pay table" in app_text
    assert "Merged unclear split-page pay table" in app_text
    assert "Unclear duplicate pay tables need human selection" in app_text
    assert "standard 38-hour table" in app_text
    assert "non-standard 35-hour table" in app_text
    assert "weekly: 0, annual: 1, fortnightly: 2" in app_text
    assert "other than physical" in app_text
    assert "current LGA table" in app_text
    assert "Split-agreement QA retained current LGA table" in app_text
    assert "all employees except" in app_text
    assert "legacy council cohort" in app_text
    assert "physical services loaded cohort" in app_text
    assert "community transport" in app_text
    assert "casual rates" in app_text
    assert "street cleaning" in app_text
    assert "art gallery annualised rates" in app_text
    assert "allowance schedule" in app_text
    assert "parks and gardens" in app_text
    assert "payAnchorWindow" in app_text
    assert "payExtractionPagePlan" in app_text
    assert "Trying fallback pay range" in app_text
    assert "clean - 12" in app_text
    assert "operational outdoor cohort" in app_text
    assert "Removed duplicate copy" in app_text
    assert "Removed same-title duplicate pay table" in app_text
    assert "Removed duplicate non-general pay table" in app_text
    assert "Removed overlapping generic duplicate pay table" in app_text
    assert "syntheticDistinctCohortTitlePair" in app_text
    assert "syntheticSameTitleDuplicate" in app_text
    assert "syntheticTablesHaveSameRates" in app_text
    assert "syntheticScenarioComputedOverrides" in app_text
    assert "syntheticScenarioPayTableOnly" in app_text
    assert "pass < 4" in app_text
    assert "table exists for this period but no uplift rule covers it" in app_text
    assert "use_computed_recommended" in app_text
    assert "isolated variance" in app_text
    assert "pay_table_cohort_resolution" in app_text
    assert "scenario_computed_override_policy" in app_text
    assert ".matrix-human-run-btn" in style_text
    assert ".matrix-human-steps" in style_text
    assert ".matrix-decision-summary" in style_text


def test_uplift_rule_table_binding_conflicts_surface_in_frontend():
    app_text = APP_JS.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")

    assert "table_alignment_issues" in app_text
    assert "renderUpliftTableAlignmentIssues" in app_text
    assert "Review uplift extraction before scenarios" in app_text
    assert "syntheticScenarioRuleExtractionIssues" in app_text
    assert "requestSyntheticRuleBindingImprovement" in app_text
    assert "uplift_rule_table_binding_conflict" in app_text
    assert "Stop scenario QA when an accepted uplift rule conflicts" in app_text
    assert ".uplift-alignment-card" in style_text
