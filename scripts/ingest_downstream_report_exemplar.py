from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
from xml.etree import ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from benchmarking_data_factory.workbench.wiki_layer import (  # noqa: E402
    MANIFEST_SCHEMA_VERSION,
    WIKI_SCOPE_FOCUS,
    utc_now_iso,
)


DEFAULT_SOURCE = ROOT.parent / "from user" / "entitlements draft summary report version 2.docx"
DEFAULT_WIKI_ROOT = ROOT / "wiki"
ARTIFACT_SCHEMA_VERSION = "wiki.downstream_report_exemplar.v1"
MANIFEST_ARTIFACT_SCHEMA_KEY = "downstream_artifact_schema_version"
DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DEFAULT_SCOPE = "standard_employees"
GOLD_ACCURACY_TARGET = 0.95
CURATED_OUT_ENTITLEMENT_LABELS = {
    "annual leave": "Dropped from the seed comparator for item-by-item review; baseline annual leave is too generic for the first entitlement-library pass.",
}


CATEGORY_TAGS = {
    "leave": ["leave_annual", "leave_personal_carers", "leave_parental_family", "leave_long_service"],
    "conditions": ["hours", "rostering", "remote_work", "flexibility"],
    "financial and monetary provisions": ["allowances", "overtime_penalties", "on_call_standby"],
    "work health and safety and environmental conditions": ["workload", "consultation"],
    "parental and family related enhancements": ["leave_parental_family", "family_violence"],
    "superannuation": ["superannuation"],
    "wellbeing and support": ["family_violence", "leave_personal_carers"],
}

KEYWORD_TAGS = [
    (re.compile(r"\bannual leave\b", re.I), "leave_annual"),
    (re.compile(r"\bpersonal\b|\bcarer", re.I), "leave_personal_carers"),
    (re.compile(r"\bparental\b|\bprenatal\b|\bfertility\b|\bivf\b", re.I), "leave_parental_family"),
    (re.compile(r"\bfamily violence\b|\bgender affirmation\b|\btransition leave\b", re.I), "family_violence"),
    (re.compile(r"\bpublic holiday\b|\bchristmas\b|\bnew year\b", re.I), "public_holidays"),
    (re.compile(r"\blong service\b", re.I), "leave_long_service"),
    (re.compile(r"\bcall out\b|\bon call\b|\bstandby\b", re.I), "on_call_standby"),
    (re.compile(r"\ballowance\b|\breimbursement\b|\bcash out\b|\bdonation\b", re.I), "allowances"),
    (re.compile(r"\bhigher duties\b|\bend of band\b|\bprogression\b", re.I), "higher_duties"),
    (re.compile(r"\bwork from home\b|\bflexible work\b", re.I), "remote_work"),
    (re.compile(r"\broster\b|\bminimum engagement\b", re.I), "rostering"),
    (re.compile(r"\btemperature\b|\bthermal\b|\bheat\b|\bcold\b|\bppe\b", re.I), "workload"),
    (re.compile(r"\bsuperannuation\b|\bsuper\b", re.I), "superannuation"),
]

REVIEW_FLAG_PATTERNS = [
    ("operator_recheck", re.compile(r"\bwant to recheck\b|\brecheck these numbers\b|\brecheck\b", re.I)),
    ("source_gap", re.compile(r"\bno specific provision identified\b|\bdoes not show a clearly matched provision\b|\bdoes not appear\b", re.I)),
    ("mixed_comparator_field", re.compile(r"\bmixed comparator field\b|\bnot universal\b|\bminority of peers\b", re.I)),
]

