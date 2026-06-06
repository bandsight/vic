from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_LOOP_INPUT = ROOT / "wiki" / "artifacts" / "entitlement-loop-intelligence" / "entitlement-loop-intelligence-entitlement-locator-experiment-all-cached-79-offset-0.json"
DEFAULT_OUTPUT = ROOT / "data" / "review" / "entitlement_loop_rule_overrides.json"
SCHEMA_VERSION = "wiki.entitlement_loop_rule_overrides.v1"


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


def compact_unique(values: list[Any], *, limit: int = 8) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        text = clean_sentence(value)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        items.append(text)
        if len(items) >= limit:
            break
    return items


def alias_candidates(row: dict[str, Any]) -> list[str]:
    label = clean_sentence(row.get("label"))
    question = clean_sentence(row.get("entitlement_question"))
    aliases = [label]
    if label.lower().startswith("superannuation on paid parental leave"):
        aliases.extend([
            "superannuation during paid parental leave",
            "superannuation contributions during paid parental leave",
            "superannuation whilst on paid parental leave",
        ])
    if label.lower().startswith("superannuation on unpaid parental leave"):
        aliases.extend([
            "superannuation during unpaid parental leave",
            "superannuation contributions during unpaid parental leave",
            "superannuation whilst on unpaid parental leave",
        ])
    if "does the agreement provide" in question.lower():
        tail = re.sub(r"^.*?does the agreement provide\s+", "", question, flags=re.I)
        tail = re.sub(r",\s+and\s+.*$", "", tail).strip(" ?.")
        aliases.append(tail)
    return compact_unique(aliases, limit=6)


def answer_shape_include(answer_shape: dict[str, Any]) -> str:
    kind = answer_shape.get("kind")
    if kind == "duration_or_time":
        return "Clauses that state a duration, time credit, accrual amount, access period, or expressly unquantified time-off support."
    if kind == "money":
        return "Clauses that state an amount, rate, reimbursement, allowance, payment condition, or expressly unquantified monetary support."
    if kind == "percentage":
        return "Clauses that state a percentage, loading, contribution rate, or percentage-based condition."
    if kind == "availability_or_condition":
        return "Clauses that create availability or access conditions even where no numeric value is stated."
    return "Clauses that state the operative value, condition, scope, or amount-not-stated basis."


def expected_value_review_rule(answer_shape: dict[str, Any]) -> str | None:
    expected = clean_sentence(answer_shape.get("expectation"))
    top_value = clean_sentence(answer_shape.get("top_observed_value"))
    if not top_value:
        return None
    return f"Observed value materially differs from the loop expectation: {expected}"


def boundary_for_loop_row(row: dict[str, Any]) -> dict[str, list[str] | str]:
    question = clean_sentence(row.get("entitlement_question"))
    answer_shape = row.get("answer_shape") if isinstance(row.get("answer_shape"), dict) else {}
    rules = row.get("rule_change_candidates") if isinstance(row.get("rule_change_candidates"), dict) else {}
    include = compact_unique([
        f"Operative agreement clauses that answer: {question}",
        answer_shape_include(answer_shape),
        *wiki_as_list(rules.get("include")),
    ])
    exclude = compact_unique([
        *wiki_as_list(rules.get("exclude")),
        "Table of contents, headings, definitions, or incidental mentions without an operative entitlement.",
        "Cross-references to NES, Award, Act, policy, or another clause where the agreement does not add a local entitlement.",
        "Specialist cohort-only provisions unless the entitlement definition intentionally includes that cohort.",
    ])
    review_if = compact_unique([
        *wiki_as_list(rules.get("review_if")),
        expected_value_review_rule(answer_shape),
        "Clause is reference-heavy and needs source-context validation before promotion.",
    ])
    return {
        "canonical_definition": question,
        "included": include,
        "excluded": exclude,
        "needs_review": review_if,
    }


def accepted_subclasses(row: dict[str, Any]) -> list[dict[str, str]]:
    entitlement_id = clean_sentence(row.get("entitlement_id"))
    answer_shape = row.get("answer_shape") if isinstance(row.get("answer_shape"), dict) else {}
    kind = clean_sentence(answer_shape.get("kind") or "condition_or_text")
    top_value = clean_sentence(answer_shape.get("top_observed_value"))
    subclasses = [
        {
            "subclass_id": f"{entitlement_id}.{kind}",
            "label": f"{clean_sentence(row.get('label'))} - {kind.replace('_', ' ')}",
            "relationship": "learned_loop_answer_shape",
        }
    ]
    if top_value:
        subclasses.append({
            "subclass_id": f"{entitlement_id}.normal-observed-value",
            "label": f"Normal observed value: {top_value}",
            "relationship": "learned_loop_value_expectation",
        })
    return subclasses


def override_for_loop_row(row: dict[str, Any]) -> dict[str, Any]:
    rules = row.get("rule_change_candidates") if isinstance(row.get("rule_change_candidates"), dict) else {}
    answer_shape = row.get("answer_shape") if isinstance(row.get("answer_shape"), dict) else {}
    return {
        "entitlement_id": row.get("entitlement_id"),
        "label": row.get("label"),
        "rule_origin": "learned_loop_override",
        "learning_source": "entitlement_loop_intelligence",
        "loop_status": row.get("loop_status"),
        "promotion_gate": row.get("promotion_gate"),
        "classification_boundary": boundary_for_loop_row(row),
        "accepted_subclasses": accepted_subclasses(row),
        "candidate_aliases": alias_candidates(row),
        "expected_answer_shape": answer_shape,
        "value_rules": compact_unique(wiki_as_list(rules.get("value_rules")), limit=6),
        "validation_queue": wiki_as_list(row.get("validation_queue"))[:6],
        "next_loop_steps": compact_unique(wiki_as_list(row.get("next_loop_steps")), limit=6),
    }


def build_payload(loop_payload: dict[str, Any], *, generated_at: str, source_path: Path) -> dict[str, Any]:
    rows = [
        row for row in wiki_as_list(loop_payload.get("rows"))
        if isinstance(row, dict) and clean_sentence(row.get("entitlement_id"))
    ]
    overrides = [override_for_loop_row(row) for row in rows]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_artifact": {
            "artifact_id": loop_payload.get("artifact_id"),
            "path": str(source_path),
            "generated_at": loop_payload.get("generated_at"),
        },
        "summary": {
            "overrides": len(overrides),
            "learned_boundaries": sum(1 for item in overrides if item.get("classification_boundary")),
            "with_value_rules": sum(1 for item in overrides if item.get("value_rules")),
            "with_validation_queue": sum(1 for item in overrides if item.get("validation_queue")),
        },
        "overrides": overrides,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply loop-intelligence findings as locator rule overrides for the next run.")
    parser.add_argument("--loop-input", type=Path, default=DEFAULT_LOOP_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = args.loop_input.resolve()
    payload = build_payload(load_json(source_path), generated_at=utc_now_iso(), source_path=source_path)
    output_path = args.output.resolve()
    write_json(output_path, payload)
    print(json.dumps({
        "schema_version": "wiki.entitlement_loop_rule_overrides_build.v1",
        "generated_at": payload["generated_at"],
        "output_path": str(output_path),
        "summary": payload["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
