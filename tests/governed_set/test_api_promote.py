import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import main
    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path)
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Test Council"})
    canonical_path = tmp_path / "aetest01.yaml"
    canonical_path.write_text(
        "agreement_id: aetest01\n"
        "source_name: Test Council\n"
        "sections:\n"
        "  pay_tables:\n"
        "    status: done\n"
        "    tables:\n"
        "      - effective_from: '2026-07-01'\n"
        "        table_title: Base\n"
        "        rows:\n"
        "          - {band: '1', level: '1', weekly_rate: 900}\n"
        "  uplift_rules:\n"
        "    data:\n"
        "      accepted:\n"
        "        document:\n"
        "          rules:\n"
        "            - {effective_date: '2026-07-01', quantum: '3%', quantum_type: percentage}\n"
        "  uplifts:\n"
        "    status: not_started\n"
        "    data: null\n"
    )
    monkeypatch.setattr(main, "find_pdf", lambda ae_id: canonical_path if ae_id.lower() == "aetest01" else None)
    # resolve_canonical_lga_short_name signature may fail without real metadata;
    # stub it so uplift_rule promotion path still works even if fetch_metadata is empty.
    monkeypatch.setattr(main, "fetch_metadata_for_ae_id", lambda ae_id: {})
    monkeypatch.setattr(main, "resolve_canonical_lga_short_name", lambda ae_id, meta: None)
    return TestClient(main.app)


