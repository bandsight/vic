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
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
DEFAULT_LOCATOR_INPUT = ROOT / "wiki" / "artifacts" / "entitlement-locator-experiment" / "entitlement-locator-experiment-all-cached-79-offset-0.json"
DEFAULT_EXEMPLAR_INPUT = ROOT / "wiki" / "artifacts" / "downstream-analysis-exemplars" / "ballarat-entitlement-benchmark-exemplar.json"
DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "feature-card-llm-review"
SCHEMA_VERSION = "wiki.feature_card_llm_review.v1"

TIMEFRAME_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("per_year", re.compile(r"\b(per\s+(?:annum|year)|each\s+year|annual(?:ly)?|yearly)\b", re.I)),
    ("per_occasion", re.compile(r"\b(per|each)\s+occasion\b|\bon\s+each\s+occasion\b", re.I)),
    ("per_week", re.compile(r"\b(per\s+week|weekly|rostered\s+week)\b", re.I)),
    ("per_day", re.compile(r"\b(per\s+day|daily)\b", re.I)),
    ("per_month", re.compile(r"\b(per\s+month|monthly)\b", re.I)),
    ("agreement_life", re.compile(r"\b(life|term)\s+of\s+(?:this\s+)?agreement\b", re.I)),
    ("once_every_period", re.compile(r"\bonce\s+every\s+\d+\s+(?:days?|weeks?|months?|years?)\b", re.I)),
    ("service_period", re.compile(r"\bafter\s+\d+\s+(?:months?|years?)\b|\b\d+\s+(?:months?|years?)\s+(?:service|continuous\s+service)\b", re.I)),
    ("duration_cap", re.compile(r"\b(up\s+to|maximum\s+of|minimum\s+of)\s+\d+", re.I)),
]

SPECIALIST_COHORT_RE = re.compile(
    r"\b(MCH|maternal\s+and\s+child\s+health|nurses?|immunisation|kindergarten|early\s+childhood|"
    r"child\s+care|teacher|physical\s+and\s+community\s+services|IT\s+helpdesk|engineer)\b",
    re.I,
)
REFERENCE_HEAVY_RE = re.compile(r"\b(NES|National\s+Employment\s+Standards|Award|Modern\s+Award|Fair\s+Work\s+Act|policy|procedure|clause\s+\d+)\b", re.I)
AMOUNT_NOT_STATED_RE = re.compile(r"\b(amount\s+not\s+stated|not\s+stated|no\s+clear\s+(?:amount|dollar)|unquantified)\b", re.I)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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


