from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_entitlement_self_improvement_pass import (  # noqa: E402
    compact_text,
    load_json,
    row_best_candidate,
    row_feature_cards,
    row_values,
    value_label,
    write_json,
)


DEFAULT_LOCATOR_INPUT = ROOT / "wiki" / "artifacts" / "entitlement-locator-experiment" / "entitlement-locator-experiment-all-cached-79-offset-0.json"
DEFAULT_SELF_IMPROVEMENT_INPUT = ROOT / "wiki" / "artifacts" / "entitlement-self-improvement" / "entitlement-self-improvement-pass-entitlement-locator-experiment-all-cached-79-offset-0.json"
DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "entitlement-loop-intelligence"
SCHEMA_VERSION = "wiki.entitlement_loop_intelligence.v1"


GENERIC_VALUE_LABELS = {"candidate provision", "available candidate provision", "value_not_labelled", "available"}
REFERENCE_TERMS = {"nes", "award", "act", "regulation", "policy", "procedure"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def wiki_as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def slug_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("_", " ").replace("-", " ")).strip().title()


def self_rows_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("entitlement_id") or "").strip(): row
        for row in wiki_as_list(payload.get("rows"))
        if isinstance(row, dict) and str(row.get("entitlement_id") or "").strip()
    }


def locator_profiles_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(profile.get("entitlement_id") or "").strip(): profile
        for profile in wiki_as_list(payload.get("profiles"))
        if isinstance(profile, dict) and str(profile.get("entitlement_id") or "").strip()
    }


def green_rows(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row for row in wiki_as_list(profile.get("target_rows"))
        if isinstance(row, dict) and row.get("value_extracted") and row_feature_cards(row)
    ]


def clause_only_rows(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row for row in wiki_as_list(profile.get("target_rows"))
        if isinstance(row, dict) and row.get("clause_found") and not row.get("value_extracted")
    ]


def top_common_value(self_row: dict[str, Any]) -> tuple[str, int]:
    common = self_row.get("observed_value_profile", {}).get("common_values")
    if not isinstance(common, dict) or not common:
        return "", 0
    label, count = next(iter(common.items()))
    return str(label), int(count or 0)


def unit_family(label: str, units: list[str]) -> str:
    text = f"{label} {' '.join(units)}".lower()
    if any(term in text for term in ["week", "day", "hour", "month", "year"]):
        return "duration_or_time"
    if any(term in text for term in ["aud", "$", "allowance", "dollar", "cent"]):
        return "money"
    if "%" in text or "percent" in text:
        return "percentage"
    if any(term in text for term in ["candidate provision", "available", "yes", "no"]):
        return "availability_or_condition"
    return "condition_or_text"


def expected_answer_shape(self_row: dict[str, Any]) -> dict[str, Any]:
    value_profile = self_row.get("observed_value_profile") if isinstance(self_row.get("observed_value_profile"), dict) else {}
    common_values = value_profile.get("common_values") if isinstance(value_profile.get("common_values"), dict) else {}
    units = list((value_profile.get("units") or {}).keys()) if isinstance(value_profile.get("units"), dict) else []
    top_label, top_count = top_common_value(self_row)
    green_count = int(self_row.get("coverage", {}).get("green_feature_cells") or 0)
    top_share = round(top_count / green_count, 3) if green_count else 0
    value_kind = unit_family(top_label, units)
    if not common_values:
        expectation = "No normal value can be inferred yet."
    elif top_share >= 0.6 and top_label.lower() not in GENERIC_VALUE_LABELS:
        expectation = f"Expect {top_label} as the normal answer unless source context shows a subclass or exception."
    elif top_label.lower() in GENERIC_VALUE_LABELS:
        expectation = "The current answer is availability-only; the loop should either find an explicit value or mark amount not stated."
    else:
        expectation = "Treat the answer as variable until subclasses or value-unit rules explain the spread."
    return {
        "kind": value_kind,
        "top_observed_value": top_label,
        "top_observed_count": top_count,
        "top_observed_share": top_share,
        "unit_families": units[:8],
        "expectation": expectation,
    }


