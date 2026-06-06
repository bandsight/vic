"""Static smoke tests for the governed workbench capability tree."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "static" / "app.js"
INDEX_HTML = ROOT / "static" / "index.html"
STYLE_CSS = ROOT / "static" / "style.css"
TREE_JS = ROOT / "static" / "workbench-tree.js"


def _exported_json_array(name: str) -> list[dict]:
    text = TREE_JS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name} = (\[.*?\]);", text, flags=re.S)
    assert match, f"{name} export not found"
    return json.loads(match.group(1))


def _flatten(nodes: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for node in nodes:
        rows.append(node)
        rows.extend(_flatten(node.get("children", [])))
        rows.extend(_flatten(node.get("secondarySurfaces", [])))
    return rows


def test_capability_tree_top_level_branches_render_from_config():
    tree = _exported_json_array("WORKBENCH_CAPABILITY_TREE")
    labels = [node["label"] for node in tree]

    assert labels == [
        "Source & Custody",
        "Quantum & Timing",
        "Entitlement QA",
        "Data Marts",
        "Reports & Benchmarking",
        "Governance",
    ]

    index_text = INDEX_HTML.read_text(encoding="utf-8")
    app_text = APP_JS.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")
    assert 'id="capability-tree"' in index_text
    assert 'id="view-capability"' in index_text
    assert "WORKBENCH_CAPABILITY_TREE" in app_text
    assert "renderCapabilityTree" in app_text
    assert "renderCapabilityDashboard" in app_text
    assert 'class="capability-branch-summary"' in app_text
    assert "capabilityIconHtml" in app_text
    assert 'class="capability-branch-open"' in app_text
    assert "Expand or collapse" in app_text
    assert ".capability-tree" in style_text
    assert ".capability-icon-funnel" in style_text
    assert ".capability-icon-globe" in style_text
    assert ".capability-icon-database" in style_text
    assert ".capability-icon-chart" in style_text
    assert ".capability-icon-shield" in style_text
    assert ".capability-branch-children" in style_text
    assert ".capability-node::before" in style_text
    assert "border-left: 1px solid var(--tree-line);" in style_text

    by_id = {node["id"]: node for node in tree}
    assert by_id["source_custody"]["icon"] == "globe"


def test_existing_routes_are_preserved_in_capability_tree():
    nodes = _flatten(_exported_json_array("WORKBENCH_CAPABILITY_TREE"))
    routes = {node.get("route") for node in nodes}

    assert "#incoming" in routes
    assert "#intake" in routes
    assert "#matrix" in routes
    assert "#wiki" in routes
    assert "#audit" in routes
    assert "#admin" in routes
    assert "#data/uplift_rules" in routes
    assert "#data/pay_tables" in routes
    assert "#data/charts" in routes
    assert "#data/councils" in routes
    assert "#workspace/overview" in routes
    assert "#capability/source_custody/document_spine" in routes
    assert "#capability/data_marts" in routes
    assert "#capability/data_marts/datamart_inventory" in routes
    assert "#capability/clause_intelligence" in routes
    assert "/apps/pay-horizon-explorer/" in routes
    assert "/apps/small-council-state-scroll-report/" in routes

    app_text = APP_JS.read_text(encoding="utf-8")
    assert 'area === "capability"' in app_text
    assert 'const views = ["capability", "incoming", "intake", "job-intake", "job-pipeline", "matrix", "workspace", "analysis", "audit", "wiki", "admin"]' in app_text


def test_pay_branch_uses_single_workspace_entry_with_section_slot():
    tree = _exported_json_array("WORKBENCH_CAPABILITY_TREE")
    by_id = {node["id"]: node for node in tree}
    pay_children = by_id["pay_uplift"]["children"]

    assert [child["id"] for child in pay_children] == ["agreement_workspace"]
    assert pay_children[0]["route"] == "#workspace/overview"
    assert pay_children[0]["slot"] == "workspace_sections"


def test_clause_intelligence_is_a_peer_not_nested_under_pay():
    tree = _exported_json_array("WORKBENCH_CAPABILITY_TREE")
    by_id = {node["id"]: node for node in tree}

    assert "clause_intelligence" in by_id
    assert "pay_uplift" in by_id
    pay_child_ids = {child["id"] for child in by_id["pay_uplift"]["children"]}
    assert "clause_intelligence" not in pay_child_ids

    clause_child_ids = [child["id"] for child in by_id["clause_intelligence"]["children"]]
    assert clause_child_ids == [
        "entitlement_qa_inbox",
    ]
    assert [child["label"] for child in by_id["clause_intelligence"]["children"]] == ["QA Inbox"]
    assert by_id["clause_intelligence"]["hideOverviewLink"] is True

    source_child_ids = [child["id"] for child in by_id["source_custody"]["children"]]
    assert "document_spine" in source_child_ids
    source_routes = {child["id"]: child["route"] for child in by_id["source_custody"]["children"]}
    assert source_routes["document_spine"] == "#capability/source_custody/document_spine"
    assert next(child for child in by_id["source_custody"]["children"] if child["id"] == "document_spine")["label"] == "Wiki Base"

    secondary_ids = {surface["id"] for surface in by_id["clause_intelligence"]["secondarySurfaces"]}
    assert {
        "clause_cards",
        "feature_cards",
        "entitlement_cards",
        "human_review_worksheet",
        "entitlement_library_wiki",
        "clause_evidence_graph",
        "reference_edges",
        "entitlement_locator",
        "qa_review_pack",
        "gold_seed_rows",
        "codex_suggestions",
        "governed_entitlement_measures",
    }.issubset(secondary_ids)
    assert not {
        "clause_evidence_graph",
        "reference_edges",
        "entitlement_locator",
        "qa_review_pack",
        "gold_seed_rows",
        "codex_suggestions",
        "governed_entitlement_measures",
    }.intersection(clause_child_ids)

    pipeline_stages = by_id["clause_intelligence"].get("pipelineStages", [])
    pipeline_ids = [stage["id"] for stage in pipeline_stages]
    assert by_id["clause_intelligence"]["pipelineLabel"] == "Background Clause Checks"
    assert pipeline_ids == ["source_evidence", "feature_facts", "entitlement_cards", "review_worksheet"]
    assert [stage["label"] for stage in pipeline_stages] == ["Source Evidence", "Feature Facts", "Entitlement Cards", "Review Worksheet"]
    assert all(stage.get("route") for stage in pipeline_stages)
    assert pipeline_stages[-1]["status"] == "needs_review"

    clause_routes = {child["id"]: child["route"] for child in by_id["clause_intelligence"]["children"]}
    assert clause_routes["entitlement_qa_inbox"] == "#capability/clause_intelligence"

    secondary_routes = {surface["id"]: surface["route"] for surface in by_id["clause_intelligence"]["secondarySurfaces"]}
    assert secondary_routes["entitlement_library_wiki"] == "#wiki"
    assert secondary_routes["clause_cards"] == "#capability/clause_intelligence/clause_cards"
    assert secondary_routes["feature_cards"] == "#capability/clause_intelligence/feature_cards"
    assert secondary_routes["entitlement_cards"] == "#capability/clause_intelligence/entitlement_cards"
    assert secondary_routes["human_review_worksheet"] == "#capability/clause_intelligence/human_review_worksheet"
    assert secondary_routes["clause_evidence_graph"] == "#capability/clause_intelligence/clause_evidence_graph"
    assert secondary_routes["reference_edges"] == "#capability/clause_intelligence/reference_edges"
    assert secondary_routes["entitlement_locator"] == "#capability/clause_intelligence/entitlement_locator"
    assert secondary_routes["qa_review_pack"] == "#capability/clause_intelligence/qa_review_pack"
    assert secondary_routes["gold_seed_rows"] == "#capability/clause_intelligence/gold_seed_rows"
    assert secondary_routes["codex_suggestions"] == "#capability/clause_intelligence/codex_suggestions"
    assert secondary_routes["governed_entitlement_measures"] == "#capability/clause_intelligence/governed_entitlement_measures"

    app_text = APP_JS.read_text(encoding="utf-8")
    style_text = STYLE_CSS.read_text(encoding="utf-8")
    assert "currentCapabilityNode" in app_text
    assert "capabilityChildById" in app_text
    assert "capabilitySecondarySurfaces" in app_text
    assert "renderCapabilitySecondarySurfaces" in app_text
    assert "renderCapabilityPipeline" in app_text
    assert "renderCapabilityPipelineStage" in app_text
    assert "renderCapabilityEntitlementQaInbox" in app_text
    assert "hydrateCapabilityEntitlementQaInbox" in app_text
    assert "data-entitlement-qa-open-review" in app_text
    assert "data-entitlement-qa-accept" in app_text
    assert "renderCapabilityDocumentSpineContent" in app_text
    assert "renderCapabilityEvidenceGraphContent" in app_text
    assert "renderCapabilityClauseCardsContent" in app_text
    assert "renderCapabilityFeatureCardsContent" in app_text
    assert "renderCapabilityEntitlementCardsContent" in app_text
    assert "entitlementCardRegisterHtml" in app_text
    assert "source_clauses" in app_text
    assert "Clause evidence" in app_text
    assert "capabilityPipelineFreshnessHtml" in app_text
    assert "Pipeline freshness" in app_text
    assert "entitlement_card_repair_loop" in app_text
    assert "renderCapabilityEntitlementTestMatrix" in app_text
    assert "capabilityReviewSelectedEntitlement" in app_text
    assert "data-capability-review-entitlement" in app_text
    assert "data-capability-review-council-key" in app_text
    assert "renderCapabilityReferenceEdgesContent" in app_text
    assert "renderCapabilityQaReviewPackContent" in app_text
    assert "renderCapabilityHumanReviewWorksheetContent" in app_text
    assert "renderCapabilityGovernedEntitlementMeasuresContent" in app_text
    assert "hydrateCapabilityNodePage" in app_text
    assert "ensureCouncilRows" in app_text
    assert "capabilityAgreementOptions" in app_text
    assert "Agreements without document map" in app_text
    assert "/api/wiki/clause-cards" in app_text
    assert "/api/wiki/clause-intelligence" in app_text
    assert "/api/wiki/entitlement-test-matrix" in app_text
    assert "capabilityNode: extra" in app_text
    assert 'state.currentCapabilityNode ? `#capability/${branch}/${state.currentCapabilityNode}`' in app_text
    assert ".capability-detail-card.is-selected" in style_text
    assert ".capability-node-page" in style_text
    assert 'body[data-view="capability"] .app-shell-main' in style_text
    assert ".capability-document-map-warning" in style_text
    assert ".capability-freshness" in style_text
    assert ".capability-locator-card-grid" in style_text
    assert ".capability-coverage-flow" in style_text
    assert ".capability-review-workspace" in style_text
    assert ".capability-review-shell" in style_text
    assert ".entitlement-qa-inbox" in style_text
    assert ".entitlement-qa-ledger" in style_text
    assert ".entitlement-qa-list-row" in style_text
    assert ".capability-pipeline-panel" in style_text
    assert ".capability-pipeline-stage.is-selected" in style_text
    assert ".capability-secondary-surface-panel" in style_text


def test_data_marts_are_a_real_capability_branch_with_inventory_page():
    tree = _exported_json_array("WORKBENCH_CAPABILITY_TREE")
    by_id = {node["id"]: node for node in tree}
    data_marts = by_id["data_marts"]

    assert data_marts["label"] == "Data Marts"
    assert data_marts["icon"] == "database"
    assert "canonical" in data_marts["description"].lower()
    assert "analytical marts" in data_marts["description"].lower()

    child_ids = [child["id"] for child in data_marts["children"]]
    assert child_ids[:5] == [
        "datamart_inventory",
        "council_master_data",
        "governed_pay_rows",
        "governed_uplift_rules",
        "governed_end_of_band_dollars",
    ]
    assert "benchmark_chart_data" in child_ids
    routes = {child.get("route") for child in data_marts["children"]}
    assert "#capability/data_marts/datamart_inventory" in routes
    assert "#data/councils" in routes
    assert "#data/pay_tables" in routes
    assert "#data/uplift_rules" in routes
    assert "#data/end_of_band_dollars" in routes
    assert "#data/charts" in routes

    app_text = APP_JS.read_text(encoding="utf-8")
    assert "datamart_inventory" in app_text
    assert "renderCapabilityDatamartInventoryContent" in app_text
    assert "/api/agent/datasets" in app_text
    assert "governed_canonical_dataset" in app_text
    assert "analytical_datamart" in app_text


def test_governance_is_branch_and_status_layer():
    tree = _exported_json_array("WORKBENCH_CAPABILITY_TREE")
    chips = _exported_json_array("GOVERNANCE_STATUS_CHIPS")
    chip_ids = {chip["id"] for chip in chips}
    node_statuses = {node.get("status") for node in _flatten(tree)}

    assert {"machine", "candidate", "needs_review", "reviewed", "accepted", "blocked", "promoted", "governed", "unwound", "advisory"}.issubset(chip_ids)
    assert "governance" in {node["id"] for node in tree}
    assert {"machine", "candidate", "needs_review", "promoted", "governed", "advisory"}.issubset(node_statuses)

    app_text = APP_JS.read_text(encoding="utf-8")
    assert "capabilityStatusChip" in app_text
    assert "Governance is also shown as status chips across every branch" in TREE_JS.read_text(encoding="utf-8")


def test_council_audit_reachable_from_custody_and_governance():
    tree = _exported_json_array("WORKBENCH_CAPABILITY_TREE")
    by_id = {node["id"]: node for node in tree}
    source_routes = {child["route"] for child in by_id["source_custody"]["children"]}
    governance_routes = {child["route"] for child in by_id["governance"]["children"]}

    assert "#audit" in source_routes
    assert "#audit" in governance_routes
    assert by_id["source_custody"]["children"][-1]["id"] == "council_audit_lineage"
    assert any(child["id"] == "audit_trail" for child in by_id["governance"]["children"])
