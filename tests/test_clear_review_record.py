from __future__ import annotations

import csv
import json

import yaml
from fastapi.testclient import TestClient


def _isolate_clear_record_paths(tmp_path, monkeypatch):
    import main

    canonical_dir = tmp_path / "canonical"
    overrides_dir = tmp_path / "scenario-overrides"
    cache_dir = tmp_path / "cache"
    immutable_dir = tmp_path / "documents" / "immutable"
    clear_dir = tmp_path / "var" / "clear-records"
    analysis_asset = tmp_path / "data" / "analysis" / "distribution-point-analysis.json"
    multi_register = tmp_path / "registers" / "multi-council-decisions.csv"
    for path in (canonical_dir, overrides_dir, cache_dir, immutable_dir, analysis_asset.parent, multi_register.parent):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(main, "CANONICAL_DIR", canonical_dir)
    monkeypatch.setattr(main, "SCENARIO_OVERRIDES_DIR", overrides_dir)
    monkeypatch.setattr(main, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(main, "IMMUTABLE_DIR", immutable_dir)
    monkeypatch.setattr(main, "CLEAR_RECORDS_DIR", clear_dir)
    monkeypatch.setattr(main, "DISTRIBUTION_POINT_ANALYSIS_JSON", analysis_asset)
    monkeypatch.setattr(main, "MULTI_COUNCIL_REGISTER", multi_register)
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Test Council Agreement"})
    monkeypatch.setattr(main, "fetch_metadata_for_ae_id", lambda *args, **kwargs: {"Agreement Title": "Test Council Agreement"})
    main._canonical_cache.clear()
    main._multi_council_cache = None
    return main, {
        "canonical": canonical_dir,
        "overrides": overrides_dir,
        "cache": cache_dir,
        "immutable": immutable_dir,
        "clear": clear_dir,
        "analysis": analysis_asset,
        "multi": multi_register,
    }


def test_clear_review_record_archives_review_artifacts_and_resets_to_review_start(tmp_path, monkeypatch):
    main, paths = _isolate_clear_record_paths(tmp_path, monkeypatch)

    (paths["canonical"] / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Test Council Agreement\n"
        "overview:\n"
        "  generated_at: '2026-04-30T00:00:00Z'\n"
        "sections:\n"
        "  pay_tables:\n"
        "    status: done\n"
        "    completed_at: '2026-04-30T00:00:00Z'\n"
        "    tables:\n"
        "      - effective_from: '2026-07-01'\n"
        "        rows:\n"
        "          - {band: '1', level: 'A', weekly_rate: 1000}\n"
        "  uplifts:\n"
        "    data:\n"
        "      periods:\n"
        "        - effective_from: '2026-07-01'\n"
        "          pay_table_governed_at: '2026-04-30T00:00:00Z'\n"
        "          pay_table:\n"
        "            rows:\n"
        "              - {band: '1', level: 'A', weekly_rate: 1000}\n",
        encoding="utf-8",
    )
    (paths["overrides"] / "aetest01.json").write_text('{"overrides":{"2026-07-01":{}}}', encoding="utf-8")
    (paths["cache"] / "aetest01").mkdir()
    (paths["cache"] / "aetest01" / "pages.json").write_text("[]", encoding="utf-8")
    paths["analysis"].write_text('{"stale": true}', encoding="utf-8")
    (paths["immutable"] / "aetest01.pdf").write_bytes(b"%PDF-1.4\n")

    response = TestClient(main.app).post(
        "/api/councils/aetest01/clear-review-record",
        json={"reason": "Restart review from source evidence.", "include_related": True},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["clear_record"]["agreement_id"] == "aetest01"
    assert body["clear_record"]["moved_artifact_count"] == 4
    assert {item["kind"] for item in body["moved_artifacts"]} >= {
        "canonical_state",
        "scenario_override_state",
        "workspace_cache",
        "derived_analysis_asset",
    }
    manifest_path = body["manifest"]["path"]
    manifest = json.loads(open(manifest_path, encoding="utf-8").read())
    assert manifest["reason"] == "Restart review from source evidence."
    assert manifest["retained_boundaries"]

    assert not (paths["overrides"] / "aetest01.json").exists()
    assert not (paths["cache"] / "aetest01").exists()
    assert not paths["analysis"].exists()
    assert (paths["immutable"] / "aetest01.pdf").exists()

    saved = yaml.safe_load((paths["canonical"] / "aetest01.yaml").read_text(encoding="utf-8"))
    assert saved["sections"]["pay_tables"]["status"] == "not_started"
    assert saved["sections"]["pay_tables"]["tables"] == []
    assert saved["overview"]["generated_at"] is None
    assert saved["review_clear_records"][0]["archive_id"] == body["clear_record"]["archive_id"]


def test_clear_review_record_collapses_split_scope_artifacts(tmp_path, monkeypatch):
    main, paths = _isolate_clear_record_paths(tmp_path, monkeypatch)

    (paths["canonical"] / "aetest01.yaml").write_text(
        "agreement_id: aetest01\nsource_name: Parent Agreement\nsections: {}\n",
        encoding="utf-8",
    )
    (paths["canonical"] / "aetest01__alpha.yaml").write_text(
        "agreement_id: aetest01__alpha\nsource_name: Split Agreement\nsections: {}\n",
        encoding="utf-8",
    )
    (paths["overrides"] / "aetest01__alpha.json").write_text('{"notes":"split"}', encoding="utf-8")
    (paths["cache"] / "aetest01__alpha").mkdir()
    (paths["cache"] / "aetest01__alpha" / "pages.json").write_text("[]", encoding="utf-8")
    (paths["immutable"] / "aetest01.pdf").write_bytes(b"%PDF-1.4\n")
    (paths["immutable"] / "aetest01__alpha.pdf").write_bytes(b"%PDF-1.4 split\n")
    with paths["multi"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=main.multi_council_register_fields())
        writer.writeheader()
        writer.writerow({
            "ae_id": "aetest01",
            "is_multi": "true",
            "lgas_assigned": "Alpha|Beta",
            "parent_content_hash": "abc",
            "split_files": "aetest01__alpha.pdf",
            "decided_by": "human-ui",
            "decided_at": "2026-04-30T00:00:00Z",
            "notes": "split",
        })
    main._multi_council_cache = None

    response = TestClient(main.app).post(
        "/api/councils/aetest01__alpha/clear-review-record",
        json={"reason": "Wrong split.", "include_related": True},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["clear_record"]["agreement_id"] == "aetest01"
    assert "aetest01__alpha" in body["clear_record"]["related_ae_ids"]
    assert {record["kind"] for record in body["archived_records"]} == {"multi_council_decision"}
    assert any(item["kind"] == "split_source_pdf" for item in body["moved_artifacts"])

    assert (paths["canonical"] / "aetest01.yaml").exists()
    assert not (paths["canonical"] / "aetest01__alpha.yaml").exists()
    assert not (paths["overrides"] / "aetest01__alpha.json").exists()
    assert not (paths["cache"] / "aetest01__alpha").exists()
    assert not (paths["immutable"] / "aetest01__alpha.pdf").exists()
    assert (paths["immutable"] / "aetest01.pdf").exists()
    assert main.load_multi_council_decisions() == {}
