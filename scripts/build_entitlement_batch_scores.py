from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_entitlement_clause_evidence as annual
from scripts import build_standard_entitlement_profile_evidence as standard
from scripts.entitlement_statistical_calibration import calibrate_binary_metric_groups


DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "entitlement-clause-evidence"


STANDARD_PROFILES = [
    standard.FAMILY_DOMESTIC_VIOLENCE_PROFILE,
    standard.NATURAL_DISASTER_PROFILE,
    standard.COMPASSIONATE_PROFILE,
    standard.CULTURAL_CEREMONIAL_PROFILE,
    standard.EMERGENCY_SERVICES_PROFILE,
    standard.PARENTAL_PRIMARY_PROFILE,
    standard.PARENTAL_NON_PRIMARY_PROFILE,
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def latest_candidate_agreements_by_lga() -> dict[str, dict[str, str]]:
    rows_by_lga: dict[str, list[dict[str, str]]] = {}
    candidate_path = ROOT / "data/bronze/phase1_source_build/candidate_agreements/candidate_agreements.csv"
    with candidate_path.open(newline="", encoding="cp1252", errors="replace") as handle:
        for row in csv.DictReader(handle):
            if row.get("state_name") != "Victoria" or row.get("classification") != "core_local_gov":
                continue
            agreement_id = (row.get("Agreement ID") or "").lower()
            if not annual.AGREEMENT_ID_PATTERN.fullmatch(agreement_id):
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


def curated_council_names() -> set[str]:
    names = {normalise_name(row["council"]) for row in annual.COMPARATOR_AGREEMENTS}
    names.update(normalise_name(f"{row['council']} council") for row in annual.COMPARATOR_AGREEMENTS)
    return names


def intake_decisions_by_agreement_id() -> dict[str, dict[str, Any]]:
    path = ROOT / "registers" / "intake-decisions.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    decisions: dict[str, dict[str, Any]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            agreement_id = str(value.get("ae_id") or "").lower()
            if annual.AGREEMENT_ID_PATTERN.fullmatch(agreement_id):
                decisions[agreement_id] = value
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return decisions


def has_valid_agreement_text(agreement_id: str, decisions: dict[str, dict[str, Any]]) -> bool:
    decision = decisions.get(agreement_id.lower())
    if not decision:
        return True
    reason = normalise_name(decision.get("reason", ""))
    notes = normalise_name(decision.get("notes", ""))
    decision_text = f"{reason} {notes}"
    return not (
        decision.get("status") == "needs_review"
        and "approval decision" in decision_text
        and "not agreement text" in decision_text
    )


def eligible_latest_cached_agreements() -> list[dict[str, str]]:
    current_councils = curated_council_names()
    current_agreement_ids = {
        row["agreement_id"]
        for row in annual.COMPARATOR_AGREEMENTS
    } | {
        row.get("resolved_from_agreement_id", row["agreement_id"])
        for row in annual.COMPARATOR_AGREEMENTS
    }
    latest_by_lga = latest_candidate_agreements_by_lga()
    intake_decisions = intake_decisions_by_agreement_id()
    selected: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for council in sorted(latest_by_lga):
        if normalise_name(council) in current_councils:
            continue
        latest_seed = latest_by_lga[council]["Agreement ID"].lower()
        resolved = annual.latest_agreement_for_council(council, latest_seed)
        if resolved["agreement_id"] in current_agreement_ids or resolved["agreement_id"] in seen_ids:
            continue
        if not (ROOT / "cache" / resolved["agreement_id"] / "pages.json").exists():
            continue
        if not has_valid_agreement_text(resolved["agreement_id"], intake_decisions):
            continue
        selected.append(resolved)
        seen_ids.add(resolved["agreement_id"])
    return selected


def metric_score(
    baseline_summary: dict[str, Any],
    target_summary: dict[str, Any],
    *,
    metric: str,
    metric_label: str,
    batch_key: str,
) -> dict[str, Any]:
    calibration = calibrate_binary_metric_groups(
        baseline_summary,
        {batch_key: target_summary},
        metric=metric,
        metric_label=metric_label,
    )
    return {
        "baseline": calibration["baseline"],
        "score": calibration["groups"][batch_key],
        "confidence_definition": calibration["confidence_definition"],
    }


def evidence_hits(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for row in rows:
        if row.get("presence") != "source_clause_observed":
            continue
        hits.append({
            "council": row.get("council"),
            "agreement_id": row.get("agreement_id"),
            "presence": row.get("presence"),
            "source_page": (row.get("source_ref") or {}).get("page"),
            "normalised_values": row.get("normalised_values") or [],
            "finding": row.get("finding"),
        })
    return hits


def build_standard_profile_score(profile: dict[str, Any], target_agreements: list[dict[str, str]], batch_key: str) -> dict[str, Any]:
    baseline_rows = standard.build_rows(profile, standard.BASELINE_COMPARATOR_AGREEMENTS)
    target_rows = standard.build_rows(profile, target_agreements)
    baseline_summary = standard.summary_for_rows(baseline_rows)
    target_summary = standard.summary_for_rows(target_rows)
    return {
        "artifact_id": profile["artifact_id"],
        "entitlement_id": profile["entitlement_id"],
        "label": profile["label"],
        "summary": target_summary,
        "metrics": {
            "source_clause_observed": metric_score(
                baseline_summary,
                target_summary,
                metric="source_clause_observed",
                metric_label="council rows with a source-backed clause",
                batch_key=batch_key,
            ),
            "source_quantum_observed": metric_score(
                baseline_summary,
                target_summary,
                metric="source_quantum_observed_rows",
                metric_label="council rows with a source-backed quantum",
                batch_key=batch_key,
            ),
        },
        "source_hits": evidence_hits(target_rows),
    }


def build_additional_annual_score(target_agreements: list[dict[str, str]], batch_key: str) -> dict[str, Any]:
    profile = annual.ADDITIONAL_ANNUAL_LEAVE_PROFILE
    baseline_rows = annual.build_rows(profile, annual.BASELINE_COMPARATOR_AGREEMENTS)
    target_rows = annual.build_rows(profile, target_agreements)
    baseline_summary = annual.summary_for_rows(baseline_rows)
    target_summary = annual.summary_for_rows(target_rows)
    return {
        "artifact_id": profile["artifact_id"],
        "entitlement_id": profile["entitlement_id"],
        "label": profile["label"],
        "summary": target_summary,
        "metrics": {
            "source_clause_observed": metric_score(
                baseline_summary,
                target_summary,
                metric="source_clause_observed",
                metric_label="council rows with a source-backed clause",
                batch_key=batch_key,
            ),
        },
        "source_hits": evidence_hits(target_rows),
    }


def build_score_payload(batch_size: int | None, offset: int, generated_at: str) -> dict[str, Any]:
    eligible = eligible_latest_cached_agreements()
    effective_batch_size = len(eligible) - offset if batch_size is None else batch_size
    target_agreements = eligible[offset: offset + effective_batch_size]
    batch_key = f"next_{effective_batch_size}_offset_{offset}"
    profiles = [
        build_additional_annual_score(target_agreements, batch_key),
        *[
            build_standard_profile_score(profile, target_agreements, batch_key)
            for profile in STANDARD_PROFILES
        ],
    ]
    return {
        "schema_version": "wiki.entitlement_batch_scores.v1",
        "artifact_id": f"entitlement-batch-scores-next-{effective_batch_size}-offset-{offset}",
        "generated_at": generated_at,
        "scope_focus": "standard_employees",
        "selection_rule": (
            "Latest cached Victorian core-local-government agreements, sorted by council name, excluding the curated "
            "23-council A/B/C comparator set and cached approval-decision PDFs that the intake register marks as not agreement text."
        ),
        "batch_size": effective_batch_size,
        "offset": offset,
        "available_eligible_councils": len(eligible),
        "target_comparator_set": [
            {
                "council": row["council"],
                "agreement_id": row["agreement_id"],
                "agreement_name": annual.agreement_name(row["agreement_id"]),
                "resolved_from_agreement_id": row.get("resolved_from_agreement_id", row["agreement_id"]),
                "latest_resolution": row.get("latest_resolution", "supplied_agreement_id"),
                "cohort": "D_next_independent_score_batch",
            }
            for row in target_agreements
        ],
        "profiles": profiles,
    }


def score_status(score: dict[str, Any]) -> str:
    if score.get("inside_95_predictive_interval"):
        return "inside_95"
    return "outside_95"


def markdown_for_payload(payload: dict[str, Any]) -> str:
    lines = [
        "# Entitlement Batch Scores",
        "",
        payload["selection_rule"],
        "",
        "## Target Councils",
        "",
    ]
    for row in payload["target_comparator_set"]:
        lines.append(f"- {row['council']}: {row['agreement_id'].upper()}")
    lines.extend([
        "",
        "## Scores",
        "",
        "| Entitlement | Metric | A observed | Expected in batch | Batch observed | 80% range | 95% range | Fit confidence | Status |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | ---: | --- |",
    ])
    for profile in payload["profiles"]:
        for metric_payload in profile["metrics"].values():
            baseline = metric_payload["baseline"]
            score = metric_payload["score"]
            interval_80 = score["predictive_intervals"]["80_percent"]["count"]
            interval_95 = score["predictive_intervals"]["95_percent"]["count"]
            lines.append(
                f"| {profile['label']} | {score['metric_label']} | "
                f"{baseline['observed_count']}/{baseline['sample_size']} | "
                f"{score['expected_count']} | "
                f"{score['observed_count']}/{score['sample_size']} | "
                f"{interval_80[0]}-{interval_80[1]} | "
                f"{interval_95[0]}-{interval_95[1]} | "
                f"{score['fit_confidence']} | {score_status(score)} |"
            )
    lines.extend([
        "",
        "## Source Hits",
        "",
    ])
    for profile in payload["profiles"]:
        lines.append(f"### {profile['label']}")
        hits = profile["source_hits"]
        if not hits:
            lines.append("")
            lines.append("No source-backed rows in this batch.")
            lines.append("")
            continue
        lines.append("")
        for hit in hits:
            page = f" p.{hit['source_page']}" if hit.get("source_page") else ""
            lines.append(f"- {hit['council']}: {hit['agreement_id'].upper()}{page} - {hit['finding']}")
        lines.append("")
    return "\n".join(lines)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build beta-binomial scorecards for the next independent council batch.")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument(
        "--all-eligible",
        action="store_true",
        help="Score every currently eligible latest cached council after the offset.",
    )
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    batch_size = None if args.all_eligible else args.batch_size
    payload = build_score_payload(batch_size, args.offset, utc_now_iso())
    artifact_dir = args.output_dir
    write_json(artifact_dir / f"{payload['artifact_id']}.json", payload)
    (artifact_dir / f"{payload['artifact_id']}.md").write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.entitlement_batch_scores_build.v1",
        "generated_at": payload["generated_at"],
        "artifact_id": payload["artifact_id"],
        "artifact_path": str(artifact_dir / f"{payload['artifact_id']}.json"),
        "target_councils": [row["council"] for row in payload["target_comparator_set"]],
    }, indent=2))


if __name__ == "__main__":
    main()
