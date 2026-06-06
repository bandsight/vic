from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import statistics
from typing import Any
import xml.etree.ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCX = ROOT.parent / "from user" / "entitlements draft summary report version 2.docx"
DEFAULT_OUTPUT = ROOT / "data" / "review" / "entitlement_report_learning.json"
SCHEMA_VERSION = "wiki.entitlement_report_learning.v1"

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
COUNCILS = [
    "Ararat",
    "Ballarat",
    "Central Goldfields",
    "Golden Plains",
    "Greater Bendigo",
    "Hepburn",
    "Moorabool",
    "Mount Alexander",
    "Pyrenees",
    "Wyndham",
]
UNIT_NORMALISATION = {
    "day": "days",
    "days": "days",
    "hour": "hours",
    "hours": "hours",
    "week": "weeks",
    "weeks": "weeks",
    "month": "months",
    "months": "months",
    "year": "years",
    "years": "years",
}
TIMEFRAME_PATTERNS = [
    ("per_year", re.compile(r"\b(per\s+(?:year|annum|calendar\s+year)|each\s+year|annually)\b", re.I)),
    ("per_occasion", re.compile(r"\bper\s+occasion\b", re.I)),
    ("per_week", re.compile(r"\b(per\s+week|/week|weekly)\b", re.I)),
    ("per_day", re.compile(r"\b(per\s+day|/day|daily)\b", re.I)),
    ("per_fortnight", re.compile(r"\b(per\s+fortnight|/fortnight|fortnightly)\b", re.I)),
    ("life_of_agreement", re.compile(r"\blife\s+of\s+(?:the\s+)?agreement\b", re.I)),
    ("over_period", re.compile(r"\bover\s+(?:the\s+)?(?:life\s+of\s+(?:the\s+)?agreement|\d+\s+(?:days?|weeks?|months?|years?))\b", re.I)),
]
CONDITION_PATTERNS = [
    re.compile(r"\bincluding\s+[^.]+", re.I),
    re.compile(r"\bplus\s+[^.]+", re.I),
    re.compile(r"\bfor\s+[^.]+", re.I),
    re.compile(r"\bsubject\s+to\s+[^.]+", re.I),
    re.compile(r"\bif\s+[^.]+", re.I),
    re.compile(r"\bwhere\s+[^.]+", re.I),
    re.compile(r"\bwith\s+[^.]+", re.I),
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_key(value: Any) -> str:
    text = clean_text(value).lower()
    text = text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cell_paragraphs(cell: ET.Element) -> list[str]:
    paragraphs: list[str] = []
    for para in cell.findall(".//w:p", WORD_NS):
        text = "".join(node.text or "" for node in para.findall(".//w:t", WORD_NS)).strip()
        if text:
            paragraphs.append(clean_text(text))
    return paragraphs


def docx_rows(path: Path) -> list[dict[str, Any]]:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    rows: list[dict[str, Any]] = []
    for table in root.findall(".//w:tbl", WORD_NS):
        table_rows = table.findall("./w:tr", WORD_NS)
        if not table_rows:
            continue
        for row in table_rows[1:]:
            cells = row.findall("./w:tc", WORD_NS)
            if len(cells) < 3:
                continue
            entitlement_parts = cell_paragraphs(cells[0])
            if not entitlement_parts:
                continue
            rows.append({
                "label": entitlement_parts[0],
                "definition": clean_text(" ".join(entitlement_parts[1:])),
                "council_summary": clean_text(" ".join(cell_paragraphs(cells[1]))),
                "ballarat_takeaway": clean_text(" ".join(cell_paragraphs(cells[2]))),
            })
    return rows


def council_segments(summary: str) -> dict[str, str]:
    council_pattern = "|".join(re.escape(council) for council in sorted(COUNCILS, key=len, reverse=True))
    matches = list(re.finditer(rf"\b({council_pattern}):\s*", summary))
    output: dict[str, str] = {}
    for index, match in enumerate(matches):
        council = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(summary)
        output[council] = clean_text(summary[match.end():end].strip(" |"))
    return output


def value_kind(text: str) -> str:
    lower = text.lower()
    if "no specific provision identified" in lower or "not identified" in lower:
        return "not_identified"
    if "amount not stated" in lower or "amount is not fixed" in lower or "no clear dollar amount" in lower:
        return "amount_not_stated"
    if re.search(r"\$|\b\d+(?:\.\d+)?\s*(?:aud|dollars?)\b", lower):
        return "money"
    if re.search(r"\b\d+(?:\.\d+)?\s*%", lower):
        return "percentage"
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:paid\s+)?(?:days?|hours?|weeks?|months?|years?)\b", lower):
        return "duration_or_time"
    if re.search(r"\b(available|provided|yes|cash-out allowed|access is identified|shutdown period:\s*yes)\b", lower):
        return "availability_or_condition"
    return "descriptive"


