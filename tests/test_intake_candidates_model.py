import json

from benchmarking_data_factory.workbench.intake_candidates import (
    build_intake_candidate_rows_from_sources,
    candidate_lgas,
    intake_acceptance_state,
    load_candidate_rows_from_path,
    load_intake_decisions_from_path,
)


def test_candidate_loader_normalises_excel_serial_dates(tmp_path):
    path = tmp_path / "candidate_agreements.json"
    path.write_text(
        json.dumps([
            {
                "Agreement ID": "AE1",
                "Operative Date": 45474,
                "Expiry Date": "46570",
            }
        ]),
        encoding="utf-8",
    )

    rows = load_candidate_rows_from_path(path)

    assert rows[0]["Operative Date"] == "2024-07-01"
    assert rows[0]["Expiry Date"] == "2027-07-02"


def test_candidate_lgas_support_pipe_lists_and_lga_fallback():
    assert candidate_lgas({"matched_lga_names": "Alpine|Ballarat"}) == ["Alpine", "Ballarat"]
    assert candidate_lgas({"matched_lga_names": "", "lga_short_name": "Bayside"}) == ["Bayside"]


def test_intake_acceptance_state_prioritises_analyst_decision():
    assert intake_acceptance_state(
        decision_status="needs_review",
        in_working_set=True,
        pipeline_status="active",
    ) == "needs_review"
    assert intake_acceptance_state(
        decision_status="",
        in_working_set=False,
        pipeline_status="superseded_by_newer",
    ) == "rejected"


def test_build_intake_candidate_rows_marks_source_and_scope_gates():
    candidate_rows = [
        {
            "Agreement ID": "AE100002",
            "Agreement Title": "Example Shire Agreement",
            "Operative Date": "2024-07-01",
            "Expiry Date": "2027-06-30",
            "matched_lga_names": "Example",
            "pipeline_status": "active",
        },
        {
            "Agreement ID": "AE200001",
            "Agreement Title": "Unmatched Agreement",
            "Operative Date": "2024-07-01",
            "matched_lga_names": "",
            "pipeline_status": "active",
        },
    ]

    rows = build_intake_candidate_rows_from_sources(
        candidate_rows=candidate_rows,
        registry={"ae100002": "Fetched source"},
        frozen_pdf_ids={"ae100002"},
        intake_decisions={"ae200001": {"status": "needs_review"}},
        pdf_source_lookup=lambda ae_id: {"frozen": ae_id == "ae100002"},
    )

    fetched = rows[0]
    unmatched = next(row for row in rows if row["ae_id"] == "ae200001")
    assert fetched["source_name"] == "Fetched source"
    assert fetched["acceptance_state"] == "accepted"
    assert fetched["qa_available"] is True
    assert fetched["report_values"]["agreement_period"] == "2024-07-01 to 2027-06-30"
    assert unmatched["acceptance_state"] == "needs_review"
    assert unmatched["processing_gated"] is True


def test_load_intake_decisions_accepts_list_and_dict_payloads(tmp_path):
    list_path = tmp_path / "list.json"
    list_path.write_text(json.dumps({"decisions": [{"ae_id": "AE1", "status": "accepted"}]}), encoding="utf-8")
    dict_path = tmp_path / "dict.json"
    dict_path.write_text(json.dumps({"AE2": {"status": "rejected"}}), encoding="utf-8")

    assert load_intake_decisions_from_path(list_path)["ae1"]["status"] == "accepted"
    assert load_intake_decisions_from_path(dict_path)["ae2"]["ae_id"] == "ae2"
