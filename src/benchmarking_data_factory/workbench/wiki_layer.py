from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable


DOCUMENT_MAP_SCHEMA_VERSION = "wiki.document_map.v1"
REFERENCE_INPUT_SCHEMA_VERSION = "wiki.reference_input.v1"
PILOT_RUN_SCHEMA_VERSION = "wiki.pilot_run.v1"
LANGUAGE_MAP_SCHEMA_VERSION = "wiki.language_map.v1"
QUESTION_SCHEMA_VERSION = "wiki.questions.v1"
LEARNING_BACKLOG_SCHEMA_VERSION = "wiki.learning_backlog.v1"
MANIFEST_SCHEMA_VERSION = "wiki.manifest.v1"
WIKI_SCOPE_FOCUS = "entitlements_conditions_benefits"
LANGUAGE_MAP_ID = "clause-context-terms"
MAX_DIRECTION_QUESTIONS_PER_DOCUMENT = 15


@dataclass(frozen=True)
class TagPattern:
    tag: str
    patterns: tuple[str, ...]


CLAUSE_FUNCTION_PATTERNS: tuple[TagPattern, ...] = (
    TagPattern("allowances", (r"\ballowance\b", r"\ballowances\b", r"\bfirst\s+aid\b", r"\btool\s+allowance\b", r"\btravel\s+allowance\b")),
    TagPattern("hours", (r"\bordinary\s+hours\b", r"\bhours\s+of\s+work\b", r"\bspan\s+of\s+hours\b", r"\brostered\s+hours\b")),
    TagPattern("overtime_penalties", (r"\bovertime\b", r"\btime\s+and\s+a\s+half\b", r"\bdouble\s+time\b", r"\bpenalty\s+rate\b", r"\bweekend\s+penalt")),
    TagPattern("leave_annual", (r"\bannual\s+leave\b", r"\bleave\s+loading\b", r"\bannual\s+leave\s+loading\b")),
    TagPattern("leave_personal_carers", (r"\bpersonal\s+leave\b", r"\bcarer'?s\s+leave\b", r"\bsick\s+leave\b")),
    TagPattern("leave_parental_family", (r"\bparental\s+leave\b", r"\bpartner\s+leave\b", r"\bfamily\s+leave\b")),
    TagPattern("leave_long_service", (r"\blong\s+service\s+leave\b", r"\blsl\b")),
    TagPattern("public_holidays", (r"\bpublic\s+holiday\b", r"\bpublic\s+holidays\b")),
    TagPattern("consultation", (r"\bconsultation\b", r"\bmajor\s+change\b", r"\bworkplace\s+change\b", r"\bchange\s+in\s+the\s+workplace\b")),
    TagPattern("dispute_resolution", (r"\bdispute\s+resolution\b", r"\bgrievance\b", r"\bdispute\b", r"\bfair\s+work\b")),
    TagPattern("flexibility", (r"\bflexibility\b", r"\bindividual\s+flexibility\b", r"\bflexible\s+work\b")),
    TagPattern("redundancy_redeployment", (r"\bredundancy\b", r"\bredeployment\b", r"\bseverance\b")),
    TagPattern("higher_duties", (r"\bhigher\s+duties\b", r"\bacting\s+allowance\b", r"\brelieving\s+allowance\b")),
    TagPattern("on_call_standby", (r"\bon[-\s]?call\b", r"\bstandby\b", r"\bavailability\s+allowance\b")),
    TagPattern("rostering", (r"\broster\b", r"\brostering\b", r"\bshift\s+work\b", r"\bshiftworker\b")),
    TagPattern("training_development", (r"\btraining\b", r"\bprofessional\s+development\b", r"\bstudy\s+assistance\b")),
    TagPattern("union_rights", (r"\bunion\b", r"\bdelegate\b", r"\bright\s+of\s+entry\b")),
    TagPattern("family_violence", (r"\bfamily\s+violence\b", r"\bdomestic\s+violence\b")),
    TagPattern("workload", (r"\bworkload\b", r"\bstaffing\b", r"\bwork\s+intensity\b")),
    TagPattern("remote_work", (r"\bremote\s+work\b", r"\bworking\s+from\s+home\b", r"\bwork\s+from\s+home\b")),
    TagPattern("termination", (r"\btermination\b", r"\bnotice\s+of\s+termination\b", r"\bsummary\s+dismissal\b")),
    TagPattern("superannuation", (r"\bsuperannuation\b", r"\bsuperannuation\s+contribution", r"\bsuper\b")),
    TagPattern("accident_makeup_pay", (r"\baccident\s+make[-\s]?up\s+pay\b", r"\bworkers?\s+compensation\b")),
)