def test_promote_pay_table_endpoint(client):
    response = client.post(
        "/api/councils/aetest01/governed-set/promote",
        json={"period_effective_from": "2026-07-01", "kind": "pay_table"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ae_id"] == "aetest01"
    periods = body["governed"]["periods"]
    assert len(periods) == 1
    assert periods[0]["pay_table"] is not None


def test_promote_uplift_rule_endpoint(client):
    response = client.post(
        "/api/councils/aetest01/governed-set/promote",
        json={"period_effective_from": "2026-07-01", "kind": "uplift_rule"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    periods = body["governed"]["periods"]
    assert periods[0]["uplift_rule"]["pattern_archetype"] == "flat_pct"


def test_promote_uplift_rule_endpoint_filters_multi_employer_by_lga(client, monkeypatch):
    import main

    monkeypatch.setattr(main, "resolve_canonical_lga_short_name", lambda ae_id, meta: "Central Goldfields")
    (main.CANONICAL_DIR / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Ararat Rural City Council and Central Goldfields Shire Council Single Interest Employer Agreement No. 1\n"
        "sections:\n"
        "  uplift_rules:\n"
        "    data:\n"
        "      accepted:\n"
        "        document:\n"
        "          rules:\n"
        "            - period_label: Year 2 - Ararat Rural City Council\n"
        "              effective_date: '2025-07-01'\n"
        "              quantum: 3.5% or $50.00 per week, whichever is greater\n"
        "              quantum_type: pct_OR_floor\n"
        "            - period_label: Year 2 - Central Goldfields Shire Council\n"
        "              effective_date: '2025-07-01'\n"
        "              quantum: 3% or $50.00 per week, whichever is greater\n"
        "              quantum_type: pct_OR_floor\n"
        "  uplifts:\n"
        "    status: not_started\n"
        "    data: null\n",
        encoding="utf-8",
    )

    response = client.post(
        "/api/councils/aetest01/governed-set/promote",
        json={"period_effective_from": "2025-07-01", "kind": "uplift_rule"},
    )

    assert response.status_code == 200, response.text
    rule = response.json()["governed"]["periods"][0]["uplift_rule"]
    assert rule["pct_component"] == 3.0
    assert rule["source_rule_id"] == "2025-07-01::Year 2 - Central Goldfields Shire Council"


def test_promote_rate_cap_rule_endpoint_preserves_components(client, monkeypatch):
    import main
    from benchmarking_data_factory.uplift_rules.rate_cap import resolver

    monkeypatch.setattr(main, "resolve_canonical_lga_short_name", lambda ae_id, meta: "Example")
    monkeypatch.setattr(
        resolver,
        "resolve_effective_rate",
        lambda lga, fy, quantum, external_ref=None: {
            "raw_rate_cap": 3.0,
            "fraction": 0.9,
            "fixed_floor_pct": 3.0,
            "dollar_floor_per_week": 50.0,
            "effective_rate": 3.0,
        },
    )
    update = client.patch(
        "/api/councils/aetest01/uplift-rules/accepted/rules",
        json={"rules": [{
            "effective_date": "2026-07-01",
            "quantum": "90% of the official rate cap, or 3.0% or $50 per week, whichever is greater",
            "quantum_type": "conditional",
        }]},
    )
    assert update.status_code == 200, update.text

    response = client.post(
        "/api/councils/aetest01/governed-set/promote",
        json={"period_effective_from": "2026-07-01", "kind": "uplift_rule"},
    )

    assert response.status_code == 200, response.text
    rule = response.json()["governed"]["periods"][0]["uplift_rule"]
    assert rule["pct_component"] == 3.0
    assert rule["internal_pct_component"] == 3.0
    assert rule["pct_of_rate_cap"] == 0.9
    assert rule["external_cap_pct"] == 3.0
    assert rule["external_formula_pct"] == 2.7
    assert rule["resolved_pct"] == 3.0
    assert rule["dollar_floor_component"] == 50.0


def test_promote_unknown_kind_400(client):
    response = client.post(
        "/api/councils/aetest01/governed-set/promote",
        json={"period_effective_from": "2026-07-01", "kind": "nonsense"},
    )
    assert response.status_code == 400


@pytest.mark.parametrize("period_effective_from", ["", "   "])
def test_promote_blank_period_400(client, period_effective_from):
    response = client.post(
        "/api/councils/aetest01/governed-set/promote",
        json={"period_effective_from": period_effective_from, "kind": "pay_table"},
    )
    assert response.status_code == 400
    assert "period_effective_from" in response.json()["detail"]


def test_get_governed_set_empty_initially(client):
    response = client.get("/api/councils/aetest01/governed-set")
    assert response.status_code == 200
    assert response.json()["governed"]["periods"] == []


def test_get_governed_set_resolves_legacy_rate_cap_from_table(client, monkeypatch):
    import main

    monkeypatch.setattr(main, "resolve_canonical_lga_short_name", lambda ae_id, meta: "Moorabool")
    (main.CANONICAL_DIR / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Moorabool Shire Council Enterprise Agreement No. 10 2023\n"
        "sections:\n"
        "  uplifts:\n"
        "    status: in_progress\n"
        "    data:\n"
        "      periods:\n"
        "        - effective_from: '2023-07-01'\n"
        "          uplift_rule_governed_at: '2026-04-23T00:00:00Z'\n"
        "          uplift_rule:\n"
        "            pct_component: 90.0\n"
        "            rate_cap_component: 3.35\n"
        "            pct_of_rate_cap: 0.9\n"
        "            floor_pct: 3.35\n"
        "            pattern_archetype: rate_cap_tracking\n"
        "            pattern_variant: 3.35%, or 90% of rate cap if greater than 3.35%\n",
        encoding="utf-8",
    )

    response = client.get("/api/councils/aetest01/governed-set")

    assert response.status_code == 200, response.text
    rule = response.json()["governed"]["periods"][0]["uplift_rule"]
    assert rule["rate_cap_financial_year"] == "2023-24"
    assert rule["pct_component"] == 3.35
    assert rule["external_cap_pct"] == 3.5
    assert rule["external_cap_share"] == 0.9
    assert rule["external_formula_pct"] == 3.15
    assert rule["resolved_pct"] == 3.35
    assert rule["resolved_basis"] == "internal_pct_floor"


def test_promote_missing_period_404(client):
    response = client.post(
        "/api/councils/aetest01/governed-set/promote",
        json={"period_effective_from": "2099-01-01", "kind": "pay_table"},
    )
    assert response.status_code == 404
