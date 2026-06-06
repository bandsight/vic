from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLD = ROOT / "data" / "review" / "entitlement_locator_gold_v1.jsonl"
DEFAULT_QA_PACK = ROOT / "wiki" / "artifacts" / "entitlement-locator-qa-review" / "locator-qa-review-entitlement-locator-experiment-next-52-offset-0.json"
DEFAULT_OUTPUT = ROOT / "data" / "review" / "entitlement_locator_codex_suggestions_v1.jsonl"
SUGGESTION_SCHEMA_VERSION = "review.entitlement_locator_codex_suggestion.v1"

SUGGESTION_SOURCE = "codex_simulation"
FORBIDDEN_SUGGESTION_FIELDS = {
    "review_status",
    "review_decision",
    "reviewed_by",
    "reviewed_at",
    "eligible_for_governance",
    "promote_to_governed",
    "governance_status",
}

SUGGESTED_REVIEW_DECISIONS = {
    "correct",
    "wrong_clause",
    "right_clause_wrong_span",
    "right_span_wrong_value",
    "right_value_wrong_scope",
    "cross_reference_missing",
    "amount_not_stated_but_presence_correct",
    "true_absence",
    "source_unclear",
    "needs_value_review",
    "reviewed_absent_candidate",
    "cross_reference_required",
}

SUGGESTED_CROSS_REFERENCE_REVIEW = {
    "not_required",
    "present",
    "missing",
    "unresolved",
    "required",
}

