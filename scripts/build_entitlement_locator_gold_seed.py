from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QA_PACK = ROOT / "wiki" / "artifacts" / "entitlement-locator-qa-review" / "locator-qa-review-entitlement-locator-experiment-next-52-offset-0.json"
DEFAULT_OUTPUT = ROOT / "data" / "review" / "entitlement_locator_gold_v1.jsonl"
GOLD_SCHEMA_VERSION = "review.entitlement_locator_gold.v1"

REVIEW_STATUSES = {
    "not_reviewed",
    "reviewed_correct",
    "reviewed_corrected",
    "reviewed_rejected",
    "source_unclear",
    "cross_reference_required",
    "reviewed_absent",
    "amount_not_stated_confirmed",
    "eligible_for_governance",
    "governed_for_scope",
}

REVIEW_DECISIONS = {
    "correct",
    "wrong_clause",
    "right_clause_wrong_span",
    "right_span_wrong_value",
    "right_value_wrong_scope",
    "cross_reference_missing",
    "amount_not_stated_but_presence_correct",
    "true_absence",
    "source_unclear",
}

EXPECTED_PRESENCE = {
    "present",
    "absent_reviewed",
    "not_reviewed",
    "unclear",
}

EXPECTED_VALUE_STATUS = {
    "quantified",
    "amount_not_stated",
    "discretionary",
    "conditional",
    "cross_reference_required",
    "not_applicable",
    "extraction_failed",
    "not_reviewed",
}

CROSS_REFERENCE_STATUS = {
    "not_required",
    "present",
    "missing",
    "unresolved",
    "not_reviewed",
}