def learning_status(self_row: dict[str, Any]) -> str:
    suggestion_types = {
        str(item.get("type"))
        for item in wiki_as_list(self_row.get("improvement_suggestions"))
        if isinstance(item, dict)
    }
    green_count = int(self_row.get("coverage", {}).get("green_feature_cells") or 0)
    if not green_count or "external_research" in suggestion_types:
        return "research_first"
    if "definition_boundary" in suggestion_types:
        return "define_boundary"
    if "normal_value_review" in suggestion_types:
        return "split_or_normalise_values"
    if "value_extraction" in suggestion_types:
        return "repair_value_extraction"
    if "exclusion_tuning" in suggestion_types:
        return "tighten_exclusions"
    return "ready_for_validation"


def promotion_gate(status: str, self_row: dict[str, Any]) -> str:
    green_count = int(self_row.get("coverage", {}).get("green_feature_cells") or 0)
    if status in {"research_first", "define_boundary"}:
        return "blocked_until_definition_research"
    if status in {"split_or_normalise_values", "repair_value_extraction", "tighten_exclusions"}:
        return "needs_loop_review"
    if green_count >= 10:
        return "candidate_for_human_validation"
    return "needs_more_evidence"


def entitlement_question(label: str, answer_shape: dict[str, Any]) -> str:
    kind = answer_shape.get("kind")
    if kind == "duration_or_time":
        answer = "what duration, time credit, accrual, or access condition applies"
    elif kind == "money":
        answer = "what amount, rate, reimbursement, or payment condition applies"
    elif kind == "percentage":
        answer = "what percentage or loading applies"
    elif kind == "availability_or_condition":
        answer = "whether the entitlement exists and what operative condition controls access"
    else:
        answer = "what operative value, condition, or scope applies"
    return f"For standard employees, does the agreement provide {label}, and {answer}?"


def value_rule_candidates(self_row: dict[str, Any], answer_shape: dict[str, Any]) -> list[str]:
    rules: list[str] = []
    top_label = str(answer_shape.get("top_observed_value") or "").lower()
    if top_label in GENERIC_VALUE_LABELS:
        rules.append("If a clause only confirms availability, record amount_not_stated instead of treating the provision as a benchmark value.")
    if answer_shape.get("top_observed_share", 0) >= 0.6 and answer_shape.get("top_observed_value"):
        rules.append(f"Use {answer_shape['top_observed_value']} as the provisional normal value and flag materially different values for review.")
    if self_row.get("observed_value_profile", {}).get("numeric_distinct_count", 0) >= 8:
        rules.append("Split or tag values by subclass before comparing them as a single entitlement.")
    if not rules:
        rules.append("Require an explicit source value, unit, condition, or amount-not-stated reason before promotion.")
    return rules


def rule_change_candidates(self_row: dict[str, Any], answer_shape: dict[str, Any]) -> dict[str, list[str]]:
    contract = self_row.get("rule_contract") if isinstance(self_row.get("rule_contract"), dict) else {}
    boundary = contract.get("classification_boundary") if isinstance(contract.get("classification_boundary"), dict) else {}
    suggestions = {
        str(item.get("type"))
        for item in wiki_as_list(self_row.get("improvement_suggestions"))
        if isinstance(item, dict)
    }
    include = list(wiki_as_list(boundary.get("included")))[:5]
    exclude = list(wiki_as_list(boundary.get("excluded")))[:5]
    review_if = list(wiki_as_list(boundary.get("needs_review")))[:5]
    if "definition_boundary" in suggestions and not include:
        include.append("Operative clauses that create, extend, quantify, or materially condition the entitlement for standard employees.")
    if "exclusion_tuning" in suggestions and not exclude:
        exclude.append("Adjacent references, headings, definitions, or specialist-cohort text that does not create the standard employee entitlement.")
    if "normal_value_review" in suggestions:
        review_if.append("Observed value is materially outside the current cross-council pattern or appears to belong to a different subclass.")
    if "value_extraction" in suggestions:
        review_if.append("Clause is found but value, unit, condition, or amount-not-stated reason is not explicit.")
    return {
        "include": include[:6],
        "exclude": exclude[:6],
        "review_if": review_if[:6],
        "value_rules": value_rule_candidates(self_row, answer_shape),
    }