CONFIDENCE_LEVELS = {"high", "medium", "low"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def qa_detail_index(qa_pack: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for profile in qa_pack.get("profiles", []):
        key = str(profile.get("key") or "")
        for row in profile.get("details", []):
            index[(str(row.get("council") or ""), key)] = row
    return index


def first_feature_for_detail(detail: dict[str, Any]) -> dict[str, Any]:
    ids = detail.get("feature_card_ids") or []
    features = detail.get("feature_cards") or []
    if features:
        return features[0]
    return {"feature_id": ids[0] if ids else ""}


def value_from_span(text: str) -> str:
    match = re.search(r"\b(\d+(?:\.\d+)?)\b", text or "")
    return match.group(1) if match else ""


def unit_from_span(text: str) -> str:
    lower = (text or "").lower()
    for unit in ["weeks", "week", "days", "day", "hours", "hour"]:
        if re.search(rf"\b{unit}\b", lower):
            if unit.endswith("s"):
                return unit
            return unit + "s"
    return ""


def scope_hint(record: dict[str, Any], detail: dict[str, Any]) -> str:
    key = str(record.get("entitlement_key") or "")
    label = str(record.get("entitlement_label") or "").lower()
    span = str(detail.get("evidence_span", {}).get("text") or record.get("evidence_span_text") or "").lower()
    if "primary" in key or "primary carer" in label:
        return "primary_carer"
    if "non_primary" in key or "non-primary" in label or "partner" in span:
        return "non_primary_carer"
    if "family_and_domestic" in key:
        return "employee_experiencing_family_or_domestic_violence"
    if "natural_disaster" in key:
        return "employee_affected_by_natural_disaster_or_emergency"
    if "emergency_services" in key:
        return "employee_volunteer_emergency_services"
    if "compassionate" in key:
        return "compassionate_or_bereavement_leave"
    if "cultural" in key:
        return "cultural_or_ceremonial_leave"
    if "additional_annual" in key:
        return "standard_staff_additional_annual_leave"
    return "standard_staff"


def quantified_suggestion(record: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    span_text = str(detail.get("evidence_span", {}).get("text") or record.get("evidence_span_text") or "")
    value = value_from_span(span_text)
    unit = unit_from_span(span_text)
    if not value or not unit:
        suggestion = needs_value_review_suggestion(record, detail)
        suggestion["reasons"] = [
            "Machine marked the row as quantified, but the sidecar could not identify a clear value and unit in the evidence span.",
            "Human review should confirm whether this is a true quantified value, a span issue, or a normalisation issue.",
        ]
        suggestion["risk_flags"] = sorted({*suggestion["risk_flags"], "machine_quantified_but_sidecar_value_unclear"})
        return suggestion
    feature_ids = record.get("feature_card_ids") or []
    confidence = "high" if feature_ids and span_text else "medium"
    risk_flags = []
    if record.get("reference_link_count", 0):
        risk_flags.append("reference_links_present")
    return {
        "suggested_review_decision": "correct",
        "suggested_expected_provision_present": True,
        "suggested_expected_quantified_value_found": True,
        "suggested_value": value,
        "suggested_unit": unit,
        "suggested_scope": scope_hint(record, detail),
        "suggested_cross_reference_review": "present" if record.get("reference_link_count", 0) else "not_required",
        "confidence": confidence,
        "reasons": [
            "Machine feature card includes an evidence span with a quantified value.",
            "Human reviewer must confirm clause, span, value, unit, and scope before any governance transition.",
        ],
        "risk_flags": risk_flags,
    }


def amount_not_stated_suggestion(record: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    risk_flags = ["amount_not_stated"]
    if record.get("reference_link_count", 0):
        risk_flags.append("reference_links_present")
    return {
        "suggested_review_decision": "amount_not_stated_but_presence_correct",
        "suggested_expected_provision_present": True,
        "suggested_expected_quantified_value_found": False,
        "suggested_value": None,
        "suggested_unit": None,
        "suggested_scope": scope_hint(record, detail),
        "suggested_cross_reference_review": "present" if record.get("reference_link_count", 0) else "not_required",
        "confidence": "medium",
        "reasons": [
            "Machine evidence indicates provision presence but no fixed quantum was normalised.",
            "This should be reviewed as provision-present evidence, not as quantified benchmark success.",
        ],
        "risk_flags": risk_flags,
    }


def needs_value_review_suggestion(record: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "suggested_review_decision": "needs_value_review",
        "suggested_expected_provision_present": True,
        "suggested_expected_quantified_value_found": False,
        "suggested_value": None,
        "suggested_unit": None,
        "suggested_scope": scope_hint(record, detail),
        "suggested_cross_reference_review": "unresolved" if record.get("reference_link_count", 0) else "not_required",
        "confidence": "low",
        "reasons": [
            "Machine locator found a plausible clause but did not normalise a benchmark value.",
            "Human review should decide whether the clause is amount-not-stated, discretionary, cross-reference dependent, or an extraction failure.",
        ],
        "risk_flags": ["value_review_required"],
    }


def absence_or_blocked_suggestion(record: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    if record.get("machine_cell_status") == "not_found":
        decision = "source_unclear"
        reasons = [
            "Machine locator found no candidate clause.",
            "This is not reviewed absence; human review must confirm search scope before any absence claim.",
        ]
        risk_flags = ["not_reviewed_absence"]
        confidence = "low"
    else:
        decision = "reviewed_absent_candidate"
        reasons = [
            "Machine candidate is blocked or adjacent rather than a true clause finding.",
            "Human review should confirm whether this is a false positive or an out-of-scope provision.",
        ]
        risk_flags = ["blocked_or_adjacent_candidate"]
        confidence = "medium"
    return {
        "suggested_review_decision": decision,
        "suggested_expected_provision_present": False,
        "suggested_expected_quantified_value_found": False,
        "suggested_value": None,
        "suggested_unit": None,
        "suggested_scope": scope_hint(record, detail),
        "suggested_cross_reference_review": "not_required",
        "confidence": confidence,
        "reasons": reasons,
        "risk_flags": risk_flags,
    }


def suggestion_for_record(record: dict[str, Any], detail: dict[str, Any] | None, *, generated_at: str) -> dict[str, Any]:
    detail = detail or {}
    value_status = str(record.get("machine_value_status") or "")
    if value_status == "quantified":
        suggestion = quantified_suggestion(record, detail)
    elif value_status in {"amount_not_stated", "discretionary_or_amount_not_stated", "cross_reference_required"}:
        suggestion = amount_not_stated_suggestion(record, detail)
        if value_status == "cross_reference_required":
            suggestion["suggested_review_decision"] = "cross_reference_required"
            suggestion["suggested_cross_reference_review"] = "required"
            suggestion["risk_flags"] = sorted({*suggestion["risk_flags"], "cross_reference_required"})
    elif record.get("machine_provision_present") or value_status == "needs_value_review":
        suggestion = needs_value_review_suggestion(record, detail)
    else:
        suggestion = absence_or_blocked_suggestion(record, detail)

    return {
        "schema_version": SUGGESTION_SCHEMA_VERSION,
        "suggestion_id": f"codex_suggestion_v1_{slug(record.get('review_id', ''))}",
        "created_at": generated_at,
        "gold_review_id": record.get("review_id", ""),
        "source_artifact": record.get("source_artifact", ""),
        "qa_pack": record.get("qa_pack", ""),
        "suggestion_source": SUGGESTION_SOURCE,
        "requires_human_confirmation": True,
        "evidence_summary": {
            "council": record.get("council", ""),
            "agreement_id": record.get("agreement_id", ""),
            "entitlement_key": record.get("entitlement_key", ""),
            "entitlement_label": record.get("entitlement_label", ""),
            "clause_card_id": record.get("clause_card_id", ""),
            "feature_card_id": record.get("feature_card_id", ""),
            "feature_card_ids": record.get("feature_card_ids", []),
            "evidence_span_text": record.get("evidence_span_text", ""),
            "evidence_span_text_hash": record.get("evidence_span_text_hash", ""),
            "machine_cell_status": record.get("machine_cell_status", ""),
            "machine_presence_status": record.get("machine_presence_status", ""),
            "machine_value_status": record.get("machine_value_status", ""),
            "machine_failure_reason": record.get("machine_failure_reason", ""),
            "reference_link_count": record.get("reference_link_count", 0),
        },
        **suggestion,
    }


def suggestions_from_gold(gold_records: list[dict[str, Any]], qa_pack: dict[str, Any], *, generated_at: str) -> list[dict[str, Any]]:
    index = qa_detail_index(qa_pack)
    suggestions: list[dict[str, Any]] = []
    for record in gold_records:
        detail = index.get((str(record.get("council") or ""), str(record.get("entitlement_key") or "")))
        suggestions.append(suggestion_for_record(record, detail, generated_at=generated_at))
    return suggestions


def validate_suggestion(record: dict[str, Any], valid_review_ids: set[str]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    suggestion_id = str(record.get("suggestion_id") or "<missing>")
    for field in FORBIDDEN_SUGGESTION_FIELDS:
        if field in record:
            errors.append({"suggestion_id": suggestion_id, "code": "forbidden_authority_field", "field": field})
    if record.get("gold_review_id") not in valid_review_ids:
        errors.append({"suggestion_id": suggestion_id, "code": "invalid_gold_review_id"})
    if record.get("suggestion_source") != SUGGESTION_SOURCE:
        errors.append({"suggestion_id": suggestion_id, "code": "invalid_suggestion_source"})
    if record.get("requires_human_confirmation") is not True:
        errors.append({"suggestion_id": suggestion_id, "code": "human_confirmation_required"})
    if record.get("suggested_review_decision") not in SUGGESTED_REVIEW_DECISIONS:
        errors.append({"suggestion_id": suggestion_id, "code": "invalid_suggested_review_decision"})
    if record.get("suggested_cross_reference_review") not in SUGGESTED_CROSS_REFERENCE_REVIEW:
        errors.append({"suggestion_id": suggestion_id, "code": "invalid_suggested_cross_reference_review"})
    if record.get("confidence") not in CONFIDENCE_LEVELS:
        errors.append({"suggestion_id": suggestion_id, "code": "invalid_confidence"})
    if not isinstance(record.get("reasons"), list) or not record.get("reasons"):
        errors.append({"suggestion_id": suggestion_id, "code": "reasons_required"})
    if not isinstance(record.get("risk_flags"), list):
        errors.append({"suggestion_id": suggestion_id, "code": "risk_flags_must_be_list"})

    quantified = record.get("suggested_expected_quantified_value_found") is True
    evidence = record.get("evidence_summary") or {}
    if quantified:
        if not record.get("suggested_value") or not record.get("suggested_unit"):
            errors.append({"suggestion_id": suggestion_id, "code": "quantified_suggestion_requires_value_and_unit"})
        if not evidence.get("feature_card_id"):
            errors.append({"suggestion_id": suggestion_id, "code": "quantified_suggestion_requires_feature_card"})
        if not evidence.get("evidence_span_text"):
            errors.append({"suggestion_id": suggestion_id, "code": "quantified_suggestion_requires_evidence_span"})
    elif record.get("suggested_value") or record.get("suggested_unit"):
        errors.append({"suggestion_id": suggestion_id, "code": "non_quantified_suggestion_must_not_set_value"})

    if record.get("suggested_review_decision") == "amount_not_stated_but_presence_correct":
        if record.get("suggested_expected_quantified_value_found") is True:
            errors.append({"suggestion_id": suggestion_id, "code": "amount_not_stated_cannot_be_quantified_success"})
        if record.get("suggested_value") or record.get("suggested_unit"):
            errors.append({"suggestion_id": suggestion_id, "code": "amount_not_stated_must_not_set_value"})
    return errors


def validate_suggestions(records: list[dict[str, Any]], gold_records: list[dict[str, Any]]) -> list[dict[str, str]]:
    valid_review_ids = {str(record.get("review_id") or "") for record in gold_records}
    errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in records:
        suggestion_id = str(record.get("suggestion_id") or "")
        if suggestion_id in seen:
            errors.append({"suggestion_id": suggestion_id, "code": "duplicate_suggestion_id"})
        seen.add(suggestion_id)
        errors.extend(validate_suggestion(record, valid_review_ids))
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Codex simulation suggestions as a sidecar to gold review rows.")
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--qa-pack", type=Path, default=DEFAULT_QA_PACK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gold_path = args.gold.resolve()
    original_gold_text = gold_path.read_text(encoding="utf-8") if gold_path.exists() else ""
    gold_records = jsonl_rows(gold_path)
    qa_pack = load_json(args.qa_pack.resolve())
    generated_at = utc_now_iso()
    suggestions = suggestions_from_gold(gold_records, qa_pack, generated_at=generated_at)
    errors = validate_suggestions(suggestions, gold_records)
    after_gold_text = gold_path.read_text(encoding="utf-8") if gold_path.exists() else ""
    if after_gold_text != original_gold_text:
        errors.append({"suggestion_id": "<gold-file>", "code": "gold_file_was_modified"})
    if errors:
        print(json.dumps({
            "schema_version": "review.entitlement_locator_codex_suggestion_build.v1",
            "generated_at": generated_at,
            "status": "failed",
            "errors": errors,
        }, indent=2))
        sys.exit(1)
    write_jsonl(args.output.resolve(), suggestions)
    print(json.dumps({
        "schema_version": "review.entitlement_locator_codex_suggestion_build.v1",
        "generated_at": generated_at,
        "status": "passed",
        "output_path": str(args.output.resolve()),
        "suggestions_written": len(suggestions),
        "gold_rows_read": len(gold_records),
    }, indent=2))


if __name__ == "__main__":
    main()
