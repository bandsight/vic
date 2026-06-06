from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def test_agent_status_reports_manifest_and_llm_shape():
    response = client.get("/api/agent/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["project"]["id"] == "municipal-benchmark-eba-workbench"
    assert payload["manifest"]["exists"] is True
    assert payload["portable_manifest"]["exists"] is True
    assert "ready" in payload["llm"]
    assert payload["package_profile"]["inferred_profile"] in {
        "runtime_code",
        "with_governed_data",
        "with_source_evidence",
    }
    assert payload["routes"]["count"] >= 4
    assert payload["report_assets"]["distribution_point_analysis"]["validation"]["valid"] is True
    assert "csv" in payload["report_exports"]["implemented_formats"]
    assert payload["operator_commands"]["commands_ready"] is True
    assert "matrix" in payload["portable_validation"]
    assert hasattr(main.app.state, "workbench_services")
    assert main.app.state.workbench_services.paths.root == main.ROOT


def test_agent_catalog_exposes_key_data_sets_and_routes():
    response = client.get("/api/agent/catalog")

    assert response.status_code == 200
    payload = response.json()
    dataset_ids = {item["id"] for item in payload["datasets"]}
    route_paths = {item["path"] for item in payload["routes"]}

    assert {
        "intake_candidates",
        "pay_tables",
        "uplift_rules",
        "distribution_point_analysis",
        "distribution_point_analysis_asset",
    } <= dataset_ids
    assert "/api/agent/status" in route_paths
    assert "/api/analysis/pay-tables" in route_paths
    assert "/api/analysis/distribution-point-analysis/exports" in route_paths
    assert "/api/analysis/distribution-point-analysis/report-asset/status" in route_paths
    assert "/api/analysis/distribution-point-analysis/exports/{format_name}" in route_paths
    assert "/api/wiki/status" in route_paths
    assert payload["packaging"]["default_profile"] == "runtime_code"
    assert payload["report_assets"]["assets"][0]["asset_id"] == "distribution_point_analysis_default"
    assert payload["report_exports"]["assets"][0]["asset_id"] == "distribution_point_analysis_default"
    assert payload["wiki_layer"]["status"]["latest_run_id"]
    assert "smoke" in payload["operator_commands"]["groups"]
    assert "smoke_windows" in payload["operator_commands"]["groups"]["smoke"]
    assert "smoke_windows" in {
        binding["command_id"] for binding in payload["portable_validation"]["command_bindings"]
    }


def test_agent_datasets_exposes_datamart_inventory_without_full_catalog():
    response = client.get("/api/agent/datasets")

    assert response.status_code == 200
    payload = response.json()
    dataset_ids = {item["id"] for item in payload["datasets"]}
    kinds = {item["kind"] for item in payload["datasets"]}

    assert "governed_canonical_layer" in dataset_ids
    assert "datamart_layer" in dataset_ids
    assert "governed_canonical:pay_rows" in dataset_ids
    assert "datamart:pay_service_horizon_curve_view" in dataset_ids
    assert "governed_canonical_dataset" in kinds
    assert "analytical_datamart" in kinds
    assert "routes" not in payload


def test_agent_actions_exposes_report_export_action():
    response = client.get("/api/agent/actions")

    assert response.status_code == 200
    payload = response.json()
    assert any(action["id"] == "export_distribution_point_analysis" for action in payload["report_export_actions"])
    assert any(action["id"] == "read_portable_validation_status" for action in payload["portable_validation_actions"])
    assert any(action["id"] == "read_wiki_status" for action in payload["wiki_actions"])


def test_agent_io_declares_root_write_boundary():
    response = client.get("/api/agent/io")

    assert response.status_code == 200
    payload = response.json()
    assert payload["safety"]["do_not_write_outside_root"] is True
    assert payload["safety"]["write_boundary"] == payload["root"]
    assert payload["manifests"]["agent"]["exists"] is True
    assert payload["packaging"]["valid"] is True
    assert "package_windows" in payload["packaging"]["scripts"]
    assert payload["report_assets"]["contract"]["exists"] is True
    assert payload["report_exports"]["assets"][0]["targets"][0]["implemented"] is True
    assert "test_windows" in payload["operator_commands"]["safety"]["agent_safe_verification_commands"]
    assert "package_windows" in payload["operator_commands"]["safety"]["operator_intent_required_for"]
    assert "does not execute" in payload["portable_validation"]["execution_policy"]