CONTEXT_SCOPE_PATTERNS: tuple[TagPattern, ...] = (
    TagPattern("agreement_coverage", (r"\bcoverage\b", r"\bcovered\s+by\s+this\s+agreement\b", r"\bapplies\s+to\b", r"\bparties\s+to\s+this\s+agreement\b")),
    TagPattern("all_employee_context", (r"\ball\s+employees\b", r"\bordinary\s+employee", r"\bemployees\s+covered\b")),
    TagPattern("employment_type_context", (r"\bpart[-\s]?time\b", r"\bfull[-\s]?time\b", r"\bcasual\b", r"\btemporary\b", r"\bfixed\s+term\b", r"\bshiftworker\b")),
    TagPattern("classification_context", (r"\bclassification\b", r"\bclassifications\b", r"\bband\s+\d", r"\bband\s+level\b", r"\blevel\s+[a-d]\b", r"\bincrement\b")),
    TagPattern("band_responsibility_context", (
        r"\baccountability\s+(?:and|&)\s+extent\s+of\s+authority\b",
        r"\bextent\s+of\s+authority\b",
        r"\bjudg(?:e)?ment\s+(?:and|&)\s+decision[-\s]?making\b",
        r"\bspecialist\s+knowledge\s+and\s+skills\b",
        r"\bmanagement\s+skills\b",
        r"\binterpersonal\s+skills\b",
        r"\bqualifications?\s+and\s+experience\b",
        r"\bjob\s+(?:characteristics|descriptors)\b",
        r"\bkey\s+responsibilit(?:y|ies)\b",
        r"\bduties\s+and\s+responsibilit(?:y|ies)\b",
        r"\bposition\s+descriptions?\b",
    )),
    TagPattern("service_area_context", (r"\blibrary\b", r"\blocal\s+laws\b", r"\bparking\b", r"\bwaste\b", r"\boutdoor\b", r"\bindoor\b", r"\brecreation\b", r"\bcommunity\s+services\b")),
    TagPattern("schedule_context", (r"\bschedule\b", r"\bappendix\b", r"\bpart\s+[a-z]\b")),
    TagPattern("specialist_occupation_context", (r"\bnurse\b", r"\bnurses\b", r"\bmaternal\b", r"\bchild\s+health\b", r"\bearly\s+childhood\b", r"\bkindergarten\b", r"\baquatic\b", r"\bsenior\s+officer\b", r"\bexecutive\b")),
    TagPattern("external_or_excluded_context", (r"\bexcluded\b", r"\bnot\s+covered\b", r"\boutside\s+the\s+scope\b", r"\baward\s+applies\b", r"\bnot\s+apply\b")),
    TagPattern("implementation_context", (r"\bpayroll\b", r"\boperative\s+date\b", r"\bcommence\b", r"\btransition\b", r"\bgrandfather")),
)


LANGUAGE_PATTERNS: dict[str, tuple[str, ...]] = {
    "classification_structure": ("classification structure", "banded structure", "band level", "incremental structure", "classification definitions"),
    "band_responsibilities": (
        "accountability and extent of authority",
        "accountability & extent of authority",
        "judgement and decision making",
        "judgement & decision making",
        "judgment and decision making",
        "judgment & decision making",
        "specialist knowledge and skills",
        "management skills",
        "interpersonal skills",
        "qualifications and experience",
        "job characteristics",
        "job descriptors",
        "key responsibility areas",
        "duties and responsibilities",
    ),
    "position_descriptions": ("position description", "position descriptions"),
    "ordinary_hours": ("ordinary hours", "hours of work", "span of hours", "rostered hours"),
    "higher_duties": ("higher duties", "acting allowance", "relieving allowance"),
    "on_call_standby": ("on-call", "on call", "standby", "availability allowance"),
    "overtime_penalties": ("overtime", "time and a half", "double time", "penalty rate"),
    "allowances": ("allowance", "allowances", "first aid allowance", "tool allowance", "travel allowance"),
    "annual_leave": ("annual leave", "leave loading", "annual leave loading"),
    "personal_carers_leave": ("personal leave", "carer's leave", "carers leave", "sick leave"),
    "parental_family_leave": ("parental leave", "partner leave", "family leave"),
    "long_service_leave": ("long service leave", "lsl"),
    "public_holidays": ("public holiday", "public holidays"),
    "consultation": ("consultation", "major change", "workplace change", "change in the workplace"),
    "dispute_resolution": ("dispute resolution", "grievance", "dispute settling", "settlement of disputes"),
    "family_violence": ("family violence", "domestic violence"),
    "redundancy_redeployment": ("redundancy", "redeployment", "severance"),
    "training_development": ("training", "professional development", "study assistance"),
    "superannuation": ("superannuation", "superannuation contribution", "super"),
    "remote_work": ("remote work", "working from home", "work from home"),
    "termination_notice": ("termination", "notice of termination", "summary dismissal"),
}


CORE_CLAUSE_FUNCTIONS = {pattern.tag for pattern in CLAUSE_FUNCTION_PATTERNS}

