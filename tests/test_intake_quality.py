from __future__ import annotations

import csv
from types import SimpleNamespace

from fastapi.testclient import TestClient

import main
from benchmarking_data_factory.workbench.intake_quality import IntakeQualityService


def _candidate_rows():
    return [
        {
            "Agreement ID": "AE100002",
            "Agreement Title": "Example Shire Council Enterprise Agreement 2024",
            "agreement_num_clean": 100002,
            "Operative Date": "2024-07-01",
            "Expiry Date": "2028-06-30",
            "matched_lga_names": "Example",
            "pipeline_status": "active",
            "likely_most_current": "likely_current",
            "pdf_url": "https://example.test/ae100002.pdf",
        },
        {
            "Agreement ID": "AE100001",
            "Agreement Title": "Example Shire Council Enterprise Agreement 2020",
            "agreement_num_clean": 100001,
            "Operative Date": "2020-07-01",
            "Expiry Date": "2024-06-30",
            "matched_lga_names": "Example",
            "pipeline_status": "superseded_by_newer",
            "likely_most_current": "likely_current",
            "superseded_by_ae_id": "AE100002",
        },
        {
            "Agreement ID": "AE200001",
            "Agreement Title": "Unmatched Regional Council Agreement 2024",
            "agreement_num_clean": 200001,
            "Operative Date": "2024-01-01",
            "matched_lga_names": "",
            "pipeline_status": "active",
            "likely_most_current": "likely_current",
        },
    ]


def test_intake_quality_summarises_candidates_and_runner_up(monkeypatch):
    monkeypatch.setattr(main, "load_candidate_agreement_rows", _candidate_rows)
    monkeypatch.setattr(main, "load_registry", lambda: {"ae100002": "Example"})
    monkeypatch.setattr(main, "list_pdfs", lambda: ["ae100002"])

    summary = main.build_intake_quality_summary(
        [
            {"ae_id": "ae100002", "fetch_metadata": {"pipeline_status": "active"}},
            {"ae_id": "ae100001", "fetch_metadata": {"pipeline_status": "superseded_by_newer"}},
        ]
    )

    assert summary["candidate_records"]["total"] == 3
    assert summary["candidate_records"]["active"] == 2
    assert summary["candidate_records"]["active_unmatched"] == 1
    assert summary["candidate_records"]["likely_current_but_demoted"] == 1
    assert summary["working_set"]["visible_superseded"] == 1
    assert summary["top_two_review"]["unique_runner_up_candidates"] == 1
    assert summary["top_two_review"]["runner_up_examples"][0]["ae_id"] == "ae100001"


def test_intake_quality_endpoint_returns_summary(monkeypatch):
    monkeypatch.setattr(main, "load_candidate_agreement_rows", _candidate_rows)
    monkeypatch.setattr(main, "load_registry", lambda: {})
    monkeypatch.setattr(main, "list_pdfs", lambda: [])
    monkeypatch.setattr(main, "api_councils", lambda include_split_parents=False: [])

    response = TestClient(main.app).get("/api/intake/quality?force_refresh=true")

    assert response.status_code == 200
    assert response.json()["selection_rule"]["top_two_note"]
    assert response.json()["cache"]["state"] == "refreshed"


def test_intake_quality_service_caches_and_invalidates(tmp_path):
    calls = {"councils": 0}
    candidate_file = tmp_path / "candidate_agreements.json"
    candidate_file.write_text("[]", encoding="utf-8")

    def api_councils(include_split_parents=False):
        calls["councils"] += 1
        return []

    deps = SimpleNamespace(
        load_candidate_agreement_rows=_candidate_rows,
        api_councils=api_councils,
        load_registry=lambda: {},
        list_pdfs=lambda: [],
        candidate_agreements_json=lambda: candidate_file,
    )
    service = IntakeQualityService(
        deps_factory=lambda: deps,
        now=lambda: "2026-05-07T00:00:00+00:00",
        ttl_seconds=60,
    )

    first = service.summary()
    second = service.summary()
    service.invalidate("test")
    third = service.summary()

    assert first["cache"]["state"] == "refreshed"
    assert second["cache"]["state"] == "cached"
    assert third["cache"]["state"] == "refreshed"
    assert calls["councils"] == 2


def test_intake_candidates_return_real_candidate_rows(monkeypatch):
    monkeypatch.setattr(main, "load_candidate_agreement_rows", _candidate_rows)
    monkeypatch.setattr(main, "load_intake_decisions", lambda: {})
    monkeypatch.setattr(main, "load_registry", lambda: {"ae100002": "Example fetched source"})
    monkeypatch.setattr(main, "list_pdfs", lambda: ["ae100002"])

    rows = main.build_intake_candidate_rows()

    assert len(rows) == 3
    current = rows[0]
    assert current["ae_id"] == "ae100002"
    assert current["candidate_stage"] == "active"
    assert current["pdf_frozen"] is True
    assert current["qa_available"] is True
    assert current["acceptance_state"] == "accepted"
    assert current["canonical_lga_short_name"] == "Example"
    rejected = next(row for row in rows if row["ae_id"] == "ae100001")
    assert rejected["acceptance_state"] == "rejected"
    unmatched = next(row for row in rows if row["ae_id"] == "ae200001")
    assert unmatched["processing_gated"] is True
    assert unmatched["matched_lgas"] == []


