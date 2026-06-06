from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW_INPUT = (
    ROOT
    / "wiki"
    / "artifacts"
    / "feature-card-llm-review"
    / "feature-card-llm-review-entitlement-locator-experiment-all-cached-79-offset-0.json"
)
DEFAULT_OVERRIDES_INPUT = ROOT / "data" / "review" / "entitlement_loop_rule_overrides.json"
DEFAULT_OUTPUT = DEFAULT_OVERRIDES_INPUT
SCHEMA_VERSION = "wiki.entitlement_loop_rule_overrides.v3"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wiki_as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def clean_sentence(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def slug_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "review-subclass"


def append_unique(existing: list[Any], additions: list[Any], *, limit: int = 18) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in [*existing, *additions]:
        text = clean_sentence(value)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
        if len(output) >= limit:
            break
    return output


def review_rows_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("entitlement_id") or "").strip(): row
        for row in wiki_as_list(payload.get("rows"))
        if isinstance(row, dict) and str(row.get("entitlement_id") or "").strip()
    }


def decision_counts(row: dict[str, Any]) -> dict[str, int]:
    review = row.get("llm_review") if isinstance(row.get("llm_review"), dict) else {}
    return dict(sorted(Counter(
        str(item.get("decision") or "unlabelled")
        for item in wiki_as_list(review.get("feature_card_decisions"))
        if isinstance(item, dict)
    ).items()))


def review_section(row: dict[str, Any], key: str) -> dict[str, Any]:
    review = row.get("llm_review") if isinstance(row.get("llm_review"), dict) else {}
    section = review.get(key)
    return section if isinstance(section, dict) else {}


def rule_updates(row: dict[str, Any]) -> dict[str, Any]:
    return review_section(row, "rule_updates")


def value_rule_additions(row: dict[str, Any]) -> list[str]:
    quantum = review_section(row, "quantum_review")
    updates = rule_updates(row)
    additions: list[Any] = []
    normal_model = clean_sentence(quantum.get("normal_value_model"))
    required_fields = [clean_sentence(item) for item in wiki_as_list(quantum.get("required_context_fields")) if clean_sentence(item)]
    if normal_model:
        additions.append(f"Feature-card LLM normal value model: {normal_model}")
    if required_fields:
        additions.append(f"Before promotion, require context fields: {', '.join(required_fields)}.")
    additions.extend(wiki_as_list(quantum.get("timeframe_rules")))
    additions.extend(wiki_as_list(quantum.get("unit_normalisation_rules")))
    additions.extend(wiki_as_list(quantum.get("cohort_scope_rules")))
    additions.extend(wiki_as_list(updates.get("value_rules")))
    return append_unique([], additions, limit=14)


def needs_review_additions(row: dict[str, Any]) -> list[str]:
    definition = review_section(row, "definition_review")
    alignment = review_section(row, "alignment_review")
    updates = rule_updates(row)
    review = row.get("llm_review") if isinstance(row.get("llm_review"), dict) else {}
    additions: list[Any] = []
    additions.extend(wiki_as_list(definition.get("review_if")))
    additions.extend(f"LLM suspicious pattern: {item}" for item in wiki_as_list(alignment.get("suspicious_patterns")))
    additions.extend(f"LLM missing context pattern: {item}" for item in wiki_as_list(alignment.get("missing_context_patterns")))
    additions.extend(wiki_as_list(updates.get("definition_updates")))
    for decision in wiki_as_list(review.get("feature_card_decisions"))[:6]:
        if not isinstance(decision, dict):
            continue
        label = clean_sentence(decision.get("decision"))
        if label == "promote_candidate":
            continue
        reason = clean_sentence(decision.get("required_fix") or decision.get("reason"))
        feature_id = clean_sentence(decision.get("feature_id"))
        additions.append(f"Feature-card review {label} for {feature_id}: {reason}")
    return append_unique([], additions, limit=16)


def subclass_additions(entitlement_id: str, row: dict[str, Any]) -> list[dict[str, str]]:
    additions: list[dict[str, str]] = []
    for item in wiki_as_list(rule_updates(row).get("subclass_splits"))[:8]:
        label = clean_sentence(item)
        if not label:
            continue
        additions.append({
            "subclass_id": f"{entitlement_id}.{slug_key(label)}",
            "label": label,
            "relationship": "feature_card_llm_subclass_split",
        })
    return additions


def append_unique_subclasses(existing: list[Any], additions: list[dict[str, str]], *, limit: int = 16) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in [*existing, *additions]:
        if not isinstance(item, dict):
            continue
        subclass_id = clean_sentence(item.get("subclass_id"))
        label = clean_sentence(item.get("label"))
        relationship = clean_sentence(item.get("relationship"))
        key = subclass_id.lower() or label.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append({
            "subclass_id": subclass_id,
            "label": label,
            "relationship": relationship,
        })
        if len(output) >= limit:
            break
    return output