HEADING_PATTERNS = (
    re.compile(r"^\s*((?:clause|section)\s+)?\d{1,3}(?:\.\d{1,3}){0,3}\s*[\).\:-]?\s+(.{3,110})$", re.I),
    re.compile(r"^\s*(part|schedule)\s+[a-z0-9]+[\s\).\:-]+(.{3,110})$", re.I),
    re.compile(r"^\s*(appendix)\s+[a-z0-9]+[\s\).\:-]+(.{3,110})$", re.I),
)
STANDALONE_CLAUSE_NUMBER_PATTERN = re.compile(r"^\s*\d{1,3}(?:\.\d{1,3}){0,4}\.?\s*$")
FWC_METADATA_HEADING_PATTERN = re.compile(
    r"^\s*(?:"
    r"\[\d{4}\]\s+fwca\b|"
    r"<ae\d+\s+pr\d+>|"
    r"(?:deputy\s+president|commissioner)(?:\s+[a-z'-]+)?$|"
    r"melbourne,\s+\d{1,2}\s+[a-z]+\s+\d{4}$|"
    r"decision$"
    r")",
    re.I,
)
DATE_LINE_PATTERN = re.compile(r"^\s*\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\b", re.I)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _safe_run_id(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_-]+", "-", value).strip("-")


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _pattern_hits(text: str, patterns: Iterable[TagPattern]) -> tuple[list[dict[str, Any]], Counter[str]]:
    lower_text = text.lower()
    tags: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for group in patterns:
        evidence_terms: list[str] = []
        score = 0
        for pattern in group.patterns:
            matches = re.findall(pattern, lower_text, flags=re.I)
            if matches:
                score += len(matches)
                evidence_terms.append(_pattern_label(pattern))
        if score:
            counts[group.tag] = score
            tags.append({
                "tag": group.tag,
                "score": score,
                "evidence_terms": sorted(set(evidence_terms)),
            })
    return sorted(tags, key=lambda item: (-item["score"], item["tag"])), counts


def _pattern_label(pattern: str) -> str:
    label = pattern.replace(r"\b", "").replace("\\s+", " ").replace("[-\\s]?", "-")
    label = re.sub(r"[^0-9A-Za-z _'-]+", "", label)
    return _normalise_space(label).lower()


def classify_text_block(text: str) -> dict[str, Any]:
    clause_tags, clause_counts = _pattern_hits(text, CLAUSE_FUNCTION_PATTERNS)
    context_tags, context_counts = _pattern_hits(text, CONTEXT_SCOPE_PATTERNS)
    function_names = set(clause_counts)
    has_core_clause = bool(function_names & CORE_CLAUSE_FUNCTIONS)
    has_specialist_or_excluded_context = bool(
        context_counts.get("specialist_occupation_context")
        or context_counts.get("external_or_excluded_context")
    )
    if has_core_clause and has_specialist_or_excluded_context:
        relevance = "needs_review"
    elif has_core_clause:
        relevance = "core_clause"
    elif context_counts.get("external_or_excluded_context"):
        relevance = "exclusion"
    elif context_counts:
        relevance = "context"
    else:
        relevance = "none"

    return {
        "clause_context_relevance": relevance,
        "clause_function": clause_tags,
        "context_scope": context_tags,
        "score": sum(clause_counts.values()) + sum(context_counts.values()),
    }