def feature_validation_reason(row: dict[str, Any], common_labels: set[str]) -> list[str]:
    reasons: list[str] = []
    labels = [value_label(value) for value in row_values(row)]
    label_text = " ".join(labels).lower()
    if any(label.lower() in GENERIC_VALUE_LABELS for label in labels):
        reasons.append("availability-only value")
    if labels and not any(label in common_labels for label in labels):
        reasons.append("uncommon value")
    if not labels:
        reasons.append("missing value label")
    candidate = row_best_candidate(row)
    text = f"{candidate.get('heading', '')} {candidate.get('excerpt', '')}".lower()
    if any(term in text for term in REFERENCE_TERMS):
        reasons.append("reference-heavy context")
    if row.get("locator_confidence") is not None:
        try:
            if float(row.get("locator_confidence") or 0) < 0.55:
                reasons.append("low locator confidence")
        except (TypeError, ValueError):
            pass
    return reasons


def validation_queue(profile: dict[str, Any], self_row: dict[str, Any], *, limit: int = 6) -> list[dict[str, Any]]:
    common = self_row.get("observed_value_profile", {}).get("common_values")
    common_labels = set(list(common.keys())[:3]) if isinstance(common, dict) else set()
    candidates: list[tuple[int, dict[str, Any]]] = []
    for row in green_rows(profile):
        reasons = feature_validation_reason(row, common_labels)
        cards = row_feature_cards(row)
        values = row_values(row)
        score = len(reasons)
        if not score:
            score = 1
            reasons = ["representative green feature card"]
        candidates.append((
            -score,
            {
                "council": row.get("council"),
                "agreement_id": row.get("agreement_id"),
                "reasons": reasons,
                "value_labels": [value_label(value) for value in values],
                "feature_card_ids": [card.get("feature_id") for card in cards if card.get("feature_id")],
                "page": (cards[0].get("page_number_physical") if cards else None) or row_best_candidate(row).get("page"),
                "evidence": compact_text((cards[0].get("evidence_span_text") if cards else "") or row_best_candidate(row).get("excerpt", ""), limit=320),
                "review_question": "Does this clause answer the entitlement question, and should its value update the normal-value model?",
            },
        ))
    candidates.sort(key=lambda item: (item[0], str(item[1].get("council") or "")))
    return [item for _score, item in candidates[:limit]]


def loop_steps(status: str, gate: str) -> list[str]:
    if status == "research_first":
        return [
            "Confirm the industry/legal meaning before interpreting absence or availability.",
            "Review source PDF clauses for any missed operative provisions.",
            "Only then decide whether locator aliases or source coverage need to change.",
        ]
    if status == "define_boundary":
        return [
            "Write the inclusion/exclusion boundary in plain entitlement language.",
            "Map accepted subclasses before comparing values.",
            "Rerun locator after boundary rules are explicit.",
        ]
    if status == "split_or_normalise_values":
        return [
            "Cluster observed values by unit and subclass.",
            "Promote only values that answer the same entitlement question.",
            "Add review-if rules for outliers and generic availability values.",
        ]
    if status == "repair_value_extraction":
        return [
            "Review clause-only cells and decide whether the value is implicit, cross-referenced, or absent.",
            "Add amount-not-stated handling where availability exists without a value.",
            "Add extraction aliases for recurring value phrasing.",
        ]
    if status == "tighten_exclusions":
        return [
            "Review blocked/adjacent examples against exclusions.",
            "Keep operative clauses and drop headings, definitions, references, and specialist-only text.",
            "Rerun the feature-card extraction after blockers are tuned.",
        ]
    if gate == "candidate_for_human_validation":
        return [
            "Validate sampled green feature cards against the entitlement question.",
            "Confirm the normal value expectation is stable enough for reporting.",
            "Promote only reviewed feature cards into governed measures.",
        ]
    return [
        "Collect more source-backed feature cards.",
        "Compare values against the cross-council pattern.",
        "Keep the entitlement out of governed promotion until evidence depth improves.",
    ]


