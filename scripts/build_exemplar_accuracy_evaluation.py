from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXEMPLAR_PATH = (
    ROOT
    / "wiki"
    / "artifacts"
    / "downstream-analysis-exemplars"
    / "ballarat-entitlement-benchmark-exemplar.json"
)
DEFAULT_LOCATOR_DIR = ROOT / "wiki" / "artifacts" / "entitlement-locator-experiment"
DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "exemplar-accuracy-evaluation"
SCHEMA_VERSION = "wiki.exemplar_accuracy_evaluation.v1"

ABSENCE_FINDING_RE = re.compile(
    r"\b(no\s+specific\s+provision|not\s+identified|not\s+clearly\s+identified|no\s+clear|not\s+clear|"
    r"no\s+stated\s+amount|not\s+stated|amount\s+not\s+stated)\b",
    re.I,
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def latest_locator_path(locator_dir: Path = DEFAULT_LOCATOR_DIR) -> Path:
    gold = sorted(locator_dir.glob("entitlement-locator-experiment-gold-exemplar-v2-*.json"), key=lambda p: p.stat().st_mtime)
    if gold:
        return gold[-1]
    all_cached = sorted(locator_dir.glob("entitlement-locator-experiment-all-cached-*.json"), key=lambda p: p.stat().st_mtime)
    if all_cached:
        return all_cached[-1]
    candidates = sorted(locator_dir.glob("entitlement-locator-experiment-*.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"No locator artifacts found in {locator_dir}")
    return candidates[-1]


def answer_kind(quantification_type: str) -> str:
    return {
        "quantified_value": "quantitative",
        "quantification_required": "quantitative_review",
        "binary_presence_or_absence": "boolean",
        "qualitative_condition": "descriptive",
    }.get(quantification_type, "descriptive")


def normalise_signal(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("$", " aud ")
    text = text.replace(",", "")
    text = re.sub(r"\bpaid\b", "", text)
    text = re.sub(r"\bper\s+(?:year|annum|week|month|occasion)\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def value_signals(row: dict[str, Any]) -> set[str]:
    signals = {normalise_signal(item) for item in row.get("value_signals") or [] if str(item or "").strip()}
    for value in row.get("normalised_values") or []:
        if not isinstance(value, dict):
            continue
        raw = " ".join(
            str(part).strip()
            for part in (value.get("value"), value.get("unit"))
            if str(part or "").strip()
        )
        if raw:
            signals.add(normalise_signal(raw))
    return {item for item in signals if item}


def expected_quantum_signals(reference_entry: dict[str, Any]) -> set[str]:
    return {
        normalise_signal(item)
        for item in reference_entry.get("quantum_signals") or []
        if str(item or "").strip()
    }


def absent_or_gap_reference(reference_entry: dict[str, Any]) -> bool:
    if reference_entry.get("presence") == "no_specific_provision_identified":
        return True
    finding = str(reference_entry.get("finding") or "")
    return not reference_entry.get("quantum_signals") and bool(ABSENCE_FINDING_RE.search(finding))


def row_has_source(row: dict[str, Any]) -> bool:
    return bool(
        row.get("clause_cards")
        or row.get("feature_cards")
        or row.get("best_candidate")
        or row.get("candidate_pages")
    )


def row_has_feature(row: dict[str, Any]) -> bool:
    return bool(row.get("feature_cards") or row.get("normalised_values"))


def row_has_clause(row: dict[str, Any]) -> bool:
    state = str(row.get("state") or "")
    return bool(row.get("clause_cards")) or state in {
        "clause_found_value_extracted",
        "clause_found_value_missing",
    }


def evaluate_cell(
    *,
    entitlement_id: str,
    entitlement_label: str,
    category: str,
    quantification_type: str,
    reference_entry: dict[str, Any],
    machine_row: dict[str, Any] | None,
    can_disagree_with_gold: bool,
) -> dict[str, Any]:
    row = machine_row or {}
    state = str(row.get("state") or "not_profiled")
    expected_signals = expected_quantum_signals(reference_entry)
    observed_signals = value_signals(row)
    has_clause = row_has_clause(row)
    has_feature = row_has_feature(row)
    has_source = row_has_source(row)
    expected_absence = absent_or_gap_reference(reference_entry)
    supported_disagreement = False
    strict_pass = False
    operational_pass = False

    if expected_absence:
        strict_pass = not observed_signals and state in {
            "no_candidate_clause_found",
            "adjacent_or_blocked_clause_found",
            "clause_found_value_missing",
        }
        supported_disagreement = bool(can_disagree_with_gold and has_source and state != "no_candidate_clause_found")
        operational_pass = strict_pass or supported_disagreement
        expectation = "absence_or_gap"
    elif quantification_type == "binary_presence_or_absence":
        strict_pass = has_clause or has_feature
        operational_pass = strict_pass
        expectation = "boolean_presence"
    elif quantification_type == "qualitative_condition":
        strict_pass = has_clause or has_feature
        operational_pass = strict_pass
        expectation = "descriptive_condition"
    elif quantification_type == "quantification_required":
        strict_pass = has_clause or has_feature
        operational_pass = strict_pass
        expectation = "quantification_review"
    elif expected_signals:
        strict_pass = bool(expected_signals.intersection(observed_signals))
        supported_disagreement = bool(can_disagree_with_gold and has_feature and observed_signals)
        operational_pass = strict_pass or supported_disagreement
        expectation = "quantified_value"
    else:
        strict_pass = has_clause or has_feature
        supported_disagreement = bool(can_disagree_with_gold and has_source)
        operational_pass = strict_pass or supported_disagreement
        expectation = "descriptive_or_unquantified"

    reasons: list[str] = []
    if strict_pass:
        reasons.append("strict_reference_match")
    elif operational_pass and supported_disagreement:
        reasons.append("source_backed_disagreement_allowed_by_gold_contract")
    elif expected_absence and observed_signals:
        reasons.append("machine_extracted_value_for_gold_gap")
    elif expected_signals and not observed_signals:
        reasons.append("reference_quantum_missing_from_machine")
    elif not has_source:
        reasons.append("no_source_candidate")
    else:
        reasons.append("semantic_review_needed")

    return {
        "entitlement_id": entitlement_id,
        "entitlement_label": entitlement_label,
        "category": category,
        "council": reference_entry.get("council"),
        "agreement_id": row.get("agreement_id"),
        "answer_kind": answer_kind(quantification_type),
        "quantification_type": quantification_type,
        "expectation": expectation,
        "reference_presence": reference_entry.get("presence"),
        "reference_finding": reference_entry.get("finding"),
        "reference_quantum_signals": sorted(expected_signals),
        "machine_state": state,
        "machine_value_signals": sorted(observed_signals),
        "machine_has_clause": has_clause,
        "machine_has_feature": has_feature,
        "machine_has_source": has_source,
        "strict_reference_match": strict_pass,
        "operational_semantic_agreement": operational_pass,
        "supported_disagreement": supported_disagreement,
        "reasons": reasons,
        "best_heading": ((row.get("best_candidate") or {}).get("heading") if isinstance(row.get("best_candidate"), dict) else ""),
    }


def evaluate(exemplar: dict[str, Any], locator: dict[str, Any], *, target: float) -> dict[str, Any]:
    gold = exemplar.get("gold_comparator_target") if isinstance(exemplar.get("gold_comparator_target"), dict) else {}
    can_disagree = bool(gold.get("can_disagree_with_gold"))
    profiles = {
        str(profile.get("entitlement_id") or ""): profile
        for profile in locator.get("profiles") or []
        if isinstance(profile, dict)
    }
    cells: list[dict[str, Any]] = []
    entitlement_scores: list[dict[str, Any]] = []
    by_answer_kind: dict[str, Counter[str]] = defaultdict(Counter)
    by_expectation: dict[str, Counter[str]] = defaultdict(Counter)
    by_category: dict[str, Counter[str]] = defaultdict(Counter)

    for category in exemplar.get("categories") or []:
        if not isinstance(category, dict):
            continue
        for entitlement in category.get("entitlements") or []:
            if not isinstance(entitlement, dict):
                continue
            entitlement_id = str(entitlement.get("entitlement_id") or "")
            mapping = entitlement.get("semantic_mapping") if isinstance(entitlement.get("semantic_mapping"), dict) else {}
            quantification = mapping.get("quantification_semantics") if isinstance(mapping.get("quantification_semantics"), dict) else {}
            comparator = mapping.get("comparator_semantics") if isinstance(mapping.get("comparator_semantics"), dict) else {}
            quantification_type = str(quantification.get("quantification_type") or "qualitative_condition")
            machine_profile = profiles.get(entitlement_id) or {}
            rows_by_council = {
                str(row.get("council") or ""): row
                for row in machine_profile.get("target_rows") or []
                if isinstance(row, dict)
            }
            row_cells = [
                evaluate_cell(
                    entitlement_id=entitlement_id,
                    entitlement_label=str(entitlement.get("entitlement_label") or entitlement_id),
                    category=str(category.get("label") or entitlement.get("category") or ""),
                    quantification_type=quantification_type,
                    reference_entry=entry,
                    machine_row=rows_by_council.get(str(entry.get("council") or "")),
                    can_disagree_with_gold=can_disagree,
                )
                for entry in comparator.get("entries") or []
                if isinstance(entry, dict)
            ]
            cells.extend(row_cells)
            operational_passes = sum(1 for cell in row_cells if cell["operational_semantic_agreement"])
            strict_passes = sum(1 for cell in row_cells if cell["strict_reference_match"])
            denominator = len(row_cells)
            entitlement_scores.append({
                "entitlement_id": entitlement_id,
                "entitlement_label": entitlement.get("entitlement_label") or entitlement_id,
                "category": category.get("label") or entitlement.get("category") or "",
                "answer_kind": answer_kind(quantification_type),
                "quantification_type": quantification_type,
                "cells": denominator,
                "operational_semantic_agreement": operational_passes,
                "strict_reference_match": strict_passes,
                "operational_score": round(operational_passes / denominator, 4) if denominator else 0,
                "strict_score": round(strict_passes / denominator, 4) if denominator else 0,
                "passes_target": (operational_passes / denominator) >= target if denominator else False,
            })

    summary_counter = Counter()
    for cell in cells:
        summary_counter["cells"] += 1
        summary_counter["operational_pass"] += int(cell["operational_semantic_agreement"])
        summary_counter["strict_pass"] += int(cell["strict_reference_match"])
        summary_counter["supported_disagreement"] += int(cell["supported_disagreement"])
        answer_counter = by_answer_kind[cell["answer_kind"]]
        answer_counter["cells"] += 1
        answer_counter["operational_pass"] += int(cell["operational_semantic_agreement"])
        answer_counter["strict_pass"] += int(cell["strict_reference_match"])
        expectation_counter = by_expectation[cell["expectation"]]
        expectation_counter["cells"] += 1
        expectation_counter["operational_pass"] += int(cell["operational_semantic_agreement"])
        expectation_counter["strict_pass"] += int(cell["strict_reference_match"])
        category_counter = by_category[cell["category"]]
        category_counter["cells"] += 1
        category_counter["operational_pass"] += int(cell["operational_semantic_agreement"])
        category_counter["strict_pass"] += int(cell["strict_reference_match"])

    def rollup(counter: Counter[str]) -> dict[str, Any]:
        cells_count = counter["cells"]
        return {
            "cells": cells_count,
            "operational_pass": counter["operational_pass"],
            "strict_pass": counter["strict_pass"],
            "operational_accuracy": round(counter["operational_pass"] / cells_count, 4) if cells_count else 0,
            "strict_accuracy": round(counter["strict_pass"] / cells_count, 4) if cells_count else 0,
        }

    failed_cells = [cell for cell in cells if not cell["operational_semantic_agreement"]]
    failed_cells.sort(key=lambda cell: (cell["category"], cell["entitlement_label"], str(cell["council"])))
    operational_accuracy = rollup(summary_counter)["operational_accuracy"]
    strict_accuracy = rollup(summary_counter)["strict_accuracy"]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "target": target,
        "passes_target": operational_accuracy >= target,
        "summary": {
            "entitlements": len(entitlement_scores),
            "comparator_cells": summary_counter["cells"],
            "operational_accuracy": operational_accuracy,
            "strict_reference_accuracy": strict_accuracy,
            "operational_pass": summary_counter["operational_pass"],
            "strict_pass": summary_counter["strict_pass"],
            "supported_disagreements": summary_counter["supported_disagreement"],
            "remaining_failures": len(failed_cells),
        },
        "source": {
            "exemplar_artifact_id": exemplar.get("artifact_id"),
            "locator_artifact_id": locator.get("artifact_id"),
            "locator_run_scope": locator.get("run_scope"),
            "accuracy_unit": "row_semantic_agreement_mean_over_comparator_cells",
            "gold_can_disagree_with_source_evidence": can_disagree,
        },
        "by_answer_kind": {key: rollup(value) for key, value in sorted(by_answer_kind.items())},
        "by_expectation": {key: rollup(value) for key, value in sorted(by_expectation.items())},
        "by_category": {key: rollup(value) for key, value in sorted(by_category.items())},
        "entitlement_scores": sorted(entitlement_scores, key=lambda item: (item["operational_score"], item["category"], item["entitlement_label"])),
        "failed_cells": failed_cells[:120],
    }


def markdown_for_payload(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Exemplar Accuracy Evaluation",
        "",
        f"Target: {payload['target']:.0%}",
        f"Operational semantic agreement: {summary['operational_accuracy']:.1%}",
        f"Strict reference match: {summary['strict_reference_accuracy']:.1%}",
        f"Passes target: {'yes' if payload['passes_target'] else 'no'}",
        "",
        "## Answer Types",
        "",
        "| Answer kind | Cells | Operational | Strict |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key, item in payload["by_answer_kind"].items():
        lines.append(f"| {key} | {item['cells']} | {item['operational_accuracy']:.1%} | {item['strict_accuracy']:.1%} |")
    lines.extend([
        "",
        "## Lowest Entitlement Scores",
        "",
        "| Entitlement | Kind | Operational | Strict |",
        "| --- | --- | ---: | ---: |",
    ])
    for item in payload["entitlement_scores"][:15]:
        lines.append(
            f"| {item['entitlement_label']} | {item['answer_kind']} | "
            f"{item['operational_score']:.1%} | {item['strict_score']:.1%} |"
        )
    lines.extend(["", "## Remaining Failures", ""])
    if not payload["failed_cells"]:
        lines.append("No remaining operational failures.")
    for cell in payload["failed_cells"][:40]:
        reasons = ", ".join(cell["reasons"])
        lines.append(
            f"- {cell['entitlement_label']} / {cell['council']}: {cell['expectation']} -> "
            f"{cell['machine_state']} ({reasons})"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate locator output against entitlements draft summary report version 2.")
    parser.add_argument("--exemplar", type=Path, default=DEFAULT_EXEMPLAR_PATH)
    parser.add_argument("--locator", type=Path)
    parser.add_argument("--target", type=float, default=0.90)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    locator_path = args.locator or latest_locator_path()
    exemplar = read_json(args.exemplar)
    locator = read_json(locator_path)
    payload = evaluate(exemplar, locator, target=args.target)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_id = f"exemplar-accuracy-{locator.get('artifact_id', locator_path.stem)}"
    json_path = output_dir / f"{artifact_id}.json"
    md_path = output_dir / f"{artifact_id}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.exemplar_accuracy_evaluation_build.v1",
        "generated_at": payload["generated_at"],
        "artifact_id": artifact_id,
        "artifact_path": str(json_path),
        "locator_path": str(locator_path),
        "operational_accuracy": payload["summary"]["operational_accuracy"],
        "strict_reference_accuracy": payload["summary"]["strict_reference_accuracy"],
        "passes_target": payload["passes_target"],
    }, indent=2))
    if not payload["passes_target"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
