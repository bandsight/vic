from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import ssl
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.build_entitlement_cards import (  # noqa: E402
    compact_text,
    dedupe_values,
    entitlement_gate_failures,
    load_json,
    process_flags,
    review_statuses,
    row_clause_cards,
    row_feature_cards,
    row_values,
    value_label,
    wiki_as_list,
    write_json,
)


DEFAULT_LOCATOR_INPUT = (
    ROOT
    / "wiki"
    / "artifacts"
    / "entitlement-locator-experiment"
    / "entitlement-locator-experiment-all-cached-79-offset-0.json"
)
DEFAULT_CARDS_INPUT = (
    ROOT
    / "wiki"
    / "artifacts"
    / "entitlement-cards"
    / "entitlement-cards-entitlement-locator-experiment-all-cached-79-offset-0.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "entitlement-card-repair-loop"
SCHEMA_VERSION = "wiki.entitlement_card_repair_loop.v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def card_examples(cards_payload: dict[str, Any], entitlement_id: str, *, limit: int = 4) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for card in wiki_as_list(cards_payload.get("cards")):
        if not isinstance(card, dict) or card.get("entitlement_id") != entitlement_id:
            continue
        rows.append({
            "council": card.get("council"),
            "agreement_id": card.get("agreement_id"),
            "simple_sentence": card.get("simple_sentence"),
            "quantum": card.get("quantum") if isinstance(card.get("quantum"), dict) else {},
            "clause_ids": wiki_as_list((card.get("source_refs") or {}).get("clause_card_ids") if isinstance(card.get("source_refs"), dict) else []),
        })
        if len(rows) >= limit:
            break
    return rows


def value_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [value for row in rows for value in row_values(row)]
    return {
        "values": len(values),
        "common_values": dict(Counter(value_label(value) for value in values).most_common(12)),
        "units": dict(Counter(clean_text(value.get("unit")) for value in values if clean_text(value.get("unit"))).most_common(8)),
        "conditions": dict(Counter(compact_text(value.get("condition"), limit=100) for value in values if clean_text(value.get("condition"))).most_common(8)),
    }


def row_summary(profile: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    clauses = row_clause_cards(row)
    features = row_feature_cards(row)
    values = dedupe_values(row_values(row))
    candidate = row.get("best_candidate") if isinstance(row.get("best_candidate"), dict) else {}
    return {
        "council": row.get("council"),
        "agreement_id": row.get("agreement_id"),
        "state": row.get("state"),
        "gate_failures": entitlement_gate_failures(profile, row),
        "review_statuses": sorted(review_statuses(row)),
        "process_rule_flags": sorted(process_flags(row)),
        "value_labels": [value_label(value) for value in values],
        "normalised_values": values[:6],
        "best_page": candidate.get("page"),
        "best_heading": candidate.get("heading"),
        "feature_samples": [
            {
                "feature_id": feature.get("feature_id"),
                "review_status": feature.get("review_status"),
                "value": feature.get("value"),
                "unit": feature.get("unit"),
                "condition": feature.get("condition"),
                "evidence": compact_text(feature.get("evidence_span_text"), limit=500),
            }
            for feature in features[:4]
        ],
        "clause_samples": [
            {
                "clause_id": clause.get("clause_id"),
                "review_status": clause.get("review_status"),
                "page": clause.get("page_number_physical"),
                "text": compact_text(clause.get("raw_clause_text"), limit=700),
            }
            for clause in clauses[:3]
        ],
    }


def score_blocked_row(row: dict[str, Any], profile: dict[str, Any]) -> int:
    failures = set(entitlement_gate_failures(profile, row))
    score = 0
    score += 20 * int(row.get("state") == "clause_found_value_extracted")
    score += 10 * int("blocking_process_rule_flags" in failures)
    score += 9 * int("review_status_not_strong" in failures)
    score += 8 * int("mixed_availability_and_quantum_values" in failures)
    score += 8 * int("availability_candidate_not_reportable_quantum" in failures)
    score += 7 * int("reference_only_value_not_reportable_quantum" in failures)
    score += 5 * len(row_feature_cards(row))
    score += 3 * len(row_clause_cards(row))
    return score


def choose_samples(profile: dict[str, Any], rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    blocked = [
        row
        for row in rows
        if entitlement_gate_failures(profile, row)
        and row.get("state") != "no_candidate_clause_found"
    ]
    blocked.sort(key=lambda row: (-score_blocked_row(row, profile), str(row.get("council") or "")))
    return blocked[:limit]


def profile_context(profile: dict[str, Any], cards_payload: dict[str, Any], *, sample_limit: int) -> dict[str, Any]:
    rows = [row for row in wiki_as_list(profile.get("target_rows")) if isinstance(row, dict)]
    blocked_rows = [row for row in rows if entitlement_gate_failures(profile, row)]
    blocked_value_rows = [row for row in blocked_rows if row.get("state") == "clause_found_value_extracted"]
    failure_counts = Counter(
        failure
        for row in blocked_rows
        for failure in entitlement_gate_failures(profile, row)
    )
    status_counts = Counter(status for row in blocked_rows for status in review_statuses(row))
    flag_counts = Counter(flag for row in blocked_rows for flag in process_flags(row))
    rule_contract = profile.get("rule_contract") if isinstance(profile.get("rule_contract"), dict) else {}
    return {
        "entitlement_id": profile.get("entitlement_id"),
        "label": profile.get("label"),
        "definition": rule_contract.get("definition") or profile.get("definition"),
        "classification_boundary": rule_contract.get("classification_boundary") if isinstance(rule_contract.get("classification_boundary"), dict) else {},
        "output_contract": profile.get("output_contract") or rule_contract.get("output_contract") or {},
        "accepted_subclasses": rule_contract.get("accepted_subclasses") or [],
        "rows": len(rows),
        "blocked_rows": len(blocked_rows),
        "blocked_value_rows": len(blocked_value_rows),
        "failure_counts": dict(sorted(failure_counts.items())),
        "review_status_counts": dict(sorted(status_counts.items())),
        "process_flag_counts": dict(sorted(flag_counts.items())),
        "blocked_value_profile": value_profile(blocked_value_rows),
        "successful_entitlement_card_examples": card_examples(cards_payload, clean_text(profile.get("entitlement_id"))),
        "blocked_samples": [row_summary(profile, row) for row in choose_samples(profile, rows, limit=sample_limit)],
    }


SYSTEM_PROMPT = """You are an expert Australian local-government EBA entitlement governance repair reviewer.
You are not approving facts. You are diagnosing why blocked council-entitlement rows failed the Entitlement Card standard.

Your job is to identify the smallest truthful repair path:
- improve extraction if source text already supports the fact,
- tighten rules if the candidate is noise,
- split subclasses if values are being mixed,
- require source PDF or external research if context is missing,
- keep the row blocked if it should not become reportable.

Return only valid JSON. No markdown. No commentary.
"""


def user_prompt(context: dict[str, Any]) -> str:
    return json.dumps({
        "task": {
            "asset": "Entitlement Card",
            "standard": "Only emit a proposed governed Entitlement Card when the machine has a source-backed, context-aligned council-entitlement fact that should not need review.",
            "decision_labels": [
                "candidate_for_card_after_specific_fix",
                "repairable_by_context_extraction",
                "repairable_by_rule_tightening",
                "needs_subclass_split",
                "requires_pdf_or_external_research",
                "should_remain_blocked_noise",
            ],
            "required_json_shape": {
                "entitlement_card_standard_review": {
                    "can_any_blocked_rows_become_cards": "yes|mixed|no",
                    "dominant_blocker": "string",
                    "standard_adjustment": "unchanged|tighten|loosen_specific|research_first",
                    "reasoning_summary": "string",
                },
                "repair_actions": [
                    {
                        "action_type": "extractor|locator_rules|definition|value_normalisation|source_research|human_review",
                        "description": "string",
                        "expected_effect": "string",
                        "risk": "string",
                    }
                ],
                "row_decisions": [
                    {
                        "council": "string",
                        "agreement_id": "string",
                        "decision": "one decision label",
                        "why_blocked": "string",
                        "specific_fix": "string",
                        "would_emit_card_after_fix": False,
                        "proposed_simple_sentence": "quantity first, unit stated, measured thing named, or empty",
                        "required_value_context": {
                            "fact_role": "entitlement_quantum|monetary_amount|percentage_rate|availability|rule_parameter|eligibility_period|unknown_candidate",
                            "timeframe": "string",
                            "operative_period": "string",
                            "cohort": "string",
                            "condition": "string",
                            "unit_basis": "string",
                        },
                    }
                ],
                "rule_updates": {
                    "definition_updates": ["string"],
                    "value_rules": ["string"],
                    "exclusion_rules": ["string"],
                    "subclass_splits": ["string"],
                    "extraction_tests": ["string"],
                },
            },
        },
        "entitlement_context": context,
    }, ensure_ascii=False)


def parse_json_response(raw: str) -> tuple[dict[str, Any], str]:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text), ""
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1]), ""
            except json.JSONDecodeError as exc:
                return {}, str(exc)
        return {}, "response did not contain a JSON object"