KNOWN_COUNCIL_NAMES = [
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

SPECIALIST_ROW_PATTERNS = [
    ("designated_higher_exposure", re.compile(r"\bdesignated higher exposure\b", re.I)),
    ("public_facing_or_outdoor_staff", re.compile(r"\bpublic facing\b|\boutdoor staff\b", re.I)),
    ("specialist_nursing_or_early_years", re.compile(r"\bnurs(?:e|es|ing)\b|\bearly[- ]years\b|\bchild care workers?\b", re.I)),
]

SPECIALIST_ENTRY_PATTERNS = [
    ("nursing", re.compile(r"\bnurs(?:e|es|ing)\b|\bimmunisation nurses?\b", re.I)),
    ("maternal_child_health", re.compile(r"\bmaternal and child health\b", re.I)),
    ("early_years_childcare", re.compile(r"\bearly[- ]years\b|\bchild care\b|\bchildcare\b|\bkindergarten\b", re.I)),
    ("aquatic_or_crossing", re.compile(r"\baquatic\b|\bswim\b|\bschool crossing\b", re.I)),
    ("senior_or_executive", re.compile(r"\bsenior officers?\b|\bexecutive\b", re.I)),
]

PROVISION_PRESENCE_PATTERNS = [
    ("no_specific_provision_identified", re.compile(r"\bno specific provision identified\b", re.I)),
    ("not_clearly_matched", re.compile(r"\bdoes not show a clearly matched provision\b|\bdoes not have a clear provision\b", re.I)),
    ("limited_or_policy_reliant", re.compile(r"\blimited provision\b|\bpoints to policy\b|\bminor provision\b|\bminimal\b", re.I)),
    ("baseline_only", re.compile(r"\bfair work baseline\b|\bstandard baseline\b|\bbaseline entitlement\b", re.I)),
    ("provided", re.compile(r"\bprovided\b|\bavailable\b|\bagreement provides\b|\bup to\b|\bsupports\b|\bentitled\b", re.I)),
]

TARGET_POSTURE_PATTERNS = [
    ("aligns_with_comparator_pattern", re.compile(r"\baligns with\b|\bstandard baseline entitlement\b|\bmain cohort pattern\b", re.I)),
    ("stronger_than_many_peers", re.compile(r"\bcompares well\b|\bstrongly\b|\bstronger\b|\bmore generous\b", re.I)),
    ("weaker_or_less_explicit", re.compile(r"\bdoes not have a clear provision\b|\blower\b|\blimited\b|\bweaker\b|\bwithout stronger\b", re.I)),
    ("middle_of_comparator_field", re.compile(r"\bin the middle\b|\bsits in the middle\b", re.I)),
    ("mixed_or_uncertain", re.compile(r"\bmixed comparator field\b|\bnot universal\b|\bminority of peers\b", re.I)),
    ("not_clearly_matched", re.compile(r"\bdoes not show a clearly matched provision\b", re.I)),
]

EVIDENCE_STATE_PATTERNS = [
    ("explicit_operator_review_required", re.compile(r"\brecheck\b|\bwant to recheck\b", re.I)),
    ("source_gap_or_absence_claim", re.compile(r"\bno specific provision identified\b|\bdoes not show a clearly matched provision\b", re.I)),
    ("mixed_comparator_interpretation", re.compile(r"\bmixed comparator field\b|\bminority of peers\b|\bnot universal\b", re.I)),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse a user-supplied downstream entitlement benchmark report into a wiki artifact exemplar."
    )
    parser.add_argument(
        "docx",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Downstream report DOCX to ingest. Defaults to the latest user-supplied entitlement report.",
    )
    parser.add_argument(
        "--artifact-id",
        default="ballarat-entitlement-benchmark-exemplar",
        help="Stable artifact id for the parsed exemplar.",
    )
    parser.add_argument(
        "--wiki-root",
        type=Path,
        default=DEFAULT_WIKI_ROOT,
        help="Wiki directory to update.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Also write a short Markdown companion summary.",
    )
    parser.add_argument(
        "--include-specialist-cohorts",
        action="store_true",
        help="Keep rows that are primarily specialist-cohort related. Defaults to standard-employees only.",
    )
    return parser.parse_args()


def normalise_docx_text(value: str) -> str:
    text = value.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(?<=[.?!])(?=[A-Z])", " ", text)
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z][a-z])", " ", text)
    text = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", text)
    text = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def paragraph_text(paragraph: ET.Element) -> str:
    return normalise_docx_text("".join(node.text or "" for node in paragraph.iterfind(".//w:t", DOCX_NS)))


def cell_text(cell: ET.Element) -> str:
    paragraphs = []
    for paragraph in cell.findall(".//w:p", DOCX_NS):
        text = paragraph_text(paragraph)
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def extract_docx_blocks(path: Path) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as docx:
        document = ET.fromstring(docx.read("word/document.xml"))
    body = document.find("w:body", DOCX_NS)
    if body is None:
        return []
    blocks: list[dict[str, Any]] = []
    for child in body:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = paragraph_text(child)
            if text:
                blocks.append({"type": "paragraph", "text": text})
        elif tag == "tbl":
            rows = []
            for table_row in child.findall("w:tr", DOCX_NS):
                cells = [cell_text(cell) for cell in table_row.findall("w:tc", DOCX_NS)]
                if any(cells):
                    rows.append(cells)
            if rows:
                blocks.append({"type": "table", "rows": rows})
    return blocks


def slugify(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "-", value.lower()).strip("-")


def sha256_for_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_entitlement_table(rows: list[list[str]]) -> bool:
    if len(rows) < 2:
        return False
    headers = [normalise_docx_text(cell).lower() for cell in rows[0]]
    return any(
        cell.startswith("entitlement and definition")
        or (cell == "entitlement" and index == 0)
        or ("entitlement and definition" in cell and index == 0)
        for index, cell in enumerate(headers)
    ) and any(
        "benchmark" in cell for cell in headers[1:]
    )