def number_value(value: str) -> float:
    return float(value.replace(",", ""))


def extract_quantums(text: str) -> list[dict[str, Any]]:
    quantums: list[dict[str, Any]] = []
    money_pattern = re.compile(
        r"(?P<modifier>up\s+to|at\s+least|minimum\s+of|maximum\s+of)?\s*\$(?P<value>\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<basis>/(?:week|day|fortnight)|per\s+(?:week|day|fortnight|year))?",
        re.I,
    )
    duration_pattern = re.compile(
        r"(?P<modifier>up\s+to|at\s+least|minimum\s+of|maximum\s+of)?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<paid>paid\s+)?(?P<unit>days?|hours?|weeks?|months?|years?)\b(?:\s+(?P<basis>per\s+(?:year|annum|calendar\s+year|occasion|week|month|day)))?",
        re.I,
    )
    percent_pattern = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*%")
    for match in money_pattern.finditer(text):
        basis = clean_text(match.group("basis")).replace("/", "per ")
        quantums.append({
            "kind": "money",
            "value": number_value(match.group("value")),
            "unit": "AUD",
            "modifier": clean_text(match.group("modifier")).lower(),
            "basis": clean_text(basis).lower(),
            "text": clean_text(match.group(0)),
        })
    for match in duration_pattern.finditer(text):
        unit = UNIT_NORMALISATION.get(match.group("unit").lower(), match.group("unit").lower())
        quantums.append({
            "kind": "duration_or_time",
            "value": number_value(match.group("value")),
            "unit": unit,
            "modifier": clean_text(match.group("modifier")).lower(),
            "paid_status": "paid" if match.group("paid") else "",
            "basis": clean_text(match.group("basis")).lower(),
            "text": clean_text(match.group(0)),
        })
    for match in percent_pattern.finditer(text):
        quantums.append({
            "kind": "percentage",
            "value": number_value(match.group("value")),
            "unit": "percent",
            "modifier": "",
            "basis": "",
            "text": clean_text(match.group(0)),
        })
    return quantums


def extract_timeframes(texts: list[str]) -> list[str]:
    found: list[str] = []
    haystack = " ".join(texts)
    for label, pattern in TIMEFRAME_PATTERNS:
        if pattern.search(haystack):
            found.append(label)
    return sorted(set(found))


def extract_conditions(text: str) -> list[str]:
    conditions: list[str] = []
    for pattern in CONDITION_PATTERNS:
        for match in pattern.finditer(text):
            conditions.append(clean_text(match.group(0).strip(" .;,")))
            if len(conditions) >= 6:
                return conditions
    return conditions


