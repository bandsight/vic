from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import statistics
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT
    / "wiki"
    / "artifacts"
    / "entitlement-cards"
    / "entitlement-cards-entitlement-locator-experiment-all-cached-79-offset-0.json"
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def first_number(value: Any) -> float | None:
    match = re.search(r"(?<![A-Za-z])(\d+(?:\.\d+)?)", clean_text(value))
    return float(match.group(1)) if match else None


def unit_family(card: dict[str, Any]) -> str:
    values = card.get("quantum", {}).get("values") if isinstance(card.get("quantum"), dict) else []
    if not isinstance(values, list) or not values:
        return ""
    unit = clean_text(values[0].get("unit")).lower()
    unit = re.sub(r"\s+", " ", unit).strip()
    return unit


def card_fact_atoms(card: dict[str, Any]) -> list[dict[str, Any]]:
    quantum = card.get("quantum") if isinstance(card.get("quantum"), dict) else {}
    atoms = quantum.get("fact_atoms")
    if isinstance(atoms, list) and atoms:
        return [atom for atom in atoms if isinstance(atom, dict)]
    values = quantum.get("values")
    if not isinstance(values, list):
        return []
    return [
        {
            "fact_role": "legacy_value",
            "value": value.get("value"),
            "unit": value.get("unit"),
            "condition": value.get("condition"),
            "value_text": clean_text(f"{value.get('value', '')} {value.get('unit', '')}"),
            "is_reportable_answer": True,
        }
        for value in values
        if isinstance(value, dict)
    ]


def atom_unit_family(atom: dict[str, Any]) -> str:
    unit = clean_text(atom.get("unit")).lower()
    unit = unit.replace("day(s)", "day").replace("week(s)", "week").replace("hour(s)", "hour")
    unit = re.sub(r"\bdays\b", "day", unit)
    unit = re.sub(r"\bweeks\b", "week", unit)
    unit = re.sub(r"\bhours\b", "hour", unit)
    unit = re.sub(r"\s+", " ", unit).strip()
    return unit


def sentence_flags(card: dict[str, Any]) -> list[str]:
    sentence = clean_text(card.get("simple_sentence"))
    value_text = clean_text(card.get("quantum", {}).get("value_text"))
    has_numeric_value = bool(re.match(r"^\d", value_text))
    flags: list[str] = []
    if has_numeric_value and sentence and not re.match(r"^\d", sentence):
        flags.append("not_quantity_first")
    if has_numeric_value and sentence.lower().startswith("provides "):
        flags.append("generic_provides_prefix")
    if has_numeric_value and len(sentence.split()) < 4:
        flags.append("too_short_for_measurement")
    return flags


def analyse_cards(payload: dict[str, Any]) -> dict[str, Any]:
    cards = [card for card in payload.get("cards", []) if isinstance(card, dict)]
    sentence_issue_counts: Counter[str] = Counter()
    report_learning_flags: Counter[str] = Counter()
    report_learning_statuses: Counter[str] = Counter()
    sentence_issue_examples: list[dict[str, Any]] = []
    by_entitlement: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for card in cards:
        by_entitlement[clean_text(card.get("entitlement_id"))].append(card)
        flags = sentence_flags(card)
        for flag in flags:
            sentence_issue_counts[flag] += 1
        if flags and len(sentence_issue_examples) < 40:
            sentence_issue_examples.append({
                "entitlement_id": card.get("entitlement_id"),
                "entitlement_label": card.get("entitlement_label"),
                "council": card.get("council"),
                "simple_sentence": card.get("simple_sentence"),
                "value_text": card.get("quantum", {}).get("value_text"),
                "flags": flags,
            })
        alignment = card.get("evidence_standard", {}).get("report_learning_alignment", {})
        if isinstance(alignment, dict):
            report_learning_statuses[clean_text(alignment.get("status")) or "missing"] += 1
            for flag in alignment.get("flags") or []:
                report_learning_flags[clean_text(flag)] += 1

    outliers: list[dict[str, Any]] = []
    mixed_measure_cards: list[dict[str, Any]] = []
    for entitlement_id, rows in by_entitlement.items():
        grouped: dict[str, list[tuple[float, dict[str, Any]]]] = defaultdict(list)
        for row in rows:
            atoms = card_fact_atoms(row)
            for atom in atoms:
                if atom.get("is_reportable_answer") is False:
                    continue
                number = first_number(atom.get("value"))
                family = atom_unit_family(atom)
                role = clean_text(atom.get("fact_role")) or "unknown"
                if number is not None and family:
                    grouped[f"{role}:{family}"].append((number, row))
            value_text = clean_text(row.get("quantum", {}).get("value_text"))
            roles = {clean_text(atom.get("fact_role")) for atom in atoms if clean_text(atom.get("fact_role"))}
            units = {atom_unit_family(atom) for atom in atoms if atom_unit_family(atom)}
            if (len(roles) > 1 or len(units) > 1 or value_text.count(";") >= 1) and len(mixed_measure_cards) < 40:
                mixed_measure_cards.append({
                    "entitlement_id": row.get("entitlement_id"),
                    "entitlement_label": row.get("entitlement_label"),
                    "council": row.get("council"),
                    "value_text": row.get("quantum", {}).get("value_text"),
                    "simple_sentence": row.get("simple_sentence"),
                    "fact_roles": sorted(roles),
                    "unit_families": sorted(units),
                })
        for family, items in grouped.items():
            numbers = [value for value, _ in items]
            if len(numbers) < 4:
                continue
            median = statistics.median(numbers)
            if median <= 0:
                continue
            for value, row in items:
                ratio = max(value / median, median / value) if value else float("inf")
                if ratio >= 8:
                    outliers.append({
                        "entitlement_id": entitlement_id,
                        "entitlement_label": row.get("entitlement_label"),
                        "council": row.get("council"),
                        "unit_family": family,
                        "value_text": row.get("quantum", {}).get("value_text"),
                        "simple_sentence": row.get("simple_sentence"),
                        "median_value_for_unit_family": median,
                        "ratio_from_median": round(ratio, 2),
                    })

    outliers.sort(key=lambda item: (-item["ratio_from_median"], clean_text(item.get("entitlement_label")), clean_text(item.get("council"))))
    return {
        "schema_version": "wiki.entitlement_card_analysis.v1",
        "source_artifact_id": payload.get("artifact_id"),
        "generated_at": payload.get("generated_at"),
        "summary": {
            "cards": len(cards),
            "sentence_issue_counts": dict(sorted(sentence_issue_counts.items())),
            "semantic_outliers": len(outliers),
            "mixed_measure_cards": len(mixed_measure_cards),
            "report_learning_statuses": dict(sorted(report_learning_statuses.items())),
            "report_learning_flags": dict(sorted(report_learning_flags.items())),
        },
        "sentence_issue_examples": sentence_issue_examples,
        "semantic_outliers": outliers[:80],
        "mixed_measure_examples": mixed_measure_cards,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyse Entitlement Cards for sentence quality and value outliers.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = load_json(args.input.resolve())
    print(json.dumps(analyse_cards(payload), indent=2))


if __name__ == "__main__":
    main()