def parse_scope_table(rows: list[list[str]]) -> dict[str, Any]:
    if not rows or len(rows[0]) < 2:
        return {}
    scope_text = normalise_docx_text(rows[0][0].replace("\n", " "))
    metric_text = normalise_docx_text(rows[0][1].replace("\n", " "))
    metrics = []
    for value, label in re.findall(r"(\d+)\s+([A-Za-z][A-Za-z ]+?)(?=\s+\d+\s+[A-Za-z]|$)", metric_text):
        metrics.append({"label": normalise_docx_text(label).lower(), "value": int(value)})
    return {
        "scope_text": scope_text,
        "metrics": metrics,
    }


def clean_council_name(raw: str) -> str:
    name = normalise_docx_text(raw)
    for known in KNOWN_COUNCIL_NAMES:
        if name == known or name.endswith(known):
            return known
    if any(blocked in name.lower() for blocked in ["ppe", "worker", "award"]):
        return ""
    return name


def extract_council_mentions(text: str) -> list[str]:
    normalised = normalise_docx_text(text.replace("\n", " "))
    names = {
        clean_council_name(match.group(1))
        for match in re.finditer(r"(?<![A-Za-z])([A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*){0,3}):", normalised)
    }
    return sorted(name for name in names if name)


def tags_for_entitlement(category_label: str, text: str) -> list[str]:
    tags = set(CATEGORY_TAGS.get(category_label.lower(), []))
    for pattern, tag in KEYWORD_TAGS:
        if pattern.search(text):
            tags.add(tag)
    return sorted(tags)


def review_flags_for_text(text: str) -> list[str]:
    return [flag for flag, pattern in REVIEW_FLAG_PATTERNS if pattern.search(text)]


def specialist_scope_signals(text: str, *, row_level: bool = False) -> list[str]:
    patterns = SPECIALIST_ROW_PATTERNS if row_level else SPECIALIST_ENTRY_PATTERNS
    return [label for label, pattern in patterns if pattern.search(text)]


def row_scope_for_entitlement(label: str, definition: str) -> dict[str, Any]:
    signals = specialist_scope_signals(f"{label} {definition}", row_level=True)
    if signals:
        return {
            "scope": "specialist_cohort_related",
            "signals": signals,
            "standard_employee_action": "exclude_from_gold_standard_employee_target",
        }
    return {
        "scope": DEFAULT_SCOPE,
        "signals": [],
        "standard_employee_action": "include",
    }


def curated_out_reason(label: str) -> str:
    return CURATED_OUT_ENTITLEMENT_LABELS.get(label.strip().casefold(), "")


def first_pattern_label(patterns: list[tuple[str, re.Pattern[str]]], text: str, *, fallback: str) -> str:
    for label, pattern in patterns:
        if pattern.search(text):
            return label
    return fallback


def provision_presence(text: str) -> str:
    return first_pattern_label(PROVISION_PRESENCE_PATTERNS, text, fallback="provision_language_observed")


def target_posture(text: str) -> str:
    return first_pattern_label(TARGET_POSTURE_PATTERNS, text, fallback="requires_semantic_review")


def evidence_state(text: str) -> str:
    return first_pattern_label(EVIDENCE_STATE_PATTERNS, text, fallback="usable_report_evidence")


def extract_quantum_signals(text: str) -> list[str]:
    normalised = normalise_docx_text(text)
    signals = set(re.findall(r"\$[\d,]+(?:\.\d+)?(?:\s+per\s+[A-Za-z]+)?", normalised))
    signals.update(re.findall(r"\b\d+(?:\.\d+)?\s*(?:paid\s+)?(?:days?|weeks?|hours?|%)\b", normalised, flags=re.I))
    return sorted(signals)


def parse_council_benchmark_entries(text: str) -> list[dict[str, Any]]:
    normalised = normalise_docx_text(text.replace("\n", " "))
    matches = list(re.finditer(r"(?<![A-Za-z])([A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*){0,3}):", normalised))
    entries: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        finding_start = match.end()
        finding_end = matches[index + 1].start() if index + 1 < len(matches) else len(normalised)
        finding = normalise_docx_text(normalised[finding_start:finding_end])
        if not finding:
            continue
        council = clean_council_name(match.group(1))
        if not council:
            continue
        scope_signals = specialist_scope_signals(finding)
        entries.append({
            "council": council,
            "finding": finding,
            "presence": provision_presence(finding),
            "quantum_signals": extract_quantum_signals(finding),
            "scope": "specialist_cohort" if scope_signals else DEFAULT_SCOPE,
            "scope_signals": scope_signals,
        })
    return entries


