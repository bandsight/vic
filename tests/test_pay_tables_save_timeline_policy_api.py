from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path)
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Test Council"})
    monkeypatch.setattr(main, "fetch_metadata_for_ae_id", lambda *args, **kwargs: {})
    monkeypatch.setattr(main, "resolve_canonical_lga_short_name", lambda *args, **kwargs: None)

    canonical_path = tmp_path / "aetest01.yaml"
    canonical_path.write_text(
        "agreement_id: aetest01\n"
        "source_name: Test Council\n"
        "sections:\n"
        "  pay_tables:\n"
        "    status: in_progress\n"
        "    tables: []\n"
        "  uplift_rules:\n"
        "    data:\n"
        "      accepted:\n"
        "        document:\n"
        "          rules:\n"
        "            - period_label: Year 1\n"
        "              quantum: 3%\n"
        "              effective_date: '2027-07-01'\n"
    )

    return TestClient(main.app)


def test_pay_tables_save_rule_anchored_applies_and_preserves_row_rates(client):
    rows = [
        {
            "band": 1,
            "level": "A",
            "weekly_rate": 1234.56,
        }
    ]
    original_rows = deepcopy(rows)

    payload = {
        "action": "replace",
        "status": "in_progress",
        "timeline_policy": "rule_anchored",
        "tables": [
            {
                "table_title": "Year 1 table",
                "rate_kind": "weekly",
                "effective_from": "2027-07-10",
                "rows": rows,
            }
        ],
    }

    response = client.post("/api/councils/aetest01/pay-tables/save", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["timeline_policy_status"] == "rule_anchored_applied"
    assert body["timeline_policy_issue"] is None
    assert body["section_status"] == "done"
    assert body["completed_at"]

    import main

    saved = main.get_canonical("aetest01")
    assert saved["sections"]["pay_tables"]["status"] == "done"
    assert saved["sections"]["pay_tables"]["completed_at"]
    table = saved["sections"]["pay_tables"]["tables"][0]

    assert table["source_date_raw"] == "2027-07-10"
    assert table["source_date_iso"] == "2027-07-10"
    assert table["canonical_date_iso"] == "2027-07-01"
    assert table["effective_from"] == "2027-07-01"

    assert table["rows"] == original_rows
    assert table["rows"][0]["weekly_rate"] == 1234.56


def test_pay_tables_rule_anchored_keeps_far_baseline_date(client):
    payload = {
        "action": "replace",
        "status": "in_progress",
        "timeline_policy": "rule_anchored",
        "tables": [
            {
                "table_title": "Pre-rule baseline",
                "rate_kind": "weekly",
                "effective_from": "2026-01-01",
                "rows": [{"band": 1, "level": "A", "weekly_rate": 1234.56}],
            }
        ],
    }

    response = client.post("/api/councils/aetest01/pay-tables/save", json=payload)
    assert response.status_code == 200, response.text

    import main

    table = main.get_canonical("aetest01")["sections"]["pay_tables"]["tables"][0]
    assert table["effective_from"] == "2026-01-01"
    assert table["canonical_date_iso"] == "2026-01-01"
    assert "92-day snap guard" in table["snap_note"]


def test_pay_tables_rule_anchored_aligns_year_header_sequence_to_same_year_rules(client):
    import main

    canonical = main.get_canonical("aetest01")
    canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"] = [
        {"period_label": "Year 1", "quantum": "4% or $65", "effective_date": "2024-10-01"},
        {"period_label": "Year 2", "quantum": "3% or $50", "effective_date": "2025-10-01"},
        {"period_label": "Year 3", "quantum": "3% or $50", "effective_date": "2026-10-01"},
    ]
    main.save_canonical("aetest01", canonical)

    payload = {
        "action": "replace",
        "status": "in_progress",
        "timeline_policy": "rule_anchored",
        "tables": [
            {
                "table_title": "Annual Salaries - Bands 1 to 8",
                "rate_kind": "annual",
                "effective_from": "2024-01-01",
                "rows": [{"band": 1, "level": "A", "annual_rate": 60640.00}],
            },
            {
                "table_title": "Annual Salaries - Bands 1 to 8",
                "rate_kind": "annual",
                "effective_from": "2025-01-01",
                "rows": [{"band": 1, "level": "A", "annual_rate": 63240.00}],
            },
            {
                "table_title": "Annual Salaries - Bands 1 to 8",
                "rate_kind": "annual",
                "effective_from": "2026-01-01",
                "rows": [{"band": 1, "level": "A", "annual_rate": 65840.00}],
            },
        ],
    }

    response = client.post("/api/councils/aetest01/pay-tables/save", json=payload)
    assert response.status_code == 200, response.text

    tables = main.get_canonical("aetest01")["sections"]["pay_tables"]["tables"]
    assert [table["effective_from"] for table in tables] == [
        "2024-10-01",
        "2025-10-01",
        "2026-10-01",
    ]
    assert {table["snap_basis"] for table in tables} == {"uplift_rule_year_header"}


def test_pay_tables_save_flags_non_standard_draft_rows(client):
    payload = {
        "action": "replace",
        "status": "in_progress",
        "timeline_policy": "rule_anchored",
        "tables": [
            {
                "table_title": "Mixed table",
                "rate_kind": "weekly",
                "effective_from": "2027-07-10",
                "rows": [
                    {"band": 1, "level": "A", "weekly_rate": 1234.56},
                    {
                        "title": "Maternal and Child Health Nurse Year 1",
                        "weekly_rate": 2000.00,
                    },
                ],
            }
        ],
    }

    response = client.post("/api/councils/aetest01/pay-tables/save", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    codes = [item["code"] for item in body["validations"]]

    assert "non_standard_band_level_rows" in codes
    assert body["section_status"] == "done"


def test_pay_table_review_hints_endpoint_flags_contiguous_candidates(client):
    response = client.post(
        "/api/councils/aetest01/pay-tables/review-hints",
        json={
            "tables": [],
            "suggestions": [],
            "candidate_pages": [20, 21, 22],
        },
    )

    assert response.status_code == 200, response.text
    codes = [hint["code"] for hint in response.json()["hints"]]
    assert "extract_range_for_page_spanning_table" in codes
