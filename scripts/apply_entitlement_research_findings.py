from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_RESEARCH_INPUT = ROOT / "wiki" / "artifacts" / "entitlement-research-loop" / "entitlement-research-loop-entitlement-locator-experiment-all-cached-79-offset-0.json"
DEFAULT_OVERRIDES_INPUT = ROOT / "data" / "review" / "entitlement_loop_rule_overrides.json"
DEFAULT_OUTPUT = DEFAULT_OVERRIDES_INPUT
SCHEMA_VERSION = "wiki.entitlement_loop_rule_overrides.v2"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wiki_as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def append_unique(existing: list[Any], additions: list[Any], *, limit: int = 12) -> list[Any]:
    output: list[Any] = []
    seen: set[str] = set()
    for value in [*existing, *additions]:
        text = str(value or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
        if len(output) >= limit:
            break
    return output


def research_rows_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("entitlement_id") or "").strip(): row
        for row in wiki_as_list(payload.get("rows"))
        if isinstance(row, dict) and str(row.get("entitlement_id") or "").strip()
    }


def apply_research_to_override(override: dict[str, Any], research_row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(override)
    boundary = dict(merged.get("classification_boundary") if isinstance(merged.get("classification_boundary"), dict) else {})
    feedback = research_row.get("feedback_actions") if isinstance(research_row.get("feedback_actions"), dict) else {}
    boundary["needs_review"] = append_unique(
        wiki_as_list(boundary.get("needs_review")),
        wiki_as_list(feedback.get("append_review_if")),
        limit=14,
    )
    merged["classification_boundary"] = boundary
    merged["value_rules"] = append_unique(
        wiki_as_list(merged.get("value_rules")),
        wiki_as_list(feedback.get("append_value_rules")),
        limit=12,
    )
    merged["research_findings"] = {
        "research_status": research_row.get("research_status"),
        "definition_candidate": research_row.get("definition_candidate"),
        "official_sources": research_row.get("official_sources") if isinstance(research_row.get("official_sources"), list) else [],
        "cross_council_value_model": research_row.get("cross_council_value_model") if isinstance(research_row.get("cross_council_value_model"), dict) else {},
        "research_risks": research_row.get("research_risks") if isinstance(research_row.get("research_risks"), list) else [],
        "source_pdf_samples": research_row.get("source_pdf_samples") if isinstance(research_row.get("source_pdf_samples"), list) else [],
    }
    merged["research_applied"] = True
    return merged


def build_payload(overrides_payload: dict[str, Any], research_payload: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    research_by_id = research_rows_by_id(research_payload)
    overrides = []
    applied = 0
    for item in wiki_as_list(overrides_payload.get("overrides")):
        if not isinstance(item, dict):
            continue
        entitlement_id = str(item.get("entitlement_id") or "").strip()
        research_row = research_by_id.get(entitlement_id)
        if research_row:
            overrides.append(apply_research_to_override(item, research_row))
            applied += 1
        else:
            overrides.append(item)
    return {
        **overrides_payload,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "research_source_artifact": {
            "artifact_id": research_payload.get("artifact_id"),
            "generated_at": research_payload.get("generated_at"),
        },
        "summary": {
            **(overrides_payload.get("summary") if isinstance(overrides_payload.get("summary"), dict) else {}),
            "research_applied": applied,
            "with_official_sources": sum(
                1
                for item in overrides
                if wiki_as_list((item.get("research_findings") or {}).get("official_sources") if isinstance(item.get("research_findings"), dict) else [])
            ),
        },
        "overrides": overrides,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply entitlement research-loop findings to learned rule overrides.")
    parser.add_argument("--research-input", type=Path, default=DEFAULT_RESEARCH_INPUT)
    parser.add_argument("--overrides-input", type=Path, default=DEFAULT_OVERRIDES_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_payload(
        load_json(args.overrides_input.resolve()),
        load_json(args.research_input.resolve()),
        generated_at=utc_now_iso(),
    )
    output_path = args.output.resolve()
    write_json(output_path, payload)
    print(json.dumps({
        "schema_version": "wiki.entitlement_research_findings_apply.v1",
        "generated_at": payload["generated_at"],
        "output_path": str(output_path),
        "summary": payload["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