def target_aliases(target_council: str) -> set[str]:
    cleaned = re.sub(r"\b(city|shire|borough|council)\b", "", target_council, flags=re.I)
    aliases = {target_council.strip().lower(), normalise_docx_text(cleaned).lower()}
    first_word = target_council.split()[0].strip().lower() if target_council.split() else ""
    if first_word:
        aliases.add(first_word)
    return {alias for alias in aliases if alias}


def target_entry_from_comparators(entries: list[dict[str, Any]], target_council: str) -> dict[str, Any] | None:
    aliases = target_aliases(target_council)
    for entry in entries:
        council = str(entry.get("council") or "").lower()
        if council in aliases or any(alias and alias in council for alias in aliases):
            return entry
    return None


def comparison_basis(label: str, definition: str, benchmark_summary: str) -> str:
    text = f"{label} {definition} {benchmark_summary}".lower()
    if any(token in text for token in ["$", "allowance", "per week", "payment", "cash out"]):
        return "quantum_or_monetary_value"
    if any(token in text for token in ["days", "weeks", "leave"]):
        return "leave_duration_or_access"
    if any(token in text for token in ["provided", "available", "provision identified", "protections"]):
        return "presence_or_explicitness"
    return "semantic_equivalence"


def quantification_type(semantic_mapping: dict[str, Any]) -> str:
    comparator_signals = semantic_mapping["comparator_semantics"]["quantum_signals"]
    target_finding = semantic_mapping["target_semantics"].get("target_finding") or {}
    target_signals = target_finding.get("quantum_signals") if isinstance(target_finding, dict) else []
    basis = semantic_mapping["concept"]["comparison_basis"]
    if target_signals or comparator_signals:
        return "quantified_value"
    if basis in {"leave_duration_or_access", "quantum_or_monetary_value"}:
        return "quantification_required"
    if semantic_mapping["target_semantics"]["presence"] in {
        "no_specific_provision_identified",
        "not_clearly_matched",
        "provided",
        "baseline_only",
    }:
        return "binary_presence_or_absence"
    return "qualitative_condition"


def support_status_for_row(semantic_mapping: dict[str, Any], review_flags: list[str]) -> str:
    if "operator_recheck" in review_flags:
        return "not_supportable_until_rechecked"
    if semantic_mapping["target_semantics"]["presence"] in {"no_specific_provision_identified", "not_clearly_matched"}:
        return "negative_or_gap_claim_needs_source_confirmation"
    if semantic_mapping["quantification_semantics"]["quantification_type"] == "quantification_required":
        return "not_supportable_until_quantified"
    return "report_semantics_captured_source_refs_required_for_production"


def learning_action_for_row(review_flags: list[str], posture: str, presence: str, quant_type: str) -> str:
    if "operator_recheck" in review_flags:
        return "verify_numeric_or_clause_values_before_reuse"
    if quant_type == "quantification_required":
        return "extract_measurable_value_and_unit_from_source_clause"
    if presence in {"no_specific_provision_identified", "not_clearly_matched"}:
        return "separate_true_absence_from_extraction_gap"
    if posture in {"mixed_or_uncertain", "requires_semantic_review"}:
        return "ask_user_or_reviewer_to_confirm_comparator_interpretation"
    return "candidate_for_structured_report_generation"


