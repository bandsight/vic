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
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from benchmarking_data_factory.workbench.wiki_layer import source_container_type_for_text  # noqa: E402


DEFAULT_LOCATOR_INPUT = ROOT / "wiki" / "artifacts" / "entitlement-locator-experiment" / "entitlement-locator-experiment-all-cached-79-offset-0.json"
DEFAULT_RULE_OVERRIDES_INPUT = ROOT / "data" / "review" / "entitlement_loop_rule_overrides.json"
DEFAULT_DOCUMENT_MAP_DIR = ROOT / "wiki" / "document-maps"
DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "spine-clause-improvement"
SCHEMA_VERSION = "wiki.spine_clause_improvement_pass.v1"
SOURCE_CONTAINER_CACHE: dict[str, str] = {}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wiki_as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def compact_preview(value: Any, *, limit: int = 340) -> str:
    text = clean_text(value)
    return text if len(text) <= limit else f"{text[:limit].rstrip()}..."


def document_map_index(document_map_dir: Path) -> dict[str, dict[str, Any]]:
    maps: dict[str, dict[str, Any]] = {}
    if not document_map_dir.exists():
        return maps
    for path in sorted(document_map_dir.glob("*.json")):
        try:
            payload = load_json(path)
        except json.JSONDecodeError:
            continue
        agreement_id = clean_text(payload.get("agreement_id") or path.stem).lower()
        if agreement_id:
            maps[agreement_id] = payload | {"_path": str(path)}
    return maps


def rule_override_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        clean_text(item.get("entitlement_id")): item
        for item in wiki_as_list(payload.get("overrides"))
        if isinstance(item, dict) and clean_text(item.get("entitlement_id"))
    }


def locator_profiles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [profile for profile in wiki_as_list(payload.get("profiles")) if isinstance(profile, dict)]


def target_agreements(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in wiki_as_list(payload.get("target_comparator_set")) if isinstance(row, dict)]