def test_intake_candidates_endpoint(monkeypatch):
    monkeypatch.setattr(main, "load_candidate_agreement_rows", _candidate_rows)
    monkeypatch.setattr(main, "load_intake_decisions", lambda: {})
    monkeypatch.setattr(main, "load_registry", lambda: {})
    monkeypatch.setattr(main, "list_pdfs", lambda: [])

    response = TestClient(main.app).get("/api/intake/candidates")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["fetch_metadata"]["Agreement Title"]
    assert {"row_key", "ae_id", "candidate_stage", "qa_available"} <= set(body[0])


def test_council_audit_endpoint_returns_lineage_report(monkeypatch):
    monkeypatch.setattr(main, "load_candidate_agreement_rows", _candidate_rows)
    monkeypatch.setattr(
        main,
        "load_intake_decisions",
        lambda: {
            "ae100002": {
                "ae_id": "ae100002",
                "status": "accepted",
                "reason": "Confirmed current source",
                "decided_at": "2026-04-28T01:00:00+00:00",
            }
        },
    )
    monkeypatch.setattr(main, "load_registry", lambda: {"ae100002": "Example fetched source"})
    monkeypatch.setattr(main, "list_pdfs", lambda: ["ae100002"])
    monkeypatch.setattr(
        main,
        "load_source_register_by_ae_id",
        lambda: {
            "ae100002": {
                "fetched_at": "2026-04-28T00:00:00+00:00",
                "source_status": "active",
                "serviceability_status": "frozen",
                "file_size_bytes": "2048",
                "source_origin": "https://example.test/ae100002.pdf",
            }
        },
    )
    monkeypatch.setattr(main, "load_multi_council_decisions", lambda: {})
    monkeypatch.setattr(main, "pdf_source_metadata", lambda ae_id: {"frozen": ae_id == "ae100002"})

    def fake_summary(ae_id, registry=None, decisions=None):
        return {
            "ae_id": ae_id,
            "source_name": f"Example {ae_id}",
            "canonical_lga_short_name": "Example",
            "fetch_metadata": main.load_candidate_agreements().get(ae_id),
            "geography": {"short_name": "Example"},
            "done_count": 2,
            "total_sections": 6,
            "pay_table_summary": [],
        }

    monkeypatch.setattr(main, "build_council_summary", fake_summary)
    monkeypatch.setattr(
        main,
        "_audit_workspace_snapshot",
        lambda ae_id, row=None: {
            "ae_id": ae_id,
            "done_count": 2,
            "total_sections": 6,
            "completed_sections": [
                {
                    "section": "overview",
                    "label": "Overview",
                    "status": "done",
                    "completed_at": "2026-04-28T02:00:00+00:00",
                    "source_ref": "Generated overview",
                }
            ],
            "governed": {
                "periods": 1,
                "pay_table_periods": 1,
                "uplift_rule_periods": 1,
                "pay_table_rows": 3,
                "pay_table_governed_at": ["2026-04-28T03:00:00+00:00"],
                "uplift_rule_governed_at": ["2026-04-28T04:00:00+00:00"],
            },
        },
    )
    monkeypatch.setattr(
        main,
        "_audit_governed_events",
        lambda ae_id, workspace: [
            {
                "date": "2026-04-28T03:00:00+00:00",
                "kind": "governance",
                "label": "Pay tables promoted",
                "detail": "1 governed period",
                "ae_id": ae_id,
                "source": "Governed Set",
            }
        ],
    )

    response = TestClient(main.app).get("/api/audit/councils/Example")

    assert response.status_code == 200
    body = response.json()
    assert body["council"]["short_name"] == "Example"
    assert body["latest"]["ae_id"] == "ae100002"
    assert [row["ae_id"] for row in body["lineage"]] == ["ae100001", "ae100002"]
    assert body["summary"]["governed_periods"] == 2
    assert body["summary"]["pay_table_periods"] == 2
    assert body["summary"]["uplift_rule_periods"] == 2
    assert body["summary"]["pay_table_rows"] == 6
    assert body["governed"]["agreement_count"] == 2
    assert body["quality_standard"]["agreement_count"] == 2
    assert len(body["quality_standard"]["agreements"]) == 2
    assert all(item["max_score"] == 1000 for item in body["quality_standard"]["agreements"])
    assert any(event["label"] == "Source PDF fetched" for event in body["events"])
    assert body["changes"][0]["to_ae_id"] == "ae100002"