def semantic_mapping_for_entitlement(
    *,
    category_label: str,
    label: str,
    definition: str,
    benchmark_summary: str,
    target_takeaway: str,
    target_council: str,
    tags: list[str],
    review_flags: list[str],
) -> dict[str, Any]:
    comparator_entries = parse_council_benchmark_entries(benchmark_summary)
    target_entry = target_entry_from_comparators(comparator_entries, target_council)
    standard_entries = [entry for entry in comparator_entries if entry.get("scope") == DEFAULT_SCOPE]
    specialist_entries = [entry for entry in comparator_entries if entry.get("scope") == "specialist_cohort"]
    posture = target_posture(target_takeaway)
    target_presence = provision_presence(
        " ".join([str(target_entry.get("finding")) if target_entry else "", target_takeaway])
    )
    semantic_state = evidence_state(" ".join([benchmark_summary, target_takeaway]))
    mapping = {
        "semantic_unit": "entitlement_condition_benefit",
        "concept": {
            "canonical_label_candidate": label,
            "working_definition": definition,
            "human_taxonomy_path": [category_label, label],
            "category": category_label,
            "clause_context_tags": tags,
            "comparison_basis": comparison_basis(label, definition, benchmark_summary),
        },
        "comparator_semantics": {
            "cohort_grain": "council_agreement",
            "entry_count": len(comparator_entries),
            "standard_employee_entry_count": len(standard_entries),
            "specialist_cohort_entry_count": len(specialist_entries),
            "entries": comparator_entries,
            "presence_mix": dict(sorted(Counter(entry["presence"] for entry in comparator_entries).items())),
            "quantum_signals": sorted({signal for entry in comparator_entries for signal in entry["quantum_signals"]}),
            "standard_employee_quantum_signals": sorted({signal for entry in standard_entries for signal in entry["quantum_signals"]}),
        },
        "target_semantics": {
            "target_council": target_council,
            "target_finding": target_entry,
            "presence": target_presence,
            "comparator_posture": posture,
            "scope_basis": target_entry.get("scope") if isinstance(target_entry, dict) else DEFAULT_SCOPE,
            "takeaway": target_takeaway,
        },
        "output_semantics": {
            "row_role": "benchmark_report_row",
            "decision_support_role": "helps a user understand whether the target agreement is aligned, stronger, weaker, unclear, or missing source evidence for this entitlement.",
        },
    }
    quant_type = quantification_type(mapping)
    target_finding = mapping["target_semantics"].get("target_finding") or {}
    mapping["quantification_semantics"] = {
        "quantification_type": quant_type,
        "target_quantum_signals": target_finding.get("quantum_signals", []) if isinstance(target_finding, dict) else [],
        "comparator_quantum_signals": mapping["comparator_semantics"]["quantum_signals"],
        "normalisation_required": quant_type in {"quantified_value", "quantification_required"},
        "supportable_output_requires": [
            "canonical entitlement id",
            "source agreement id",
            "page or clause reference",
            "extracted value and unit where measurable",
            "presence/absence state",
            "review state",
        ],
    }
    mapping["supportability_semantics"] = {
        "current_support_level": "downstream_report_exemplar",
        "production_support_status": support_status_for_row(mapping, review_flags),
        "support_boundary": "This report shows the semantic target. Production wiki facts still need source-linked EBA evidence.",
        "minimum_evidence": [
            "source_ref",
            "clause_or_section_title",
            "evidence_excerpt",
            "value_unit_basis_or_absence_reason",
            "review_state",
        ],
    }
    mapping["review_semantics"] = {
        "evidence_state": semantic_state,
        "review_flags": review_flags,
        "learning_action": learning_action_for_row(review_flags, posture, target_presence, quant_type),
    }
    return mapping


def clean_label_and_note(label: str) -> tuple[str, str]:
    note = ""
    note_match = re.search(r"\bI want to recheck these numbers\b", label, flags=re.I)
    if note_match:
        note = note_match.group(0)
        label = (label[: note_match.start()] + label[note_match.end() :]).strip()
    return label, note


def entitlement_record(row: list[str], *, category_label: str, ordinal: int, target_council: str) -> dict[str, Any]:
    first = row[0] if len(row) > 0 else ""
    benchmark_summary = row[1] if len(row) > 1 else ""
    target_takeaway = row[2] if len(row) > 2 else ""
    lines = [line.strip() for line in first.splitlines() if line.strip()]
    raw_label = lines[0] if lines else f"Entitlement {ordinal}"
    label, operator_note = clean_label_and_note(raw_label)
    definition = " ".join(lines[1:]).strip()
    combined = "\n".join([first, benchmark_summary, target_takeaway])
    review_flags = review_flags_for_text(combined)
    tags = tags_for_entitlement(category_label, combined)
    scope = row_scope_for_entitlement(label, definition)
    semantic_mapping = semantic_mapping_for_entitlement(
        category_label=category_label,
        label=label,
        definition=definition,
        benchmark_summary=benchmark_summary,
        target_takeaway=target_takeaway,
        target_council=target_council,
        tags=tags,
        review_flags=review_flags,
    )
    return {
        "entitlement_id": slugify(f"{category_label}-{label}") or f"entitlement-{ordinal}",
        "entitlement_label": label,
        "definition": definition,
        "category": category_label,
        "scope": scope,
        "clause_context_tags": tags,
        "semantic_mapping": semantic_mapping,
        "row_model": {
            "entitlement_and_definition": first,
            "council_benchmark_summary": benchmark_summary,
            "target_takeaway": target_takeaway,
        },
        "council_mentions": extract_council_mentions(benchmark_summary),
        "operator_note": operator_note,
        "review_flags": review_flags,
    }