def first_locator_rows_by_agreement(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for profile in locator_profiles(payload):
        for row in wiki_as_list(profile.get("target_rows")):
            if not isinstance(row, dict):
                continue
            agreement_id = clean_text(row.get("agreement_id")).lower()
            if agreement_id and agreement_id not in rows:
                rows[agreement_id] = row
    return rows


def agreement_diagnostics(locator_payload: dict[str, Any], document_maps: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    first_rows = first_locator_rows_by_agreement(locator_payload)
    diagnostics: list[dict[str, Any]] = []
    backfill_queue: list[dict[str, Any]] = []
    cache_repair_queue: list[dict[str, Any]] = []
    for target in target_agreements(locator_payload):
        agreement_id = clean_text(target.get("agreement_id")).lower()
        first_row = first_rows.get(agreement_id, {})
        page_count = int(first_row.get("page_count") or 0)
        document_map = document_maps.get(agreement_id)
        map_summary = document_map.get("summary") if isinstance(document_map, dict) and isinstance(document_map.get("summary"), dict) else {}
        status = "ready"
        if page_count <= 0:
            status = "source_cache_repair_needed"
            cache_repair_queue.append({
                "agreement_id": agreement_id,
                "council": target.get("council"),
                "reason": "No cached page text was available to build the document spine.",
            })
        elif not document_map:
            status = "document_map_backfill_needed"
            backfill_queue.append({
                "agreement_id": agreement_id,
                "council": target.get("council"),
                "page_count": page_count,
                "reason": "Cached source pages exist, but wiki/document-maps has no spine map for this agreement.",
            })
        diagnostics.append({
            "agreement_id": agreement_id,
            "council": target.get("council"),
            "agreement_name": target.get("agreement_name"),
            "page_count": page_count,
            "source_spine_ready": page_count > 0,
            "document_map_ready": bool(document_map),
            "status": status,
            "document_map_summary": {
                "pages_scanned": map_summary.get("pages_scanned"),
                "sections_detected": map_summary.get("sections_detected"),
                "headings_detected": map_summary.get("headings_detected"),
                "page_role_counts": map_summary.get("page_role_counts") if isinstance(map_summary.get("page_role_counts"), dict) else {},
                "learning_backlog_items": map_summary.get("learning_backlog_items"),
            },
        })
    return diagnostics, {
        "document_map_backfill_queue": backfill_queue,
        "source_cache_repair_queue": cache_repair_queue,
    }


def card_container_type(card: dict[str, Any]) -> str:
    explicit = clean_text(card.get("source_container_type"))
    if explicit and explicit != "clause_or_clause_window":
        return explicit
    text = clean_text(card.get("raw_clause_text"))
    cache_key = clean_text(card.get("raw_clause_text_hash")) or text[:500]
    if cache_key not in SOURCE_CONTAINER_CACHE:
        SOURCE_CONTAINER_CACHE[cache_key] = source_container_type_for_text(text)
    return SOURCE_CONTAINER_CACHE[cache_key]


def card_process_flags(card: dict[str, Any]) -> list[str]:
    flags = [clean_text(item) for item in wiki_as_list(card.get("process_rule_flags")) if clean_text(item)]
    if flags:
        return sorted(set(flags))
    inferred: list[str] = []
    container = card_container_type(card)
    if "table_of_contents" in container:
        inferred.append("routing_only_table_of_contents")
    if "approval_decision" in container:
        inferred.append("front_matter_context_not_clause_source")
    if wiki_as_list(card.get("reference_links")):
        inferred.append("reference_heavy_context")
    if clean_text(card.get("review_status")) == "needs_quantification_review":
        inferred.append("quantification_or_amount_not_stated_review")
    return sorted(set(inferred))


def sample_clause_row(profile: dict[str, Any], row: dict[str, Any], *, reason: str) -> dict[str, Any]:
    candidate = row.get("best_candidate") if isinstance(row.get("best_candidate"), dict) else {}
    card = next((item for item in wiki_as_list(row.get("clause_cards")) if isinstance(item, dict)), {})
    return {
        "entitlement_id": profile.get("entitlement_id"),
        "label": profile.get("label"),
        "council": row.get("council"),
        "agreement_id": row.get("agreement_id"),
        "state": row.get("state"),
        "reason": reason,
        "page": candidate.get("page") or card.get("page_number_physical"),
        "heading": candidate.get("heading") or (wiki_as_list(card.get("heading_path"))[:1] or [""])[0],
        "blocker_signals": wiki_as_list(candidate.get("blocker_signals"))[:8],
        "process_rule_flags": card_process_flags(card) if card else [],
        "source_container_type": card_container_type(card) if card else "",
        "evidence": compact_preview(card.get("raw_clause_text") or candidate.get("excerpt")),
    }


def clause_action(counts: Counter[str], target_count: int, feature_cells: int) -> str:
    clause_only = counts["clause_found_value_missing"]
    blocked = counts["adjacent_or_blocked_clause_found"]
    no_candidate = counts["no_candidate_clause_found"]
    if target_count and feature_cells == target_count:
        return "validate_representative_feature_cards"
    if clause_only >= max(2, target_count // 5):
        return "resolve_clause_only_values_or_amount_not_stated"
    if blocked >= max(2, target_count // 5):
        return "tighten_scope_boundaries_and_source_container_roles"
    if no_candidate >= max(2, target_count // 4):
        return "expand_aliases_using_spine_language_and_research"
    if feature_cells:
        return "review_partial_feature_set_before_promotion"
    return "definition_and_source_research_needed"


def clause_diagnostics(locator_payload: dict[str, Any], rule_overrides: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    container_counts: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    queues: dict[str, list[dict[str, Any]]] = {
        "clause_quantification_queue": [],
        "blocked_clause_review_queue": [],
        "routing_or_front_matter_review_queue": [],
    }
    for profile in locator_profiles(locator_payload):
        target_rows = [row for row in wiki_as_list(profile.get("target_rows")) if isinstance(row, dict)]
        counts = Counter(clean_text(row.get("state")) or "unknown" for row in target_rows)
        state_counts.update(counts)
        feature_cells = sum(1 for row in target_rows if wiki_as_list(row.get("feature_cards")))
        clause_cells = sum(1 for row in target_rows if wiki_as_list(row.get("clause_cards")))
        for row in target_rows:
            cards = [card for card in wiki_as_list(row.get("clause_cards")) if isinstance(card, dict)]
            for card in cards:
                container = card_container_type(card)
                container_counts[container] += 1
                flags = card_process_flags(card)
                flag_counts.update(flags)
                if (
                    {"routing_only_table_of_contents", "front_matter_context_not_clause_source"} & set(flags)
                    and len(queues["routing_or_front_matter_review_queue"]) < 24
                ):
                    queues["routing_or_front_matter_review_queue"].append(sample_clause_row(profile, row, reason="routing_or_front_matter_signal"))
            if row.get("state") == "clause_found_value_missing" and len(queues["clause_quantification_queue"]) < 30:
                queues["clause_quantification_queue"].append(sample_clause_row(profile, row, reason="clause_found_without_feature_value"))
            if row.get("state") == "adjacent_or_blocked_clause_found" and len(queues["blocked_clause_review_queue"]) < 30:
                queues["blocked_clause_review_queue"].append(sample_clause_row(profile, row, reason="blocked_or_adjacent_clause"))
        entitlement_id = clean_text(profile.get("entitlement_id"))
        override = rule_overrides.get(entitlement_id, {})
        rows.append({
            "entitlement_id": entitlement_id,
            "label": profile.get("label"),
            "target_councils": len(target_rows),
            "clause_card_cells": clause_cells,
            "feature_card_cells": feature_cells,
            "clause_only_cells": counts["clause_found_value_missing"],
            "blocked_or_adjacent_cells": counts["adjacent_or_blocked_clause_found"],
            "no_candidate_cells": counts["no_candidate_clause_found"],
            "state_counts": dict(sorted(counts.items())),
            "learned_rule_ready": bool(override),
            "research_applied": bool(override.get("research_applied")),
            "next_process_action": clause_action(counts, len(target_rows), feature_cells),
        })
    rows.sort(key=lambda item: (item["next_process_action"], str(item.get("label") or "")))
    return rows, {
        **queues,
        "source_container_type_counts": dict(sorted(container_counts.items())),
        "process_rule_flag_counts": dict(sorted(flag_counts.items())),
        "state_counts": dict(sorted(state_counts.items())),
    }


def build_payload(
    locator_payload: dict[str, Any],
    *,
    document_map_dir: Path = DEFAULT_DOCUMENT_MAP_DIR,
    rule_overrides_payload: dict[str, Any] | None = None,
    generated_at: str,
    source_path: Path,
) -> dict[str, Any]:
    document_maps = document_map_index(document_map_dir)
    rules = rule_override_index(rule_overrides_payload or {})
    agreements, spine_queues = agreement_diagnostics(locator_payload, document_maps)
    entitlements, clause_queues = clause_diagnostics(locator_payload, rules)
    summary = {
        "target_agreements": len(agreements),
        "source_spines_ready": sum(1 for row in agreements if row["source_spine_ready"]),
        "document_maps_ready": sum(1 for row in agreements if row["document_map_ready"]),
        "document_map_backfill_needed": len(spine_queues["document_map_backfill_queue"]),
        "source_cache_repair_needed": len(spine_queues["source_cache_repair_queue"]),
        "entitlements": len(entitlements),
        "test_cells": sum(int(row.get("target_councils") or 0) for row in entitlements),
        "clause_card_cells": sum(int(row.get("clause_card_cells") or 0) for row in entitlements),
        "feature_card_cells": sum(int(row.get("feature_card_cells") or 0) for row in entitlements),
        "clause_only_cells": sum(int(row.get("clause_only_cells") or 0) for row in entitlements),
        "blocked_or_adjacent_cells": sum(int(row.get("blocked_or_adjacent_cells") or 0) for row in entitlements),
        "no_candidate_cells": sum(int(row.get("no_candidate_cells") or 0) for row in entitlements),
        "entitlements_with_learned_rules": sum(1 for row in entitlements if row.get("learned_rule_ready")),
        "entitlements_with_research_applied": sum(1 for row in entitlements if row.get("research_applied")),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"spine-clause-improvement-{locator_payload.get('artifact_id', 'unknown')}",
        "generated_at": generated_at,
        "source_artifact": {
            "locator_artifact_id": locator_payload.get("artifact_id"),
            "path": str(source_path),
            "generated_at": locator_payload.get("generated_at"),
        },
        "method": {
            "name": "document_spine_and_clause_process_improvement",
            "scope": (
                "Turns the all-council entitlement run into spine and clause process repairs: map coverage, "
                "source-role routing, clause-only quantification queues, blocked-scope queues, and promotion rules."
            ),
        },
        "summary": summary,
        "document_spine": {
            "agreements": agreements,
            **spine_queues,
        },
        "clause_process": {
            "entitlements": entitlements,
            **clause_queues,
        },
    }


def markdown_for_payload(payload: dict[str, Any]) -> str:
    lines = [
        "# Spine Clause Improvement Pass",
        "",
        payload["method"]["scope"],
        "",
        "## Summary",
        "",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Top Process Actions", ""])
    for row in payload["clause_process"]["entitlements"][:12]:
        lines.append(
            f"- {row['label']}: `{row['next_process_action']}` "
            f"(feature {row['feature_card_cells']}/{row['target_councils']}, clause-only {row['clause_only_cells']})"
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a spine/clause process improvement pass from the locator run.")
    parser.add_argument("--locator-input", type=Path, default=DEFAULT_LOCATOR_INPUT)
    parser.add_argument("--rule-overrides-input", type=Path, default=DEFAULT_RULE_OVERRIDES_INPUT)
    parser.add_argument("--document-map-dir", type=Path, default=DEFAULT_DOCUMENT_MAP_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    locator_path = args.locator_input.resolve()
    overrides_path = args.rule_overrides_input.resolve()
    overrides_payload = load_json(overrides_path) if overrides_path.exists() else {}
    payload = build_payload(
        load_json(locator_path),
        document_map_dir=args.document_map_dir.resolve(),
        rule_overrides_payload=overrides_payload,
        generated_at=utc_now_iso(),
        source_path=locator_path,
    )
    output_dir = args.output_dir.resolve()
    json_path = output_dir / f"{payload['artifact_id']}.json"
    md_path = output_dir / f"{payload['artifact_id']}.md"
    write_json(json_path, payload)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.spine_clause_improvement_build.v1",
        "generated_at": payload["generated_at"],
        "artifact_id": payload["artifact_id"],
        "artifact_path": str(json_path),
        "markdown_path": str(md_path),
        "summary": payload["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