def compact_text(value: Any, *, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def wiki_as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def value_label(value: dict[str, Any]) -> str:
    label = " ".join(
        str(part or "").strip()
        for part in (value.get("value"), value.get("unit"))
        if str(part or "").strip()
    )
    return label or str(value.get("condition") or value.get("subclass_label") or "value_not_labelled")


def value_signature(value: dict[str, Any]) -> str:
    return value_label(value).lower()


def numeric_value(value: dict[str, Any]) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value.get("value") or ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def row_feature_cards(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [card for card in wiki_as_list(row.get("feature_cards")) if isinstance(card, dict)]


def row_values(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [value for value in wiki_as_list(row.get("normalised_values")) if isinstance(value, dict)]


def feature_evidence(card: dict[str, Any], row: dict[str, Any]) -> str:
    if card.get("evidence_span_text"):
        return compact_text(card.get("evidence_span_text"), limit=1000)
    candidate = row.get("best_candidate") if isinstance(row.get("best_candidate"), dict) else {}
    return compact_text(candidate.get("excerpt"), limit=1000)


def infer_timeframes(text: str, value: dict[str, Any]) -> list[str]:
    haystack = " ".join([
        str(text or ""),
        str(value.get("condition") or ""),
        str(value.get("unit") or ""),
    ])
    matches = [label for label, pattern in TIMEFRAME_PATTERNS if pattern.search(haystack)]
    return sorted(set(matches))


def context_flags(*, evidence: str, value: dict[str, Any], common_values: set[str]) -> list[str]:
    flags: list[str] = []
    label = value_signature(value)
    if label in {"available", "available candidate provision", "candidate provision", "value_not_labelled"}:
        flags.append("availability_only")
    if value.get("unit") in {"days", "weeks", "hours", "months", "AUD", "percent"} and not infer_timeframes(evidence, value):
        flags.append("timeframe_or_basis_missing")
    if not str(value.get("condition") or "").strip():
        flags.append("condition_missing")
    if SPECIALIST_COHORT_RE.search(evidence):
        flags.append("specialist_cohort_signal")
    if REFERENCE_HEAVY_RE.search(evidence):
        flags.append("reference_heavy_context")
    if AMOUNT_NOT_STATED_RE.search(evidence):
        flags.append("amount_not_stated_language")
    if common_values and label not in common_values:
        flags.append("uncommon_against_feature_set")
    return sorted(set(flags))


def exemplar_by_entitlement(exemplar_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for category in wiki_as_list(exemplar_payload.get("categories")):
        if not isinstance(category, dict):
            continue
        for entitlement in wiki_as_list(category.get("entitlements")):
            if isinstance(entitlement, dict) and entitlement.get("entitlement_id"):
                rows[str(entitlement["entitlement_id"])] = entitlement
    return rows


def value_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [value for row in rows for value in row_values(row)]
    labels = Counter(value_label(value) for value in values if value_label(value))
    units = Counter(str(value.get("unit") or "").strip() for value in values if str(value.get("unit") or "").strip())
    conditions = Counter(compact_text(value.get("condition"), limit=120) for value in values if str(value.get("condition") or "").strip())
    numeric = [number for value in values for number in [numeric_value(value)] if number is not None]
    return {
        "feature_values": len(values),
        "common_values": dict(labels.most_common(15)),
        "units": dict(units.most_common(10)),
        "conditions": dict(conditions.most_common(10)),
        "numeric_min": min(numeric) if numeric else None,
        "numeric_max": max(numeric) if numeric else None,
        "numeric_distinct_count": len(set(numeric)),
    }


def feature_card_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profile = value_profile(rows)
    common_values = {str(label).lower() for label in list(profile["common_values"].keys())[:4]}
    items: list[dict[str, Any]] = []
    for row in rows:
        values = row_values(row)
        cards = row_feature_cards(row)
        best_candidate = row.get("best_candidate") if isinstance(row.get("best_candidate"), dict) else {}
        for index, card in enumerate(cards):
            value = values[index] if index < len(values) else card.get("normalised_value") if isinstance(card.get("normalised_value"), dict) else {}
            evidence = feature_evidence(card, row)
            items.append({
                "feature_id": card.get("feature_id"),
                "council": row.get("council"),
                "agreement_id": row.get("agreement_id"),
                "page": card.get("page_number_physical") or best_candidate.get("page"),
                "value": value.get("value"),
                "unit": value.get("unit"),
                "condition": value.get("condition"),
                "subclass_label": value.get("subclass_label") or card.get("subclass_label"),
                "benchmark_value": value.get("benchmark_value") or card.get("benchmark_value"),
                "timeframe_signals": infer_timeframes(evidence, value),
                "context_flags": context_flags(evidence=evidence, value=value, common_values=common_values),
                "evidence": evidence,
            })
    return items


def choose_review_samples(items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    if len(items) <= limit:
        return items
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for item in items:
        flags = item.get("context_flags") or []
        score = 0
        score += 8 * int("timeframe_or_basis_missing" in flags)
        score += 7 * int("availability_only" in flags)
        score += 6 * int("specialist_cohort_signal" in flags)
        score += 5 * int("reference_heavy_context" in flags)
        score += 4 * int("uncommon_against_feature_set" in flags)
        score += 3 * int("condition_missing" in flags)
        scored.append((-score, str(item.get("council") or ""), item))
    selected: list[dict[str, Any]] = []
    seen_features: set[str] = set()
    for _score, _council, item in sorted(scored, key=lambda row: (row[0], row[1], str(row[2].get("feature_id") or ""))):
        feature_id = str(item.get("feature_id") or "")
        if feature_id in seen_features:
            continue
        selected.append(item)
        seen_features.add(feature_id)
        if len(selected) >= limit:
            break
    return selected


def profile_context(profile: dict[str, Any], exemplar: dict[str, Any]) -> dict[str, Any]:
    rows = [
        row for row in wiki_as_list(profile.get("target_rows"))
        if isinstance(row, dict) and row.get("value_extracted") and row_feature_cards(row)
    ]
    cards = feature_card_items(rows)
    flag_counts = Counter(flag for item in cards for flag in wiki_as_list(item.get("context_flags")))
    review_samples = choose_review_samples(cards, limit=10)
    contract = profile.get("rule_contract") if isinstance(profile.get("rule_contract"), dict) else {}
    mapping = exemplar.get("semantic_mapping") if isinstance(exemplar.get("semantic_mapping"), dict) else {}
    quantification = mapping.get("quantification_semantics") if isinstance(mapping.get("quantification_semantics"), dict) else {}
    comparator = mapping.get("comparator_semantics") if isinstance(mapping.get("comparator_semantics"), dict) else {}
    return {
        "entitlement_id": profile.get("entitlement_id"),
        "label": profile.get("label"),
        "definition": contract.get("definition") or profile.get("definition") or "",
        "taxonomy_path": contract.get("taxonomy_path") or [],
        "output_contract": profile.get("output_contract") or contract.get("output_contract") or {},
        "classification_boundary": contract.get("classification_boundary") or {},
        "accepted_subclasses": contract.get("accepted_subclasses") or [],
        "exemplar_quantification_type": quantification.get("quantification_type"),
        "exemplar_comparator_quantum_signals": quantification.get("comparator_quantum_signals") or [],
        "exemplar_presence_mix": comparator.get("presence_mix") or {},
        "green_feature_cells": len(rows),
        "feature_cards": len(cards),
        "observed_value_profile": value_profile(rows),
        "context_flag_counts": dict(sorted(flag_counts.items())),
        "review_samples": review_samples,
    }


SYSTEM_PROMPT = """You are an expert Australian local-government enterprise agreement entitlement reviewer.
You are reviewing feature cards extracted from agreement source text.

Your job is not to admire the extraction. Your job is to decide whether the card values make sense.
Numbers only matter when the definition, timeframe, cohort, unit basis, condition, and source context are clear.

Return only valid JSON. No markdown. No commentary.
"""


def user_prompt(context: dict[str, Any]) -> str:
    return json.dumps({
        "task": {
            "review_dimensions": [
                "Does the current definition ask the right entitlement question?",
                "Do the feature cards fit the inclusion boundary, or should some be excluded/split?",
                "For numeric values, what timeframe or basis is required before the value is meaningful?",
                "What normal value or normal value range makes sense across councils?",
                "Which sample feature cards need review, correction, subclassing, or promotion?",
            ],
            "decision_labels": [
                "promote_candidate",
                "needs_timeframe_or_basis",
                "needs_scope_or_cohort_review",
                "wrong_entitlement_or_noise",
                "split_subclass",
                "amount_not_stated",
                "needs_external_or_pdf_research",
            ],
            "required_json_shape": {
                "definition_review": {
                    "status": "good|tighten|split|research_first",
                    "industry_standard_definition": "string",
                    "inclusions": ["string"],
                    "exclusions": ["string"],
                    "review_if": ["string"],
                },
                "quantum_review": {
                    "normal_value_model": "string",
                    "required_context_fields": ["timeframe", "cohort", "unit_basis", "condition"],
                    "timeframe_rules": ["string"],
                    "unit_normalisation_rules": ["string"],
                    "cohort_scope_rules": ["string"],
                },
                "alignment_review": {
                    "overall_status": "aligned|mixed|weak|cannot_tell",
                    "comparator_alignment_notes": "string",
                    "suspicious_patterns": ["string"],
                    "missing_context_patterns": ["string"],
                },
                "feature_card_decisions": [
                    {
                        "feature_id": "string",
                        "decision": "one decision label",
                        "reason": "string",
                        "value_interpretation": "string",
                        "required_fix": "string",
                    }
                ],
                "rule_updates": {
                    "definition_updates": ["string"],
                    "value_rules": ["string"],
                    "subclass_splits": ["string"],
                    "promotion_gate": "string",
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


def llm_review(context: dict[str, Any], *, env: dict[str, str], model: str, max_tokens: int) -> dict[str, Any]:
    try:
        import anthropic
    except ImportError as exc:
        return {
            "llm_status": "blocked",
            "error": f"anthropic package missing: {exc}",
            "parsed": {},
            "raw_response": "",
        }
    api_key = env.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "llm_status": "blocked",
            "error": "ANTHROPIC_API_KEY not set",
            "parsed": {},
            "raw_response": "",
        }
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
        return {
            "llm_status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "parsed": {},
            "raw_response": "",
        }
    parsed, parse_error = parse_json_response(raw)
    return {
        "llm_status": "parsed" if parsed else "parse_error",
        "error": parse_error,
        "parsed": parsed,
        "raw_response": raw,
    }


def offline_review(context: dict[str, Any]) -> dict[str, Any]:
    flags = context.get("context_flag_counts") or {}
    missing_context = [flag for flag, count in flags.items() if count]
    return {
        "llm_status": "offline_deterministic",
        "error": "",
        "parsed": {
            "definition_review": {
                "status": "tighten" if missing_context else "good",
                "industry_standard_definition": context.get("definition") or "",
                "inclusions": wiki_as_list((context.get("classification_boundary") or {}).get("included"))[:5],
                "exclusions": wiki_as_list((context.get("classification_boundary") or {}).get("excluded"))[:5],
                "review_if": wiki_as_list((context.get("classification_boundary") or {}).get("needs_review"))[:5],
            },
            "quantum_review": {
                "normal_value_model": "Use observed value distribution only after timeframe, cohort, unit basis, and condition are present.",
                "required_context_fields": ["timeframe", "cohort", "unit_basis", "condition", "source_clause"],
                "timeframe_rules": ["Do not compare days/weeks/hours/dollars unless the per-year/per-occasion/per-week basis is known."],
                "unit_normalisation_rules": ["Keep amount-not-stated and availability-only separate from numeric values."],
                "cohort_scope_rules": ["Flag specialist cohort language before treating the value as standard employee coverage."],
            },
            "alignment_review": {
                "overall_status": "mixed" if missing_context else "aligned",
                "comparator_alignment_notes": "Deterministic fallback; LLM review was not executed.",
                "suspicious_patterns": missing_context,
                "missing_context_patterns": missing_context,
            },
            "feature_card_decisions": [
                {
                    "feature_id": sample.get("feature_id"),
                    "decision": "needs_timeframe_or_basis" if sample.get("context_flags") else "promote_candidate",
                    "reason": ", ".join(sample.get("context_flags") or ["representative source-backed feature card"]),
                    "value_interpretation": value_label(sample),
                    "required_fix": "Resolve context flags before promotion." if sample.get("context_flags") else "Human validation before governance promotion.",
                }
                for sample in wiki_as_list(context.get("review_samples"))
            ],
            "rule_updates": {
                "definition_updates": [],
                "value_rules": ["Require timeframe, cohort, condition, and source clause context before numeric comparison."],
                "subclass_splits": [],
                "promotion_gate": "llm_review_required",
            },
        },
        "raw_response": "",
    }


def build_payload(
    locator_payload: dict[str, Any],
    exemplar_payload: dict[str, Any],
    *,
    generated_at: str,
    source_path: Path,
    env: dict[str, str],
    model: str,
    max_tokens: int,
    offline: bool,
    entitlement_ids: set[str] | None = None,
) -> dict[str, Any]:
    exemplar_rows = exemplar_by_entitlement(exemplar_payload)
    profiles = [
        profile for profile in wiki_as_list(locator_payload.get("profiles"))
        if isinstance(profile, dict) and (not entitlement_ids or str(profile.get("entitlement_id")) in entitlement_ids)
    ]
    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    for index, profile in enumerate(profiles, start=1):
        context = profile_context(profile, exemplar_rows.get(str(profile.get("entitlement_id")), {}))
        print(json.dumps({
            "event": "feature_card_llm_review_started",
            "index": index,
            "total": len(profiles),
            "entitlement_id": profile.get("entitlement_id"),
            "label": profile.get("label"),
            "feature_cards": context["feature_cards"],
        }), file=sys.stderr, flush=True)
        review = offline_review(context) if offline else llm_review(context, env=env, model=model, max_tokens=max_tokens)
        status_counts[review["llm_status"]] += 1
        parsed = review.get("parsed") if isinstance(review.get("parsed"), dict) else {}
        for decision in wiki_as_list(parsed.get("feature_card_decisions")):
            if isinstance(decision, dict):
                decision_counts[str(decision.get("decision") or "unlabelled")] += 1
        rows.append({
            "entitlement_id": context["entitlement_id"],
            "label": context["label"],
            "green_feature_cards": context["feature_cards"],
            "observed_value_profile": context["observed_value_profile"],
            "context_flag_counts": context["context_flag_counts"],
            "review_samples": context["review_samples"],
            "llm_status": review["llm_status"],
            "llm_error": review["error"],
            "llm_review": parsed,
            "raw_response": review["raw_response"],
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"feature-card-llm-review-{locator_payload.get('artifact_id', 'unknown')}",
        "generated_at": generated_at,
        "source_artifact": {
            "locator_artifact_id": locator_payload.get("artifact_id"),
            "path": str(source_path),
            "generated_at": locator_payload.get("generated_at"),
        },
        "method": {
            "name": "feature_card_definition_quantum_llm_review",
            "model": model if not offline else "offline_deterministic",
            "scope": (
                "Reviews green feature cards for definition fit, quantum/timeframe context, cohort scope, "
                "cross-council alignment, and promotion readiness."
            ),
            "sample_policy": "Each entitlement sends the highest-risk feature-card samples plus observed value distributions to the LLM.",
        },
        "summary": {
            "entitlements_reviewed": len(rows),
            "green_feature_cards_in_scope": sum(int(row.get("green_feature_cards") or 0) for row in rows),
            "llm_statuses": dict(sorted(status_counts.items())),
            "sample_decisions": dict(sorted(decision_counts.items())),
            "context_flags": dict(sorted(Counter(
                flag
                for row in rows
                for flag, count in (row.get("context_flag_counts") or {}).items()
                for _ in range(int(count or 0))
            ).items())),
        },
        "rows": rows,
    }


def markdown_for_payload(payload: dict[str, Any]) -> str:
    lines = [
        "# Feature Card LLM Review",
        "",
        payload["method"]["scope"],
        "",
        "## Summary",
        "",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Entitlement Reviews", ""])
    for row in payload["rows"]:
        review = row.get("llm_review") if isinstance(row.get("llm_review"), dict) else {}
        definition = review.get("definition_review") if isinstance(review.get("definition_review"), dict) else {}
        quantum = review.get("quantum_review") if isinstance(review.get("quantum_review"), dict) else {}
        alignment = review.get("alignment_review") if isinstance(review.get("alignment_review"), dict) else {}
        rule_updates = review.get("rule_updates") if isinstance(review.get("rule_updates"), dict) else {}
        lines.extend([
            f"### {row['label']}",
            "",
            f"- LLM status: `{row['llm_status']}`",
            f"- Green feature cards: `{row['green_feature_cards']}`",
            f"- Definition status: `{definition.get('status', 'not_returned')}`",
            f"- Alignment: `{alignment.get('overall_status', 'not_returned')}`",
            f"- Normal value model: {compact_text(quantum.get('normal_value_model'), limit=260)}",
            f"- Promotion gate: {compact_text(rule_updates.get('promotion_gate'), limit=220)}",
            "",
        ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an LLM review over entitlement feature cards for definition and quantum sense-making.")
    parser.add_argument("--input", type=Path, default=DEFAULT_LOCATOR_INPUT)
    parser.add_argument("--exemplar", type=Path, default=DEFAULT_EXEMPLAR_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model", default="")
    parser.add_argument("--max-tokens", type=int, default=3500)
    parser.add_argument("--offline", action="store_true", help="Build the deterministic review pack without calling the LLM.")
    parser.add_argument("--entitlement-id", action="append", default=[], help="Limit to one or more entitlement ids.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = {**load_env_file(ROOT / ".env")}
    model = args.model or env.get("ANTHROPIC_MODEL") or env.get("EXTRACT_MODEL") or "claude-sonnet-4-20250514"
    source_path = args.input.resolve()
    payload = build_payload(
        load_json(source_path),
        load_json(args.exemplar.resolve()),
        generated_at=utc_now_iso(),
        source_path=source_path,
        env=env,
        model=model,
        max_tokens=args.max_tokens,
        offline=args.offline,
        entitlement_ids=set(args.entitlement_id) if args.entitlement_id else None,
    )
    output_dir = args.output_dir.resolve()
    json_path = output_dir / f"{payload['artifact_id']}.json"
    md_path = output_dir / f"{payload['artifact_id']}.md"
    write_json(json_path, payload)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.feature_card_llm_review_build.v1",
        "generated_at": payload["generated_at"],
        "artifact_id": payload["artifact_id"],
        "artifact_path": str(json_path),
        "markdown_path": str(md_path),
        "summary": payload["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
