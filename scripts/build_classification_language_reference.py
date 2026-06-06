from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DEFAULT_REFERENCE_INPUT_DIR = ROOT / "wiki" / "reference-inputs"
DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "classification-language-reference"
SCHEMA_VERSION = "wiki.classification_language_reference.v1"
ARTIFACT_ID = "classification-language-reference"


PatternMap = dict[str, tuple[re.Pattern[str], ...]]


DESCRIPTOR_PATTERNS: PatternMap = {
    "accountability_authority": (
        re.compile(r"\baccountability\s+(?:and|&)\s+extent\s+of\s+authority\b", re.I),
        re.compile(r"\bextent\s+of\s+authority\b", re.I),
    ),
    "judgement_decision_making": (
        re.compile(r"\bjudg(?:e)?ment\s+(?:and|&)\s+decision[-\s]?making\b", re.I),
    ),
    "specialist_knowledge_skills": (
        re.compile(r"\bspecialist\s+knowledge\s+and\s+skills\b", re.I),
    ),
    "management_skills": (
        re.compile(r"\bmanagement\s+skills\b", re.I),
        re.compile(r"\bmanagerial\s+skills\b", re.I),
    ),
    "interpersonal_skills": (
        re.compile(r"\binterpersonal\s+skills\b", re.I),
    ),
    "qualifications_experience": (
        re.compile(r"\bqualifications?\s+and\s+experience\b", re.I),
    ),
    "duties_responsibilities": (
        re.compile(r"\bduties\s+and\s+responsibilit(?:y|ies)\b", re.I),
        re.compile(r"\bkey\s+responsibilit(?:y|ies|y\s+areas)\b", re.I),
    ),
}

ROLE_FAMILY_PATTERNS: PatternMap = {
    "physical_community_services": (
        re.compile(r"\bphysical\s*/?\s*community\s+services\b", re.I),
        re.compile(r"\bphysical\s+services\b", re.I),
        re.compile(r"\bcommunity\s+services\s+employees\b", re.I),
    ),
    "employees_other_than_physical_community": (
        re.compile(r"\bemployees\s+other\s+than\s+physical\s*/?\s*community\b", re.I),
        re.compile(r"\bother\s+than\s+physical\s*/?\s*community\s+services\b", re.I),
    ),
    "child_care_workers": (
        re.compile(r"\bchild\s+care\s+workers?\b", re.I),
    ),
    "senior_executive_officers": (
        re.compile(r"\bsenior\s+executive\s+officers?\b", re.I),
        re.compile(r"\bSEOs?\b", re.I),
    ),
}

PROCESS_PATTERNS: PatternMap = {
    "classification_definitions": (
        re.compile(r"\bclassification\s+definitions?\b", re.I),
        re.compile(r"\bappendix\s+a\b", re.I),
    ),
    "position_descriptions": (
        re.compile(r"\bposition\s+descriptions?\b", re.I),
    ),
    "annual_review": (
        re.compile(r"\bannual\s+review\b", re.I),
        re.compile(r"\breview\s+of\s+the\s+(?:level|band)\b", re.I),
    ),
    "entry_points": (
        re.compile(r"\bentry\s+points?\b", re.I),
        re.compile(r"\bminimum\s+classifications?\b", re.I),
    ),
    "higher_duties": (
        re.compile(r"\bhigher\s+duties\b", re.I),
    ),
    "multi_skilling": (
        re.compile(r"\bmulti[-\s]?skilling\b", re.I),
    ),
}

BAND_RANGE_PATTERNS: PatternMap = {
    "bands_1_to_5": (
        re.compile(r"\bbands?\s+1\s+(?:to|-)\s+5\b", re.I),
    ),
    "bands_3_to_8": (
        re.compile(r"\bbands?\s+3\s+(?:to|-)\s+8\b", re.I),
    ),
    "cross_over_bands_3_to_5": (
        re.compile(r"\bcross[-\s]?over\s+bands?\s+3\s+(?:to|-)\s+5\b", re.I),
    ),
    "bands_2_to_7": (
        re.compile(r"\bbands?\s+2\s+(?:to|-)\s+7\b", re.I),
    ),
}