def range_summary(quantums: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    examples: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    modifiers: Counter[str] = Counter()
    range_modifiers: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    for quantum in quantums:
        key = (
            clean_text(quantum.get("kind")),
            clean_text(quantum.get("unit")),
            clean_text(quantum.get("basis")),
        )
        grouped[key].append(float(quantum["value"]))
        if len(examples[key]) < 6:
            examples[key].append(clean_text(quantum.get("text")))
        if clean_text(quantum.get("modifier")):
            modifier = clean_text(quantum.get("modifier"))
            modifiers[modifier] += 1
            range_modifiers[key][modifier] += 1
    ranges: list[dict[str, Any]] = []
    for (kind, unit, basis), values in sorted(grouped.items()):
        modifiers_for_range = range_modifiers[(kind, unit, basis)]
        ranges.append({
            "kind": kind,
            "unit": unit,
            "basis": basis,
            "bound": range_bound(modifiers_for_range),
            "modifiers": dict(modifiers_for_range),
            "count": len(values),
            "min": min(values),
            "median": statistics.median(values),
            "max": max(values),
            "common_values": dict(Counter(values).most_common(8)),
            "examples": examples[(kind, unit, basis)],
        })
    return {
        "ranges": ranges,
        "modifiers": dict(modifiers),
    }


def range_bound(modifiers: Counter[str]) -> str:
    modifier_text = " ".join(modifiers)
    if re.search(r"\b(up\s+to|maximum\s+of)\b", modifier_text, re.I):
        return "upper"
    if re.search(r"\b(at\s+least|minimum\s+of)\b", modifier_text, re.I):
        return "lower"
    return "observed"


def conversion_hints(ranges: list[dict[str, Any]]) -> list[str]:
    hints: list[str] = []
    money_bases = {item["basis"] for item in ranges if item["kind"] == "money" and item.get("basis")}
    duration_units = {item["unit"] for item in ranges if item["kind"] == "duration_or_time"}
    if {"per week", "per day"} <= money_bases or {"per fortnight", "per day"} <= money_bases:
        hints.append("Money values appear in mixed bases; convert to a common per-day or per-week basis only when the source basis is explicit.")
    if len(duration_units.intersection({"hours", "days", "weeks"})) > 1:
        hints.append("Time values appear in mixed units; convert only with an explicit working-hours or working-days basis from the clause.")
    if any(item["kind"] == "duration_or_time" and item["basis"] == "per year" for item in ranges):
        hints.append("Annual leave-style measures should preserve the annual timeframe in the governed sentence.")
    return hints


def learning_for_row(row: dict[str, Any]) -> dict[str, Any]:
    segments = council_segments(row["council_summary"])
    council_findings: list[dict[str, Any]] = []
    all_quantums: list[dict[str, Any]] = []
    kinds: Counter[str] = Counter()
    all_conditions: list[str] = []
    for council in COUNCILS:
        text = segments.get(council, "")
        kind = value_kind(text)
        quantums = extract_quantums(text)
        kinds[kind] += 1
        all_quantums.extend(quantums)
        conditions = extract_conditions(text)
        all_conditions.extend(conditions)
        council_findings.append({
            "council": council,
            "summary": text,
            "value_kind": kind,
            "quantums": quantums,
            "timeframes": extract_timeframes([text]),
            "conditions": conditions[:4],
        })
    value_ranges = range_summary(all_quantums)
    expected_kind = expected_kind_for_profile(kinds, value_ranges["ranges"])
    observed_timeframes = extract_timeframes([row["council_summary"], row["ballarat_takeaway"]])
    return {
        "entitlement_key": stable_key(row["label"]),
        "label": row["label"],
        "definition": row["definition"],
        "expected_answer_kind": expected_kind,
        "observed_value_kinds": dict(kinds),
        "observed_timeframes": observed_timeframes,
        "observed_conditions": list(dict.fromkeys(all_conditions))[:12],
        "quantum_profile": {
            **value_ranges,
            "conversion_hints": conversion_hints(value_ranges["ranges"]),
        },
        "council_findings": council_findings,
        "ballarat_takeaway": row["ballarat_takeaway"],
    }


def expected_kind_for_profile(kinds: Counter[str], ranges: list[dict[str, Any]]) -> str:
    range_kinds = {item["kind"] for item in ranges}
    if "money" in range_kinds:
        return "money"
    if "percentage" in range_kinds:
        return "percentage"
    if "duration_or_time" in range_kinds:
        return "duration_or_time"
    if kinds.get("amount_not_stated"):
        return "amount_not_stated"
    if kinds.get("availability_or_condition"):
        return "availability_or_condition"
    return kinds.most_common(1)[0][0] if kinds else "unknown"


def build_payload(docx_path: Path, *, generated_at: str) -> dict[str, Any]:
    rows = docx_rows(docx_path)
    entitlements = [learning_for_row(row) for row in rows]
    kind_counts = Counter(item["expected_answer_kind"] for item in entitlements)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source_document": str(docx_path),
        "summary": {
            "entitlements": len(entitlements),
            "expected_answer_kinds": dict(sorted(kind_counts.items())),
            "with_quantum_ranges": sum(1 for item in entitlements if item["quantum_profile"]["ranges"]),
            "with_conversion_hints": sum(1 for item in entitlements if item["quantum_profile"]["conversion_hints"]),
        },
        "entitlements": entitlements,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract benchmark expectations from the entitlement draft summary report.")
    parser.add_argument("--docx", type=Path, default=DEFAULT_DOCX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_payload(args.docx.resolve(), generated_at=utc_now_iso())
    write_json(args.output.resolve(), payload)
    print(json.dumps({
        "schema_version": "wiki.entitlement_report_learning_build.v1",
        "generated_at": payload["generated_at"],
        "output_path": str(args.output.resolve()),
        "summary": payload["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
