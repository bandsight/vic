import csv
import math
from pathlib import Path
import re

from scripts.build_entitlement_clause_evidence import (
    ADDITIONAL_ANNUAL_LEAVE_PROFILE,
    build_payload,
)
from scripts.entitlement_statistical_calibration import (
    beta_binomial_distribution,
    beta_binomial_predictive_calibration,
)
from scripts.build_standard_entitlement_profile_evidence import (
    COMPASSIONATE_PROFILE,
    CULTURAL_CEREMONIAL_PROFILE,
    EMERGENCY_SERVICES_PROFILE,
    FAMILY_DOMESTIC_VIOLENCE_PROFILE,
    NATURAL_DISASTER_PROFILE,
    PARENTAL_NON_PRIMARY_PROFILE,
    PARENTAL_PRIMARY_PROFILE,
    build_payload as build_standard_entitlement_payload,
)


ROOT = Path(__file__).resolve().parents[1]


def _normalise_suffix(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _latest_candidate_by_lga() -> dict[str, dict[str, str]]:
    rows_by_lga: dict[str, list[dict[str, str]]] = {}
    candidate_path = ROOT / "data/bronze/phase1_source_build/candidate_agreements/candidate_agreements.csv"
    with candidate_path.open(newline="", encoding="cp1252", errors="replace") as handle:
        for row in csv.DictReader(handle):
            if row.get("state_name") != "Victoria" or row.get("classification") != "core_local_gov":
                continue
            agreement_id = (row.get("Agreement ID") or "").lower()
            if not agreement_id.startswith("ae"):
                continue
            lga_names = [row["lga_short_name"]] if row.get("lga_short_name") else []
            if not lga_names and row.get("matched_lga_names"):
                lga_names = [name.strip() for name in row["matched_lga_names"].split("|") if name.strip()]
            for lga_name in lga_names:
                rows_by_lga.setdefault(lga_name, []).append(row)

    def sort_key(row: dict[str, str]) -> tuple[int, int]:
        try:
            operative_date = int(float(row.get("Operative Date") or 0))
        except ValueError:
            operative_date = 0
        agreement_number = int(re.sub(r"\D", "", row.get("Agreement ID") or "0") or 0)
        return operative_date, agreement_number

    return {
        lga_name: max(rows, key=sort_key)
        for lga_name, rows in rows_by_lga.items()
    }


def test_beta_binomial_calibration_uses_real_predictive_math():
    distribution = beta_binomial_distribution(8, 2.5, 8.5)
    calibration = beta_binomial_predictive_calibration(
        2,
        10,
        3,
        8,
        metric="source_clause_observed",
        target_label="B stress extension",
    )

    assert math.isclose(sum(distribution), 1.0, rel_tol=0, abs_tol=1e-12)
    assert calibration["expected_count"] == 1.82
    assert calibration["expected_percent"] == 22.7
    assert calibration["predictive_intervals"]["95_percent"]["count"][0] == 0
    assert calibration["predictive_intervals"]["95_percent"]["count"][1] >= 3
    assert calibration["inside_95_predictive_interval"] is True
    assert 0 <= calibration["fit_confidence"] <= 1


def test_latest_candidate_agreements_are_promoted_to_canonical():
    canonical_ids = {path.stem.lower() for path in (ROOT / "canonical").glob("ae*.yaml")}
    latest_by_lga = _latest_candidate_by_lga()

    missing = []
    for lga_name, row in latest_by_lga.items():
        agreement_id = row["Agreement ID"].lower()
        suffixed_agreement_id = f"{agreement_id}__{_normalise_suffix(lga_name)}"
        if agreement_id not in canonical_ids and suffixed_agreement_id not in canonical_ids:
            missing.append((lga_name, row["Agreement ID"], row["Agreement Title"]))

    assert not missing
    assert latest_by_lga["Wyndham"]["Agreement ID"] == "AE521909"


def test_additional_annual_leave_profile_finds_clause_backed_evidence():
    payload = build_payload(ADDITIONAL_ANNUAL_LEAVE_PROFILE, generated_at="2026-05-05T00:00:00+00:00")
    rows = {row["council"]: row for row in payload["council_evidence"]}

    assert payload["summary"]["councils"] == 23
    assert payload["summary"]["source_clause_observed"] == 6
    assert payload["summary"]["rows_needing_absence_or_scope_automation"] == 17
    assert payload["summary"]["row_source_backed_percent"] == 26.1
    assert payload["summary"]["row_remaining_automation_percent"] == 73.9
    assert payload["summary"]["total_pages_scanned"] > 3500
    assert payload["summary"]["candidate_pages_found"] == 53
    assert payload["summary"]["candidate_subclass_counts"]["Top-of-Band Payment"] == 6
    assert payload["summary"]["candidate_subclass_counts"]["Work Area / Roster Specific Additional Leave"] == 1
    assert payload["summary"]["candidate_subclass_counts"]["Existing Leave Administration"] == 1
    assert "Needs Review" not in payload["summary"]["candidate_subclass_counts"]
    assert payload["summary"]["source_subclass_counts"]["Annual Leave Management Bonus Leave"] == 2
    assert payload["classification_boundary"]["canonical_definition"]
    assert payload["global_takeaway"].startswith("Across the current source evidence set")
    assert "Ballarat" not in payload["global_takeaway"]
    assert "above the NES" in payload["classification_boundary"]["canonical_definition"]
    assert "Extra paid leave above the NES or ordinary annual leave baseline." in payload["classification_boundary"]["included"]
    assert "Purchased leave funded through reduced pay." in payload["classification_boundary"]["excluded"]
    assert payload["ab_test"]["baseline"]["councils"] == 10
    assert payload["ab_test"]["baseline"]["source_clause_observed"] == 2
    assert payload["ab_test"]["baseline"]["row_source_backed_percent"] == 20.0
    assert payload["ab_test"]["training_variant"]["councils"] == 18
    assert payload["ab_test"]["training_variant"]["source_clause_observed"] == 5
    assert payload["ab_test"]["validation_batch"]["councils"] == 5
    assert payload["ab_test"]["validation_batch"]["source_clause_observed"] == 1
    assert len(payload["ab_test"]["extension_comparator_set"]) == 8
    assert len(payload["ab_test"]["validation_comparator_set"]) == 5
    assert payload["ab_test"]["stress_extension"]["councils"] == 8
    assert payload["ab_test"]["stress_extension"]["source_clause_observed"] == 3
    calibration = payload["ab_test"]["statistical_calibration"]
    assert calibration["model"] == "beta_binomial_predictive"
    assert calibration["prior"] == {"name": "Jeffreys beta(0.5, 0.5)", "alpha": 0.5, "beta": 0.5}
    assert calibration["baseline"]["observed_count"] == 2
    assert calibration["baseline"]["sample_size"] == 10
    assert calibration["baseline"]["posterior_mean_percent"] == 22.7
    assert calibration["groups"]["stress_extension"]["observed_count"] == 3
    assert calibration["groups"]["stress_extension"]["sample_size"] == 8
    assert calibration["groups"]["stress_extension"]["expected_count"] == 1.82
    assert calibration["groups"]["stress_extension"]["inside_95_predictive_interval"] is True
    assert calibration["groups"]["validation_batch"]["observed_count"] == 1
    assert calibration["groups"]["validation_batch"]["sample_size"] == 5
    assert calibration["groups"]["extension_plus_validation"]["observed_count"] == 4
    assert calibration["groups"]["extension_plus_validation"]["sample_size"] == 13
    assert payload["methodology"]["hit_discovery_method"]["acceptance_rule"]
    assert payload["methodology"]["hit_discovery_method"]["classification_boundary"]["included"]
    assert payload["methodology"]["hit_discovery_method"]["learned_hit_patterns"]
    assert payload["learned_pattern_retest"]["rows_retested"] == 17
    assert payload["learned_pattern_retest"]["remaining_needs_review_candidates"] == 0
    assert payload["methodology"]["learnings_applied"]
    comparator_rows = {row["council"]: row for row in payload["comparator_set"]}
    assert comparator_rows["Ballarat"]["agreement_id"] == "ae526078"
    assert comparator_rows["Ballarat"]["resolved_from_agreement_id"] == "ae507751"
    assert comparator_rows["Darebin"]["agreement_id"] == "ae526336"
    assert comparator_rows["Maroondah"]["agreement_id"] == "ae530749"
    assert rows["Moorabool"]["presence"] == "source_clause_observed"
    assert rows["Moorabool"]["source_ref"]["agreement_id"] == "ae521210"
    assert rows["Moorabool"]["source_excerpts"][0]["clause_label"]
    assert rows["Moorabool"]["source_excerpts"][0]["page_label"].startswith("p.")
    assert rows["Moorabool"]["source_excerpts"][0]["clause_segments"]
    assert len(rows["Moorabool"]["source_excerpts"][0]["clause_text"]) < len(rows["Moorabool"]["source_excerpts"][0]["excerpt"])
    assert any(value["value"] == "1 or 2" for value in rows["Moorabool"]["normalised_values"])
    assert any("top of band" in value["condition"] for value in rows["Moorabool"]["normalised_values"])
    assert rows["Wyndham"]["presence"] == "source_clause_observed"
    assert rows["Wyndham"]["source_ref"]["page"] == 64
    assert any(value["value"] == "5" for value in rows["Wyndham"]["normalised_values"])
    assert rows["Queenscliffe"]["presence"] == "source_clause_observed"
    assert any(value["value"] == "5" for value in rows["Queenscliffe"]["normalised_values"])
    assert rows["Southern Grampians"]["presence"] == "source_clause_observed"
    assert any("16 years" in value["condition"] for value in rows["Southern Grampians"]["normalised_values"])
    assert rows["Maribyrnong"]["presence"] == "source_clause_observed"
    assert rows["Maribyrnong"]["source_ref"]["page"] == 29
    assert any(value["value"] == "3" for value in rows["Maribyrnong"]["normalised_values"])
    assert any(value["value"] == "4" for value in rows["Maribyrnong"]["normalised_values"])
    assert rows["Greater Geelong"]["presence"] == "source_clause_observed"
    assert rows["Greater Geelong"]["source_ref"]["page"] == 61
    assert rows["Greater Geelong"]["normalised_values"][0]["value"] == "3"
    assert rows["Greater Geelong"]["normalised_values"][0]["subclass_label"] == "Annual Leave Management Bonus Leave"

    assert rows["Ballarat"]["presence"] == "no_source_clause_match"
    assert rows["Ballarat"]["candidate_pages"][0]["out_of_scope_signals"]
    assert rows["Knox"]["presence"] == "no_source_clause_match"
    assert "purchased_leave_model" in rows["Knox"]["candidate_pages"][0]["out_of_scope_signals"]
    assert "carer_special_needs" in rows["Darebin"]["candidate_pages"][0]["out_of_scope_signals"]
    assert any(
        "specialist_mch_or_nurse" in candidate["out_of_scope_signals"]
        for candidate in rows["Glen Eira"]["candidate_pages"]
    )
    assert rows["East Gippsland"]["candidate_pages"][0]["suggested_subclass"]["label"] == "Top-of-Band Payment"
    assert rows["Port Phillip"]["candidate_pages"][0]["suggested_subclass"]["label"] == "Top-of-Band Payment"
    assert rows["Stonnington"]["candidate_pages"][0]["suggested_subclass"]["label"] == "Specialist Cohort Additional Leave"
    assert any(
        candidate["suggested_subclass"]["label"] == "Work Area / Roster Specific Additional Leave"
        for candidate in rows["Maroondah"]["candidate_pages"]
    )


def test_family_domestic_violence_profile_reconciles_reference_values():
    payload = build_standard_entitlement_payload(
        FAMILY_DOMESTIC_VIOLENCE_PROFILE,
        generated_at="2026-05-09T00:00:00+00:00",
    )
    rows = {row["council"]: row for row in payload["council_evidence"]}

    assert payload["summary"]["councils"] == 10
    assert payload["summary"]["source_clause_observed"] == 10
    assert payload["summary"]["row_source_backed_percent"] == 100.0
    assert payload["summary"]["reference_value_matched_rows"] == 9
    assert payload["summary"]["reference_value_partial_rows"] == 0
    assert payload["summary"]["reference_value_unmatched_rows"] == 1
    assert payload["summary"]["reference_comparison_counts"]["reference_values_matched"] == 9
    assert "reference_values_partially_matched" not in payload["summary"]["reference_comparison_counts"]
    assert payload["summary"]["reference_comparison_counts"]["reference_value_not_source_backed"] == 1
    assert payload["methodology"]["hit_discovery_method"]["reference_reconciliation_rule"]

    comparator_rows = {row["council"]: row for row in payload["comparator_set"]}
    assert comparator_rows["Ararat"]["agreement_id"] == "ae532042__ararat"
    assert comparator_rows["Ararat"]["resolved_from_agreement_id"] == "ae516638"
    assert comparator_rows["Ballarat"]["agreement_id"] == "ae526078"
    assert comparator_rows["Ballarat"]["resolved_from_agreement_id"] == "ae507751"

    assert rows["Ararat"]["source_ref"]["agreement_id"] == "ae532042__ararat"
    assert rows["Ararat"]["reference_comparison"]["source_quantum_signals"] == ["20 days"]
    assert rows["Central Goldfields"]["source_ref"]["agreement_id"] == "ae532042__central_goldfields"
    assert rows["Central Goldfields"]["source_ref"]["page"] == 51
    assert rows["Golden Plains"]["source_ref"]["agreement_id"] == "ae531808"
    assert rows["Pyrenees"]["reference_comparison"]["source_quantum_signals"] == ["10 days"]

    assert rows["Hepburn"]["reference_comparison"]["status"] == "reference_values_matched"
    assert any(
        value["value"] == "5" and value["subclass_label"] == "Support Person FDV Paid Leave"
        for value in rows["Hepburn"]["normalised_values"]
    )

    assert rows["Ballarat"]["reference_comparison"]["status"] == "reference_values_matched"
    assert rows["Ballarat"]["reference_comparison"]["missing_reference_quantum_signals"] == []
    assert rows["Ballarat"]["reference_comparison"]["source_quantum_signals"] == ["20 days", "5 days"]

    assert rows["Mount Alexander"]["reference_comparison"]["status"] == "reference_values_matched"
    assert any(
        value["value"] == "5" and value["benchmark_value"] == "false"
        for value in rows["Mount Alexander"]["normalised_values"]
    )

    assert rows["Wyndham"]["presence"] == "source_clause_observed"
    assert rows["Wyndham"]["source_ref"]["page"] == 61
    assert rows["Wyndham"]["reference_comparison"]["status"] == "reference_value_not_source_backed"
    assert rows["Wyndham"]["reference_comparison"]["missing_reference_quantum_signals"] == ["20 days"]


def test_natural_disaster_profile_reconciles_reference_values():
    payload = build_standard_entitlement_payload(
        NATURAL_DISASTER_PROFILE,
        generated_at="2026-05-09T00:00:00+00:00",
    )
    rows = {row["council"]: row for row in payload["council_evidence"]}

    assert payload["summary"]["councils"] == 10
    assert payload["summary"]["source_clause_observed"] == 8
    assert payload["summary"]["row_source_backed_percent"] == 80.0
    assert payload["summary"]["reference_value_matched_rows"] == 10
    assert payload["summary"]["reference_value_unmatched_rows"] == 0
    assert payload["summary"]["reference_comparison_counts"]["reference_values_matched"] == 10

    assert rows["Ararat"]["source_ref"]["agreement_id"] == "ae532042__ararat"
    assert rows["Ararat"]["source_ref"]["page"] == 61
    assert rows["Ararat"]["reference_comparison"]["source_quantum_signals"] == ["5 paid days"]
    assert rows["Central Goldfields"]["reference_comparison"]["source_quantum_signals"] == ["5 paid days"]
    assert rows["Greater Bendigo"]["source_ref"]["agreement_id"] == "ae528428"
    assert rows["Greater Bendigo"]["source_ref"]["page"] == 30
    assert rows["Greater Bendigo"]["reference_comparison"]["source_quantum_signals"] == ["2 weeks"]

    assert rows["Ballarat"]["presence"] == "source_clause_observed"
    assert rows["Ballarat"]["source_ref"]["page"] == 62
    assert rows["Golden Plains"]["presence"] == "source_clause_observed"
    assert rows["Moorabool"]["presence"] == "source_clause_observed"
    assert rows["Mount Alexander"]["presence"] == "source_clause_observed"
    assert rows["Wyndham"]["presence"] == "source_clause_observed"
    assert rows["Wyndham"]["source_ref"]["page"] == 64

    assert rows["Hepburn"]["presence"] == "no_source_clause_match"
    assert rows["Pyrenees"]["presence"] == "no_source_clause_match"


def test_parental_primary_profile_reconciles_reference_values():
    payload = build_standard_entitlement_payload(
        PARENTAL_PRIMARY_PROFILE,
        generated_at="2026-05-09T00:00:00+00:00",
    )
    rows = {row["council"]: row for row in payload["council_evidence"]}

    assert payload["summary"]["councils"] == 10
    assert payload["summary"]["source_clause_observed"] == 10
    assert payload["summary"]["row_source_backed_percent"] == 100.0
    assert payload["summary"]["reference_value_matched_rows"] == 10
    assert payload["summary"]["reference_value_unmatched_rows"] == 0
    assert payload["summary"]["reference_comparison_counts"]["reference_values_matched"] == 10

    assert rows["Ararat"]["reference_comparison"]["source_quantum_signals"] == ["10 days", "17 weeks"]
    assert rows["Central Goldfields"]["reference_comparison"]["source_quantum_signals"] == ["10 days", "17 weeks"]
    assert rows["Golden Plains"]["reference_comparison"]["source_quantum_signals"] == ["16 weeks"]
    assert rows["Moorabool"]["source_ref"]["page"] == 112
    assert rows["Moorabool"]["reference_comparison"]["source_quantum_signals"] == ["19 weeks"]
    assert rows["Wyndham"]["reference_comparison"]["source_quantum_signals"] == ["17 weeks", "3 days"]
    assert len(rows["Wyndham"]["source_excerpts"]) > 1


def test_parental_non_primary_profile_marks_ballarat_reference_disagreement():
    payload = build_standard_entitlement_payload(
        PARENTAL_NON_PRIMARY_PROFILE,
        generated_at="2026-05-09T00:00:00+00:00",
    )
    rows = {row["council"]: row for row in payload["council_evidence"]}

    assert payload["summary"]["councils"] == 10
    assert payload["summary"]["source_clause_observed"] == 10
    assert payload["summary"]["row_source_backed_percent"] == 100.0
    assert payload["summary"]["reference_value_matched_rows"] == 9
    assert payload["summary"]["reference_value_partial_rows"] == 1
    assert payload["summary"]["reference_value_unmatched_rows"] == 0
    assert payload["summary"]["reference_comparison_counts"]["reference_values_matched"] == 9
    assert payload["summary"]["reference_comparison_counts"]["reference_values_partially_matched"] == 1

    assert rows["Ballarat"]["source_ref"]["page"] == 40
    assert rows["Ballarat"]["reference_comparison"]["status"] == "reference_values_partially_matched"
    assert rows["Ballarat"]["reference_comparison"]["missing_reference_quantum_signals"] == ["10 days"]
    assert rows["Ballarat"]["reference_comparison"]["extra_source_quantum_signals"] == ["5 days"]

    assert rows["Golden Plains"]["reference_comparison"]["source_quantum_signals"] == ["3 weeks"]
    assert rows["Moorabool"]["source_ref"]["page"] == 112
    assert rows["Moorabool"]["reference_comparison"]["source_quantum_signals"] == ["3 weeks"]
    assert rows["Pyrenees"]["reference_comparison"]["source_quantum_signals"] == ["1 day", "2 weeks"]
    assert rows["Wyndham"]["reference_comparison"]["source_quantum_signals"] == ["5 hours", "6 weeks"]


def test_compassionate_profile_reconciles_reference_values():
    payload = build_standard_entitlement_payload(
        COMPASSIONATE_PROFILE,
        generated_at="2026-05-09T00:00:00+00:00",
    )
    rows = {row["council"]: row for row in payload["council_evidence"]}

    assert payload["summary"]["councils"] == 10
    assert payload["summary"]["source_clause_observed"] == 10
    assert payload["summary"]["row_source_backed_percent"] == 100.0
    assert payload["summary"]["reference_value_matched_rows"] == 10
    assert payload["summary"]["reference_value_unmatched_rows"] == 0
    assert payload["summary"]["reference_comparison_counts"]["reference_values_matched"] == 10

    assert rows["Ararat"]["source_ref"]["agreement_id"] == "ae532042__ararat"
    assert rows["Ararat"]["reference_comparison"]["source_quantum_signals"] == ["5 days"]
    assert rows["Golden Plains"]["reference_comparison"]["source_quantum_signals"] == ["3 days", "4 days"]
    assert rows["Moorabool"]["reference_comparison"]["source_quantum_signals"] == ["3 days", "5 days"]
    assert rows["Pyrenees"]["source_ref"]["page"] == 25
    assert rows["Pyrenees"]["reference_comparison"]["source_quantum_signals"] == ["5 days", "8 weeks"]
    assert rows["Wyndham"]["reference_comparison"]["source_quantum_signals"] == ["3 days", "4 days"]


def test_cultural_ceremonial_profile_reconciles_reference_values():
    payload = build_standard_entitlement_payload(
        CULTURAL_CEREMONIAL_PROFILE,
        generated_at="2026-05-09T00:00:00+00:00",
    )
    rows = {row["council"]: row for row in payload["council_evidence"]}

    assert payload["summary"]["councils"] == 10
    assert payload["summary"]["source_clause_observed"] == 8
    assert payload["summary"]["row_source_backed_percent"] == 80.0
    assert payload["summary"]["reference_value_matched_rows"] == 10
    assert payload["summary"]["reference_value_unmatched_rows"] == 0
    assert payload["summary"]["reference_comparison_counts"]["reference_values_matched"] == 10

    assert rows["Ararat"]["reference_comparison"]["source_quantum_signals"] == ["1 paid day"]
    assert rows["Golden Plains"]["source_ref"]["page"] == 38
    assert rows["Golden Plains"]["reference_comparison"]["source_quantum_signals"] == ["1 paid day"]
    assert rows["Greater Bendigo"]["reference_comparison"]["source_quantum_signals"] == ["3 paid days"]
    assert rows["Moorabool"]["presence"] == "source_clause_observed"
    assert rows["Moorabool"]["reference_comparison"]["source_quantum_signals"] == []
    assert rows["Pyrenees"]["presence"] == "no_source_clause_match"
    assert rows["Wyndham"]["presence"] == "source_clause_observed"
    assert rows["Wyndham"]["reference_comparison"]["source_quantum_signals"] == []


def test_emergency_services_profile_reconciles_reference_values():
    payload = build_standard_entitlement_payload(
        EMERGENCY_SERVICES_PROFILE,
        generated_at="2026-05-09T00:00:00+00:00",
    )
    rows = {row["council"]: row for row in payload["council_evidence"]}

    assert payload["summary"]["councils"] == 10
    assert payload["summary"]["source_clause_observed"] == 8
    assert payload["summary"]["row_source_backed_percent"] == 80.0
    assert payload["summary"]["reference_value_matched_rows"] == 10
    assert payload["summary"]["reference_value_unmatched_rows"] == 0
    assert payload["summary"]["reference_comparison_counts"]["reference_values_matched"] == 10

    assert rows["Ararat"]["reference_comparison"]["source_quantum_signals"] == ["2 weeks"]
    assert rows["Ballarat"]["reference_comparison"]["source_quantum_signals"] == ["1 week"]
    assert rows["Golden Plains"]["presence"] == "no_source_clause_match"
    assert rows["Greater Bendigo"]["presence"] == "source_clause_observed"
    assert rows["Greater Bendigo"]["reference_comparison"]["source_quantum_signals"] == []
    assert rows["Mount Alexander"]["source_ref"]["page"] == 31
    assert rows["Mount Alexander"]["reference_comparison"]["source_quantum_signals"] == ["5 paid days"]
    assert rows["Wyndham"]["presence"] == "source_clause_observed"
    assert rows["Wyndham"]["reference_comparison"]["source_quantum_signals"] == []