SINGLE_BAND_RE = re.compile(r"\bband\s+([1-8])\b", re.I)
CLASSIFICATION_TERMS = {
    "band_responsibilities",
    "classification_structure",
    "position_descriptions",
    "higher_duties",
    "training_development",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def wiki_as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def compact_text(value: Any, *, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tag_names(record: dict[str, Any]) -> set[str]:
    payload = record.get("tags") if isinstance(record.get("tags"), dict) else {}
    names: set[str] = set()
    for key in ("clause_function", "context_scope"):
        for item in wiki_as_list(payload.get(key)):
            if isinstance(item, dict) and item.get("tag"):
                names.add(str(item["tag"]))
    return names


def matched_keys(text: str, patterns: PatternMap) -> list[str]:
    return sorted(
        key
        for key, expressions in patterns.items()
        if any(expression.search(text) for expression in expressions)
    )


def band_mentions(text: str) -> list[str]:
    mentions = set(matched_keys(text, BAND_RANGE_PATTERNS))
    for match in SINGLE_BAND_RE.findall(text):
        mentions.add(f"band_{match}")
    return sorted(mentions)


def source_ref_type(source_type: str) -> str:
    return "source_id" if source_type == "reference" else "agreement_id"


def section_is_classification_relevant(section: dict[str, Any]) -> bool:
    tags = tag_names(section)
    excerpt = str(section.get("evidence_excerpt") or "")
    if tags & {"band_responsibility_context", "classification_context"}:
        return True
    return bool(
        matched_keys(excerpt, DESCRIPTOR_PATTERNS)
        or matched_keys(excerpt, PROCESS_PATTERNS)
        or band_mentions(excerpt)
    )


def load_reference_inputs(reference_input_dir: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    if not reference_input_dir.exists():
        return payloads
    for path in sorted(reference_input_dir.glob("*.json")):
        payload = read_json(path)
        if isinstance(payload, dict) and payload.get("schema_version") == "wiki.reference_input.v1":
            payloads.append(payload)
    return payloads


def counter_records(counter: Counter[str], *, limit: int | None = None) -> list[dict[str, Any]]:
    items = counter.most_common(limit)
    return [{"id": key, "count": count} for key, count in items]


def examples_for_key(examples: dict[str, list[dict[str, Any]]], key: str, *, limit: int = 5) -> list[dict[str, Any]]:
    return examples.get(key, [])[:limit]


def add_example(examples: dict[str, list[dict[str, Any]]], key: str, example: dict[str, Any], *, limit: int = 5) -> None:
    bucket = examples[key]
    if len(bucket) >= limit:
        return
    comparable = (example.get("source_id"), example.get("page"), example.get("title"))
    if any((item.get("source_id"), item.get("page"), item.get("title")) == comparable for item in bucket):
        return
    bucket.append(example)


def build_payload(
    reference_inputs: Iterable[dict[str, Any]],
    *,
    generated_at: str | None = None,
    source_dir: Path | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now_iso()
    reference_payloads = list(reference_inputs)
    descriptor_counts: Counter[str] = Counter()
    role_family_counts: Counter[str] = Counter()
    process_counts: Counter[str] = Counter()
    band_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    descriptor_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    section_hits: list[dict[str, Any]] = []
    term_inventory: dict[str, dict[str, Any]] = {}
    pages_with_classification_tags = 0
    sections_scanned = 0

    for payload in reference_payloads:
        source_id = str(payload.get("source_id") or "").strip() or "unknown-source"
        source_name = str(payload.get("source_name") or source_id)
        source_summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        source_counts[source_id] = int(source_summary.get("context_scope_counts", {}).get("band_responsibility_context") or 0)

        for page in wiki_as_list(payload.get("pages")):
            if isinstance(page, dict) and tag_names(page) & {"band_responsibility_context", "classification_context"}:
                pages_with_classification_tags += 1

        for section in wiki_as_list(payload.get("sections")):
            if not isinstance(section, dict):
                continue
            sections_scanned += 1
            if not section_is_classification_relevant(section):
                continue
            excerpt = compact_text(section.get("evidence_excerpt"), limit=520)
            text = " ".join([
                str(section.get("heading") or ""),
                str(section.get("title") or ""),
                excerpt,
            ])
            descriptors = matched_keys(text, DESCRIPTOR_PATTERNS)
            roles = matched_keys(text, ROLE_FAMILY_PATTERNS)
            processes = matched_keys(text, PROCESS_PATTERNS)
            bands = band_mentions(text)
            tags = sorted(tag_names(section))
            ref = section.get("source_ref") if isinstance(section.get("source_ref"), dict) else {}
            page_num = ref.get("page")
            hit = {
                "source_id": source_id,
                "source_name": source_name,
                "section_id": section.get("section_id"),
                "title": section.get("title") or section.get("heading") or "Detected section",
                "page": page_num,
                "tags": tags,
                "descriptor_signals": descriptors,
                "role_family_signals": roles,
                "classification_process_signals": processes,
                "band_mentions": bands,
                "source_ref": {
                    source_ref_type("reference"): source_id,
                    "page": page_num,
                },
                "excerpt": excerpt,
                "review_state": section.get("review_state") or payload.get("review_state") or "proposed",
            }
            section_hits.append(hit)
            for key in descriptors:
                descriptor_counts[key] += 1
                add_example(descriptor_examples, key, {
                    "source_id": source_id,
                    "source_name": source_name,
                    "page": page_num,
                    "title": hit["title"],
                    "excerpt": excerpt,
                })
            for key in roles:
                role_family_counts[key] += 1
            for key in processes:
                process_counts[key] += 1
            for key in bands:
                band_counts[key] += 1

        for candidate in wiki_as_list(payload.get("language_candidates")):
            if not isinstance(candidate, dict):
                continue
            canonical_term = str(candidate.get("canonical_term") or "").strip()
            if canonical_term not in CLASSIFICATION_TERMS:
                continue
            observed_term = str(candidate.get("observed_term") or "").strip()
            language_counts[canonical_term] += 1
            term = term_inventory.setdefault(canonical_term, {
                "canonical_term": canonical_term,
                "observed_terms": Counter(),
                "source_refs": [],
            })
            if observed_term:
                term["observed_terms"][observed_term] += 1
            source_ref = candidate.get("source_ref") if isinstance(candidate.get("source_ref"), dict) else {}
            if source_ref and source_ref not in term["source_refs"]:
                term["source_refs"].append(source_ref)

    descriptor_records = [
        {
            "id": item["id"],
            "count": item["count"],
            "examples": examples_for_key(descriptor_examples, item["id"]),
        }
        for item in counter_records(descriptor_counts)
    ]
    term_records = []
    for term in sorted(term_inventory.values(), key=lambda item: item["canonical_term"]):
        term_records.append({
            "canonical_term": term["canonical_term"],
            "count": language_counts[term["canonical_term"]],
            "observed_terms": counter_records(term["observed_terms"]),
            "source_refs": term["source_refs"][:12],
        })

    section_hits.sort(key=lambda item: (str(item["source_id"]), int(item.get("page") or 0), str(item.get("title") or "")))
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": ARTIFACT_ID,
        "title": "Classification Language Reference",
        "wiki_role": "classification_language_reference",
        "scope_focus": "pay_classification_progression",
        "generated_at": generated_at,
        "source": {
            "reference_input_dir": str(source_dir or DEFAULT_REFERENCE_INPUT_DIR),
            "source_schema_version": "wiki.reference_input.v1",
        },
        "summary": {
            "reference_inputs_scanned": len(reference_payloads),
            "sections_scanned": sections_scanned,
            "classification_section_hits": len(section_hits),
            "pages_with_classification_tags": pages_with_classification_tags,
            "descriptor_signal_sections": sum(descriptor_counts.values()),
            "classification_language_candidates": sum(language_counts.values()),
            "source_band_responsibility_hits": dict(sorted(source_counts.items())),
        },
        "descriptor_signals": descriptor_records,
        "role_family_signals": counter_records(role_family_counts),
        "classification_process_signals": counter_records(process_counts),
        "band_mentions": counter_records(band_counts),
        "language_terms": term_records,
        "evidence": section_hits,
        "review_prompts": [
            {
                "id": "descriptor_field_ontology",
                "question": "Should the six recurring descriptor headings become first-class classification ontology fields?",
                "reason": "The reference materials repeatedly use the same descriptor headings to explain how band responsibility is assessed.",
            },
            {
                "id": "guide_family_boundary",
                "question": "Should Guide 1 and Guide 2 language be separated into different role-family lenses?",
                "reason": "The references distinguish Bands 1-5 Physical/Community Services and Bands 3-8 employees other than that stream.",
            },
            {
                "id": "pd_to_band_bridge",
                "question": "Should position-description fields from council job sources be mapped against these descriptor signals?",
                "reason": "The same language appears in PD guidance and could support later classification explanation or QA.",
            },
        ],
    }


def markdown_for_payload(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    lines = [
        "# Classification Language Reference",
        "",
        f"Generated: `{payload.get('generated_at')}`",
        "",
        "## Summary",
        "",
        f"- Reference inputs scanned: {summary.get('reference_inputs_scanned', 0)}",
        f"- Classification section hits: {summary.get('classification_section_hits', 0)}",
        f"- Descriptor signal matches: {summary.get('descriptor_signal_sections', 0)}",
        f"- Classification language candidates: {summary.get('classification_language_candidates', 0)}",
        "",
        "## Descriptor Signals",
        "",
    ]
    for item in wiki_as_list(payload.get("descriptor_signals")):
        lines.append(f"- `{item.get('id')}`: {item.get('count')} section hit(s)")
    lines.extend(["", "## Band And Role Language", ""])
    for item in wiki_as_list(payload.get("band_mentions"))[:12]:
        lines.append(f"- `{item.get('id')}`: {item.get('count')}")
    for item in wiki_as_list(payload.get("role_family_signals"))[:8]:
        lines.append(f"- `{item.get('id')}`: {item.get('count')}")
    lines.extend(["", "## Sample Evidence", ""])
    for hit in wiki_as_list(payload.get("evidence"))[:12]:
        page = hit.get("page")
        page_text = f"p. {page}" if page else "page not stated"
        signals = ", ".join(wiki_as_list(hit.get("descriptor_signals"))[:4]) or "classification language"
        lines.append(f"- {hit.get('source_name')} {page_text}: {hit.get('title')} (`{signals}`)")
    lines.extend(["", "## Review Prompts", ""])
    for prompt in wiki_as_list(payload.get("review_prompts")):
        lines.append(f"- {prompt.get('question')}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a source-linked classification language reference artifact.")
    parser.add_argument("--reference-input-dir", type=Path, default=DEFAULT_REFERENCE_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reference_input_dir = args.reference_input_dir.resolve()
    output_dir = args.output_dir.resolve()
    payload = build_payload(
        load_reference_inputs(reference_input_dir),
        generated_at=utc_now_iso(),
        source_dir=reference_input_dir,
    )
    json_path = output_dir / f"{payload['artifact_id']}.json"
    md_path = output_dir / f"{payload['artifact_id']}.md"
    write_json(json_path, payload)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "artifact_id": payload["artifact_id"],
        "artifact_path": str(json_path),
        "markdown_path": str(md_path),
        "summary": payload["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
