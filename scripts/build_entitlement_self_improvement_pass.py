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

from scripts.build_entitlement_locator_experiment import LOCATOR_SPECS, serialisable_rule_contract


DEFAULT_INPUT = ROOT / "wiki" / "artifacts" / "entitlement-locator-experiment" / "entitlement-locator-experiment-all-cached-79-offset-0.json"
DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "entitlement-self-improvement"
SCHEMA_VERSION = "wiki.entitlement_self_improvement_pass.v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def compact_text(value: Any, *, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def numeric_value(value: Any) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def value_label(value: dict[str, Any]) -> str:
    parts = [
        str(value.get("value") or "").strip(),
        str(value.get("unit") or "").strip(),
    ]
    label = " ".join(part for part in parts if part)
    return label or str(value.get("condition") or value.get("subclass_label") or "value_not_labelled")


def row_values(row: dict[str, Any]) -> list[dict[str, Any]]:
    values = row.get("normalised_values")
    return [value for value in values if isinstance(value, dict)] if isinstance(values, list) else []


def row_feature_cards(row: dict[str, Any]) -> list[dict[str, Any]]:
    cards = row.get("feature_cards")
    return [card for card in cards if isinstance(card, dict)] if isinstance(cards, list) else []


def row_best_candidate(row: dict[str, Any]) -> dict[str, Any]:
    candidate = row.get("best_candidate")
    return candidate if isinstance(candidate, dict) else {}


def evidence_text(row: dict[str, Any]) -> str:
    for feature in row_feature_cards(row):
        if feature.get("evidence_span_text"):
            return compact_text(feature.get("evidence_span_text"))
    candidate = row_best_candidate(row)
    return compact_text(candidate.get("excerpt", ""))


