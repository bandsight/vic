from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from benchmarking_data_factory.uplift_rules.schema import (
    ExtractionInputs,
    Provenance,
    RulesDocument,
    UpliftRule,
    UpliftRulesSuggestion,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path)
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Test Council"})
    monkeypatch.setattr(main, "fetch_metadata_for_ae_id", lambda *args, **kwargs: {})
    monkeypatch.setattr(main, "resolve_canonical_lga_short_name", lambda *args, **kwargs: None)
    (tmp_path / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Test Council\n"
        "sections:\n"
        "  pay_tables:\n"
        "    status: not_started\n"
        "    tables: []\n"
        "  uplift_rules:\n"
        "    status: not_started\n"
        "    data: {}\n",
        encoding="utf-8",
    )
    return TestClient(main.app)


def _failed_suggestion() -> UpliftRulesSuggestion:
    inputs = ExtractionInputs(
        pdf_sha256="p",
        page_numbers=(1, 2),
        page_text_sha256="t",
        prompt_version="pass1_system_v1",
        prompt_sha256="ps",
        model="m",
    )
    now = datetime.now(timezone.utc)
    return UpliftRulesSuggestion(
        document=RulesDocument(
            ae_id="aetest01",
            council="(unknown)",
            timing_pattern="unknown",
            rules=(),
            notes="LLM adapter raised an error",
        ),
        provenance=Provenance(
            inputs=inputs,
            code_git_sha="testsha",
            run_started_at=now,
            run_completed_at=now,
            run_duration_ms=1,
            llm_raw_response="ERROR: ANTHROPIC_API_KEY not set",
            extraction_status="llm_error",
        ),
        suggestion_id="failed123",
    )


def _ok_suggestion() -> UpliftRulesSuggestion:
    inputs = ExtractionInputs(
        pdf_sha256="p",
        page_numbers=(10, 11),
        page_text_sha256="t",
        prompt_version="pass1_system_v2",
        prompt_sha256="ps",
        model="m",
    )
    now = datetime.now(timezone.utc)
    return UpliftRulesSuggestion(
        document=RulesDocument(
            ae_id="aetest01",
            council="Test Council",
            timing_pattern="irregular_multi_date",
            rules=(
                UpliftRule(
                    period_label="Year 1",
                    quantum="2.75%",
                    quantum_type="percentage",
                    timing_clause="first full pay period after 1 July 2024",
                    effective_date="2024-07-01",
                    source_page=10,
                    confidence=0.9,
                ),
                UpliftRule(
                    period_label="Year 2",
                    quantum="3.00%",
                    quantum_type="percentage",
                    timing_clause="first full pay period after 1 July 2025",
                    effective_date="2025-07-01",
                    source_page=11,
                    confidence=0.88,
                ),
            ),
        ),
        provenance=Provenance(
            inputs=inputs,
            code_git_sha="testsha",
            run_started_at=now,
            run_completed_at=now,
            run_duration_ms=1,
            llm_raw_response='{"rules":[]}',
            extraction_status="ok",
        ),
        suggestion_id="ok123",
    )


def test_suggest_endpoint_rejects_failed_llm_suggestion(client, monkeypatch):
    import main

    monkeypatch.setattr(main, "run_uplift_suggest", lambda *args, **kwargs: _failed_suggestion())

    response = client.post("/api/councils/aetest01/uplift-rules/suggest")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["status"] == "llm_error"
    assert "ANTHROPIC_API_KEY" in detail["reason"]
    saved = main.get_canonical("aetest01")
    assert "suggestion" not in (saved["sections"]["uplift_rules"].get("data") or {})


def test_accept_endpoint_rejects_failed_suggestion(client):
    import main

    canonical = main.get_canonical("aetest01")
    canonical["sections"]["uplift_rules"]["data"] = {
        "suggestion": main._serialise_suggestion(_failed_suggestion())
    }
    main.save_canonical("aetest01", canonical)

    response = client.post("/api/councils/aetest01/uplift-rules/accept", json={})

    assert response.status_code == 400
    assert "Cannot accept failed" in response.json()["detail"]


def test_rerun_suggestion_reopens_uplift_review_and_accepts_reviewed_subset(client, monkeypatch):
    import main

    monkeypatch.setattr(main, "run_uplift_suggest", lambda *args, **kwargs: _ok_suggestion())

    response = client.post("/api/councils/aetest01/uplift-rules/suggest?force_refresh=true")

    assert response.status_code == 200
    assert response.json()["section_status"] == "in_progress"

    reviewed_rules = [response.json()["suggestion"]["document"]["rules"][1]]
    accept = client.post("/api/councils/aetest01/uplift-rules/accept", json={"rules": reviewed_rules})

    assert accept.status_code == 200
    saved = main.get_canonical("aetest01")
    data = saved["sections"]["uplift_rules"]["data"]
    assert len(data["suggestion"]["document"]["rules"]) == 2
    assert len(data["accepted"]["document"]["rules"]) == 1
    assert data["accepted"]["document"]["rules"][0]["period_label"] == "Year 2"
    assert saved["sections"]["uplift_rules"]["status"] == "done"


def test_discard_suggestion_restores_existing_accepted_uplift_rules(client):
    import main

    suggestion = main._serialise_suggestion(_ok_suggestion())
    canonical = main.get_canonical("aetest01")
    canonical["sections"]["uplift_rules"]["status"] = "in_progress"
    canonical["sections"]["uplift_rules"]["data"] = {
        "suggestion": suggestion,
        "suggestion_generated_at": "2026-05-09T01:00:00Z",
        "accepted": {
            "document": {
                **suggestion["document"],
                "rules": [suggestion["document"]["rules"][0]],
            },
            "suggestion_id": "older123",
        },
        "accepted_at": "2026-05-08T01:00:00Z",
    }
    main.save_canonical("aetest01", canonical)

    response = client.delete("/api/councils/aetest01/uplift-rules/suggestion")

    assert response.status_code == 200
    saved = main.get_canonical("aetest01")
    data = saved["sections"]["uplift_rules"]["data"]
    assert "suggestion" not in data
    assert data["accepted"]["document"]["rules"][0]["period_label"] == "Year 1"
    assert saved["sections"]["uplift_rules"]["status"] == "done"
