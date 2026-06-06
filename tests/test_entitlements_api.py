from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_entitlements_extract_saves_clause_backed_records(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path)
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Test Council"})
    monkeypatch.setattr(main, "find_pdf", lambda _ae_id: None)
    monkeypatch.setattr(main, "fetch_metadata_for_ae_id", lambda *args, **kwargs: {})
    monkeypatch.setattr(main, "resolve_canonical_lga_short_name", lambda *args, **kwargs: "Test Council")
    monkeypatch.setattr(
        main,
        "extract_all_page_texts",
        lambda _ae_id: [
            "Allowance clause. First aid allowance is $2.00 per day for standard employees.",
            "Unrelated page.",
        ],
    )
    monkeypatch.setattr(
        main,
        "call_llm",
        lambda *args, **kwargs: json.dumps(
            {
                "schema_version": "conditions_v1",
                "multi_employer": False,
                "covered_councils": ["Test Council"],
                "items": [
                    {
                        "item_id": "allowances.first_aid",
                        "category": "allowances_reimbursements",
                        "title": "First aid allowance",
                        "summary": "Standard employees appointed to first aid duty receive $2.00 per day.",
                        "materiality": "big_ticket",
                        "extraction_status": "extracted",
                        "applies_to": {"employee_groups": ["standard employees"]},
                        "clauses": [
                            {
                                "clause_id": "clause-1",
                                "heading": "Allowance clause",
                                "source_kind": "agreement_clause",
                                "page_start": 1,
                                "page_end": 1,
                                "text": "First aid allowance is $2.00 per day for standard employees.",
                            }
                        ],
                        "council_applicability": {
                            "mode": "single_council",
                            "applies_to_councils": ["Test Council"],
                        },
                        "values": [
                            {
                                "value_id": "first_aid_allowance_amount",
                                "label": "First aid allowance",
                                "value_type": "money",
                                "raw_value": "$2.00 per day",
                                "role": "entitlement",
                                "basis": "per_day",
                                "numeric_value": 2.0,
                                "currency": "AUD",
                                "source_clause_ids": ["clause-1"],
                            }
                        ],
                        "comparison_keys": ["first_aid_allowance_amount"],
                        "source_pages": [1],
                        "confidence": 0.9,
                    }
                ],
            }
        ),
    )
    (tmp_path / "aetest01.yaml").write_text(
        "agreement_id: aetest01\nsource_name: Test Council\nsections: {}\n",
        encoding="utf-8",
    )

    response = TestClient(main.app).post("/api/councils/aetest01/entitlements/extract")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    canonical = main.get_canonical("aetest01")
    clauses = canonical["sections"]["clauses"]
    assert clauses["status"] == "in_progress"
    assert clauses["data"]["items"][0]["item_id"] == "allowances.first_aid"
    assert clauses["data"]["category_definitions"]["allowances_reimbursements"]