def llm_repair(context: dict[str, Any], *, env: dict[str, str], model: str, max_tokens: int) -> dict[str, Any]:
    try:
        import anthropic
    except ImportError as exc:
        return {"llm_status": "blocked", "error": f"anthropic package missing: {exc}", "parsed": {}, "raw_response": ""}
    api_key = env.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"llm_status": "blocked", "error": "ANTHROPIC_API_KEY not set", "parsed": {}, "raw_response": ""}
    try:
        from benchmarking_data_factory.workbench.llm_client import anthropic_ssl_context

        client = anthropic.Anthropic(
            api_key=api_key,
            http_client=anthropic.DefaultHttpxClient(verify=anthropic_ssl_context(ssl)),
        )
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt(context)}],
        )
        raw = response.content[0].text if response.content else ""
    except Exception as exc:
        return {"llm_status": "error", "error": f"{type(exc).__name__}: {exc}", "parsed": {}, "raw_response": ""}
    parsed, parse_error = parse_json_response(raw)
    return {
        "llm_status": "parsed" if parsed else "parse_error",
        "error": parse_error,
        "parsed": parsed,
        "raw_response": raw,
    }


def offline_repair(context: dict[str, Any]) -> dict[str, Any]:
    failures = context.get("failure_counts") if isinstance(context.get("failure_counts"), dict) else {}
    return {
        "llm_status": "offline_deterministic",
        "error": "",
        "parsed": {
            "entitlement_card_standard_review": {
                "can_any_blocked_rows_become_cards": "mixed" if context.get("blocked_value_rows") else "no",
                "dominant_blocker": next(iter(failures.keys()), "no blocked rows"),
                "standard_adjustment": "unchanged",
                "reasoning_summary": "Deterministic fallback. Preserve strict card standard and repair source context before promotion.",
            },
            "repair_actions": [
                {
                    "action_type": "value_normalisation",
                    "description": "Resolve listed gate failures before attempting Entitlement Card emission.",
                    "expected_effect": "Rows either become eligible for a strict card or remain explicitly blocked.",
                    "risk": "No semantic repair was performed because the LLM was not used.",
                }
            ],
            "row_decisions": [
                {
                    "council": sample.get("council"),
                    "agreement_id": sample.get("agreement_id"),
                    "decision": "requires_pdf_or_external_research" if sample.get("state") != "clause_found_value_extracted" else "repairable_by_context_extraction",
                    "why_blocked": ", ".join(sample.get("gate_failures") or []),
                    "specific_fix": "Resolve failure-specific context and rerun Entitlement Card gates.",
                    "would_emit_card_after_fix": False,
                    "proposed_simple_sentence": "",
                    "required_value_context": {"timeframe": "", "cohort": "", "condition": "", "unit_basis": ""},
                }
                for sample in wiki_as_list(context.get("blocked_samples"))
            ],
            "rule_updates": {
                "definition_updates": [],
                "value_rules": [],
                "exclusion_rules": [],
                "subclass_splits": [],
                "extraction_tests": [],
            },
        },
        "raw_response": "",
    }