def extract_report_payload(
    blocks: list[dict[str, Any]],
    *,
    source_path: Path,
    artifact_id: str,
    generated_at: str,
    include_specialist_cohorts: bool,
) -> dict[str, Any]:
    paragraphs = [block["text"] for block in blocks if block["type"] == "paragraph"]
    title = paragraphs[0] if paragraphs else source_path.stem
    subtitle = paragraphs[1] if len(paragraphs) > 1 else ""
    target_match = re.match(r"(.+?)\s+Enterprise Agreement", title, flags=re.I)
    target_council = target_match.group(1).strip() if target_match else ""

    benchmark_scope: dict[str, Any] = {}
    categories: list[dict[str, Any]] = []
    pending_paragraphs: list[str] = []
    category_counts: Counter[str] = Counter()
    council_mentions: set[str] = set()
    qa_queue: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []

    for block in blocks:
        if block["type"] == "paragraph":
            pending_paragraphs.append(block["text"])
            continue
        rows = block["rows"]
        if is_entitlement_table(rows):
            category_label = pending_paragraphs[-2] if len(pending_paragraphs) >= 2 else "Entitlements"
            description = pending_paragraphs[-1] if pending_paragraphs else ""
            entitlements = [
                entitlement_record(row, category_label=category_label, ordinal=index, target_council=target_council)
                for index, row in enumerate(rows[1:], start=1)
                if any(cell.strip() for cell in row)
            ]
            kept_entitlements = []
            for entitlement in entitlements:
                row_scope = entitlement["scope"]
                reason = curated_out_reason(entitlement["entitlement_label"])
                if reason:
                    excluded_rows.append({
                        "entitlement_id": entitlement["entitlement_id"],
                        "entitlement_label": entitlement["entitlement_label"],
                        "category": category_label,
                        "scope": row_scope,
                        "exclusion_reason": "curated_out_for_item_by_item_review",
                        "note": reason,
                    })
                    continue
                if row_scope["scope"] == "specialist_cohort_related" and not include_specialist_cohorts:
                    excluded_rows.append({
                        "entitlement_id": entitlement["entitlement_id"],
                        "entitlement_label": entitlement["entitlement_label"],
                        "category": category_label,
                        "scope": row_scope,
                        "exclusion_reason": "specialist_cohort_related",
                    })
                    continue
                kept_entitlements.append(entitlement)
                category_counts[category_label] += 1
                council_mentions.update(entitlement["council_mentions"])
                if "operator_recheck" in entitlement["review_flags"]:
                    qa_queue.append({
                        "item_id": entitlement["entitlement_id"],
                        "category": category_label,
                        "entitlement_label": entitlement["entitlement_label"],
                        "reason": entitlement["operator_note"] or "Explicit recheck marker found in report.",
                        "suggested_action": "Re-open the source clauses and verify the numeric comparator values before generating a final report.",
                    })
            categories.append({
                "category_id": slugify(category_label),
                "label": category_label,
                "description": description,
                "row_count": len(kept_entitlements),
                "excluded_row_count": len(entitlements) - len(kept_entitlements),
                "clause_context_tags": sorted({tag for item in kept_entitlements for tag in item["clause_context_tags"]}),
                "entitlements": kept_entitlements,
            })
        else:
            parsed_scope = parse_scope_table(rows)
            if parsed_scope:
                benchmark_scope = parsed_scope
        pending_paragraphs = []

    all_entitlements = [
        item
        for category in categories
        for item in category["entitlements"]
    ]
    explicit_review_items = len(qa_queue)
    source_gap_items = sum(
        1
        for item in all_entitlements
        if "source_gap" in item["review_flags"]
    )
    quantification_counts = Counter(
        item["semantic_mapping"]["quantification_semantics"]["quantification_type"]
        for item in all_entitlements
    )
    supportability_counts = Counter(
        item["semantic_mapping"]["supportability_semantics"]["production_support_status"]
        for item in all_entitlements
    )
    posture_counts = Counter(
        item["semantic_mapping"]["target_semantics"]["comparator_posture"]
        for item in all_entitlements
    )
    excluded_reason_counts = Counter(
        row.get("exclusion_reason", "unspecified")
        for row in excluded_rows
    )

    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "artifact_type": "downstream_analysis_exemplar",
        "title": title,
        "subtitle": subtitle,
        "description": "User-supplied exemplar for an entitlement benchmark report generated from EBA clause evidence.",
        "generated_at": generated_at,
        "scope_focus": WIKI_SCOPE_FOCUS,
        "wiki_role": "supporting_document_pattern",
        "source": {
            "source_kind": "user_supplied_docx",
            "source_path": str(source_path),
            "original_filename": source_path.name,
            "source_sha256": sha256_for_path(source_path),
        },
        "target_council": target_council,
        "summary": {
            "categories": len(categories),
            "entitlements": sum(category["row_count"] for category in categories),
            "comparator_councils_observed": len(council_mentions),
            "explicit_review_items": explicit_review_items,
            "source_gap_markers": source_gap_items,
            "row_model_fields": 3,
            "standard_employee_scope": not include_specialist_cohorts,
            "specialist_cohort_rows_excluded": excluded_reason_counts.get("specialist_cohort_related", 0),
            "curated_rows_excluded": excluded_reason_counts.get("curated_out_for_item_by_item_review", 0),
            "excluded_row_counts": dict(sorted(excluded_reason_counts.items())),
            "quantification_counts": dict(sorted(quantification_counts.items())),
            "supportability_counts": dict(sorted(supportability_counts.items())),
            "target_posture_counts": dict(sorted(posture_counts.items())),
        },
        "gold_comparator_target": {
            "target_id": "standard_employee_entitlement_benchmark_recreation",
            "objective": "Use the source EBAs for this comparator cohort to recreate the downstream entitlement benchmark output for standard employees.",
            "accuracy_target": GOLD_ACCURACY_TARGET,
            "accuracy_unit": "row_semantic_agreement",
            "seed_role": "thought_starter_and_comparator_council_selection",
            "gold_standard_source": source_path.name,
            "source_authority_rule": "The exemplar starts the taxonomy and council cohort; source EBAs decide final truth.",
            "target_council": target_council,
            "comparator_councils": sorted(council_mentions),
            "scope": DEFAULT_SCOPE if not include_specialist_cohorts else "all_reported_rows",
            "excluded_scope": ["specialist_cohort_related"] if not include_specialist_cohorts else [],
            "can_disagree_with_gold": True,
            "disagreement_rule": "A recreated row may disagree with the exemplar only when it provides source-linked evidence, explains the difference, and queues the item for review.",
            "pass_criteria": [
                "recreate the human category and entitlement row set",
                "match or explain the target-council presence/absence state",
                "extract equivalent values and units for quantifiable entitlements",
                "match comparator posture or provide evidence-backed disagreement",
                "flag unsupported, specialist-cohort, or ambiguous items instead of forcing a confident answer",
            ],
        },
        "engine_contract": {
            "operating_principle": "human_taxonomy_first_quantified_supportable_facts_underneath",
            "default_scope": DEFAULT_SCOPE,
            "specialist_cohort_policy": "excluded_from_gold_target_unless_explicitly_requested",
            "human_facing_taxonomy": {
                "grain": "entitlement, condition, or benefit",
                "top_level_categories": [category["label"] for category in categories],
                "category_nodes": [
                    {
                        "category_id": category["category_id"],
                        "label": category["label"],
                        "description": category["description"],
                        "entitlement_count": category["row_count"],
                        "tags": category["clause_context_tags"],
                    }
                    for category in categories
                ],
            },
            "supportable_entitlement_fact_shape": [
                "human taxonomy path",
                "canonical entitlement concept",
                "source agreement and page/clause evidence",
                "presence or absence state",
                "quantified value and unit where measurable",
                "comparator normalisation basis",
                "target-council comparator posture",
                "review state and learning action",
            ],
            "non_negotiables": [
                "Do not treat extracted words as knowledge until mapped to a human concept.",
                "Do not treat absence language as a fact without checking source coverage.",
                "Do not generate a benchmark row unless the value, presence state, or uncertainty is supportable.",
                "Keep operator review notes as first-class semantic signals.",
            ],
        },
        "report_shape": {
            "grain": "one row per entitlement definition",
            "category_names": [category["label"] for category in categories],
            "columns": [
                {
                    "id": "entitlement_and_definition",
                    "role": "Names the entitlement or condition and states the working definition used for matching.",
                },
                {
                    "id": "council_benchmark_summary",
                    "role": "Normalises comparator council findings into a compact cross-council summary.",
                },
                {
                    "id": "target_takeaway",
                    "role": "Explains how the target council compares and where evidence is strong, weak, or ambiguous.",
                },
            ],
        },
        "benchmark_scope": benchmark_scope,
        "categories": categories,
        "excluded_rows": excluded_rows,
        "qa_queue": qa_queue,
        "self_improvement_hooks": [
            "Grow a human-friendly entitlement taxonomy first, then map source clauses and quantified values underneath it.",
            "Promote entitlement labels into the clause-context language map when repeated across agreements.",
            "Prefer quantifiable supportable entitlement facts over loose summary text.",
            "Track source-gap markers separately from entitlement absence so missing text is not confused with a negative finding.",
            "Use explicit operator recheck notes as high-priority learning questions for the next extraction pass.",
            "Generate report rows only after each entitlement has source-linked evidence, comparator normalisation, and a target-council takeaway.",
        ],
        "wiki_implications": {
            "keep_as_artifact_not_reference": True,
            "why": "The document is a useful report pattern, but it is authored analysis rather than primary legal or policy source material.",
            "near_term_build": [
                "Add canonical entitlement definitions.",
                "Create a human-facing entitlement taxonomy that groups legal concepts in plain operational language.",
                "Map each definition to clause-context tags.",
                "Require quantification fields for measurable entitlements such as days, weeks, hours, percentages, and dollar amounts.",
                "Capture comparator summaries as structured row evidence.",
                "Expose review flags before report generation.",
            ],
        },
    }