def feature_card_review_summary(row: dict[str, Any]) -> dict[str, Any]:
    definition = review_section(row, "definition_review")
    quantum = review_section(row, "quantum_review")
    alignment = review_section(row, "alignment_review")
    updates = rule_updates(row)
    return {
        "review_status": row.get("llm_status"),
        "definition_status": definition.get("status"),
        "alignment_status": alignment.get("overall_status"),
        "promotion_gate": updates.get("promotion_gate"),
        "green_feature_cards": row.get("green_feature_cards"),
        "decision_counts": decision_counts(row),
        "context_flag_counts": row.get("context_flag_counts") if isinstance(row.get("context_flag_counts"), dict) else {},
        "required_context_fields": wiki_as_list(quantum.get("required_context_fields")),
        "normal_value_model": quantum.get("normal_value_model"),
    }


def apply_review_to_override(override: dict[str, Any], review_row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(override)
    entitlement_id = clean_sentence(merged.get("entitlement_id"))
    definition = review_section(review_row, "definition_review")
    updates = rule_updates(review_row)
    boundary = dict(merged.get("classification_boundary") if isinstance(merged.get("classification_boundary"), dict) else {})
    industry_definition = clean_sentence(definition.get("industry_standard_definition"))
    if industry_definition:
        boundary["canonical_definition"] = industry_definition
    boundary["included"] = append_unique(
        wiki_as_list(boundary.get("included")),
        wiki_as_list(definition.get("inclusions")),
        limit=18,
    )
    boundary["excluded"] = append_unique(
        wiki_as_list(boundary.get("excluded")),
        wiki_as_list(definition.get("exclusions")),
        limit=18,
    )
    boundary["needs_review"] = append_unique(
        wiki_as_list(boundary.get("needs_review")),
        needs_review_additions(review_row),
        limit=24,
    )
    merged["classification_boundary"] = boundary
    merged["value_rules"] = append_unique(
        wiki_as_list(merged.get("value_rules")),
        value_rule_additions(review_row),
        limit=24,
    )
    merged["accepted_subclasses"] = append_unique_subclasses(
        wiki_as_list(merged.get("accepted_subclasses")),
        subclass_additions(entitlement_id, review_row),
        limit=18,
    )
    promotion_gate = clean_sentence(updates.get("promotion_gate"))
    if promotion_gate:
        merged["feature_card_promotion_gate"] = promotion_gate
    merged["feature_card_llm_review"] = feature_card_review_summary(review_row)
    merged["feature_card_llm_review_applied"] = True
    return merged


def build_payload(overrides_payload: dict[str, Any], review_payload: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    reviews = review_rows_by_id(review_payload)
    overrides: list[dict[str, Any]] = []
    applied = 0
    for item in wiki_as_list(overrides_payload.get("overrides")):
        if not isinstance(item, dict):
            continue
        entitlement_id = clean_sentence(item.get("entitlement_id"))
        review_row = reviews.get(entitlement_id)
        if review_row:
            overrides.append(apply_review_to_override(item, review_row))
            applied += 1
        else:
            overrides.append(item)
    review_statuses = Counter(
        str(row.get("llm_status") or "missing")
        for row in reviews.values()
    )
    return {
        **overrides_payload,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "feature_card_llm_review_source_artifact": {
            "artifact_id": review_payload.get("artifact_id"),
            "generated_at": review_payload.get("generated_at"),
        },
        "summary": {
            **(overrides_payload.get("summary") if isinstance(overrides_payload.get("summary"), dict) else {}),
            "feature_card_llm_review_applied": applied,
            "feature_card_llm_review_statuses": dict(sorted(review_statuses.items())),
            "with_feature_card_quantum_rules": sum(1 for item in overrides if wiki_as_list(item.get("value_rules"))),
        },
        "overrides": overrides,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply feature-card LLM definition and quantum findings to locator rule overrides.")
    parser.add_argument("--review-input", type=Path, default=DEFAULT_REVIEW_INPUT)
    parser.add_argument("--overrides-input", type=Path, default=DEFAULT_OVERRIDES_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_payload(
        load_json(args.overrides_input.resolve()),
        load_json(args.review_input.resolve()),
        generated_at=utc_now_iso(),
    )
    output_path = args.output.resolve()
    write_json(output_path, payload)
    print(json.dumps({
        "schema_version": "wiki.feature_card_llm_review_findings_apply.v1",
        "generated_at": payload["generated_at"],
        "output_path": str(output_path),
        "summary": payload["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
