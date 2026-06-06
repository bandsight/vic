from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLD = ROOT / "data" / "review" / "entitlement_locator_gold_v1.jsonl"
DEFAULT_QA_PACK = ROOT / "wiki" / "artifacts" / "entitlement-locator-qa-review" / "locator-qa-review-entitlement-locator-experiment-next-52-offset-0.json"
DEFAULT_SUGGESTIONS = ROOT / "data" / "review" / "entitlement_locator_codex_suggestions_v1.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "entitlement-locator-human-review"
WORKSHEET_SCHEMA_VERSION = "review.entitlement_locator_human_review_worksheet.v1"

HUMAN_REVIEW_COLUMNS = [
    "human_clause_locator_result",
    "human_span_result",
    "human_presence_result",
    "human_value_result",
    "human_expected_value",
    "human_expected_unit",
    "human_expected_scope",
    "human_cross_reference_result",
    "human_review_decision",
    "human_review_notes",
    "human_governance_result",
]

CSV_COLUMNS = [
    "gold_review_id",
    "council",
    "agreement_id",
    "entitlement_label",
    "sample_reason",
    "machine_cell_status",
    "machine_presence_status",
    "machine_value_status",
    "machine_failure_reason",
    "codex_advisory_label",
    "codex_suggested_review_decision",
    "codex_suggested_provision_present",
    "codex_suggested_quantified_value_found",
    "codex_suggested_value",
    "codex_suggested_unit",
    "codex_suggested_scope",
    "codex_suggested_cross_reference_review",
    "codex_confidence",
    "codex_risk_flags",
    "clause_card_id",
    "feature_card_id",
    "page",
    "block_id",
    "parser_used",
    "parser_version",
    "raw_clause_text_hash",
    "evidence_span_text_hash",
    "evidence_span_text",
    "reference_link_count",
    "reference_links_summary",
    "blocker_signals",
    "failure_reason",
    *HUMAN_REVIEW_COLUMNS,
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def short_text(text: Any, limit: int = 240) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."


def qa_detail_index(qa_pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for profile in qa_pack.get("profiles", []):
        for row in profile.get("details", []):
            review_id = f"locator_gold_v1_{slug(row.get('council', ''))}_{slug(row.get('entitlement_key', ''))}"
            index[review_id] = row
    return index


def slug(value: Any) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def suggestion_index(suggestions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("gold_review_id")): row for row in suggestions}


def reference_links_summary(links: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for link in links[:5]:
        target = link.get("to_clause") or link.get("to_schedule") or link.get("to_external") or ""
        relationship = link.get("relationship", "")
        parts.append(f"{relationship}:{target}" if target else relationship)
    suffix = f"; +{len(links) - 5} more" if len(links) > 5 else ""
    return "; ".join(parts) + suffix


def worksheet_row(gold: dict[str, Any], qa: dict[str, Any], suggestion: dict[str, Any] | None) -> dict[str, Any]:
    suggestion = suggestion or {}
    evidence = suggestion.get("evidence_summary") or {}
    links = gold.get("reference_links") or qa.get("reference_links") or []
    row = {
        "gold_review_id": gold.get("review_id", ""),
        "council": gold.get("council", ""),
        "agreement_id": gold.get("agreement_id", ""),
        "entitlement_key": gold.get("entitlement_key", ""),
        "entitlement_label": gold.get("entitlement_label", ""),
        "sample_reason": gold.get("sample_reason", ""),
        "machine_cell_status": gold.get("machine_cell_status", ""),
        "machine_clause_found": gold.get("machine_clause_found", False),
        "machine_feature_found": gold.get("machine_feature_found", False),
        "machine_provision_present": gold.get("machine_provision_present", False),
        "machine_quantified_value_found": gold.get("machine_quantified_value_found", False),
        "machine_presence_status": gold.get("machine_presence_status", ""),
        "machine_value_status": gold.get("machine_value_status", ""),
        "machine_failure_reason": gold.get("machine_failure_reason", ""),
        "codex_advisory_label": "advisory_only_human_confirmation_required" if suggestion else "missing_suggestion",
        "codex_suggestion_id": suggestion.get("suggestion_id", ""),
        "codex_suggested_review_decision": suggestion.get("suggested_review_decision", ""),
        "codex_suggested_provision_present": suggestion.get("suggested_expected_provision_present", ""),
        "codex_suggested_quantified_value_found": suggestion.get("suggested_expected_quantified_value_found", ""),
        "codex_suggested_value": suggestion.get("suggested_value", ""),
        "codex_suggested_unit": suggestion.get("suggested_unit", ""),
        "codex_suggested_scope": suggestion.get("suggested_scope", ""),
        "codex_suggested_cross_reference_review": suggestion.get("suggested_cross_reference_review", ""),
        "codex_confidence": suggestion.get("confidence", ""),
        "codex_reasons": suggestion.get("reasons", []),
        "codex_risk_flags": suggestion.get("risk_flags", []),
        "codex_requires_human_confirmation": suggestion.get("requires_human_confirmation", ""),
        "clause_card_id": gold.get("clause_card_id", "") or evidence.get("clause_card_id", ""),
        "feature_card_id": gold.get("feature_card_id", "") or evidence.get("feature_card_id", ""),
        "feature_card_ids": gold.get("feature_card_ids", []) or evidence.get("feature_card_ids", []),
        "page": gold.get("page"),
        "block_id": gold.get("block_id", ""),
        "parser_used": gold.get("parser_used", ""),
        "parser_version": gold.get("parser_version", ""),
        "raw_clause_text_hash": gold.get("raw_clause_text_hash", ""),
        "evidence_span_text_hash": gold.get("evidence_span_text_hash", ""),
        "evidence_span_text": gold.get("evidence_span_text", "") or evidence.get("evidence_span_text", ""),
        "reference_link_count": gold.get("reference_link_count", 0),
        "reference_links_summary": reference_links_summary(links),
        "reference_links": links,
        "blocker_signals": qa.get("blocker_signals", []),
        "failure_reason": qa.get("failure_reason", gold.get("machine_failure_reason", "")),
    }
    for column in HUMAN_REVIEW_COLUMNS:
        row[column] = ""
    return row


def worksheet_rows(gold_rows: list[dict[str, Any]], qa_pack: dict[str, Any], suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    qa_index = qa_detail_index(qa_pack)
    suggestion_by_review_id = suggestion_index(suggestions)
    rows = [
        worksheet_row(
            gold,
            qa_index.get(str(gold.get("review_id")), {}),
            suggestion_by_review_id.get(str(gold.get("review_id"))),
        )
        for gold in gold_rows
    ]
    return sorted(rows, key=lambda item: (str(item["council"]), str(item["entitlement_label"])))


def validate_worksheet(rows: list[dict[str, Any]], gold_rows: list[dict[str, Any]], suggestions: list[dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    gold_ids = {str(row.get("review_id")) for row in gold_rows}
    suggestion_ids = {str(row.get("gold_review_id")) for row in suggestions}
    row_ids = {str(row.get("gold_review_id")) for row in rows}
    if len(rows) != len(gold_rows):
        errors.append({"code": "worksheet_row_count_mismatch", "message": f"worksheet rows {len(rows)} != gold rows {len(gold_rows)}"})
    missing = sorted(gold_ids - row_ids)
    if missing:
        errors.append({"code": "worksheet_missing_gold_rows", "message": ", ".join(missing[:5])})
    missing_suggestions = sorted(gold_ids - suggestion_ids)
    if missing_suggestions:
        errors.append({"code": "suggestions_missing_gold_rows", "message": ", ".join(missing_suggestions[:5])})
    for row in rows:
        review_id = str(row.get("gold_review_id"))
        if row.get("codex_advisory_label") != "advisory_only_human_confirmation_required":
            errors.append({"code": "codex_suggestion_not_marked_advisory", "review_id": review_id})
        for column in HUMAN_REVIEW_COLUMNS:
            if row.get(column) not in {"", None}:
                errors.append({"code": "human_review_field_prefilled", "review_id": review_id, "field": column})
        if row.get("machine_cell_status") in {"clause_value", "clause_only"} and not row.get("evidence_span_text"):
            errors.append({"code": "source_row_missing_evidence_span", "review_id": review_id})
        if row.get("entitlement_key") == "additional_annual_leave":
            if row.get("machine_cell_status") not in {"blocked", "not_found", "adjacent_candidate"}:
                errors.append({"code": "additional_annual_not_conservative_target", "review_id": review_id})
            if row.get("human_governance_result"):
                errors.append({"code": "additional_annual_prefilled_governance", "review_id": review_id})
    return errors


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: csv_value(row.get(column, "")) for column in CSV_COLUMNS})


def markdown_for_rows(rows: list[dict[str, Any]], *, generated_at: str) -> str:
    lines = [
        "# Entitlement Locator Human Review Worksheet",
        "",
        "This worksheet is for human semantic adjudication. Codex suggestions are advisory only and require human confirmation.",
        "",
        f"Generated at: `{generated_at}`",
        f"Rows: `{len(rows)}`",
        "",
        "## Review Dimensions",
        "",
        "- Clause locator correctness",
        "- Evidence span correctness",
        "- Provision presence correctness",
        "- Quantified value correctness",
        "- Scope/reference correctness",
        "- Governance eligibility for the stated review scope",
        "",
        "## Blank Human Fields",
        "",
    ]
    for column in HUMAN_REVIEW_COLUMNS:
        lines.append(f"- `{column}`")
    current_council = None
    for row in rows:
        if row["council"] != current_council:
            current_council = row["council"]
            lines.extend(["", f"## {current_council}", ""])
        lines.extend([
            f"### {row['entitlement_label']}",
            "",
            f"- Gold review ID: `{row['gold_review_id']}`",
            f"- Agreement: `{row['agreement_id']}`",
            f"- Machine: `{row['machine_cell_status']}` / `{row['machine_presence_status']}` / `{row['machine_value_status']}`",
            f"- Codex suggestion: **advisory only** `{row['codex_suggested_review_decision']}`; confidence `{row['codex_confidence']}`; risk `{', '.join(row['codex_risk_flags']) or 'none'}`",
            f"- Clause/feature: `{row['clause_card_id'] or 'none'}` / `{row['feature_card_id'] or 'none'}`",
            f"- Page/block/parser: p.{row['page'] or '?'} / `{row['block_id'] or 'none'}` / `{row['parser_used'] or 'unknown'}`",
            f"- Hashes: clause `{row['raw_clause_text_hash'] or 'none'}`; span `{row['evidence_span_text_hash'] or 'none'}`",
            f"- References: {row['reference_link_count']} ({row['reference_links_summary'] or 'none'})",
            f"- Blockers/failure: `{', '.join(row['blocker_signals']) or 'none'}` / `{row['failure_reason'] or 'none'}`",
            "",
            "Evidence span:",
            "",
            f"> {short_text(row['evidence_span_text'], 600) or '[no evidence span]'}",
            "",
            "Human review fields: leave blank until reviewed.",
            "",
        ])
        for column in HUMAN_REVIEW_COLUMNS:
            lines.append(f"- `{column}`: ")
        lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build human review worksheet from gold seed, QA pack, and Codex suggestions.")
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--qa-pack", type=Path, default=DEFAULT_QA_PACK)
    parser.add_argument("--suggestions", type=Path, default=DEFAULT_SUGGESTIONS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generated_at = utc_now_iso()
    gold_rows = jsonl_rows(args.gold.resolve())
    qa_pack = load_json(args.qa_pack.resolve())
    suggestions = jsonl_rows(args.suggestions.resolve())
    rows = worksheet_rows(gold_rows, qa_pack, suggestions)
    errors = validate_worksheet(rows, gold_rows, suggestions)
    if errors:
        print(json.dumps({
            "schema_version": "review.entitlement_locator_human_review_worksheet_build.v1",
            "generated_at": generated_at,
            "status": "failed",
            "errors": errors,
        }, indent=2))
        raise SystemExit(1)
    output_dir = args.output_dir.resolve()
    csv_path = output_dir / "locator-human-review-worksheet-v1.csv"
    md_path = output_dir / "locator-human-review-worksheet-v1.md"
    try:
        write_csv(csv_path, rows)
    except PermissionError:
        stamp = generated_at.replace("-", "").replace(":", "").replace(".", "").replace("+", "z")
        csv_path = output_dir / f"locator-human-review-worksheet-v1-{stamp}.csv"
        md_path = output_dir / f"locator-human-review-worksheet-v1-{stamp}.md"
        write_csv(csv_path, rows)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown_for_rows(rows, generated_at=generated_at), encoding="utf-8")
    print(json.dumps({
        "schema_version": "review.entitlement_locator_human_review_worksheet_build.v1",
        "generated_at": generated_at,
        "status": "passed",
        "rows": len(rows),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
    }, indent=2))


if __name__ == "__main__":
    main()