def markdown_summary(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        f"# {payload['title']}",
        "",
        payload.get("subtitle", ""),
        "",
        "## Exemplar Role",
        "",
        "This is a downstream analysis pattern for entitlement, condition and benefit benchmarking. It should guide report generation, not primary legal interpretation.",
        "",
        "## Shape",
        "",
        f"- Categories: {summary['categories']}",
        f"- Entitlement rows: {summary['entitlements']}",
        f"- Observed comparator councils: {summary['comparator_councils_observed']}",
        f"- Explicit review items: {summary['explicit_review_items']}",
        f"- Source-gap markers: {summary['source_gap_markers']}",
        f"- Specialist cohort rows excluded: {summary['specialist_cohort_rows_excluded']}",
        f"- Curated rows excluded: {summary['curated_rows_excluded']}",
        "",
        "## Gold Comparator Target",
        "",
        f"- Objective: {payload['gold_comparator_target']['objective']}",
        f"- Seed role: {payload['gold_comparator_target']['seed_role']}",
        f"- Accuracy target: {payload['gold_comparator_target']['accuracy_target']:.0%}",
        f"- Scope: {payload['gold_comparator_target']['scope']}",
        f"- Can disagree with gold: {payload['gold_comparator_target']['can_disagree_with_gold']}",
        "",
        "## Semantic Contract",
        "",
        f"- Principle: {payload['engine_contract']['operating_principle']}",
        f"- Quantification mix: {summary['quantification_counts']}",
        f"- Supportability mix: {summary['supportability_counts']}",
        "",
        "## Categories",
        "",
    ]
    for category in payload["categories"]:
        lines.append(f"- {category['label']}: {category['row_count']} rows")
    lines.extend([
        "",
        "## Self-Improvement Hooks",
        "",
        *[f"- {item}" for item in payload["self_improvement_hooks"]],
        "",
    ])
    return "\n".join(line for line in lines if line is not None)


