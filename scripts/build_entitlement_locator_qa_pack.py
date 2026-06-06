from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "wiki" / "artifacts" / "entitlement-locator-experiment" / "entitlement-locator-experiment-next-52-offset-0.json"
DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "entitlement-locator-qa-review"
QA_SCHEMA_VERSION = "wiki.entitlement_locator_qa_review.v1"

DOCTRINE = (
    "Clause Evidence Graph owns source-backed structure and evidence. "
    "Entitlement Engine owns benchmark interpretation. "
    "Reporting owns presentation. Governance decides what is safe to promote."
)

STATUS_LABELS = {
    "clause_value": "clause+value",
    "clause_only": "clause_only",
    "adjacent_candidate": "adjacent_candidate",
    "blocked": "blocked",
    "not_found": "not_found",
    "needs_review": "needs_review",
}

STATUS_ORDER = [
    "clause_value",
    "clause_only",
    "blocked",
    "adjacent_candidate",
    "not_found",
    "needs_review",
]

MACHINE_PRESENCE_STATUSES = {
    "present_candidate",
    "unclear_candidate",
    "not_found_not_reviewed",
}

MACHINE_VALUE_STATUSES = {
    "quantified",
    "amount_not_stated",
    "discretionary_or_amount_not_stated",
    "cross_reference_required",
    "needs_value_review",
    "not_applicable",
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


def short_text(text: str, limit: int = 220) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def has_review_metadata(item: dict[str, Any]) -> bool:
    return any(item.get(key) for key in REVIEW_METADATA_KEYS)


def best_card(row: dict[str, Any]) -> dict[str, Any]:
    cards = row.get("clause_cards") or []
    return cards[0] if cards else {}


def best_feature(row: dict[str, Any]) -> dict[str, Any]:
    features = row.get("feature_cards") or []
    return features[0] if features else {}


def best_candidate(row: dict[str, Any]) -> dict[str, Any]:
    candidate = row.get("best_candidate")
    if isinstance(candidate, dict):
        return candidate
    candidates = row.get("candidate_pages") or []
    return candidates[0] if candidates else {}


def cell_status(row: dict[str, Any]) -> str:
    if row.get("value_extracted"):
        return "clause_value"
    if row.get("clause_found"):
        return "clause_only"
    if row.get("state") == "adjacent_or_blocked_clause_found":
        candidate = best_candidate(row)
        if candidate.get("blocker_signals"):
            return "blocked"
        return "adjacent_candidate"
    if row.get("state") == "no_candidate_clause_found":
        return "not_found"
    return "needs_review"


def failure_reason(row: dict[str, Any]) -> str:
    if row.get("value_extracted"):
        return ""
    state = str(row.get("state") or "")
    candidate = best_candidate(row)
    blockers = candidate.get("blocker_signals") or []
    if state == "clause_found_value_missing":
        return "clause_found_but_no_normalised_value"
    if state == "adjacent_or_blocked_clause_found" and blockers:
        return "candidate_blocked_by_scope_signals: " + ", ".join(str(item) for item in blockers)
    if state == "adjacent_or_blocked_clause_found":
        return "adjacent_candidate_without_clause_confirmation"
    if state == "no_candidate_clause_found":
        return "no_candidate_clause_found"
    return state or "unknown"


def quantified_feature(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    if text == "unlimited":
        return True
    return any(char.isdigit() for char in text)


def machine_presence_status(row: dict[str, Any]) -> str:
    if row.get("clause_found") or row.get("value_extracted"):
        return "present_candidate"
    if row.get("state") == "adjacent_or_blocked_clause_found":
        return "unclear_candidate"
    return "not_found_not_reviewed"


def machine_value_status(row: dict[str, Any]) -> str:
    features = row.get("feature_cards") or []
    values = [
        feature.get("normalised_value", {})
        for feature in features
        if isinstance(feature.get("normalised_value", {}), dict)
    ]
    if values and any(quantified_feature(value.get("value")) for value in values):
        return "quantified"
    if values:
        combined = " ".join(
            " ".join(str(value.get(key, "")) for key in ("value", "unit", "condition", "subclass_label"))
            for value in values
        ).lower()
        if any(term in combined for term in ("nes", "award", "schedule", "cross-reference")):
            return "cross_reference_required"
        if any(term in combined for term in ("discretion", "approval", "may be granted", "unquantified")):
            return "discretionary_or_amount_not_stated"
        return "amount_not_stated"
    if row.get("clause_found"):
        return "needs_value_review"
    return "not_applicable"


def evidence_span(feature: dict[str, Any], card: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if feature.get("evidence_span_text"):
        return {
            "text": feature.get("evidence_span_text", ""),
            "text_hash": feature.get("evidence_span_text_hash", ""),
            "start": feature.get("evidence_span_start"),
            "end": feature.get("evidence_span_end"),
            "basis": feature.get("span_basis", "feature_card"),
        }
    if card.get("locator_span_text"):
        return {
            "text": card.get("locator_span_text", ""),
            "text_hash": card.get("locator_span_text_hash", ""),
            "start": card.get("locator_span_start"),
            "end": card.get("locator_span_end"),
            "basis": "locator_span",
        }
    return {
        "text": short_text(candidate.get("excerpt", "")),
        "text_hash": "",
        "start": None,
        "end": None,
        "basis": "candidate_excerpt",
    }


def qa_detail_row(profile: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    card = best_card(row)
    feature = best_feature(row)
    candidate = best_candidate(row)
    span = evidence_span(feature, card, candidate)
    return {
        "entitlement_key": profile.get("key"),
        "entitlement_id": profile.get("entitlement_id"),
        "entitlement_label": profile.get("label"),
        "council": row.get("council"),
        "agreement_id": row.get("agreement_id"),
        "agreement_name": row.get("agreement_name"),
        "row_state": row.get("state"),
        "cell_status": cell_status(row),
        "clause_found": bool(row.get("clause_found")),
        "value_found": bool(row.get("value_extracted")),
        "provision_present": machine_presence_status(row) == "present_candidate",
        "quantified_value_found": machine_value_status(row) == "quantified",
        "machine_presence_status": machine_presence_status(row),
        "machine_value_status": machine_value_status(row),
        "candidate_count": row.get("candidate_count", 0),
        "locator_confidence": row.get("locator_confidence", 0),
        "page": card.get("page_number_physical") or candidate.get("page"),
        "block_id": card.get("block_id") or feature.get("block_id", ""),
        "clause_card_id": card.get("clause_id", ""),
        "feature_card_ids": [item.get("feature_id", "") for item in row.get("feature_cards", []) if item.get("feature_id")],
        "feature_governance_statuses": [
            item.get("governance_status", "")
            for item in row.get("feature_cards", [])
            if item.get("governance_status")
        ],
        "feature_review_statuses": [
            item.get("review_status", "")
            for item in row.get("feature_cards", [])
            if item.get("review_status")
        ],
        "primary_feature_card_id": feature.get("feature_id", ""),
        "parser_used": card.get("parser_used") or feature.get("parser_used", ""),
        "parser_version": card.get("parser_version") or feature.get("parser_version", ""),
        "source_file_id": card.get("source_file_id") or feature.get("source_file_id", ""),
        "source_file_hash": card.get("source_file_hash") or feature.get("source_file_hash", ""),
        "raw_clause_text_hash": card.get("raw_clause_text_hash", ""),
        "evidence_span": span,
        "interpretation_status": card.get("interpretation_status", ""),
        "review_status": card.get("review_status", ""),
        "governance_status": card.get("governance_status", ""),
        "reference_links": row.get("reference_links", []),
        "blocker_signals": candidate.get("blocker_signals", []),
        "adjacent_or_blocked_candidates": [
            {
                "page": item.get("page"),
                "heading": item.get("heading", ""),
                "state": item.get("state", ""),
                "blocker_signals": item.get("blocker_signals", []),
                "matched_terms": item.get("matched_terms", []),
            }
            for item in row.get("candidate_pages", [])
            if item.get("state") == "adjacent_or_blocked_clause_found" or item.get("blocker_signals")
        ],
        "failure_reason": failure_reason(row),
    }


def profile_summary(detail_rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {key: 0 for key in STATUS_ORDER}
    for row in detail_rows:
        counts[row["cell_status"]] = counts.get(row["cell_status"], 0) + 1
    return {
        "councils": len(detail_rows),
        "clause_found": sum(1 for row in detail_rows if row["clause_found"]),
        "value_found": sum(1 for row in detail_rows if row["value_found"]),
        "cell_status_counts": {key: counts[key] for key in STATUS_ORDER if counts.get(key)},
        "groups": {
            "clause_found_value_found": [
                row["council"] for row in detail_rows if row["cell_status"] == "clause_value"
            ],
            "clause_found_no_value": [
                row["council"] for row in detail_rows if row["cell_status"] == "clause_only"
            ],
            "no_clause_found": [
                row["council"] for row in detail_rows if row["cell_status"] == "not_found"
            ],
            "adjacent_or_blocked_candidates": [
                row["council"] for row in detail_rows if row["cell_status"] in {"blocked", "adjacent_candidate"}
            ],
        },
    }


def matrix_for_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_council: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        key = str(profile["key"])
        for row in profile["details"]:
            council = str(row["council"])
            item = by_council.setdefault(council, {"council": council, "agreement_ids": {}, "statuses": {}})
            item["agreement_ids"][key] = row["agreement_id"]
            item["statuses"][key] = {
                "status": row["cell_status"],
                "label": STATUS_LABELS[row["cell_status"]],
                "clause_found": row["clause_found"],
                "value_found": row["value_found"],
                "provision_present": row["provision_present"],
                "quantified_value_found": row["quantified_value_found"],
                "machine_presence_status": row["machine_presence_status"],
                "machine_value_status": row["machine_value_status"],
                "clause_card_id": row["clause_card_id"],
                "feature_card_ids": row["feature_card_ids"],
                "failure_reason": row["failure_reason"],
            }
    return [by_council[key] for key in sorted(by_council)]


def recommended_review_sample(matrix: list[dict[str, Any]], profiles: list[dict[str, Any]]) -> list[dict[str, str]]:
    profile_keys = [str(profile["key"]) for profile in profiles]
    detail_rows = [row for profile in profiles for row in profile["details"]]
    by_council_details: dict[str, list[dict[str, Any]]] = {}
    for row in detail_rows:
        by_council_details.setdefault(str(row["council"]), []).append(row)

    scored: list[tuple[int, int, str]] = []
    for row in matrix:
        statuses = [row["statuses"].get(key, {}).get("status") for key in profile_keys]
        good = sum(1 for status in statuses if status == "clause_value")
        friction = sum(1 for status in statuses if status in {"clause_only", "blocked", "adjacent_candidate", "not_found"})
        scored.append((good, -friction, row["council"]))
    clean = sorted(scored, reverse=True)[0][2] if scored else ""

    messy_scores: list[tuple[int, str]] = []
    for row in matrix:
        statuses = [row["statuses"].get(key, {}).get("status") for key in profile_keys]
        friction = sum(1 for status in statuses if status in {"clause_only", "blocked", "adjacent_candidate", "not_found"})
        messy_scores.append((friction, row["council"]))
    messy = sorted(messy_scores, reverse=True)[0][1] if messy_scores else ""

    reference_scores = [
        (sum(len(item.get("reference_links") or []) for item in rows), council)
        for council, rows in by_council_details.items()
    ]
    cross_reference = sorted(reference_scores, reverse=True)[0][1] if reference_scores else ""

    hard_value_failure = ""
    for profile in profiles:
        profile_key = str(profile["key"])
        if not ("natural_disaster" in profile_key or "emergency_services" in profile_key):
            continue
        for row in profile["details"]:
            if row["cell_status"] in {"clause_only", "blocked", "adjacent_candidate"}:
                hard_value_failure = row["council"]
                break
        if hard_value_failure:
            break

    additional_annual = ""
    for profile in profiles:
        if profile["key"] != "additional_annual_leave":
            continue
        for row in profile["details"]:
            if row["cell_status"] in {"blocked", "adjacent_candidate"}:
                additional_annual = row["council"]
                break

    sample = [
        ("clean_high_value_extraction", clean),
        ("messy_status_mix", messy),
        ("cross_reference_heavy", cross_reference),
        ("emergency_or_natural_value_failure", hard_value_failure),
        ("additional_annual_conservative_candidate", additional_annual),
    ]
    seen: set[str] = set()
    output: list[dict[str, str]] = []
    for reason, council in sample:
        if not council or council in seen:
            continue
        seen.add(council)
        output.append({"council": council, "reason": reason})
    if len(output) < 5:
        for row in matrix:
            council = row["council"]
            if council in seen:
                continue
            seen.add(council)
            output.append({"council": council, "reason": "coverage_fill"})
            if len(output) >= 5:
                break
    return output


def guardrail_errors(payload: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for profile in payload["profiles"]:
        for row in profile["details"]:
            if (
                profile["key"] == "additional_annual_leave"
                and row.get("row_state") == "adjacent_or_blocked_clause_found"
                and (row["clause_found"] or row["value_found"])
            ):
                errors.append({
                    "code": "additional_annual_adjacent_counted_as_clause",
                    "message": f"{row['council']} Additional Annual Leave adjacent/blocked candidate was counted as a true clause.",
                })
            if row["value_found"] and not row["evidence_span"].get("text"):
                errors.append({
                    "code": "value_found_without_evidence_span",
                    "message": f"{row['council']} {profile['label']} has value_found=true without an evidence span.",
                })
            if row["value_found"] and not row["feature_card_ids"]:
                errors.append({
                    "code": "value_found_without_feature_card",
                    "message": f"{row['council']} {profile['label']} has value_found=true without a feature card.",
                })
            governed_items = [
                item
                for item in [
                    *(row.get("reference_links") or []),
                ]
                if item.get("governance_status") == "governed_for_scope" and not has_review_metadata(item)
            ]
            if row.get("governance_status") == "governed_for_scope" and not has_review_metadata(row):
                governed_items.append(row)
            if "governed_for_scope" in row.get("feature_governance_statuses", []) and not has_review_metadata(row):
                governed_items.append(row)
            if governed_items:
                errors.append({
                    "code": "governed_without_review_metadata",
                    "message": f"{row['council']} {profile['label']} emitted governed_for_scope without review metadata.",
                })
    return errors


def build_qa_payload(locator_payload: dict[str, Any], *, generated_at: str, source_path: Path | None = None) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    for profile in locator_payload.get("profiles", []):
        details = [qa_detail_row(profile, row) for row in profile.get("target_rows", [])]
        profiles.append({
            "key": profile.get("key"),
            "entitlement_id": profile.get("entitlement_id"),
            "label": profile.get("label"),
            "summary": profile_summary(details),
            "details": details,
        })
    matrix = matrix_for_profiles(profiles)
    payload = {
        "schema_version": QA_SCHEMA_VERSION,
        "artifact_id": f"locator-qa-review-{locator_payload.get('artifact_id', 'unknown')}",
        "generated_at": generated_at,
        "source_artifact": {
            "artifact_id": locator_payload.get("artifact_id"),
            "schema_version": locator_payload.get("schema_version"),
            "path": str(source_path) if source_path else "",
            "generated_at": locator_payload.get("generated_at"),
        },
        "doctrine": DOCTRINE,
        "review_questions": [
            "Did the system find the right clause?",
            "Did it extract the right sentence or span?",
            "Did it normalise the value correctly?",
            "Did it avoid false absence?",
            "Did it avoid false presence?",
        ],
        "semantic_status_model": {
            "presence": sorted(MACHINE_PRESENCE_STATUSES),
            "value": sorted(MACHINE_VALUE_STATUSES),
            "note": (
                "These are machine review statuses only. They separate provision presence from quantified values; "
                "truth enters through explicit review decisions and governance promotion."
            ),
        },
        "status_legend": STATUS_LABELS,
        "guardrails": [
            "Additional Annual Leave blocked/adjacent candidates are not counted as true clauses.",
            "value_found cannot be true without a feature card and evidence span.",
            "provision_present and quantified_value_found remain separate review dimensions.",
            "governed_for_scope cannot be emitted by the experiment unless explicit review metadata exists.",
            "clause_found and value_found remain separate metrics.",
        ],
        "profiles": profiles,
        "summary_matrix": matrix,
        "recommended_review_sample": recommended_review_sample(matrix, profiles),
    }
    payload["guardrail_errors"] = guardrail_errors(payload)
    payload["guardrail_status"] = "failed" if payload["guardrail_errors"] else "passed"
    return payload


def markdown_for_payload(payload: dict[str, Any]) -> str:
    profile_keys = [profile["key"] for profile in payload["profiles"]]
    profile_labels = {profile["key"]: profile["label"] for profile in payload["profiles"]}
    lines = [
        "# Entitlement Locator QA Review Pack",
        "",
        payload["doctrine"],
        "",
        f"Source artifact: `{payload['source_artifact']['artifact_id']}`",
        f"Guardrail status: `{payload['guardrail_status']}`",
        "",
        "The QA pack makes locator outputs reviewable. It does not make them true. Truth enters the system only through explicit review decisions and governance promotion.",
        "",
        "## Status Legend",
        "",
    ]
    for key, label in STATUS_LABELS.items():
        lines.append(f"- `{key}`: {label}")
    lines.extend([
        "",
        "## Review Questions",
        "",
    ])
    for question in payload["review_questions"]:
        lines.append(f"- {question}")
    lines.extend([
        "",
        "## Semantic Status Model",
        "",
        "- `provision_present` and `quantified_value_found` are separate machine dimensions.",
        "- Machine presence/value statuses are review prompts, not governed facts.",
    ])
    lines.extend([
        "",
        "## Recommended Five-Council Review Sample",
        "",
    ])
    for item in payload["recommended_review_sample"]:
        lines.append(f"- {item['council']}: {item['reason']}")
    lines.extend([
        "",
        "## Entitlement Summary",
        "",
        "| Entitlement | Clause found | Value found | Status counts |",
        "| --- | ---: | ---: | --- |",
    ])
    for profile in payload["profiles"]:
        summary = profile["summary"]
        counts = ", ".join(f"{key}: {value}" for key, value in summary["cell_status_counts"].items())
        lines.append(
            f"| {profile['label']} | {summary['clause_found']}/{summary['councils']} | "
            f"{summary['value_found']}/{summary['councils']} | {counts} |"
        )
    lines.extend([
        "",
        "## Summary Matrix",
        "",
        "| Council | " + " | ".join(profile_labels[key] for key in profile_keys) + " |",
        "| --- | " + " | ".join("---" for _ in profile_keys) + " |",
    ])
    for row in payload["summary_matrix"]:
        statuses = [
            row["statuses"].get(key, {}).get("label", "not_run")
            for key in profile_keys
        ]
        lines.append(f"| {row['council']} | " + " | ".join(statuses) + " |")
    lines.extend([
        "",
        "## Entitlement Details",
        "",
    ])
    for profile in payload["profiles"]:
        lines.append(f"### {profile['label']}")
        lines.append("")
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in profile["details"]:
            grouped.setdefault(row["cell_status"], []).append(row)
        for status in STATUS_ORDER:
            rows = grouped.get(status, [])
            if not rows:
                continue
            lines.append(f"#### {STATUS_LABELS[status]}")
            lines.append("")
            for row in rows:
                span = row["evidence_span"]
                ids = row["feature_card_ids"][:2]
                feature_text = ", ".join(ids) if ids else "none"
                ref_count = len(row.get("reference_links") or [])
                blocker_text = ", ".join(row.get("blocker_signals") or []) or "none"
                lines.append(
                    f"- {row['council']} `{row['agreement_id']}` p.{row.get('page') or '?'} "
                    f"clause `{row['clause_card_id'] or 'none'}` feature `{feature_text}`; "
                    f"parser `{row['parser_used'] or 'unknown'}`; block `{row['block_id'] or 'none'}`; "
                    f"status `{row['interpretation_status'] or row['cell_status']}`; refs {ref_count}; blockers {blocker_text}; "
                    f"failure `{row['failure_reason'] or 'none'}`; span `{short_text(span.get('text', ''), 180)}`"
                )
            lines.append("")
    if payload["guardrail_errors"]:
        lines.extend(["## Guardrail Errors", ""])
        for error in payload["guardrail_errors"]:
            lines.append(f"- `{error['code']}`: {error['message']}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an operator QA review pack from a locator experiment artifact.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = args.input.resolve()
    locator_payload = load_json(source_path)
    payload = build_qa_payload(locator_payload, generated_at=utc_now_iso(), source_path=source_path)
    output_dir = args.output_dir
    output_path = output_dir / f"{payload['artifact_id']}.json"
    markdown_path = output_dir / f"{payload['artifact_id']}.md"
    write_json(output_path, payload)
    markdown_path.write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.entitlement_locator_qa_review_build.v1",
        "generated_at": payload["generated_at"],
        "artifact_id": payload["artifact_id"],
        "artifact_path": str(output_path),
        "markdown_path": str(markdown_path),
        "guardrail_status": payload["guardrail_status"],
        "guardrail_errors": payload["guardrail_errors"],
    }, indent=2))
    if payload["guardrail_errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
