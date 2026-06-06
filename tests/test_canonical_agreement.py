from __future__ import annotations

from benchmarking_data_factory.workbench.canonical_agreement import (
    build_provenance_stamp,
    fresh_canonical,
    get_nominated_expiry,
    merge_defaults,
    resolve_fwc,
)


def test_fresh_canonical_has_report_defaults_and_independent_lists():
    first = fresh_canonical("ae1", "Agreement One")
    second = fresh_canonical("ae2", "Agreement Two")

    first["overview"]["likely_pay_table_pages"].append(44)
    first["sections"]["pay_tables"]["tables"].append({"table_title": "Schedule A"})

    assert first["agreement_id"] == "ae1"
    assert first["source_name"] == "Agreement One"
    assert second["overview"]["likely_pay_table_pages"] == []
    assert second["sections"]["pay_tables"]["tables"] == []
    assert first["sections"]["overview"]["status"] == "not_started"


def test_merge_defaults_preserves_saved_data_and_fills_missing_sections():
    merged = merge_defaults(
        {
            "agreement_id": "stale",
            "source_name": "Saved Source Name",
            "overview": {"page_count": 162},
            "sections": {"pay_tables": {"status": "done", "tables": [{"table_title": "Band 1"}]}},
        },
        "ae527870",
        "Registry Source Name",
    )

    assert merged["agreement_id"] == "ae527870"
    assert merged["source_name"] == "Saved Source Name"
    assert merged["overview"]["page_count"] == 162
    assert merged["overview"]["red_flags"] == []
    assert merged["sections"]["pay_tables"]["status"] == "done"
    assert merged["sections"]["overview"]["status"] == "not_started"


def test_resolve_fwc_prefers_canonical_fields_over_fetch_metadata():
    resolved = resolve_fwc(
        {
            "fwc": {
                "matter_number": "AG2026/1",
                "expiry_date": "2028-06-30",
            }
        },
        {
            "lga_code": "20110",
            "Matter Number": "AG2024/1004",
            "Print ID": "PR773364",
            "Expiry Date": "2026-06-30",
            "Version": "1",
        },
    )

    assert resolved["lga_code"] == "20110"
    assert resolved["matter_number"] == "AG2026/1"
    assert resolved["print_id"] == "PR773364"
    assert resolved["expiry_date"] == "2028-06-30"
    assert resolved["version"] == "1"


def test_nominated_expiry_uses_canonical_then_provenance_then_lookup():
    assert (
        get_nominated_expiry(
            {
                "agreement_id": "ae1",
                "fwc": {"expiry_date": "2027-06-30"},
                "sections": {"front_matter": {"data": {"nominated_expiry": "2030-06-30"}}},
            },
            lambda _ae_id: {"Expiry Date": "2099-01-01"},
        )
        == "2030-06-30"
    )

    assert (
        get_nominated_expiry(
            {
                "agreement_id": "ae2",
                "fwc": {},
                "sections": {
                    "front_matter": {"data": None},
                    "pay_tables": {"tables": [{"provenance": {"expiry_date": "2027-09-30"}}]},
                },
            },
            lambda _ae_id: {"Expiry Date": "2099-01-01"},
        )
        == "2027-09-30"
    )

    assert get_nominated_expiry({"agreement_id": "ae3", "fwc": {}, "sections": {}}, lambda _ae_id: {"Expiry Date": "2028-12-31"}) == "2028-12-31"


def test_nominated_expiry_lookup_failure_is_non_blocking():
    def lookup(_ae_id: str) -> dict:
        raise RuntimeError("metadata not available")

    assert get_nominated_expiry({"agreement_id": "ae1", "fwc": {}, "sections": {}}, lookup) is None


def test_build_provenance_stamp_uses_standard_fwc_and_lineage_fields():
    stamp = build_provenance_stamp(
        {"fwc": {"expiry_date": "2028-06-30"}},
        {
            "lga_code": "20110",
            "Matter Number": "AG2024/1004",
            "Print ID": "PR773364",
            "Version": "1",
            "scope_resolution_status": "title_only_unresolved",
            "lineage_key": "Alpine::matter::ag2024 1004",
        },
        "ae524168",
        "Alpine",
    )

    assert stamp == {
        "agreement_id": "ae524168",
        "canonical_lga_short_name": "Alpine",
        "lga_code": "20110",
        "matter_number": "AG2024/1004",
        "print_id": "PR773364",
        "expiry_date": "2028-06-30",
        "version": "1",
        "superseded_by_ae_id": None,
        "scope_resolution_status": "title_only_unresolved",
        "lineage_key": "Alpine::matter::ag2024 1004",
    }