def contract_for_profile(profile: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    artifact_contract = profile.get("rule_contract")
    if isinstance(artifact_contract, dict):
        origin = str(artifact_contract.get("rule_origin") or "").strip()
        if origin:
            return artifact_contract, origin != "generic_taxonomy_fallback"
        return artifact_contract, True
    entitlement_id = str(profile.get("entitlement_id") or "")
    for spec in LOCATOR_SPECS:
        if spec.entitlement_id == entitlement_id:
            return serialisable_rule_contract(spec), bool(spec.profile.get("classification_boundary"))
    return {
        "entitlement_id": entitlement_id,
        "label": profile.get("label") or entitlement_id,
        "definition": "",
        "classification_boundary": {"canonical_definition": "", "included": [], "excluded": [], "needs_review": []},
        "accepted_subclasses": [],
        "ai_improvement_questions": [],
    }, False


def observed_value_profile(green_rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [value for row in green_rows for value in row_values(row)]
    labels = Counter(value_label(value) for value in values if value_label(value))
    units = Counter(str(value.get("unit") or "").strip() for value in values if str(value.get("unit") or "").strip())
    subclasses = Counter(str(value.get("subclass_label") or "").strip() for value in values if str(value.get("subclass_label") or "").strip())
    numeric_values = [number for value in values for number in [numeric_value(value.get("value"))] if number is not None]
    return {
        "feature_values": len(values),
        "common_values": dict(labels.most_common(12)),
        "units": dict(units.most_common(8)),
        "subclasses": dict(subclasses.most_common(8)),
        "numeric_min": min(numeric_values) if numeric_values else None,
        "numeric_max": max(numeric_values) if numeric_values else None,
        "numeric_distinct_count": len(set(numeric_values)),
    }


def normal_value_hypothesis(value_profile: dict[str, Any], green_count: int) -> str:
    common = value_profile.get("common_values") or {}
    if not common:
        return "No normal value expectation can be inferred yet because no green feature values were observed."
    top_label, top_count = next(iter(common.items()))
    units = ", ".join((value_profile.get("units") or {}).keys())
    range_text = ""
    if value_profile.get("numeric_min") is not None and value_profile.get("numeric_max") is not None:
        range_text = f" Observed numeric range: {value_profile['numeric_min']:g} to {value_profile['numeric_max']:g}."
    unit_text = f" Main unit pattern: {units}." if units else ""
    return f"Most common observed value is {top_label} ({top_count}/{max(green_count, 1)} green cells).{unit_text}{range_text}"


def improvement_suggestions(
    *,
    label: str,
    contract: dict[str, Any],
    hand_authored_boundary: bool,
    green_rows: list[dict[str, Any]],
    clause_only_rows: list[dict[str, Any]],
    blocked_rows: list[dict[str, Any]],
    missing_rows: list[dict[str, Any]],
    value_profile: dict[str, Any],
) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    boundary = contract.get("classification_boundary") if isinstance(contract.get("classification_boundary"), dict) else {}
    if not hand_authored_boundary:
        suggestions.append({
            "type": "definition_boundary",
            "priority": "high",
            "message": f"Author a proper industry-standard inclusion/exclusion boundary for {label}; current rules are generic fallback review guidance.",
        })
    if not green_rows:
        suggestions.append({
            "type": "external_research",
            "priority": "high",
            "message": "No green feature cards exist, so use source PDF review plus external industrial/legal research before treating absence as meaningful.",
        })
    if len(green_rows) < 5:
        suggestions.append({
            "type": "evidence_depth",
            "priority": "medium",
            "message": "Observed feature set is thin. Compare more councils before deriving a normal value expectation.",
        })
    if len(clause_only_rows) >= 5:
        suggestions.append({
            "type": "value_extraction",
            "priority": "medium",
            "message": f"{len(clause_only_rows)} clause-only cells need value reasoning; improve value/unit extraction or classify as amount-not-stated.",
        })
    if len(blocked_rows) >= 5:
        blockers = Counter(
            str(signal)
            for row in blocked_rows
            for signal in (row_best_candidate(row).get("blocker_signals") or [])
        )
        top_blockers = ", ".join(name for name, _count in blockers.most_common(4))
        suggestions.append({
            "type": "exclusion_tuning",
            "priority": "medium",
            "message": f"{len(blocked_rows)} blocked/adjacent cells should be reviewed against exclusions; recurring blockers: {top_blockers or 'not labelled'}.",
        })
    if value_profile.get("numeric_distinct_count", 0) >= 8:
        suggestions.append({
            "type": "normal_value_review",
            "priority": "medium",
            "message": "Observed values vary widely. Ask whether values represent the same entitlement, separate subclasses, or parser over-capture.",
        })
    if not boundary.get("needs_review"):
        suggestions.append({
            "type": "ambiguity_rules",
            "priority": "low",
            "message": "Add explicit review-if rules for discretionary, cross-referenced, specialist-cohort, and unusual-value cases.",
        })
    if len(missing_rows) >= 1:
        suggestions.append({
            "type": "source_spine",
            "priority": "low",
            "message": f"{len(missing_rows)} cells have no source spine. Repair source cache before interpreting absence.",
        })
    return suggestions


def sample_green_cards(rows: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in rows[:limit]:
        values = row_values(row)
        cards = row_feature_cards(row)
        samples.append({
            "council": row.get("council"),
            "agreement_id": row.get("agreement_id"),
            "page": (cards[0].get("page_number_physical") if cards else None) or row_best_candidate(row).get("page"),
            "feature_card_ids": [card.get("feature_id") for card in cards if card.get("feature_id")],
            "value_labels": [value_label(value) for value in values],
            "evidence": evidence_text(row),
            "validation_prompt": "Does this source span fit the entitlement definition, and does the value/unit/scope make contextual sense compared with other councils?",
        })
    return samples


def improvement_row(profile: dict[str, Any]) -> dict[str, Any]:
    contract, hand_authored_boundary = contract_for_profile(profile)
    rows = [row for row in profile.get("target_rows", []) if isinstance(row, dict)]
    green_rows = [row for row in rows if row.get("value_extracted") and row_feature_cards(row)]
    clause_only_rows = [row for row in rows if row.get("clause_found") and not row.get("value_extracted")]
    blocked_rows = [row for row in rows if row.get("state") == "adjacent_or_blocked_clause_found"]
    missing_rows = [row for row in rows if int(row.get("page_count") or 0) == 0]
    value_profile = observed_value_profile(green_rows)
    suggestions = improvement_suggestions(
        label=str(profile.get("label") or profile.get("entitlement_id") or "entitlement"),
        contract=contract,
        hand_authored_boundary=hand_authored_boundary,
        green_rows=green_rows,
        clause_only_rows=clause_only_rows,
        blocked_rows=blocked_rows,
        missing_rows=missing_rows,
        value_profile=value_profile,
    )
    status = "definition_ready_candidate"
    if not green_rows:
        status = "needs_external_research"
    elif not hand_authored_boundary:
        status = "needs_definition_solidification"
    elif any(item["type"] in {"normal_value_review", "value_extraction"} for item in suggestions):
        status = "needs_value_pattern_review"
    return {
        "entitlement_id": profile.get("entitlement_id"),
        "key": profile.get("key"),
        "label": profile.get("label"),
        "status": status,
        "coverage": {
            "councils": len(rows),
            "green_feature_cells": len(green_rows),
            "clause_only_cells": len(clause_only_rows),
            "blocked_or_adjacent_cells": len(blocked_rows),
            "missing_spine_cells": len(missing_rows),
        },
        "rule_contract": contract,
        "observed_value_profile": value_profile,
        "normal_value_hypothesis": normal_value_hypothesis(value_profile, len(green_rows)),
        "sample_green_cards": sample_green_cards(green_rows),
        "research_tasks": [
            "Review sampled source PDF clauses and surrounding subclauses for fit against the definition.",
            "Compare green feature cards against the entitlement's cross-council value pattern.",
            "Check external legal/industrial sources for statutory floors and industry-standard terminology before promotion.",
            "Update definition, inclusions, exclusions, review-if rules, aliases, and normal value expectations for the next locator run.",
        ],
        "improvement_suggestions": suggestions,
        "ai_review_prompt": (
            f"Review {profile.get('label')} using the rule contract, green feature samples, and observed value profile. "
            "Decide whether the definition is industry-standard, whether included/excluded boundaries match the feature set, "
            "what value/unit/scope is normal, and what extraction or definition rule should change next."
        ),
    }


def build_payload(locator_payload: dict[str, Any], *, generated_at: str, source_path: Path) -> dict[str, Any]:
    profiles = [profile for profile in locator_payload.get("profiles", []) if isinstance(profile, dict)]
    rows = [improvement_row(profile) for profile in profiles]
    status_counts = Counter(row["status"] for row in rows)
    suggestion_counts = Counter(
        suggestion["type"]
        for row in rows
        for suggestion in row["improvement_suggestions"]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"entitlement-self-improvement-pass-{locator_payload.get('artifact_id', 'unknown')}",
        "generated_at": generated_at,
        "source_artifact": {
            "artifact_id": locator_payload.get("artifact_id"),
            "path": str(source_path),
            "generated_at": locator_payload.get("generated_at"),
        },
        "method": {
            "name": "internal_feature_card_self_improvement_pass",
            "scope": "Uses current locator feature cards, rule contracts, cross-council value patterns, and review prompts. External research is queued as explicit tasks, not silently treated as completed.",
            "green_feature_cell_definition": "value_extracted=true and at least one feature card exists",
        },
        "summary": {
            "entitlements": len(rows),
            "green_feature_cells": sum(row["coverage"]["green_feature_cells"] for row in rows),
            "statuses": dict(sorted(status_counts.items())),
            "suggestion_types": dict(sorted(suggestion_counts.items())),
            "definition_solidification_needed": sum(1 for row in rows if row["status"] in {"needs_definition_solidification", "needs_external_research"}),
        },
        "rows": rows,
    }


def markdown_for_payload(payload: dict[str, Any]) -> str:
    lines = [
        "# Entitlement Self-Improvement Pass",
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
        suggestions = "; ".join(item["message"] for item in row["improvement_suggestions"][:3]) or "No immediate improvement suggested."
        lines.extend([
            f"### {row['label']}",
            "",
            f"- Status: `{row['status']}`",
            f"- Green feature cells: `{row['coverage']['green_feature_cells']}`",
            f"- Normal value: {row['normal_value_hypothesis']}",
            f"- Suggestions: {suggestions}",
            "",
        ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an internal self-improvement pass over green entitlement feature cards.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = args.input.resolve()
    locator_payload = load_json(source_path)
    payload = build_payload(locator_payload, generated_at=utc_now_iso(), source_path=source_path)
    output_dir = args.output_dir.resolve()
    json_path = output_dir / f"{payload['artifact_id']}.json"
    md_path = output_dir / f"{payload['artifact_id']}.md"
    write_json(json_path, payload)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.entitlement_self_improvement_pass_build.v1",
        "generated_at": payload["generated_at"],
        "artifact_id": payload["artifact_id"],
        "artifact_path": str(json_path),
        "markdown_path": str(md_path),
        "summary": payload["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