def test_intake_fetch_registry_endpoint_rebuilds_and_returns_refreshed_rows(monkeypatch):
    calls = {}

    def fake_run_phase1(**kwargs):
        calls.update(kwargs)
        return {
            "registry_rows": 42,
            "candidate_agreements": 3,
            "frozen_candidate_pdfs": 0,
        }

    monkeypatch.setattr(main, "run_phase1", fake_run_phase1)
    monkeypatch.setattr(main, "load_candidate_agreement_rows", _candidate_rows)
    monkeypatch.setattr(main, "load_intake_decisions", lambda: {})
    monkeypatch.setattr(main, "load_registry", lambda: {"ae100002": "Example fetched source"})
    monkeypatch.setattr(main, "list_pdfs", lambda: ["ae100002"])
    monkeypatch.setattr(main, "api_councils", lambda include_split_parents=False: [])

    response = TestClient(main.app).post("/api/intake/fetch-registry?force_refresh=true")

    assert response.status_code == 200
    body = response.json()
    assert calls == {"fetch_pdfs": False, "pdf_limit": None, "force_registry": True}
    assert body["run"]["registry_rows"] == 42
    assert len(body["candidates"]) == 3
    assert body["candidates"][0]["ae_id"] == "ae100002"
    assert body["quality"]["candidate_records"]["total"] == 3


def test_intake_decision_endpoint_persists_and_overlays_candidate(tmp_path, monkeypatch):
    decisions_path = tmp_path / "intake-decisions.json"
    monkeypatch.setattr(main, "INTAKE_DECISIONS_JSON", decisions_path)
    monkeypatch.setattr(main, "_intake_decisions_cache", None)
    monkeypatch.setattr(main, "load_candidate_agreement_rows", _candidate_rows)
    monkeypatch.setattr(main, "load_registry", lambda: {})
    monkeypatch.setattr(main, "list_pdfs", lambda: [])

    response = TestClient(main.app).post(
        "/api/intake/candidates/ae200001/decision",
        json={"status": "rejected", "reason": "Not Victorian local government", "notes": "Checked title."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["candidate"]["acceptance_state"] == "rejected"
    assert body["candidate"]["decision_source"] == "analyst"
    assert body["decision"]["reason"] == "Not Victorian local government"
    assert decisions_path.exists()


def test_intake_freeze_endpoint_downloads_hashes_and_registers(tmp_path, monkeypatch):
    immutable_dir = tmp_path / "immutable"
    registry_csv = tmp_path / "source-document-register.csv"
    pdf_bytes = b"%PDF-1.4\n% intake freeze test\n"

    monkeypatch.setattr(main, "IMMUTABLE_DIR", immutable_dir)
    monkeypatch.setattr(main, "REGISTRY_CSV", registry_csv)
    monkeypatch.setattr(main, "_source_register_cache", None)
    monkeypatch.setattr(main, "_candidate_agreements_cache", None)
    monkeypatch.setattr(main, "load_candidate_agreement_rows", _candidate_rows)
    monkeypatch.setattr(main, "load_intake_decisions", lambda: {})
    monkeypatch.setattr(main, "find_fwc_document_download_url", lambda ae_id, **kwargs: None)

    def fake_download(url, destination):
        assert url == "https://example.test/ae100002.pdf"
        destination.write_bytes(pdf_bytes)

    monkeypatch.setattr(main, "download_pdf_to_path", fake_download)

    response = TestClient(main.app).post("/api/intake/candidates/ae100002/freeze")

    assert response.status_code == 200
    body = response.json()
    frozen_path = immutable_dir / "ae100002.pdf"
    assert frozen_path.exists()
    assert body["already_frozen"] is False
    assert body["content_hash"] == main.sha256_file(frozen_path)
    assert body["candidate"]["pdf_frozen"] is True
    assert body["candidate"]["in_working_set"] is True

    with registry_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["discovery_reference"] == "ae100002.pdf"
    assert rows[0]["source_origin"] == "https://example.test/ae100002.pdf"
    assert rows[0]["content_hash"] == body["content_hash"]


def test_intake_freeze_falls_back_to_current_fwc_document_search(tmp_path, monkeypatch):
    immutable_dir = tmp_path / "immutable"
    registry_csv = tmp_path / "source-document-register.csv"
    fallback_url = "https://www.fwc.gov.au/document-view/media/download/816310"
    attempted = []

    monkeypatch.setattr(main, "IMMUTABLE_DIR", immutable_dir)
    monkeypatch.setattr(main, "REGISTRY_CSV", registry_csv)
    monkeypatch.setattr(main, "_source_register_cache", None)
    monkeypatch.setattr(main, "_candidate_agreements_cache", None)
    monkeypatch.setattr(main, "load_candidate_agreement_rows", _candidate_rows)
    monkeypatch.setattr(main, "load_intake_decisions", lambda: {})
    monkeypatch.setattr(main, "find_fwc_document_download_url", lambda ae_id, **kwargs: fallback_url)

    def fake_download(url, destination):
        attempted.append(url)
        if url == "https://example.test/ae100002.pdf":
            raise main.requests.HTTPError("404 Client Error: Not Found")
        destination.write_bytes(b"%PDF-1.7\nfallback\n")

    monkeypatch.setattr(main, "download_pdf_to_path", fake_download)

    response = TestClient(main.app).post("/api/intake/candidates/ae100002/freeze")

    assert response.status_code == 200
    body = response.json()
    assert attempted == ["https://example.test/ae100002.pdf", fallback_url]
    assert body["pdf_source_url"] == fallback_url
    with registry_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["source_origin"] == fallback_url
