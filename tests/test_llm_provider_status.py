from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


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
        "    status: in_progress\n"
        "    tables: []\n"
        "  uplift_rules:\n"
        "    status: not_started\n"
        "    data: {}\n",
        encoding="utf-8",
    )
    return TestClient(main.app)


def test_llm_status_reports_missing_anthropic_key(client, monkeypatch):
    monkeypatch.delenv("EXTRACT_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = client.get("/api/llm/status")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "anthropic"
    assert body["ready"] is False
    assert body["vision_capable"] is False
    assert body["credential"] == "missing"


def test_connections_endpoint_exposes_providers_without_secrets(client, monkeypatch):
    monkeypatch.setenv("EXTRACT_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-secret")

    response = client.get("/api/connections")

    assert response.status_code == 200
    assert "sk-ant-test-secret" not in response.text
    body = response.json()
    assert body["llm"]["active"]["credential"] == "set"
    providers = {provider["id"]: provider for provider in body["llm"]["providers"]}
    assert providers["anthropic"]["active"] is True
    assert providers["anthropic"]["status"]["credential"] == "set"
    assert providers["openclaw_codex"]["status"]["vision_capable"] is False
    assert providers["openai"]["adapter_state"] == "planned"


def test_update_llm_connection_writes_local_env_without_echoing_secret(client, tmp_path, monkeypatch):
    import main

    env_file = tmp_path / ".env"
    monkeypatch.setattr(main, "ENV_FILE", env_file)
    monkeypatch.delenv("EXTRACT_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = client.post(
        "/api/connections/llm",
        json={
            "provider": "anthropic",
            "model": "claude-sonnet-4-20250514",
            "api_key": "sk-ant-test-secret",
        },
    )

    assert response.status_code == 200
    assert "sk-ant-test-secret" not in response.text
    body = response.json()
    assert body["llm"]["active"]["ready"] is True
    assert body["llm"]["active"]["credential"] == "set"
    written = env_file.read_text(encoding="utf-8")
    assert "EXTRACT_PROVIDER=anthropic" in written
    assert "ANTHROPIC_MODEL=claude-sonnet-4-20250514" in written
    assert "ANTHROPIC_API_KEY=sk-ant-test-secret" in written


def test_pay_extract_requires_vision_provider_before_empty_tables(client, monkeypatch):
    monkeypatch.delenv("EXTRACT_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = client.post("/api/councils/aetest01/pay-tables/extract", json={"page_num": 1})

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "Vision-capable LLM provider" in detail["message"]
    assert detail["reason"] == "ANTHROPIC_API_KEY not set"


def test_overview_generation_llm_failure_is_not_saved_as_empty_overview(client, monkeypatch):
    import main

    monkeypatch.delenv("EXTRACT_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(main, "get_page_count", lambda ae_id: 3)
    monkeypatch.setattr(main, "find_candidate_pages", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "extract_page_text", lambda *args, **kwargs: "agreement text")
    monkeypatch.setattr(main, "call_llm", lambda *args, **kwargs: "ERROR: ANTHROPIC_API_KEY not set")

    response = client.post("/api/councils/aetest01/overview/generate")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["status"] == "blocked"
    assert detail["action"] == "generate_overview"
    assert detail["reason"] == "ANTHROPIC_API_KEY not set"
    canonical = main.get_canonical("aetest01")
    assert canonical["sections"]["overview"]["status"] == "not_started"


def test_anthropic_ssl_context_ignores_unwritable_ssl_keylogfile(monkeypatch):
    import main

    class DummyContext:
        def __init__(self, protocol):
            self.protocol = protocol
            self.loaded_default_certs = False

        def load_verify_locations(self, *args, **kwargs):
            return None

        def load_default_certs(self, purpose):
            self.loaded_default_certs = True

    contexts = []

    def fake_ssl_context(protocol):
        context = DummyContext(protocol)
        contexts.append(context)
        return context

    monkeypatch.setattr(main, "_anthropic_ssl_context", None)
    monkeypatch.setenv("SSLKEYLOGFILE", r"\\.\aswMonFltProxy\FFFF990B5321D330")
    monkeypatch.setattr(main.ssl, "SSLContext", fake_ssl_context)
    monkeypatch.setattr(main.ssl, "enum_certificates", lambda _store_name: [], raising=False)

    context = main.anthropic_ssl_context()

    assert isinstance(context, DummyContext)
    assert context.protocol == main.ssl.PROTOCOL_TLS_CLIENT
    assert context.loaded_default_certs is True
    assert contexts == [context]
    assert main.os.environ["SSLKEYLOGFILE"] == r"\\.\aswMonFltProxy\FFFF990B5321D330"