def page_text_quality(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "empty"
    if len(stripped) < 250:
        return "short"
    if len([line for line in stripped.splitlines() if line.strip()]) < 5:
        return "sparse"
    return "usable"


def is_probable_table_of_contents(text: str) -> bool:
    dot_leaders = len(re.findall(r"\.{6,}", text))
    numbered_entries = len(re.findall(
        r"\b\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z /&,'()\-]{4,90}\s+\.{3,}\s+\d+",
        text,
    ))
    stacked_number_title_entries = len(re.findall(
        r"(?m)^\s*\d{1,3}\.?\s*$\s*^\s*[A-Z][A-Za-z /&,'()\-]{4,90}\s*$",
        text,
    ))
    return dot_leaders >= 3 or numbered_entries >= 4 or stacked_number_title_entries >= 8


def page_role_for_text(
    text: str,
    *,
    page_num: int | None = None,
    headings: list[dict[str, Any]] | None = None,
) -> str:
    stripped = text.strip()
    lower_text = stripped.lower()
    quality = page_text_quality(text)
    if quality == "empty":
        return "weak_text"
    if re.search(r"\b\d{4}\s+fwca\b|\bs\.185\b|\bapplication\s+for\s+approval\b|\bcommission\s+must\s+approve\b", lower_text):
        return "approval_decision_front_matter"
    if re.search(r"\bundertaking\b.{0,80}\bsection\s+190\b|\bi,\s+[a-z ,.'-]+,\s+.*\bundertaking", lower_text, flags=re.S):
        return "undertaking_source_term"
    if is_probable_table_of_contents(stripped[:5000]):
        return "table_of_contents"
    heading_text = " ".join(
        str(item.get("heading") or item.get("title") or "")
        for item in (headings or [])
        if isinstance(item, dict)
    )
    heading_lower = heading_text.lower()
    if re.search(r"\b(?:schedule|appendix)\b", heading_lower):
        return "schedule_or_appendix"
    if re.search(r"\b(?:rates?|allowances?|classification|salary|wages?)\b", lower_text[:2200]) and len(re.findall(r"\$\s*\d|\b\d+(?:\.\d+)?\s*%", stripped)) >= 5:
        return "rates_or_allowances_table"
    if headings or classify_text_block(text)["score"]:
        return "agreement_text"
    if quality == "short":
        return "weak_text"
    return "unclassified_source_text"


def source_container_type_for_role(page_role: str, relevance: str = "") -> str:
    if page_role == "table_of_contents":
        return "table_of_contents_routing"
    if page_role == "approval_decision_front_matter":
        return "approval_decision_context"
    if page_role == "undertaking_source_term":
        return "undertaking_source_term"
    if page_role == "rates_or_allowances_table":
        return "rates_or_allowances_table"
    if page_role == "schedule_or_appendix":
        return "schedule_or_appendix_clause"
    if relevance == "core_clause":
        return "agreement_clause"
    if relevance in {"context", "exclusion", "needs_review"}:
        return "agreement_context_clause"
    return "source_text_section"


def source_container_type_for_text(text: str) -> str:
    headings = extract_heading_candidates(text, max_headings=6)
    role = page_role_for_text(text, headings=headings)
    relevance = classify_text_block(text)["clause_context_relevance"]
    return source_container_type_for_role(role, relevance)


def extract_heading_candidates(page_text: str, *, max_headings: int = 40) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    lines = page_text.splitlines()
    skip_line_indexes: set[int] = set()
    for line_index, raw_line in enumerate(lines):
        if line_index in skip_line_indexes:
            continue
        candidate = _candidate_heading_line(lines, line_index)
        line = candidate["line"]
        if not _looks_like_heading(line):
            continue
        title = _normalise_heading_title(line)
        if not title:
            continue
        if candidate["consumed_line_index"] is not None:
            skip_line_indexes.add(candidate["consumed_line_index"])
        headings.append({
            "line_index": line_index,
            "heading": line,
            "title": title,
            "confidence": _heading_confidence(line),
        })
        if len(headings) >= max_headings:
            break
    return headings


def _candidate_heading_line(lines: list[str], line_index: int) -> dict[str, Any]:
    line = _normalise_space(lines[line_index])
    if STANDALONE_CLAUSE_NUMBER_PATTERN.match(line):
        for next_index in range(line_index + 1, min(len(lines), line_index + 4)):
            next_line = _normalise_space(lines[next_index])
            if not next_line:
                continue
            if _standalone_heading_title(next_line):
                return {
                    "line": f"{line} {next_line}",
                    "consumed_line_index": next_index,
                }
            break
    return {"line": line, "consumed_line_index": None}


def _standalone_heading_title(line: str) -> bool:
    if len(line) < 3 or len(line) > 110:
        return False
    if line.endswith((",", ";", ".")):
        return False
    if STANDALONE_CLAUSE_NUMBER_PATTERN.match(line):
        return False
    if FWC_METADATA_HEADING_PATTERN.match(line) or DATE_LINE_PATTERN.match(line):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'&/-]*", line)
    if not words or len(words) > 12:
        return False
    domain_signals = {
        "allowance",
        "allowances",
        "annual",
        "classification",
        "compassionate",
        "consultation",
        "dispute",
        "employment",
        "hours",
        "leave",
        "overtime",
        "parental",
        "pay",
        "personal",
        "public",
        "redundancy",
        "roster",
        "salary",
        "superannuation",
        "termination",
        "training",
        "work",
    }
    lower_words = {word.lower().strip("'&/-") for word in words}
    if lower_words & domain_signals:
        return True
    first_letter = next((char for char in line if char.isalpha()), "")
    return bool(first_letter and first_letter.isupper() and len(words) <= 5)


def _looks_like_heading(line: str) -> bool:
    if len(line) < 4 or len(line) > 120:
        return False
    if line.endswith((",", ";")):
        return False
    if FWC_METADATA_HEADING_PATTERN.match(line) or DATE_LINE_PATTERN.match(line):
        return False
    if line.count(".") >= 5:
        return False
    for pattern in HEADING_PATTERNS:
        if pattern.match(line):
            return _heading_title_is_plausible(line)
    letters = [char for char in line if char.isalpha()]
    if 4 <= len(letters) <= 60:
        upper_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
        if upper_ratio > 0.72 and _uppercase_heading_has_domain_signal(line):
            return True
    return False


def _uppercase_heading_has_domain_signal(line: str) -> bool:
    lower_line = line.lower()
    domain_signals = (
        "allowance",
        "classification",
        "consultation",
        "dispute",
        "hours",
        "leave",
        "overtime",
        "pay",
        "progression",
        "redundancy",
        "roster",
        "salary",
        "schedule",
        "training",
        "wage",
    )
    return any(signal in lower_line for signal in domain_signals)


def _heading_title_is_plausible(line: str) -> bool:
    title = _normalise_heading_title(line)
    letters = [char for char in title if char.isalpha()]
    if len(letters) < 3:
        return False
    if title.count(".") >= 4:
        return False
    if re.search(r"\b(?:and|or|to|of|by)$", title, flags=re.I):
        return False
    first_letter = next((char for char in title if char.isalpha()), "")
    if first_letter and first_letter.islower():
        return False
    if re.match(r"^\(?[a-z]\)", title, flags=re.I):
        return False
    return True


def _normalise_heading_title(line: str) -> str:
    cleaned = line
    cleaned = re.sub(r"^\s*((?:clause|section)\s+)?\d{1,3}(?:\.\d{1,3}){0,3}\s*[\).\:-]?\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^\s*(part|schedule|appendix)\s+[a-z0-9]+[\s\).\:-]+", "", cleaned, flags=re.I)
    cleaned = _normalise_space(cleaned)
    return cleaned[:110]


def _heading_confidence(line: str) -> float:
    if re.match(r"^\s*((?:clause|section)\s+)?\d{1,3}(?:\.\d{1,3}){0,3}\s*[\).\:-]?\s+", line, flags=re.I):
        return 0.86
    if re.match(r"^\s*(part|schedule|appendix)\s+", line, flags=re.I):
        return 0.8
    return 0.62


def language_candidates_for_text(
    ae_id: str,
    page_num: int,
    text: str,
    *,
    source_ref_key: str = "agreement_id",
) -> list[dict[str, Any]]:
    lower_text = text.lower()
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for canonical_term, observed_terms in LANGUAGE_PATTERNS.items():
        for observed_term in observed_terms:
            if re.search(rf"\b{re.escape(observed_term.lower())}\b", lower_text):
                key = (canonical_term, observed_term.lower())
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({
                    "canonical_term": canonical_term,
                    "observed_term": observed_term.lower(),
                    "language_role": "canonical_term" if observed_term.lower().replace(" ", "_") == canonical_term else "local_alias",
                    "source_ref": {
                        source_ref_key: ae_id,
                        "page": page_num,
                    },
                    "review_state": "proposed",
                })
    return candidates


def build_document_map(
    ae_id: str,
    page_texts: list[str],
    *,
    metadata: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    generated_at = generated_at or utc_now_iso()
    pages: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    language_candidates: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    backlog: list[dict[str, Any]] = []
    relevance_counts: Counter[str] = Counter()
    function_counts: Counter[str] = Counter()
    context_counts: Counter[str] = Counter()
    page_role_counts: Counter[str] = Counter()
    context_question_count = 0
    question_cap_backlog_added = False

    for page_index, page_text in enumerate(page_texts):
        page_num = page_index + 1
        classification = classify_text_block(page_text)
        headings = extract_heading_candidates(page_text)
        text_quality = page_text_quality(page_text)
        page_role = page_role_for_text(page_text, page_num=page_num, headings=headings)
        relevance = classification["clause_context_relevance"]
        relevance_counts[relevance] += 1
        page_role_counts[page_role] += 1
        for tag in classification["clause_function"]:
            function_counts[tag["tag"]] += int(tag["score"])
        for tag in classification["context_scope"]:
            context_counts[tag["tag"]] += int(tag["score"])

        page_record = {
            "page": page_num,
            "char_count": len(page_text),
            "text_quality": text_quality,
            "page_role": page_role,
            "clause_context_relevance": relevance,
            "tags": {
                "clause_function": classification["clause_function"],
                "context_scope": classification["context_scope"],
            },
            "heading_count": len(headings),
        }
        pages.append(page_record)
        language_candidates.extend(language_candidates_for_text(ae_id, page_num, page_text))

        if relevance == "needs_review" and context_question_count < MAX_DIRECTION_QUESTIONS_PER_DOCUMENT:
            questions.append(_question(
                ae_id,
                "clause_context_scope",
                "clause_context_scope_needs_review",
                f"Page {page_num} mixes entitlement, condition, or benefit signals with specialist/exclusion context. Should this be mapped as a general clause, specialist context, excluded context, or reference-only?",
                page_num,
                priority="high",
            ))
            context_question_count += 1
        elif relevance == "needs_review" and not question_cap_backlog_added:
            backlog.append(_backlog_item(
                ae_id,
                "question_management",
                "clause_context_question_cap_reached",
                f"More than {MAX_DIRECTION_QUESTIONS_PER_DOCUMENT} pages need clause/context scope review. Surface additional prompts after the first batch is resolved.",
                None,
                priority="medium",
            ))
            question_cap_backlog_added = True
        if text_quality in {"empty", "short", "sparse"}:
            backlog.append(_backlog_item(
                ae_id,
                "text_quality",
                "weak_page_text",
                f"Page {page_num} has {text_quality} extracted text and may need OCR or manual review.",
                page_num,
                priority="medium" if text_quality != "empty" else "high",
            ))
        if not headings and classification["score"] >= 4 and text_quality == "usable":
            backlog.append(_backlog_item(
                ae_id,
                "document_mapping",
                "tagged_page_without_heading",
                f"Page {page_num} has useful tags but no detected heading. Improve heading detection or review manually.",
                page_num,
                priority="medium",
            ))
        if page_role == "table_of_contents" and classification["score"] >= 4:
            backlog.append(_backlog_item(
                ae_id,
                "document_spine",
                "contents_page_has_entitlement_terms",
                f"Page {page_num} appears to be a table of contents. Treat entitlement terms on this page as routing signals only.",
                page_num,
                priority="low",
            ))
        if page_role == "approval_decision_front_matter" and classification["score"] >= 4:
            backlog.append(_backlog_item(
                ae_id,
                "document_spine",
                "front_matter_has_entitlement_terms",
                f"Page {page_num} appears to be approval decision front matter. Use it as context, not ordinary agreement clause evidence.",
                page_num,
                priority="medium",
            ))

        sections.extend(_section_records_for_page(ae_id, page_num, page_text, headings, page_role=page_role))

    for section in sections:
        if not section["tags"]["clause_function"] and section["confidence"] < 0.75:
            backlog.append(_backlog_item(
                ae_id,
                "tagging",
                "untagged_heading",
                f"Heading '{section['heading']}' did not map cleanly to the current controlled vocabulary.",
                section["source_ref"]["page"],
                priority="low",
            ))

    summary = {
        "pages_scanned": len(page_texts),
        "sections_detected": len(sections),
        "headings_detected": sum(page["heading_count"] for page in pages),
        "page_role_counts": dict(sorted(page_role_counts.items())),
        "clause_context_relevance_counts": dict(sorted(relevance_counts.items())),
        "top_clause_functions": _counter_records(function_counts),
        "context_scope_counts": dict(sorted(context_counts.items())),
        "language_candidates": len(language_candidates),
        "questions": len(questions),
        "learning_backlog_items": len(backlog),
    }
    return {
        "schema_version": DOCUMENT_MAP_SCHEMA_VERSION,
        "agreement_id": ae_id,
        "agreement_name": metadata.get("agreement_name") or metadata.get("source_name") or ae_id,
        "generated_at": generated_at,
        "review_state": "proposed",
        "scope_focus": WIKI_SCOPE_FOCUS,
        "source": {
            "text_source": "extracted_pdf_text",
            "source_pdf_hash": metadata.get("source_pdf_hash") or metadata.get("content_hash") or "",
            "source_pdf": metadata.get("source_pdf") or metadata.get("pdf_path") or "",
        },
        "summary": summary,
        "pages": pages,
        "sections": sections,
        "language_candidates": language_candidates,
        "questions": questions,
        "learning_backlog": backlog,
    }


def build_reference_input_map(
    source_id: str,
    page_texts: list[str],
    *,
    metadata: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    generated_at = generated_at or utc_now_iso()
    pages: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    language_candidates: list[dict[str, Any]] = []
    backlog: list[dict[str, Any]] = []
    relevance_counts: Counter[str] = Counter()
    function_counts: Counter[str] = Counter()
    context_counts: Counter[str] = Counter()
    page_role_counts: Counter[str] = Counter()

    for page_index, page_text in enumerate(page_texts):
        page_num = page_index + 1
        classification = classify_text_block(page_text)
        headings = extract_heading_candidates(page_text)
        text_quality = page_text_quality(page_text)
        page_role = page_role_for_text(page_text, page_num=page_num, headings=headings)
        relevance = classification["clause_context_relevance"]
        relevance_counts[relevance] += 1
        page_role_counts[page_role] += 1
        for tag in classification["clause_function"]:
            function_counts[tag["tag"]] += int(tag["score"])
        for tag in classification["context_scope"]:
            context_counts[tag["tag"]] += int(tag["score"])

        pages.append({
            "page": page_num,
            "char_count": len(page_text),
            "text_quality": text_quality,
            "page_role": page_role,
            "clause_context_relevance": relevance,
            "tags": {
                "clause_function": classification["clause_function"],
                "context_scope": classification["context_scope"],
            },
            "heading_count": len(headings),
        })
        language_candidates.extend(
            language_candidates_for_text(source_id, page_num, page_text, source_ref_key="source_id")
        )

        if text_quality in {"empty", "short", "sparse"}:
            backlog.append(_backlog_item(
                source_id,
                "text_quality",
                "weak_reference_page_text",
                f"Reference page {page_num} has {text_quality} extracted text and may need OCR or manual review.",
                page_num,
                priority="medium" if text_quality != "empty" else "high",
                source_ref_key="source_id",
            ))
        if not headings and classification["score"] >= 4 and text_quality == "usable":
            backlog.append(_backlog_item(
                source_id,
                "reference_mapping",
                "tagged_reference_page_without_heading",
                f"Reference page {page_num} has useful tags but no detected heading. Improve heading detection or review manually.",
                page_num,
                priority="medium",
                source_ref_key="source_id",
            ))

        sections.extend(
            _section_records_for_page(
                source_id,
                page_num,
                page_text,
                headings,
                source_ref_key="source_id",
                section_ref_prefix="reference",
                page_role=page_role,
            )
        )

    for section in sections:
        if not section["tags"]["clause_function"] and section["confidence"] < 0.75:
            backlog.append(_backlog_item(
                source_id,
                "tagging",
                "untagged_reference_heading",
                f"Reference heading '{section['heading']}' did not map cleanly to the current controlled vocabulary.",
                section["source_ref"]["page"],
                priority="low",
                source_ref_key="source_id",
            ))

    summary = {
        "pages_scanned": len(page_texts),
        "sections_detected": len(sections),
        "headings_detected": sum(page["heading_count"] for page in pages),
        "page_role_counts": dict(sorted(page_role_counts.items())),
        "clause_context_relevance_counts": dict(sorted(relevance_counts.items())),
        "top_clause_functions": _counter_records(function_counts),
        "context_scope_counts": dict(sorted(context_counts.items())),
        "language_candidates": len(language_candidates),
        "learning_backlog_items": len(backlog),
    }
    return {
        "schema_version": REFERENCE_INPUT_SCHEMA_VERSION,
        "source_id": source_id,
        "source_name": metadata.get("source_name") or metadata.get("title") or source_id,
        "generated_at": generated_at,
        "review_state": "proposed",
        "scope_focus": WIKI_SCOPE_FOCUS,
        "source_kind": metadata.get("source_kind") or "reference_material",
        "knowledge_role": metadata.get("knowledge_role") or "interpretive_reference",
        "source": {
            "text_source": metadata.get("text_source") or "extracted_pdf_text",
            "source_pdf_hash": metadata.get("source_pdf_hash") or metadata.get("content_hash") or "",
            "source_pdf": metadata.get("source_pdf") or metadata.get("pdf_path") or "",
            "source_url": metadata.get("source_url") or "",
            "retrieved_at": metadata.get("retrieved_at") or "",
            "updated_at": metadata.get("updated_at") or "",
            "copyright_notice_detected": bool(metadata.get("copyright_notice_detected")),
        },
        "summary": summary,
        "pages": pages,
        "sections": sections,
        "language_candidates": language_candidates,
        "learning_backlog": backlog,
    }


CLAUSE_FUNCTION_TAGS = {pattern.tag for pattern in CLAUSE_FUNCTION_PATTERNS}


def _section_records_for_page(
    ae_id: str,
    page_num: int,
    page_text: str,
    headings: list[dict[str, Any]],
    *,
    source_ref_key: str = "agreement_id",
    section_ref_prefix: str = "",
    page_role: str = "agreement_text",
) -> list[dict[str, Any]]:
    lines = page_text.splitlines()
    sections: list[dict[str, Any]] = []
    for index, heading in enumerate(headings):
        start = heading["line_index"]
        end = headings[index + 1]["line_index"] if index + 1 < len(headings) else min(len(lines), start + 16)
        context = "\n".join(lines[start:end]).strip()
        classification = classify_text_block(context)
        section_prefix = f"{section_ref_prefix}:" if section_ref_prefix else ""
        sections.append({
            "section_id": f"{section_prefix}{ae_id}::p{page_num:04d}::h{index + 1:02d}",
            "heading": heading["heading"],
            "title": heading["title"],
            "confidence": heading["confidence"],
            "source_container_type": source_container_type_for_role(
                page_role,
                classification["clause_context_relevance"],
            ),
            "source_ref": {
                source_ref_key: ae_id,
                "page": page_num,
                "line_index": start,
            },
            "clause_context_relevance": classification["clause_context_relevance"],
            "tags": {
                "clause_function": classification["clause_function"],
                "context_scope": classification["context_scope"],
            },
            "evidence_excerpt": _normalise_space(context)[:650],
            "review_state": "proposed",
        })
    return sections


def _question(
    ae_id: str,
    question_type: str,
    code: str,
    prompt: str,
    page_num: int | None,
    *,
    priority: str,
    source_ref_key: str = "agreement_id",
) -> dict[str, Any]:
    suffix = f"p{page_num:04d}" if page_num is not None else "document"
    return {
        "question_id": f"{ae_id}::{code}::{suffix}",
        "agreement_id": ae_id,
        "question_type": question_type,
        "code": code,
        "prompt": prompt,
        "source_ref": {source_ref_key: ae_id, "page": page_num} if page_num is not None else {source_ref_key: ae_id},
        "priority": priority,
        "status": "open",
    }


def _backlog_item(
    ae_id: str,
    item_type: str,
    code: str,
    description: str,
    page_num: int | None,
    *,
    priority: str,
    source_ref_key: str = "agreement_id",
) -> dict[str, Any]:
    suffix = f"p{page_num:04d}" if page_num is not None else "document"
    return {
        "item_id": f"{ae_id}::{code}::{suffix}",
        "agreement_id": ae_id,
        "item_type": item_type,
        "code": code,
        "description": description,
        "source_ref": {source_ref_key: ae_id, "page": page_num} if page_num is not None else {source_ref_key: ae_id},
        "priority": priority,
        "status": "observed",
    }


def _counter_records(counter: Counter[str], *, limit: int = 8) -> list[dict[str, Any]]:
    return [
        {"tag": tag, "score": score}
        for tag, score in counter.most_common(limit)
    ]


def build_language_map(document_maps: Iterable[dict[str, Any]], *, generated_at: str) -> dict[str, Any]:
    terms: dict[str, dict[str, Any]] = {}
    for document_map in document_maps:
        for candidate in document_map.get("language_candidates") or []:
            if not isinstance(candidate, dict):
                continue
            canonical_term = str(candidate.get("canonical_term") or "").strip()
            observed_term = str(candidate.get("observed_term") or "").strip()
            if not canonical_term or not observed_term:
                continue
            term_record = terms.setdefault(canonical_term, {
                "canonical_term": canonical_term,
                "review_state": "proposed",
                "observed_terms": {},
            })
            observed = term_record["observed_terms"].setdefault(observed_term, {
                "observed_term": observed_term,
                "language_role": candidate.get("language_role") or "local_alias",
                "source_refs": [],
                "count": 0,
            })
            observed["count"] += 1
            source_ref = candidate.get("source_ref")
            if isinstance(source_ref, dict) and source_ref not in observed["source_refs"]:
                observed["source_refs"].append(source_ref)

    normalised_terms = []
    for term_record in terms.values():
        observed_terms = sorted(
            term_record["observed_terms"].values(),
            key=lambda item: (-int(item["count"]), item["observed_term"]),
        )
        for observed in observed_terms:
            observed["source_refs"] = observed["source_refs"][:8]
        normalised_terms.append({
            "canonical_term": term_record["canonical_term"],
            "review_state": term_record["review_state"],
            "observed_terms": observed_terms,
        })
    return {
        "schema_version": LANGUAGE_MAP_SCHEMA_VERSION,
        "generated_at": generated_at,
        "scope_focus": WIKI_SCOPE_FOCUS,
        "terms": sorted(normalised_terms, key=lambda item: item["canonical_term"]),
    }


def build_wiki_pilot(
    *,
    root: Path,
    ae_ids: list[str],
    page_text_loader: Callable[[str], list[str]],
    metadata_loader: Callable[[str], dict[str, Any] | None] | None = None,
    now: Callable[[], str] = utc_now_iso,
) -> dict[str, Any]:
    generated_at = now()
    run_id = "wiki-run-" + _safe_run_id(generated_at)
    wiki_root = root / "wiki"
    directories = {
        "document_maps": wiki_root / "document-maps",
        "reference_inputs": wiki_root / "reference-inputs",
        "pages": wiki_root / "pages",
        "language_maps": wiki_root / "language-maps",
        "patterns": wiki_root / "patterns",
        "issues": wiki_root / "issues",
        "learning_backlog": wiki_root / "learning-backlog",
        "questions": wiki_root / "questions",
        "runs": wiki_root / "runs",
        "artifacts": wiki_root / "artifacts",
    }
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)

    document_maps: list[dict[str, Any]] = []
    run_questions: list[dict[str, Any]] = []
    run_backlog: list[dict[str, Any]] = []
    for raw_ae_id in ae_ids:
        ae_id = raw_ae_id.lower().removesuffix(".pdf")
        metadata = metadata_loader(ae_id) if metadata_loader is not None else None
        page_texts = page_text_loader(ae_id)
        document_map = build_document_map(ae_id, page_texts, metadata=metadata, generated_at=generated_at)
        document_maps.append(document_map)
        run_questions.extend(document_map["questions"])
        run_backlog.extend(document_map["learning_backlog"])
        _json_write(directories["document_maps"] / f"{ae_id}.json", document_map)

    language_map = build_language_map(document_maps, generated_at=generated_at)
    questions_payload = {
        "schema_version": QUESTION_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "questions": run_questions,
    }
    backlog_payload = {
        "schema_version": LEARNING_BACKLOG_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "items": run_backlog,
    }
    run_summary = _run_summary(run_id, generated_at, document_maps, run_questions, run_backlog, language_map)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": generated_at,
        "scope_focus": WIKI_SCOPE_FOCUS,
        "directories": {key: str(path.relative_to(root)) for key, path in directories.items()},
        "latest_run_id": run_id,
        "latest_run_file": str((directories["runs"] / f"{run_id}.json").relative_to(root)),
        "document_map_schema_version": DOCUMENT_MAP_SCHEMA_VERSION,
        "language_map_schema_version": LANGUAGE_MAP_SCHEMA_VERSION,
    }

    _json_write(wiki_root / "wiki-manifest.json", manifest)
    _json_write(directories["language_maps"] / f"{LANGUAGE_MAP_ID}.json", language_map)
    _json_write(directories["questions"] / f"{run_id}.json", questions_payload)
    _json_write(directories["learning_backlog"] / f"{run_id}.json", backlog_payload)
    _json_write(directories["runs"] / f"{run_id}.json", run_summary)
    return run_summary


def _run_summary(
    run_id: str,
    generated_at: str,
    document_maps: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    backlog: list[dict[str, Any]],
    language_map: dict[str, Any],
) -> dict[str, Any]:
    relevance_counts: Counter[str] = Counter()
    function_counts: Counter[str] = Counter()
    for document_map in document_maps:
        relevance_counts.update(document_map.get("summary", {}).get("clause_context_relevance_counts") or {})
        for item in document_map.get("summary", {}).get("top_clause_functions") or []:
            if isinstance(item, dict):
                function_counts[str(item.get("tag"))] += int(item.get("score") or 0)
    return {
        "schema_version": PILOT_RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "scope_focus": WIKI_SCOPE_FOCUS,
        "mission_objectives": [
            "map_agreement_text",
            "map_entitlements_conditions_benefits",
            "build_clause_context_language_map",
            "surface_questions_and_learning_backlog",
        ],
        "summary": {
            "agreements_mapped": len(document_maps),
            "pages_scanned": sum(int(item.get("summary", {}).get("pages_scanned") or 0) for item in document_maps),
            "sections_detected": sum(int(item.get("summary", {}).get("sections_detected") or 0) for item in document_maps),
            "language_terms": len(language_map.get("terms") or []),
            "questions": len(questions),
            "learning_backlog_items": len(backlog),
            "clause_context_relevance_counts": dict(sorted(relevance_counts.items())),
            "top_clause_functions": _counter_records(function_counts),
        },
        "outputs": {
            "document_maps": [f"wiki/document-maps/{item['agreement_id']}.json" for item in document_maps],
            "language_map": f"wiki/language-maps/{LANGUAGE_MAP_ID}.json",
            "questions": f"wiki/questions/{run_id}.json",
            "learning_backlog": f"wiki/learning-backlog/{run_id}.json",
        },
    }


__all__ = [
    "DOCUMENT_MAP_SCHEMA_VERSION",
    "LANGUAGE_MAP_SCHEMA_VERSION",
    "PILOT_RUN_SCHEMA_VERSION",
    "REFERENCE_INPUT_SCHEMA_VERSION",
    "build_document_map",
    "build_reference_input_map",
    "build_language_map",
    "build_wiki_pilot",
    "classify_text_block",
    "extract_heading_candidates",
    "is_probable_table_of_contents",
    "language_candidates_for_text",
    "page_role_for_text",
    "page_text_quality",
    "source_container_type_for_role",
    "source_container_type_for_text",
]