REVIEW_METADATA_KEYS = {
    "review_event_id",
    "reviewed_by",
    "reviewed_at",
    "governance_event_id",
    "promoted_at",
    "promotion_event_id",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, records: list[dict[str, Any]], *, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def details_by_council_and_profile(qa_pack: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for profile in qa_pack.get("profiles", []):
        key = str(profile.get("key") or "")
        for row in profile.get("details", []):
            index[(str(row.get("council") or ""), key)] = row
    return index


def gold_record_from_detail(
    qa_pack: dict[str, Any],
    detail: dict[str, Any],
    *,
    generated_at: str,
    sample_reason: str,
) -> dict[str, Any]:
    feature_ids = detail.get("feature_card_ids") or []
    reference_links = detail.get("reference_links") or []
    return {
        "schema_version": GOLD_SCHEMA_VERSION,
        "review_id": f"locator_gold_v1_{slug(detail.get('council', ''))}_{slug(detail.get('entitlement_key', ''))}",
        "created_at": generated_at,
        "source_artifact": qa_pack.get("source_artifact", {}).get("artifact_id", ""),
        "qa_pack": qa_pack.get("artifact_id", ""),
        "sample_reason": sample_reason,
        "council": detail.get("council", ""),
        "agreement_id": detail.get("agreement_id", ""),
        "entitlement_key": detail.get("entitlement_key", ""),
        "entitlement_id": detail.get("entitlement_id", ""),
        "entitlement_label": detail.get("entitlement_label", ""),
        "clause_card_id": detail.get("clause_card_id", ""),
        "feature_card_id": feature_ids[0] if feature_ids else "",
        "feature_card_ids": feature_ids,
        "machine_cell_status": detail.get("cell_status", ""),
        "machine_clause_found": bool(detail.get("clause_found")),
        "machine_feature_found": bool(feature_ids),
        "machine_provision_present": bool(detail.get("provision_present")),
        "machine_quantified_value_found": bool(detail.get("quantified_value_found")),
        "machine_presence_status": detail.get("machine_presence_status", ""),
        "machine_value_status": detail.get("machine_value_status", ""),
        "machine_failure_reason": detail.get("failure_reason", ""),
        "evidence_span_text": detail.get("evidence_span", {}).get("text", ""),
        "evidence_span_text_hash": detail.get("evidence_span", {}).get("text_hash", ""),
        "raw_clause_text_hash": detail.get("raw_clause_text_hash", ""),
        "parser_used": detail.get("parser_used", ""),
        "parser_version": detail.get("parser_version", ""),
        "page": detail.get("page"),
        "block_id": detail.get("block_id", ""),
        "reference_link_count": len(reference_links),
        "reference_links": reference_links,
        "review_status": "not_reviewed",
        "review_decision": None,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_scope": None,
        "review_notes": None,
        "corrected_clause_card_id": None,
        "corrected_feature_card_id": None,
        "corrected_evidence_span": None,
        "expected_provision_present": None,
        "expected_quantified_value_found": None,
        "expected_presence": "not_reviewed",
        "expected_value_status": "not_reviewed",
        "expected_value": None,
        "expected_unit": None,
        "expected_scope": None,
        "cross_reference_status": "not_reviewed",
        "cross_reference_review": None,
        "eligible_for_governance": False,
        "governance_status": "not_eligible",
        "follow_up_required": True,
        "promote_to_governed": False,
    }


def gold_records_from_qa_pack(qa_pack: dict[str, Any], *, generated_at: str) -> list[dict[str, Any]]:
    index = details_by_council_and_profile(qa_pack)
    sample = qa_pack.get("recommended_review_sample", [])
    profile_keys = [str(profile.get("key") or "") for profile in qa_pack.get("profiles", [])]
    records: list[dict[str, Any]] = []
    for sample_item in sample:
        council = str(sample_item.get("council") or "")
        reason = str(sample_item.get("reason") or "")
        for profile_key in profile_keys:
            detail = index.get((council, profile_key))
            if detail:
                records.append(gold_record_from_detail(
                    qa_pack,
                    detail,
                    generated_at=generated_at,
                    sample_reason=reason,
                ))
    return records


def has_review_metadata(record: dict[str, Any]) -> bool:
    return bool(record.get("reviewed_by") and record.get("reviewed_at"))


def validate_gold_record(record: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    review_id = str(record.get("review_id") or "<missing>")
    review_status = record.get("review_status")
    review_decision = record.get("review_decision")
    if review_status not in REVIEW_STATUSES:
        errors.append({"review_id": review_id, "code": "invalid_review_status"})
    if review_status == "not_reviewed":
        if review_decision is not None:
            errors.append({"review_id": review_id, "code": "not_reviewed_must_not_set_review_decision"})
    elif review_decision not in REVIEW_DECISIONS:
        errors.append({"review_id": review_id, "code": "invalid_review_decision"})
    if record.get("expected_presence") not in EXPECTED_PRESENCE:
        errors.append({"review_id": review_id, "code": "invalid_expected_presence"})
    if record.get("expected_value_status") not in EXPECTED_VALUE_STATUS:
        errors.append({"review_id": review_id, "code": "invalid_expected_value_status"})
    if record.get("cross_reference_status") not in CROSS_REFERENCE_STATUS:
        errors.append({"review_id": review_id, "code": "invalid_cross_reference_status"})

    if review_status == "not_reviewed":
        if record.get("expected_presence") != "not_reviewed" or record.get("expected_value_status") != "not_reviewed":
            errors.append({"review_id": review_id, "code": "not_reviewed_must_not_set_truth"})
        if record.get("expected_provision_present") is not None or record.get("expected_quantified_value_found") is not None:
            errors.append({"review_id": review_id, "code": "not_reviewed_must_not_set_expected_review_fields"})
        if record.get("eligible_for_governance") or record.get("promote_to_governed"):
            errors.append({"review_id": review_id, "code": "not_reviewed_cannot_promote"})

    if review_status in {
        "reviewed_correct",
        "reviewed_corrected",
        "reviewed_rejected",
        "source_unclear",
        "cross_reference_required",
        "reviewed_absent",
        "amount_not_stated_confirmed",
        "eligible_for_governance",
        "governed_for_scope",
    }:
        if not has_review_metadata(record):
            errors.append({"review_id": review_id, "code": "reviewed_status_requires_reviewer_metadata"})
        if not record.get("review_scope"):
            errors.append({"review_id": review_id, "code": "reviewed_status_requires_scope"})

    if review_status == "reviewed_correct" and review_decision != "correct":
        errors.append({"review_id": review_id, "code": "reviewed_correct_requires_correct_decision"})
    if review_decision == "correct" and record.get("expected_presence") != "present":
        errors.append({"review_id": review_id, "code": "correct_must_confirm_presence"})

    if review_status == "reviewed_corrected":
        if not (
            record.get("corrected_clause_card_id")
            or record.get("corrected_feature_card_id")
            or record.get("corrected_evidence_span")
        ):
            errors.append({"review_id": review_id, "code": "reviewed_corrected_requires_corrected_evidence"})

    if review_status == "reviewed_rejected" and (
        record.get("eligible_for_governance") or record.get("promote_to_governed")
    ):
        errors.append({"review_id": review_id, "code": "reviewed_rejected_cannot_promote"})

    if record.get("expected_value_status") == "quantified":
        if not record.get("expected_value") or not record.get("expected_unit"):
            errors.append({"review_id": review_id, "code": "quantified_value_requires_value_and_unit"})
        if not record.get("feature_card_id"):
            errors.append({"review_id": review_id, "code": "quantified_value_requires_feature_card"})
    elif record.get("expected_value") or record.get("expected_unit"):
        errors.append({"review_id": review_id, "code": "non_quantified_status_must_not_set_value"})

    if review_status == "amount_not_stated_confirmed" and review_decision != "amount_not_stated_but_presence_correct":
        errors.append({"review_id": review_id, "code": "amount_not_stated_status_requires_matching_decision"})
    if review_decision == "amount_not_stated_but_presence_correct":
        if record.get("expected_presence") != "present":
            errors.append({"review_id": review_id, "code": "amount_not_stated_requires_presence"})
        if record.get("expected_value_status") not in {
            "amount_not_stated",
            "discretionary",
            "conditional",
            "cross_reference_required",
        }:
            errors.append({"review_id": review_id, "code": "amount_not_stated_requires_non_quantified_value_status"})

    if review_status == "cross_reference_required":
        if record.get("cross_reference_review") not in {"missing", "unresolved", "required"}:
            errors.append({"review_id": review_id, "code": "cross_reference_required_requires_unresolved_review"})
        if record.get("eligible_for_governance") or record.get("promote_to_governed"):
            errors.append({"review_id": review_id, "code": "cross_reference_required_cannot_promote"})
    if review_decision == "cross_reference_missing":
        if record.get("cross_reference_status") != "missing":
            errors.append({"review_id": review_id, "code": "cross_reference_missing_requires_missing_status"})
        if not record.get("follow_up_required"):
            errors.append({"review_id": review_id, "code": "cross_reference_missing_requires_follow_up"})

    if review_status == "reviewed_absent":
        if record.get("expected_provision_present") is not False:
            errors.append({"review_id": review_id, "code": "reviewed_absent_requires_false_presence"})
        if not record.get("review_scope") and not record.get("review_notes"):
            errors.append({"review_id": review_id, "code": "reviewed_absent_requires_scope_or_notes"})
    if record.get("expected_presence") == "absent_reviewed" and review_decision != "true_absence":
        errors.append({"review_id": review_id, "code": "reviewed_absence_requires_true_absence_decision"})

    if record.get("eligible_for_governance"):
        if review_status not in {"eligible_for_governance", "governed_for_scope"}:
            errors.append({"review_id": review_id, "code": "eligible_for_governance_requires_lifecycle_status"})
        if not has_review_metadata(record):
            errors.append({"review_id": review_id, "code": "eligible_for_governance_requires_reviewer_metadata"})
        if not record.get("review_scope"):
            errors.append({"review_id": review_id, "code": "eligible_for_governance_requires_scope"})
        if not (record.get("evidence_span_text") or record.get("corrected_evidence_span")):
            errors.append({"review_id": review_id, "code": "eligible_for_governance_requires_evidence_span"})

    if record.get("governance_status") == "governed_for_scope" and not record.get("promote_to_governed"):
        errors.append({"review_id": review_id, "code": "governed_for_scope_requires_promotion_flag"})
    if record.get("promote_to_governed") and not has_review_metadata(record):
        errors.append({"review_id": review_id, "code": "governed_promotion_requires_review_metadata"})
    if record.get("promote_to_governed") and not record.get("eligible_for_governance"):
        errors.append({"review_id": review_id, "code": "governed_promotion_requires_eligible_state"})

    if (
        record.get("entitlement_key") == "additional_annual_leave"
        and record.get("machine_cell_status") in {"blocked", "adjacent_candidate", "not_found"}
        and record.get("promote_to_governed")
    ):
        errors.append({"review_id": review_id, "code": "additional_annual_conservative_candidate_cannot_promote"})

    return errors


def validate_gold_records(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in records:
        review_id = str(record.get("review_id") or "")
        if review_id in seen:
            errors.append({"review_id": review_id, "code": "duplicate_review_id"})
        seen.add(review_id)
        errors.extend(validate_gold_record(record))
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a JSONL gold-review file from the locator QA sample.")
    parser.add_argument("--qa-pack", type=Path, default=DEFAULT_QA_PACK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    if output.exists() and not args.append and not args.overwrite:
        raise SystemExit(f"{output} already exists; use --append or --overwrite.")
    qa_pack = load_json(args.qa_pack.resolve())
    generated_at = utc_now_iso()
    records = gold_records_from_qa_pack(qa_pack, generated_at=generated_at)
    existing = jsonl_rows(output) if args.append else []
    errors = validate_gold_records([*existing, *records])
    if errors:
        print(json.dumps({
            "schema_version": "review.entitlement_locator_gold_build.v1",
            "generated_at": generated_at,
            "status": "failed",
            "errors": errors,
        }, indent=2))
        sys.exit(1)
    write_jsonl(output, records, append=args.append)
    print(json.dumps({
        "schema_version": "review.entitlement_locator_gold_build.v1",
        "generated_at": generated_at,
        "status": "passed",
        "output_path": str(output),
        "records_written": len(records),
        "review_councils": sorted({record["council"] for record in records}),
    }, indent=2))


if __name__ == "__main__":
    main()