def build_payload(
    locator_payload: dict[str, Any],
    cards_payload: dict[str, Any],
    *,
    generated_at: str,
    source_path: Path,
    cards_path: Path,
    env: dict[str, str],
    model: str,
    max_tokens: int,
    offline: bool,
    sample_limit: int,
    entitlement_ids: set[str] | None = None,
) -> dict[str, Any]:
    profiles = [
        profile for profile in wiki_as_list(locator_payload.get("profiles"))
        if isinstance(profile, dict)
        and (not entitlement_ids or clean_text(profile.get("entitlement_id")) in entitlement_ids)
    ]
    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    for index, profile in enumerate(profiles, start=1):
        context = profile_context(profile, cards_payload, sample_limit=sample_limit)
        if not context["blocked_rows"]:
            continue
        print(json.dumps({
            "event": "entitlement_card_repair_started",
            "index": index,
            "total": len(profiles),
            "entitlement_id": profile.get("entitlement_id"),
            "blocked_rows": context["blocked_rows"],
            "blocked_value_rows": context["blocked_value_rows"],
        }), file=sys.stderr, flush=True)
        repair = offline_repair(context) if offline else llm_repair(context, env=env, model=model, max_tokens=max_tokens)
        status_counts[repair["llm_status"]] += 1
        parsed = repair.get("parsed") if isinstance(repair.get("parsed"), dict) else {}
        for decision in wiki_as_list(parsed.get("row_decisions")):
            if isinstance(decision, dict):
                decision_counts[clean_text(decision.get("decision")) or "unlabelled"] += 1
        rows.append({
            "entitlement_id": context["entitlement_id"],
            "label": context["label"],
            "blocked_rows": context["blocked_rows"],
            "blocked_value_rows": context["blocked_value_rows"],
            "failure_counts": context["failure_counts"],
            "review_status_counts": context["review_status_counts"],
            "process_flag_counts": context["process_flag_counts"],
            "blocked_value_profile": context["blocked_value_profile"],
            "successful_entitlement_card_examples": context["successful_entitlement_card_examples"],
            "blocked_samples": context["blocked_samples"],
            "llm_status": repair["llm_status"],
            "llm_error": repair["error"],
            "repair_review": parsed,
            "raw_response": repair["raw_response"],
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"entitlement-card-repair-loop-{locator_payload.get('artifact_id', 'unknown')}",
        "generated_at": generated_at,
        "source_artifact": {
            "locator_artifact_id": locator_payload.get("artifact_id"),
            "locator_path": str(source_path),
            "locator_generated_at": locator_payload.get("generated_at"),
            "entitlement_cards_artifact_id": cards_payload.get("artifact_id"),
            "entitlement_cards_path": str(cards_path),
            "entitlement_cards_generated_at": cards_payload.get("generated_at"),
        },
        "method": {
            "name": "blocked_entitlement_card_llm_repair_loop",
            "scope": "Diagnoses why blocked council-entitlement rows failed the strict Entitlement Card standard and proposes source-safe repair actions.",
            "sample_policy": f"Per entitlement, send up to {sample_limit} highest-repair-value blocked non-empty rows plus failure counts and successful card examples.",
        },
        "summary": {
            "entitlements_reviewed": len(rows),
            "blocked_rows_reviewed": sum(int(row.get("blocked_rows") or 0) for row in rows),
            "blocked_value_rows_reviewed": sum(int(row.get("blocked_value_rows") or 0) for row in rows),
            "llm_statuses": dict(sorted(status_counts.items())),
            "sample_decisions": dict(sorted(decision_counts.items())),
            "failure_counts": dict(sorted(Counter(
                failure
                for row in rows
                for failure, count in row.get("failure_counts", {}).items()
                for _ in range(int(count or 0))
            ).items())),
        },
        "rows": rows,
    }


def markdown_for_payload(payload: dict[str, Any]) -> str:
    lines = [
        "# Entitlement Card Repair Loop",
        "",
        payload["method"]["scope"],
        "",
        "## Summary",
        "",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Entitlement Repair Reviews", ""])
    for row in payload["rows"]:
        review = row.get("repair_review") if isinstance(row.get("repair_review"), dict) else {}
        standard = review.get("entitlement_card_standard_review") if isinstance(review.get("entitlement_card_standard_review"), dict) else {}
        actions = wiki_as_list(review.get("repair_actions"))
        lines.extend([
            f"### {row['label']}",
            "",
            f"- LLM status: `{row['llm_status']}`",
            f"- Blocked rows: `{row['blocked_rows']}`",
            f"- Blocked value rows: `{row['blocked_value_rows']}`",
            f"- Can repair: `{standard.get('can_any_blocked_rows_become_cards', 'not_returned')}`",
            f"- Dominant blocker: {compact_text(standard.get('dominant_blocker'), limit=180)}",
            f"- First action: {compact_text((actions[0] if actions and isinstance(actions[0], dict) else {}).get('description'), limit=220)}",
            "",
        ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an LLM repair loop over rows blocked from Entitlement Card promotion.")
    parser.add_argument("--locator-input", type=Path, default=DEFAULT_LOCATOR_INPUT)
    parser.add_argument("--cards-input", type=Path, default=DEFAULT_CARDS_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model", default="")
    parser.add_argument("--max-tokens", type=int, default=3500)
    parser.add_argument("--sample-limit", type=int, default=10)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--entitlement-id", action="append", default=[], help="Limit to one or more entitlement ids.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = {**load_env_file(ROOT / ".env")}
    model = args.model or env.get("ANTHROPIC_MODEL") or env.get("EXTRACT_MODEL") or "claude-sonnet-4-20250514"
    source_path = args.locator_input.resolve()
    cards_path = args.cards_input.resolve()
    payload = build_payload(
        load_json(source_path),
        load_json(cards_path),
        generated_at=utc_now_iso(),
        source_path=source_path,
        cards_path=cards_path,
        env=env,
        model=model,
        max_tokens=args.max_tokens,
        offline=args.offline,
        sample_limit=args.sample_limit,
        entitlement_ids=set(args.entitlement_id) if args.entitlement_id else None,
    )
    output_dir = args.output_dir.resolve()
    json_path = output_dir / f"{payload['artifact_id']}.json"
    md_path = output_dir / f"{payload['artifact_id']}.md"
    write_json(json_path, payload)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.entitlement_card_repair_loop_build.v1",
        "generated_at": payload["generated_at"],
        "artifact_id": payload["artifact_id"],
        "artifact_path": str(json_path),
        "markdown_path": str(md_path),
        "summary": payload["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