def update_manifest(wiki_root: Path, *, generated_at: str) -> None:
    path = wiki_root / "wiki-manifest.json"
    manifest = read_json(path) or {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "scope_focus": WIKI_SCOPE_FOCUS,
        "directories": {},
    }
    directories = manifest.setdefault("directories", {})
    for key, relative in {
        "document_maps": Path("wiki") / "document-maps",
        "reference_inputs": Path("wiki") / "reference-inputs",
        "pages": Path("wiki") / "pages",
        "language_maps": Path("wiki") / "language-maps",
        "patterns": Path("wiki") / "patterns",
        "issues": Path("wiki") / "issues",
        "learning_backlog": Path("wiki") / "learning-backlog",
        "questions": Path("wiki") / "questions",
        "runs": Path("wiki") / "runs",
        "artifacts": Path("wiki") / "artifacts",
    }.items():
        directories.setdefault(key, str(relative))
    manifest["generated_at"] = generated_at
    manifest["scope_focus"] = WIKI_SCOPE_FOCUS
    manifest[MANIFEST_ARTIFACT_SCHEMA_KEY] = ARTIFACT_SCHEMA_VERSION
    write_json(path, manifest)


def main_cli() -> None:
    args = parse_args()
    source_path = args.docx.resolve()
    if not source_path.exists():
        raise SystemExit(f"Downstream report DOCX not found: {source_path}")
    generated_at = utc_now_iso()
    wiki_root = args.wiki_root.resolve()
    artifact_dir = wiki_root / "artifacts" / "downstream-analysis-exemplars"
    payload = extract_report_payload(
        extract_docx_blocks(source_path),
        source_path=source_path,
        artifact_id=args.artifact_id,
        generated_at=generated_at,
        include_specialist_cohorts=args.include_specialist_cohorts,
    )
    write_json(artifact_dir / f"{args.artifact_id}.json", payload)
    if args.markdown:
        markdown_path = artifact_dir / f"{args.artifact_id}.md"
        markdown_path.write_text(markdown_summary(payload), encoding="utf-8")
    update_manifest(wiki_root, generated_at=generated_at)
    print(json.dumps({
        "schema_version": "wiki.downstream_report_exemplar_ingest.v1",
        "generated_at": generated_at,
        "artifact_id": args.artifact_id,
        "artifact_path": str(artifact_dir / f"{args.artifact_id}.json"),
        "summary": payload["summary"],
        "qa_queue": payload["qa_queue"],
    }, indent=2))


if __name__ == "__main__":
    main_cli()