def loop_row(profile: dict[str, Any], self_row: dict[str, Any]) -> dict[str, Any]:
    label = str(self_row.get("label") or profile.get("label") or self_row.get("entitlement_id") or "Entitlement")
    answer_shape = expected_answer_shape(self_row)
    status = learning_status(self_row)
    gate = promotion_gate(status, self_row)
    return {
        "entitlement_id": self_row.get("entitlement_id") or profile.get("entitlement_id"),
        "label": label,
        "loop_status": status,
        "promotion_gate": gate,
        "entitlement_question": entitlement_question(label, answer_shape),
        "answer_shape": answer_shape,
        "normal_value_hypothesis": self_row.get("normal_value_hypothesis"),
        "coverage": self_row.get("coverage") or {},
        "rule_change_candidates": rule_change_candidates(self_row, answer_shape),
        "validation_queue": validation_queue(profile, self_row),
        "next_loop_steps": loop_steps(status, gate),
        "ai_instruction": (
            f"Use source PDFs, the validation queue, and cross-council values to decide whether {label} "
            "has the right definition boundary, normal value model, subclasses, and promotion gate."
        ),
    }


def build_payload(locator_payload: dict[str, Any], self_improvement_payload: dict[str, Any], *, generated_at: str, source_path: Path) -> dict[str, Any]:
    profiles = locator_profiles_by_id(locator_payload)
    rows = [
        loop_row(profiles.get(entitlement_id, {}), self_row)
        for entitlement_id, self_row in self_rows_by_id(self_improvement_payload).items()
    ]
    status_counts = Counter(row["loop_status"] for row in rows)
    gate_counts = Counter(row["promotion_gate"] for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"entitlement-loop-intelligence-{locator_payload.get('artifact_id', 'unknown')}",
        "generated_at": generated_at,
        "source_artifact": {
            "locator_artifact_id": locator_payload.get("artifact_id"),
            "self_improvement_artifact_id": self_improvement_payload.get("artifact_id"),
            "path": str(source_path),
        },
        "method": {
            "name": "entitlement_loop_intelligence_synthesis",
            "scope": (
                "Turns the self-improvement diagnosis into reviewer-facing loop decisions: entitlement question, "
                "answer shape, proposed rule changes, validation queue, and promotion gate."
            ),
            "external_research_status": "queued_not_completed",
        },
        "summary": {
            "entitlements": len(rows),
            "loop_statuses": dict(sorted(status_counts.items())),
            "promotion_gates": dict(sorted(gate_counts.items())),
            "validation_queue_items": sum(len(row["validation_queue"]) for row in rows),
        },
        "rows": rows,
    }


def markdown_for_payload(payload: dict[str, Any]) -> str:
    lines = [
        "# Entitlement Loop Intelligence",
        "",
        payload["method"]["scope"],
        "",
        "## Summary",
        "",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Entitlements", ""])
    for row in payload["rows"]:
        rules = row["rule_change_candidates"]
        lines.extend([
            f"### {row['label']}",
            "",
            f"- Status: `{row['loop_status']}`",
            f"- Gate: `{row['promotion_gate']}`",
            f"- Question: {row['entitlement_question']}",
            f"- Expected answer: {row['answer_shape']['expectation']}",
            f"- Next rules: {'; '.join(rules.get('value_rules', [])[:2])}",
            "",
        ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build loop intelligence over entitlement feature-card learning.")
    parser.add_argument("--locator-input", type=Path, default=DEFAULT_LOCATOR_INPUT)
    parser.add_argument("--self-improvement-input", type=Path, default=DEFAULT_SELF_IMPROVEMENT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    locator_path = args.locator_input.resolve()
    self_path = args.self_improvement_input.resolve()
    locator_payload = load_json(locator_path)
    self_payload = load_json(self_path)
    payload = build_payload(locator_payload, self_payload, generated_at=utc_now_iso(), source_path=self_path)
    output_dir = args.output_dir.resolve()
    json_path = output_dir / f"{payload['artifact_id']}.json"
    md_path = output_dir / f"{payload['artifact_id']}.md"
    write_json(json_path, payload)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.entitlement_loop_intelligence_build.v1",
        "generated_at": payload["generated_at"],
        "artifact_id": payload["artifact_id"],
        "artifact_path": str(json_path),
        "markdown_path": str(md_path),
        "summary": payload["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
