from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.entitlement_statistical_calibration import calibrate_binary_metric_groups

DEFAULT_WIKI_ROOT = ROOT / "wiki"
SCHEMA_VERSION = "wiki.entitlement_clause_evidence.v1"


AGREEMENT_ID_PATTERN = re.compile(r"ae\d+(?:__[a-z0-9_]+)?", re.I)


def normalise_entity_name(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def canonical_scalar(text: str, key: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith(f"{key}:"):
            continue
        parts = [line.split(":", 1)[1].strip()]
        for continuation in lines[index + 1:]:
            if continuation and not continuation.startswith((" ", "\t")):
                break
            if continuation.strip():
                parts.append(continuation.strip())
        return " ".join(part.strip("'\"") for part in parts if part).strip()
    return ""


def canonical_date(text: str, key: str) -> str:
    match = re.search(rf"^\s+{re.escape(key)}:\s*['\"]?(\d{{4}}-\d{{2}}-\d{{2}})", text, flags=re.M)
    return match.group(1) if match else ""


def canonical_optional_scalar(text: str, key: str) -> str:
    match = re.search(rf"^\s+{re.escape(key)}:\s*([^#\n]+)", text, flags=re.M)
    if not match:
        return ""
    value = match.group(1).strip().strip("'\"")
    return "" if value.lower() in {"null", "none", "~"} else value


@lru_cache(maxsize=1)
def canonical_metadata_index() -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for path in sorted((ROOT / "canonical").glob("*.yaml")):
        text = path.read_text(encoding="utf-8", errors="replace")
        agreement_id = canonical_scalar(text, "agreement_id") or path.stem
        rows.append({
            "agreement_id": agreement_id.lower(),
            "source_name": canonical_scalar(text, "source_name"),
            "estimated_earliest_commencing": canonical_date(text, "estimated_earliest_commencing"),
            "estimated_latest_commencing": canonical_date(text, "estimated_latest_commencing"),
            "expiry_date": canonical_optional_scalar(text, "expiry_date"),
            "superseded_by_ae_id": canonical_optional_scalar(text, "superseded_by_ae_id").lower(),
        })
    return tuple(rows)


def agreement_id_sort_value(agreement_id: str) -> int:
    match = re.match(r"ae(\d+)", agreement_id, flags=re.I)
    return int(match.group(1)) if match else 0


def split_suffix_matches_council(agreement_id: str, council: str) -> bool:
    if "__" not in agreement_id:
        return True
    suffix = normalise_entity_name(agreement_id.split("__", 1)[1])
    council_name = normalise_entity_name(council)
    return council_name in suffix or suffix in council_name


def metadata_matches_council(metadata: dict[str, str], council: str) -> bool:
    council_name = normalise_entity_name(council)
    source_name = normalise_entity_name(metadata.get("source_name", ""))
    agreement_id = metadata.get("agreement_id", "")
    if not council_name:
        return False
    if not split_suffix_matches_council(agreement_id, council):
        return False
    return council_name in source_name or (
        "__" in agreement_id and council_name in normalise_entity_name(agreement_id.split("__", 1)[1])
    )


def latest_agreement_for_council(council: str, fallback_agreement_id: str) -> dict[str, str]:
    fallback_agreement_id = fallback_agreement_id.lower()
    candidates = [
        row
        for row in canonical_metadata_index()
        if metadata_matches_council(row, council)
    ]
    if not candidates:
        return {"council": council, "agreement_id": fallback_agreement_id}
    latest = max(
        candidates,
        key=lambda row: (
            row.get("estimated_latest_commencing") or row.get("expiry_date") or "",
            row.get("estimated_earliest_commencing") or "",
            "__" in row.get("agreement_id", ""),
            agreement_id_sort_value(row.get("agreement_id", "")),
            row.get("agreement_id", ""),
        ),
    )
    return {
        "council": council,
        "agreement_id": latest["agreement_id"],
        "resolved_from_agreement_id": fallback_agreement_id,
        "latest_resolution": "latest_known_canonical_agreement",
    }


def resolve_latest_agreements(agreements: list[dict[str, str]]) -> list[dict[str, str]]:
    resolved: list[dict[str, str]] = []
    for row in agreements:
        resolved.append(latest_agreement_for_council(row["council"], row["agreement_id"]))
    return resolved


BASELINE_COMPARATOR_SEED_AGREEMENTS = [
    {"council": "Ararat", "agreement_id": "ae516638"},
    {"council": "Ballarat", "agreement_id": "ae507751"},
    {"council": "Central Goldfields", "agreement_id": "ae514569"},
    {"council": "Golden Plains", "agreement_id": "ae518094"},
    {"council": "Greater Bendigo", "agreement_id": "ae515509"},
    {"council": "Hepburn", "agreement_id": "ae515610"},
    {"council": "Moorabool", "agreement_id": "ae521210"},
    {"council": "Mount Alexander", "agreement_id": "ae530018"},
    {"council": "Pyrenees", "agreement_id": "ae521669"},
    {"council": "Wyndham", "agreement_id": "ae521909"},
]

AB_TEST_EXTENSION_SEED_AGREEMENTS = [
    {"council": "Queenscliffe", "agreement_id": "ae517676"},
    {"council": "Southern Grampians", "agreement_id": "ae519907"},
    {"council": "Maribyrnong", "agreement_id": "ae520997"},
    {"council": "Mansfield", "agreement_id": "ae527736"},
    {"council": "Knox", "agreement_id": "ae520361"},
    {"council": "Baw Baw", "agreement_id": "ae531830"},
    {"council": "Darebin", "agreement_id": "ae524045"},
    {"council": "Glen Eira", "agreement_id": "ae531815"},
]

VALIDATION_EXTENSION_SEED_AGREEMENTS = [
    {"council": "Greater Geelong", "agreement_id": "ae527986"},
    {"council": "East Gippsland", "agreement_id": "ae527123"},
    {"council": "Port Phillip", "agreement_id": "ae530369"},
    {"council": "Maroondah", "agreement_id": "ae518997"},
    {"council": "Stonnington", "agreement_id": "ae528516"},
]

BASELINE_COMPARATOR_AGREEMENTS = resolve_latest_agreements(BASELINE_COMPARATOR_SEED_AGREEMENTS)
AB_TEST_EXTENSION_AGREEMENTS = resolve_latest_agreements(AB_TEST_EXTENSION_SEED_AGREEMENTS)
VALIDATION_EXTENSION_AGREEMENTS = resolve_latest_agreements(VALIDATION_EXTENSION_SEED_AGREEMENTS)
COMPARATOR_AGREEMENTS = [*BASELINE_COMPARATOR_AGREEMENTS, *AB_TEST_EXTENSION_AGREEMENTS, *VALIDATION_EXTENSION_AGREEMENTS]


OUT_OF_SCOPE_PATTERNS = [
    ("seven_day_shift_worker", re.compile(r"\bseven\s+day\s+shift\s+worker|\bshift\s*worker|\bperiod\s+of\s+leave\b.{0,160}\bincreased\s+by\s+half\s+a\s+day\s+for\s+each\s+month|\boperation\s+of\s+33\.21\.11\b|\bprovisions\s+of\s+41\.9\.2\b", re.I)),
    ("public_holiday_roster", re.compile(r"\brostered\s+off\s+duty\s+on\s+a\s+holiday|\bpublic\s+holiday", re.I)),
    ("illness_recredit", re.compile(r"\bincapacitating\s+illness|\bpersonal\s+and\s+serious\s+illness|\bdebit\s+such\s+periods\s+of\s+(?:personal\s+and\s+serious\s+)?(?:incapacitating\s+)?illness\s+or\s+injury\b|\bgrant\s+such\s+employee\s+(?:additional\s+)?annual\s+leave\s+equivalent\s+to\s+the\s+period\s+of\s+(?:personal\s+)?illness", re.I)),
    ("nes_shift_baseline", re.compile(r"\bas\s+described\s+in\s+the\s+NES", re.I)),
    ("purchased_leave_model", re.compile(r"\bpurchas(?:e|ed|ing)\s+(?:of\s+)?(?:additional\s+)?(?:annual\s+)?leave|\bfractional\s+models?\s+of\s+employment|\bunpaid\s+annual\s+leave|\bindependent\s+financial\s+advice\b.{0,260}\badditional\s+annual\s+leave\b|\badditional\s+annual\s+leave\s+arrangement\b|\badditional\s+annual\s+leave\s+period\b.{0,360}\brevised\s+relevant\s+rate\s+of\s+pay\b|\b(?:salary\s+increase|overtime\s+worked)\b.{0,180}\badditional\s+annual\s+leave\s+period\b|\bperiod\s+of\s+(?:the\s+)?arrangement\b|\bperiod\s+of\s+time\s+off\s+requested\s+for\s+the\s+additional\s+leave\b|\brenewal\s+will\s+not\s+be\s+automatic\b", re.I)),
    ("top_of_band_payment", re.compile(r"\btop\s+of\s+band\s+payment\b|\bend\s+of\s+band\s+payment\b|\bend\s+of\s+band\s+recognition\b(?!.{0,260}\badditional\s+annual\s+leave\b).{0,260}\b(?:payment|reward|program|performance|RADAR)\b|\blump\s+sum\s+payment\b|\bRADAR\b|\bbonus\b|\bpayment\s+of\s+\$", re.I)),
    ("work_area_or_roster_specific", re.compile(r"\bstreet\s+sweeper\s+drivers?\b|\boperations\s+centre\s+employees\b|\bnight\s+shifts?\b|\bevening\s+shift\b|\bparking\s+enforcement\b|\blocal\s+laws\b", re.I)),
    ("specialist_mch_or_nurse", re.compile(r"\bmaternal\s*&?\s*child\s+health|\bimmunisation\s+nurses?|\bMCH\s+nurses?\b|\bnurses?\b|\(\s*A8\s*\)", re.I)),
    ("carer_special_needs", re.compile(r"\bprimary\s+carer\b|\bfamily\s+special\s+needs\b|\bprofound\s+and\s+significant\s+disability\b", re.I)),
    ("cash_out_annual_leave", re.compile(r"\bcash(?:ing)?\s+out\s+(?:of\s+)?(?:additional\s+)?annual\s+leave|\bannual\s+leave\s+cash[- ]?out\b|\bcash\s+out\s+any\s+annual\s+leave|\bfinancial\s+hardship\b.{0,220}\bcash", re.I)),
    ("existing_leave_admin", re.compile(r"\bChristmas[-\s]+New\s+Year\b.{0,260}\b(?:End\s+of\s+Band\s+Leave|Annual\s+Leave)\b|\bclosing\s+down\b.{0,260}\bcover\s+their\s+absence\b|\btake\s+Time-in-Lieu\b.{0,220}\bAnnual\s+Leave\b", re.I)),
]

SUBCLASS_BY_SIGNAL = {
    "purchased_leave_model": {
        "subclass_id": "leave-purchased-leave",
        "label": "Purchased Leave",
        "relationship": "adjacent_entitlement_subclass",
    },
    "top_of_band_payment": {
        "subclass_id": "conditions-top-of-band-payment",
        "label": "Top-of-Band Payment",
        "relationship": "non_leave_lookalike",
    },
    "specialist_mch_or_nurse": {
        "subclass_id": "leave-specialist-cohort-additional-leave",
        "label": "Specialist Cohort Additional Leave",
        "relationship": "excluded_specialist_lane",
    },
    "work_area_or_roster_specific": {
        "subclass_id": "leave-work-area-roster-specific-additional-leave",
        "label": "Work Area / Roster Specific Additional Leave",
        "relationship": "excluded_specialist_or_roster_lane",
    },
    "carer_special_needs": {
        "subclass_id": "leave-carer-special-needs-additional-leave",
        "label": "Carer Special Needs Additional Leave",
        "relationship": "adjacent_entitlement_subclass",
    },
    "seven_day_shift_worker": {
        "subclass_id": "leave-shift-worker-additional-annual-leave",
        "label": "Shift Worker Annual Leave",
        "relationship": "excluded_standard_baseline_or_roster_subclass",
    },
    "public_holiday_roster": {
        "subclass_id": "leave-public-holiday-roster-substitute",
        "label": "Public Holiday Roster Substitute",
        "relationship": "adjacent_entitlement_subclass",
    },
    "illness_recredit": {
        "subclass_id": "leave-illness-recredit",
        "label": "Illness Re-credit During Annual Leave",
        "relationship": "adjacent_entitlement_subclass",
    },
    "cash_out_annual_leave": {
        "subclass_id": "leave-annual-leave-cash-out",
        "label": "Annual Leave Cash-out",
        "relationship": "excluded_cashout_or_existing_leave_admin",
    },
    "existing_leave_admin": {
        "subclass_id": "leave-existing-leave-administration",
        "label": "Existing Leave Administration",
        "relationship": "excluded_existing_leave_admin",
    },
    "nes_shift_baseline": {
        "subclass_id": "leave-nes-shift-worker-baseline",
        "label": "NES Shift Worker Baseline",
        "relationship": "excluded_standard_baseline_or_roster_subclass",
    },
    "table_of_contents": {
        "subclass_id": "document-navigation-hit",
        "label": "Table of Contents Hit",
        "relationship": "document_navigation_noise",
    },
}

ACCEPTED_SUBCLASSES = {
    "service_end_of_band_recognition": {
        "subclass_id": "leave-additional-annual-leave.service-end-of-band-recognition",
        "label": "Service / End-of-Band Recognition Leave",
        "relationship": "accepted_entitlement_subclass",
    },
    "annual_leave_management_bonus": {
        "subclass_id": "leave-additional-annual-leave.annual-leave-management-bonus",
        "label": "Annual Leave Management Bonus Leave",
        "relationship": "accepted_entitlement_subclass",
    },
}


ADDITIONAL_ANNUAL_LEAVE_BOUNDARY = {
    "canonical_definition": (
        "Extra employer-funded paid leave granted above the NES or ordinary annual leave baseline for standard employees "
        "or a broad standard-employee subset. It excludes arrangements that merely fund, roster, cash out, re-credit, "
        "or pay for existing annual leave."
    ),
    "included": [
        "Extra paid leave above the NES or ordinary annual leave baseline.",
        "Extra paid leave days because of service recognition.",
        "Extra paid leave days because an employee is at the top or end of band.",
        "Extra paid leave days because annual leave balances are well managed.",
        "General workforce wellbeing/admin leave that functions as extra paid leave and is tied to annual leave management.",
    ],
    "excluded": [
        "Purchased leave funded through reduced pay.",
        "Shift-worker or NES annual leave uplift.",
        "Public-holiday roster substitutes or days in lieu.",
        "Specialist cohort leave such as MCH/nurse-only entitlements.",
        "Carer-special-needs leave unless a separate subclass is intentionally opened.",
        "Cashing out annual leave.",
        "Top-of-band cash payments.",
        "Illness re-credit while on annual leave.",
        "Work-area or roster-specific provisions.",
    ],
    "needs_review": [
        "Broad wellbeing leave not explicitly tied to annual leave management.",
        "Leave that applies to all employees only under a special operational model.",
        "Clauses that use additional annual leave wording but function like time off in lieu.",
    ],
}


ADDITIONAL_ANNUAL_LEAVE_PROFILE = {
    "artifact_id": "additional-annual-leave-clause-evidence",
    "entitlement_id": "leave-additional-annual-leave",
    "label": "Additional Annual Leave",
    "definition": ADDITIONAL_ANNUAL_LEAVE_BOUNDARY["canonical_definition"],
    "taxonomy_path": ["Leave", "Additional Annual Leave"],
    "classification_boundary": ADDITIONAL_ANNUAL_LEAVE_BOUNDARY,
    "policy_context_sources": [
        {
            "label": "Victorian Government Public Sector Industrial Relations Policies 2025 - Enterprise Bargaining and Agreement Making",
            "url": "https://www.vic.gov.au/public-sector-industrial-relations-policies-2025/steps-making-enterprise-agreements",
            "relevance": [
                "Leave provisions above NES minimums are treated as maintained bargaining entitlements.",
                "Performance-based bonuses or incentive payments are separated from entitlement leave analysis.",
            ],
        },
    ],
    "accepted_subclasses": list(ACCEPTED_SUBCLASSES.values()),
    "search_terms": [
        "additional annual leave",
        "additional day of annual leave",
        "additional days of annual leave",
        "top of band leave",
        "top of their band",
        "end of their current band",
        "end of band recognition",
        "end of band leave",
        "service recognition leave",
        "wellbeing and administration leave",
        "annual leave accrual is managed",
    ],
    "positive_patterns": [
        ("top_of_band_leave", re.compile(r"\btop\s+of\s+band\s+leave\b|\btop\s+of\s+their\s+band\b", re.I)),
        ("service_recognition_leave", re.compile(r"\bservice\s+recognition\s+leave\b", re.I)),
        ("end_of_band_recognition", re.compile(r"\bend\s+of\s+band\s+(?:recognition|leave)\b", re.I)),
        ("end_of_band_service_leave", re.compile(r"\bend\s+of\s+(?:their|the)\s+current\s+band\b", re.I)),
        ("wellbeing_admin_leave", re.compile(r"\bwellbeing\s+and\s+administration\s+leave\b|\bannual\s+leave\s+accrual\s+is\s+managed\b|\bencourage\s+employees\s+to\s+regularly\s+take\s+annual\s+leave\b", re.I)),
        (
            "extra_days_general_criteria",
            re.compile(r"\bone\s*\(1\)\s+or\s+two\s*\(2\)\s+additional\s+days?\s+of\s+annual\s+leave", re.I),
        ),
        ("additional_leave_qualification_criteria", re.compile(r"\bqualif(?:y|ies|ication)\s+for\s+the\s+additional\s+annual\s+leave", re.I)),
    ],
    "learned_hit_patterns": [
        (
            "learned_service_recognition_ladder",
            re.compile(
                r"\bservice\s+recognition\b.{0,260}\badditional\s+annual\s+leave\b|\bcompleted\s+\d+\s+years?\s+continuous\s+service\b.{0,260}\bservice\s+recognition\s+leave\s+days?\b",
                re.I,
            ),
        ),
        (
            "learned_end_of_band_extra_days",
            re.compile(
            r"\bend\s+of\s+(?:(?:their|the)\s+)?current\s+band\b.{0,420}\badditional\s+(?:\d+|one|two|three|five)\s+days?\b|\badditional\s+(?:\d+|one|two|three|five)\s+days?\b.{0,420}\bend\s+of\s+(?:(?:their|the)\s+)?current\s+band\b",
                re.I,
            ),
        ),
        (
            "learned_annual_leave_management_condition",
            re.compile(
                r"\bencourage\s+employees\s+to\s+regularly\s+take(?:\s+periods\s+of)?\s+annual\s+leave\b.{0,520}\b(?:access\s+to|qualif(?:y|ies|ication))\b.{0,220}\b(?:additional\s+days?\s+of\s+annual\s+leave|wellbeing\s+and\s+administration\s+leave)\b",
                re.I,
            ),
        ),
        (
            "learned_additional_leave_calculation",
            re.compile(
                r"\badditional\s+leave\s+will\s+be\s+calculated\b.{0,260}\bleave\s+loading\b|\bleave\s+loading\s+(?:does\s+not\s+apply|will\s+be\s+based)\b.{0,260}\badditional\s+(?:annual\s+)?leave\b",
                re.I,
            ),
        ),
    ],
    "candidate_patterns": [
        ("additional_annual_leave", re.compile(r"\badditional\s+annual\s+leave\b", re.I)),
        ("additional_day_of_annual_leave", re.compile(r"\badditional\s+days?\s+of\s+annual\s+leave\b", re.I)),
        ("additional_day_annual_leave", re.compile(r"\badditional\s+days?\s+annual\s+leave\b", re.I)),
        ("top_of_band", re.compile(r"\btop\s+of\s+(?:their|the)\s+band\b", re.I)),
        ("end_of_band", re.compile(r"\bend\s+of\s+(?:their|the)\s+current\s+band\b|\bend\s+of\s+band\s+(?:recognition|leave)\b", re.I)),
        ("service_recognition", re.compile(r"\bservice\s+recognition\s+leave\b", re.I)),
        ("wellbeing_admin_leave", re.compile(r"\bwellbeing\s+and\s+administration\s+leave\b", re.I)),
    ],
}


@dataclass(frozen=True)
class PageCandidate:
    page: int
    candidate_type: str
    matched_terms: list[str]
    out_of_scope_signals: list[str]
    score: int
    heading: str
    excerpt: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def agreement_name(agreement_id: str) -> str:
    agreement_id = agreement_id.lower()
    for metadata in canonical_metadata_index():
        if metadata["agreement_id"] == agreement_id:
            return metadata.get("source_name") or agreement_id.upper()
    return agreement_id.upper()


def agreement_label_for_all_cached(agreement_id: str) -> str:
    name = agreement_name(agreement_id)
    label = re.sub(r"\bEnterprise Agreement\b.*$", "", name, flags=re.I).strip()
    label = re.sub(r"\bEBA\b.*$", "", label, flags=re.I).strip()
    label = re.sub(r"\bEA\b.*$", "", label, flags=re.I).strip()
    label = re.sub(r"\s+\(\s*(?:No\.?|Number).*$", "", label, flags=re.I).strip()
    label = re.sub(r"^Application for approval of\s+", "", label, flags=re.I).strip()
    return label or name


def all_cached_agreements() -> list[dict[str, str]]:
    agreements: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for row in COMPARATOR_AGREEMENTS:
        agreements.append(dict(row))
        seen_ids.add(row["agreement_id"])
    for pages_path in sorted((ROOT / "cache").glob("ae*/pages.json")):
        agreement_id = pages_path.parent.name
        label = agreement_label_for_all_cached(agreement_id)
        latest = latest_agreement_for_council(label, agreement_id)
        if not (ROOT / "cache" / latest["agreement_id"] / "pages.json").exists():
            latest = {"council": label, "agreement_id": agreement_id}
        if latest["agreement_id"] in seen_ids:
            continue
        agreements.append(latest)
        seen_ids.add(latest["agreement_id"])
    return agreements


def load_pages(agreement_id: str) -> list[str]:
    path = ROOT / "cache" / agreement_id / "pages.json"
    if not path.exists():
        return []
    payload = read_json(path)
    return payload if isinstance(payload, list) else []


def source_ref(agreement_id: str, page: int | None, *, evidence_state: str, heading: str = "") -> dict[str, Any]:
    ref: dict[str, Any] = {
        "source_type": "agreement_cache_page",
        "agreement_id": agreement_id,
        "evidence_state": evidence_state,
    }
    if page is not None:
        ref["page"] = page
    if heading:
        ref["clause_heading"] = heading
    return ref


def labelled_patterns(patterns: list[tuple[str, re.Pattern[str]]]) -> list[dict[str, str]]:
    return [{"label": label, "pattern": pattern.pattern, "flags": "ignore_case"} for label, pattern in patterns]


def hit_discovery_method(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "unit_of_analysis": "cached agreement page text from cache/<agreement_id>/pages.json",
        "pipeline": [
            "Resolve each comparator council to its latest known canonical agreement, then load cached page text for that agreement.",
            "Mark a page as a candidate when the first matching candidate or learned hit-discovery pattern fires.",
            "Build a local excerpt around the first hit so the classifier sees surrounding clause context.",
            "Apply positive concept patterns for general-workforce extra annual leave concepts.",
            "Apply learned successful-hit patterns as secondary discovery and promotion signals, then retest rows that did not convert.",
            "Reject table-of-contents hits and hold pages with scope-control signals such as shift-worker, public-holiday, purchased-leave, carer-special-needs, or MCH/nurse provisions.",
            "Accept a source clause only when the excerpt has a positive concept signal, a leave signal, a value/time signal, and no out-of-scope signal.",
            "Extract page references, headings, excerpts, quantum signals, and normalised values where a value rule is available.",
        ],
        "candidate_patterns": labelled_patterns(profile["candidate_patterns"]),
        "positive_patterns": labelled_patterns(profile["positive_patterns"]),
        "learned_hit_patterns": labelled_patterns(profile.get("learned_hit_patterns", [])),
        "out_of_scope_patterns": labelled_patterns(OUT_OF_SCOPE_PATTERNS),
        "computed_scope_signals": ["table_of_contents"],
        "classification_boundary": profile.get("classification_boundary", {}),
        "policy_context_sources": profile.get("policy_context_sources", []),
        "accepted_subclasses": profile.get("accepted_subclasses", []),
        "adjacent_subclasses": list(SUBCLASS_BY_SIGNAL.values()),
        "score_rule": "10 points per positive pattern, 4 points for a leave signal, 3 points for a value/time signal, minus 5 points per out-of-scope signal.",
        "acceptance_rule": "positive concept signal + leave signal + value/time signal + no out-of-scope signal",
        "absence_rule": "No positive match means source-search absence, not final legal absence.",
        "reuse_rule": "The same profile can be run against any agreement with cached page text; improving the candidate, positive, exclusion, or value rules changes the machine rather than just this one output.",
        "refinement_levers": [
            "add local aliases that appear in new agreements",
            "add exclusion signals when a lookalike clause belongs to another entitlement subclass",
            "add normalisation rules for new value structures",
            "compare baseline and expanded cohorts to find precision/recall drift",
            "review false positives and false negatives as training examples",
        ],
    }


def excerpt_around_match(text: str, match: re.Match[str], *, before: int = 260, after: int = 1800) -> str:
    start = max(0, match.start() - before)
    end = min(len(text), match.end() + after)
    return compact_text(text[start:end])


def out_of_scope_signals(text: str) -> list[str]:
    return [label for label, pattern in OUT_OF_SCOPE_PATTERNS if pattern.search(text)]


def learned_pattern_labels(profile: dict[str, Any], text: str) -> list[str]:
    return [label for label, pattern in profile.get("learned_hit_patterns", []) if pattern.search(text)]


def is_probable_table_of_contents(text: str) -> bool:
    dot_leaders = len(re.findall(r"\.{6,}", text))
    leave_toc_entries = len(re.findall(r"\b[A-Z][A-Z /&,'()\-]{5,}\s+LEAVE\b\s+\.{3,}\s+\d+", text))
    numbered_toc_entries = len(re.findall(r"\b\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z /&,'()\-]{4,80}\s+\.{3,}\s+\d+", text))
    return dot_leaders >= 3 and (leave_toc_entries >= 2 or numbered_toc_entries >= 2)


def blocking_scope_signals(positive_labels: list[str], signals: list[str], excerpt: str) -> list[str]:
    blockers = list(signals)
    general_top_of_band = bool(
        {"top_of_band_leave", "end_of_band_recognition", "end_of_band_service_leave"}.intersection(positive_labels)
        and re.search(r"\bstaff\s+who\b|\bbanded\s+(?:employee|staff)\b", excerpt, flags=re.I)
    )
    if general_top_of_band and "specialist_mch_or_nurse" in blockers:
        blockers.remove("specialist_mch_or_nurse")
    general_clause_excludes_specialist = bool(
        "wellbeing_admin_leave" in positive_labels
        and re.search(r"\bshall\s+not\s+apply\s+to\s+employees\s+covered\s+by\s+schedule\b|\bprovisions\s+of\s+this\s+section\s+shall\s+not\s+apply\b", excerpt, flags=re.I)
    )
    if general_clause_excludes_specialist and "specialist_mch_or_nurse" in blockers:
        blockers.remove("specialist_mch_or_nurse")
    wellbeing_heading_present = bool(
        "wellbeing_admin_leave" in positive_labels
        and re.search(r"\bwellbeing\s+and\s+administration\s+leave\b.{0,520}\baccess\s+to\s+\d+\s+days?\s+of\s+wellbeing\s+and\s+administration\s+leave", excerpt, flags=re.I)
    )
    if wellbeing_heading_present and "purchased_leave_model" in blockers:
        blockers.remove("purchased_leave_model")
    service_recognition_extra_leave = bool(
        {"service_recognition_leave", "end_of_band_recognition", "end_of_band_service_leave", "learned_service_recognition_ladder", "learned_end_of_band_extra_days"}.intersection(positive_labels)
        and re.search(r"\bservice\s+recognition\b.{0,260}\badditional\s+annual\s+leave\b|\bwill\s+receive\s+an\s+additional\s+(?:one|two|three|five|\d+)\s+days?\s+annual\s+leave", excerpt, flags=re.I)
    )
    if service_recognition_extra_leave and "cash_out_annual_leave" in blockers:
        blockers.remove("cash_out_annual_leave")
    return blockers


def positive_context_valid(positive_labels: list[str], excerpt: str) -> bool:
    if "wellbeing_admin_leave" in positive_labels:
        return bool(re.search(
            r"\bwellbeing\s+and\s+administration\s+leave\b.{0,520}\baccess\s+to\s+\d+\s+days?\s+of\s+wellbeing\s+and\s+administration\s+leave|\bto\s+(?:continue\s+to\s+)?encourage\s+employees\s+to\s+regularly\s+take(?:\s+periods\s+of)?\s+annual\s+leave",
            excerpt,
            flags=re.I,
        ))
    if {"top_of_band_leave", "end_of_band_recognition", "end_of_band_service_leave", "learned_end_of_band_extra_days"}.intersection(positive_labels):
        return bool(re.search(
            r"\b(?:top|end)\s+of\s+(?:(?:their|the)\s+current\s+|their\s+|the\s+|current\s+)?band\b.{0,520}\badditional\s+(?:\d+|one|two|three|five)\s+days?\b|\bservice\s+recognition\b.{0,420}\badditional\s+annual\s+leave\b|\badditional\s+(?:\d+|one|two|three|five)\s+days?\b.{0,520}\b(?:top|end)\s+of\s+(?:(?:their|the)\s+current\s+|their\s+|the\s+|current\s+)?band\b|\btop\s+of\s+band\s+leave\b.{0,520}\badditional\s+day",
            excerpt,
            flags=re.I,
        ))
    return True


def has_leave_signal(text: str) -> bool:
    return bool(re.search(r"\bannual\s+leave\b|\brecognition\s+leave\b|\bwellbeing\s+and\s+administration\s+leave\b|\bleave\s+day/s?\b|\bleave\s+days?\b", text, flags=re.I))


def has_value_signal(text: str) -> bool:
    return bool(re.search(r"\b\d+\b|\bone\s*\(1\)|\btwo\s*\(2\)|\bthree\s*\(3\)|\bfive\s*\(5\)|\bper\s+annum\b|\byears?\b|\bdays?\b|\bweeks?\b", text, flags=re.I))


def discovery_patterns(profile: dict[str, Any]) -> list[tuple[str, re.Pattern[str]]]:
    return [*profile["candidate_patterns"], *profile.get("learned_hit_patterns", [])]


def discovery_matches(profile: dict[str, Any], text: str) -> list[tuple[int, str, re.Match[str]]]:
    matches: list[tuple[int, str, re.Match[str]]] = []
    for label, pattern in discovery_patterns(profile):
        for index, match in enumerate(pattern.finditer(text)):
            matches.append((match.start(), label, match))
            if index >= 7:
                break
    seen: set[tuple[int, str]] = set()
    deduped: list[tuple[int, str, re.Match[str]]] = []
    for start, label, match in sorted(matches, key=lambda item: item[0]):
        key = (start, label)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((start, label, match))
    return deduped[:48]


def best_match(profile: dict[str, Any], text: str) -> tuple[str, re.Match[str]] | None:
    matches = discovery_matches(profile, text)
    if not matches:
        return None
    _, label, match = sorted(matches, key=lambda item: item[0])[0]
    return label, match


def heading_from_excerpt(excerpt: str) -> str:
    patterns = [
        r"\b(\d+(?:\.\d+)*\.?\s+[A-Z][A-Z /&,'()\-]+LEAVE)\b",
        r"\b(\d+(?:\.\d+)*\.?\s+[A-Z][a-zA-Z /&,'()\-]+leave)\b",
        r"\b([A-Z][A-Z /&,'()\-]{4,80} LEAVE)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, excerpt)
        if match:
            heading = compact_text(match.group(1)).title()
            return heading if len(heading) <= 90 else ""
    return ""


def page_candidates(profile: dict[str, Any], agreement_id: str) -> list[PageCandidate]:
    candidates: list[PageCandidate] = []
    for index, page_text in enumerate(load_pages(agreement_id), start=1):
        page_matches = discovery_matches(profile, page_text)
        if not page_matches:
            continue
        page_candidates_for_match: list[PageCandidate] = []
        for _, label, match in page_matches:
            excerpt = excerpt_around_match(page_text, match)
            positive_labels = [
                positive_label
                for positive_label, positive_pattern in profile["positive_patterns"]
                if positive_pattern.search(excerpt)
            ]
            positive_labels = sorted({*positive_labels, *learned_pattern_labels(profile, excerpt)})
            raw_scope_signals = out_of_scope_signals(excerpt)
            if is_probable_table_of_contents(excerpt):
                raw_scope_signals.append("table_of_contents")
            scope_signals = blocking_scope_signals(positive_labels, raw_scope_signals, excerpt)
            leave_signal = has_leave_signal(excerpt)
            value_signal = has_value_signal(excerpt)
            is_positive = bool(positive_labels) and positive_context_valid(positive_labels, excerpt) and leave_signal and value_signal and not scope_signals
            candidate_type = "source_clause_match" if is_positive else "out_of_scope_or_context_match"
            score = (10 * len(positive_labels)) + (4 if leave_signal else 0) + (3 if value_signal else 0) - (5 * len(scope_signals))
            page_candidates_for_match.append(
                PageCandidate(
                    page=index,
                    candidate_type=candidate_type,
                    matched_terms=sorted({label, *positive_labels}),
                    out_of_scope_signals=scope_signals,
                    score=score,
                    heading=heading_from_excerpt(excerpt),
                    excerpt=excerpt,
                )
            )
        candidates.append(sorted(
            page_candidates_for_match,
            key=lambda item: (item.candidate_type == "source_clause_match", item.score),
            reverse=True,
        )[0])
    return sorted(candidates, key=lambda item: (-item.score, item.page))


def numeric_signal(raw: str) -> str:
    text = compact_text(raw)
    replacements = {
        "one (1)": "1",
        "two (2)": "2",
        "three (3)": "3",
        "four (4)": "4",
        "five (5)": "5",
        "six (6)": "6",
        "ten (10)": "10",
        "eleven (11)": "11",
        "fifteen (15)": "15",
        "sixteen (16)": "16",
    }
    lowered = text.lower()
    for src, dst in replacements.items():
        lowered = lowered.replace(src, dst)
    for src, dst in {
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "ten": "10",
        "eleven": "11",
        "fifteen": "15",
        "sixteen": "16",
    }.items():
        lowered = re.sub(rf"\b{src}\b", dst, lowered)
    return lowered


def quantum_signals(text: str) -> list[str]:
    normalised = numeric_signal(text)
    signals: set[str] = set()
    for pattern in [
        r"\b\d+\s+additional\s+days?\b",
        r"\badditional\s+\d+\s+days?\b",
        r"\b\d+\s+days?\s+annual\s+leave\b",
        r"\b\d+\s+days?\b",
        r"\b\d+\s+years?\b",
        r"\b\d+\s+weeks?\b",
        r"\b\d+\s+hours?\b",
    ]:
        for match in re.finditer(pattern, normalised, flags=re.I):
            signals.add(compact_text(match.group(0)))
    return sorted(signals, key=lambda item: (len(item), item))[:12]


def total_days_from_fragment(fragment: str, fallback_days: str) -> str:
    total_match = re.search(r"\((\d+)\s+additional\s+(?:leave\s+)?days?\s+in\s+total\)", fragment, flags=re.I)
    return total_match.group(1) if total_match else fallback_days


def value_record(value: str, unit: str, condition: str, subclass_key: str) -> dict[str, str]:
    subclass = ACCEPTED_SUBCLASSES[subclass_key]
    return {
        "value": value,
        "unit": unit,
        "condition": condition,
        "subclass_id": subclass["subclass_id"],
        "subclass_label": subclass["label"],
    }


def dedupe_values(values: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[dict[str, str]] = []
    for item in values:
        key = (
            str(item.get("value") or ""),
            str(item.get("unit") or ""),
            str(item.get("condition") or ""),
            str(item.get("subclass_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def annual_leave_management_values(text: str, raw_text: str) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    if (
        "1 or 2 additional days of annual leave" in text
        or "1 or 2 additional days annual leave" in text
        or re.search(r"access\s+1\s+additional\s+days?\s+annual\s+leave.{0,180}access\s+2\s+additional\s+days?\s+of\s+annual\s+leave", text, flags=re.I)
    ):
        values.append(value_record(
            "1 or 2",
            "days per annum",
            "leave/RDO accrual management criteria at the qualifying date",
            "annual_leave_management_bonus",
        ))
    match = re.search(r"access\s+to\s+(\d+)\s+days?\s+of\s+wellbeing\s+and\s+administration\s+leave\s+per\s+annum", text, flags=re.I)
    if match:
        values.append(value_record(
            match.group(1),
            "days of wellbeing and administration leave per annum",
            "annual leave balance management criteria at the qualifying date",
            "annual_leave_management_bonus",
        ))
    if re.search(r"top\s+of\s+(?:their|the)\s+band\s+for\s+1\s+year\s+or\s+more", text, flags=re.I):
        values.append(value_record(
            "1",
            "additional day each year",
            "staff at the top of band for one year or more",
            "service_end_of_band_recognition",
        ))
    return values


def end_of_band_values(text: str) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    pattern = re.compile(
        r"end\s+of\s+(?:their|the)\s+current\s+band(?:,\s*)?(?:\s+(?:plus|for))?\s+(\d+)\s+years?.{0,260}?(?:receive|entitled\s+to|provided).{0,80}?(\d+)\s+(?:additional\s+)?(?:leave\s+)?days?",
        flags=re.I,
    )
    for match in pattern.finditer(text):
        years = match.group(1)
        fragment = text[match.start():match.end() + 120]
        days = total_days_from_fragment(fragment, match.group(2))
        values.append(value_record(
            days,
            "additional leave days per annum total" if int(days) > 1 else "additional day per annum",
            f"banded employee at end of current band for {years} year{'s' if years != '1' else ''}",
            "service_end_of_band_recognition",
        ))
    return values


def service_recognition_values(text: str) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    pattern = re.compile(
        r"completed\s+(\d+)\s+years\s+continuous\s+service.{0,220}?receive\s+(\d+)\s+non-cumulative\s+service\s+recognition\s+leave\s+days?",
        flags=re.I,
    )
    for match in pattern.finditer(text):
        years, days = match.groups()
        values.append(value_record(
            days,
            "non-cumulative service recognition leave day(s) per annum",
            f"permanent full-time or part-time employee with {years} years continuous service",
            "service_end_of_band_recognition",
        ))
    return values


def clause_values_for_council(council: str, evidence_text: str) -> list[dict[str, str]]:
    del council
    text = numeric_signal(evidence_text)
    values: list[dict[str, str]] = []
    values.extend(annual_leave_management_values(text, evidence_text))
    values.extend(end_of_band_values(text))
    values.extend(service_recognition_values(text))
    return dedupe_values(values)


def candidate_subclass(candidate: PageCandidate) -> dict[str, str]:
    for signal in candidate.out_of_scope_signals:
        if signal in SUBCLASS_BY_SIGNAL:
            return SUBCLASS_BY_SIGNAL[signal]
    terms = set(candidate.matched_terms)
    if candidate.candidate_type == "source_clause_match":
        if {"wellbeing_admin_leave", "extra_days_general_criteria", "additional_leave_qualification_criteria", "learned_annual_leave_management_condition"}.intersection(terms):
            return ACCEPTED_SUBCLASSES["annual_leave_management_bonus"]
        if {"service_recognition", "service_recognition_leave", "end_of_band", "end_of_band_recognition", "end_of_band_service_leave", "top_of_band", "top_of_band_leave", "learned_service_recognition_ladder", "learned_end_of_band_extra_days", "learned_additional_leave_calculation"}.intersection(terms):
            return ACCEPTED_SUBCLASSES["service_end_of_band_recognition"]
    if "table_of_contents" in candidate.out_of_scope_signals:
        return SUBCLASS_BY_SIGNAL["table_of_contents"]
    return {
        "subclass_id": "leave-additional-annual-leave.needs-review",
        "label": "Needs Review",
        "relationship": "candidate_context_needs_review",
    }


def finding_for_evidence(council: str, candidates: list[PageCandidate]) -> str:
    evidence_text = " ".join(candidate.excerpt for candidate in candidates)
    values = clause_values_for_council(council, evidence_text)
    if values:
        return "; ".join(f"{item['value']} {item['unit']} for {item['condition']}" for item in values)
    first = candidates[0].excerpt if candidates else ""
    sentence = re.split(r"(?<=[.!?])\s+", first)[0] if first else ""
    return sentence or "Source clause observed, but the value needs reviewer normalisation."


def evidence_clause_label(candidate: PageCandidate) -> str:
    subclass = candidate_subclass(candidate)
    return candidate.heading or subclass.get("label") or "Clause evidence"


RELEVANT_EVIDENCE_PATTERN = re.compile(
    r"\badditional\s+(?:annual\s+)?leave\b|\badditional\s+(?:\d+|one|two|three|five)\s+days?\b|"
    r"\bservice\s+recognition\b|\bend\s+of\s+band\b|\btop\s+of\s+band\b|"
    r"\bwellbeing\s+and\s+administration\s+leave\b|\bannual\s+leave\s+(?:accrual|balance)\b|"
    r"\bleave\s+loading\b|\bqualif(?:y|ies|ication)\b|\bemployed\s+by\s+Council\s+for\s+at\s+least\s+12\s+months\b",
    re.I,
)


CURATION_EXCLUSION_PATTERN = re.compile(
    r"\bmaternal\s*(?:&|and)?\s*child\s+health\b|\bMCH\s+nurses?\b|\bimmunisation\s+nurses?\b|\bregistered\s+nurses?\b|"
    r"\bpurchas(?:e|ed|ing)\s+(?:of\s+)?(?:additional\s+)?(?:annual\s+)?leave\b|\bcash(?:ing)?\s+out\b|"
    r"\bgender\s+equity\b|\bbereavement\b|\bcompassionate\s+leave\b|"
    r"\bNotwithstanding\s+the\s+existing\s+service\s+recognition\s+leave\s+provisions\b|\bautomatically\s+forfeit\b|"
    r"\bWORKS\s+PLANNING\s+SYSTEMS\s+AND\s+PROCESSES\b|\bresponsibility\s+of\s+each\s+eligible\s+employee\b",
    re.I,
)


SEGMENT_BOUNDARY_PATTERN = re.compile(
    r"(?:(?<!Clause)\s+(?=(?:"
    r"\d+(?:\.\d+){1,5}\.?\s+|"
    r"[a-z]\.\s+(?:If|This|End|For|Full|Part|To|All|Commencing|The|Where)\b|"
    r"•\s+"
    r"))|(?<!in)\s+(?=\([a-zivx]+\)\s+))",
    re.I,
)


SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.;:])\s+(?=(?:If|This|For|The|Each|Commencing|Where|To qualify)\b)")


def clean_evidence_segment(segment: str) -> str:
    text = compact_text(segment)
    text = re.sub(r"^Page\s+\d+\s+of\s+\d+\s+", "", text, flags=re.I)
    text = re.sub(r"^[A-Z][A-Za-z\s,.'()-]+Agreement\s+No\.\s+\d+,\s+\d{4}\s+\d+\s*\|\s*P\s*a\s*g\s*e\s+", "", text, flags=re.I)
    return text.strip(" ;")


def clause_number_for_segment(segment: str) -> str:
    match = re.match(r"(?P<number>\d+(?:\.\d+){0,5})\.?\s+", segment)
    if match:
        return match.group("number")
    match = re.match(r"\((?P<number>[a-zivx]+)\)\s+", segment, flags=re.I)
    if match:
        return f"({match.group('number')})"
    match = re.match(r"(?P<number>[a-z])\.\s+", segment, flags=re.I)
    if match:
        return f"{match.group('number')}."
    if segment.startswith("•"):
        return "•"
    return ""


def segment_body_text(segment: str, clause_number: str) -> str:
    if not clause_number:
        return segment
    if clause_number == "•":
        return segment.lstrip("• ").strip()
    if clause_number.startswith("("):
        return re.sub(rf"^{re.escape(clause_number)}\s*", "", segment, count=1).strip()
    return re.sub(rf"^{re.escape(clause_number)}\.?\s*", "", segment, count=1).strip()


def is_heading_only_segment(segment: str) -> bool:
    normalised = re.sub(r"[^A-Za-z ]+", "", segment).strip().casefold()
    headings = {
        "service recognition leave",
        "end of band recognition",
        "wellbeing and administration leave",
        "additional annual leave",
        "top of band leave",
    }
    return normalised in headings


def is_incomplete_segment(segment: str) -> bool:
    return bool(re.search(r"\b(?:attr|entit|qualif|accumulat|calculat|in|take)$", segment, flags=re.I))


def heading_match_start(text: str, heading: str) -> int | None:
    if not heading or not RELEVANT_EVIDENCE_PATTERN.search(heading):
        return None
    tokens = re.findall(r"[A-Za-z0-9]+", heading)
    if not tokens:
        return None
    pattern = r"\b" + r"[\W_]+".join(re.escape(token) for token in tokens[:8])
    match = re.search(pattern, text, flags=re.I)
    return match.start() if match else None


def curation_window(candidate: PageCandidate, agreement_id: str) -> str:
    pages = load_pages(agreement_id)
    source_text = pages[candidate.page - 1] if 0 < candidate.page <= len(pages) else candidate.excerpt
    text = compact_text(source_text)
    heading_start = heading_match_start(text, candidate.heading)
    if heading_start is not None:
        return text[heading_start:]
    starts: list[int] = []
    for pattern in [
        r"\b\d+(?:\.\d+){1,4}\.?\s+Additional\s+Annual\s+Leave\b",
        r"\bSERVICE\s+RECOGNITION\s+LEAVE\b",
        r"\bEND\s+OF\s+BAND\s+RECOGNITION\b",
        r"\bWELLBEING\s+AND\s+ADMINISTRATION\s+LEAVE\b",
        r"\bTop\s+of\s+band\s+leave\b",
    ]:
        match = re.search(pattern, text, flags=re.I)
        if match:
            starts.append(match.start())
    return text[min(starts):] if starts else text


def raw_clause_segments(candidate: PageCandidate, agreement_id: str) -> list[str]:
    text = curation_window(candidate, agreement_id)
    compact = compact_text(text)
    parts: list[str] = []
    for part in SEGMENT_BOUNDARY_PATTERN.split(compact):
        cleaned = clean_evidence_segment(part)
        if not cleaned:
            continue
        parts.extend(clean_evidence_segment(subpart) for subpart in SENTENCE_BOUNDARY_PATTERN.split(cleaned))
    return [part for part in parts if len(part) > 12]


def curated_clause_segments(candidate: PageCandidate, agreement_id: str) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for segment in raw_clause_segments(candidate, agreement_id):
        if not RELEVANT_EVIDENCE_PATTERN.search(segment):
            continue
        if CURATION_EXCLUSION_PATTERN.search(segment) or is_incomplete_segment(segment):
            continue
        if is_heading_only_segment(segment):
            continue
        number = clause_number_for_segment(segment)
        body = segment_body_text(segment, number)
        segments.append({
            "clause_number": number,
            "page": candidate.page,
            "page_label": f"p.{candidate.page}",
            "text": body,
            "raw_text": segment,
            "source_ref": source_ref(
                agreement_id,
                candidate.page,
                evidence_state=candidate.candidate_type,
                heading=candidate.heading,
            ),
        })
    if segments:
        return segments[:8]
    fallback = clean_evidence_segment(curation_window(candidate, agreement_id))
    fallback_number = clause_number_for_segment(fallback)
    return [{
        "clause_number": fallback_number,
        "page": candidate.page,
        "page_label": f"p.{candidate.page}",
        "text": segment_body_text(fallback, fallback_number),
        "raw_text": fallback,
        "source_ref": source_ref(
            agreement_id,
            candidate.page,
            evidence_state=candidate.candidate_type,
            heading=candidate.heading,
        ),
    }]


def curated_clause_text(candidate: PageCandidate, agreement_id: str) -> str:
    return "\n".join(segment["text"] for segment in curated_clause_segments(candidate, agreement_id))


def candidate_dict(candidate: PageCandidate, agreement_id: str) -> dict[str, Any]:
    subclass = candidate_subclass(candidate)
    segments = curated_clause_segments(candidate, agreement_id)
    return {
        "page": candidate.page,
        "page_label": f"p.{candidate.page}",
        "candidate_type": candidate.candidate_type,
        "matched_terms": candidate.matched_terms,
        "out_of_scope_signals": candidate.out_of_scope_signals,
        "suggested_subclass": subclass,
        "score": candidate.score,
        "heading": candidate.heading,
        "clause_label": evidence_clause_label(candidate),
        "excerpt": candidate.excerpt,
        "clause_text": "\n".join(segment["text"] for segment in segments),
        "clause_segments": segments,
        "source_ref": source_ref(
            agreement_id,
            candidate.page,
            evidence_state=candidate.candidate_type,
            heading=candidate.heading,
        ),
    }


def evidence_record(profile: dict[str, Any], council: str, agreement_id: str) -> dict[str, Any]:
    candidates = page_candidates(profile, agreement_id)
    source_matches = [candidate for candidate in candidates if candidate.candidate_type == "source_clause_match"]
    out_of_scope = [candidate for candidate in candidates if candidate.candidate_type != "source_clause_match"]
    observed_subclasses = [
        dict(item)
        for item in {
            tuple(sorted(candidate_subclass(candidate).items()))
            for candidate in candidates
        }
    ]
    agreement = agreement_name(agreement_id)
    base_record = {
        "council": council,
        "agreement_id": agreement_id,
        "agreement_name": agreement,
        "page_count": len(load_pages(agreement_id)),
        "candidate_page_count": len(candidates),
        "source_clause_page_count": len(source_matches),
        "out_of_scope_candidate_page_count": len(out_of_scope),
        "observed_subclasses": sorted(observed_subclasses, key=lambda item: item.get("label", "")),
    }
    if source_matches:
        excerpts = source_matches[:4]
        evidence_text = " ".join(item.excerpt for item in excerpts)
        values = clause_values_for_council(council, evidence_text)
        page = excerpts[0].page
        heading = excerpts[0].heading
        return {
            **base_record,
            "presence": "source_clause_observed",
            "finding": finding_for_evidence(council, excerpts),
            "quantum_signals": quantum_signals(evidence_text),
            "normalised_values": values,
            "confidence": 0.82 if values else 0.68,
            "support_status": "source_clause_supported",
            "source_ref": source_ref(agreement_id, page, evidence_state="source_clause_observed", heading=heading),
            "source_excerpts": [
                {
                    "page": item.page,
                    "page_label": f"p.{item.page}",
                    "heading": item.heading,
                    "clause_label": evidence_clause_label(item),
                    "excerpt": item.excerpt,
                    "clause_text": curated_clause_text(item, agreement_id),
                    "clause_segments": curated_clause_segments(item, agreement_id),
                    "matched_terms": item.matched_terms,
                    "suggested_subclass": candidate_subclass(item),
                    "score": item.score,
                    "source_ref": source_ref(agreement_id, item.page, evidence_state="source_clause_observed", heading=item.heading),
                }
                for item in excerpts
            ],
            "candidate_pages": [candidate_dict(item, agreement_id) for item in candidates[:10]],
        }
    if out_of_scope:
        signal_counts = Counter(signal for item in out_of_scope for signal in item.out_of_scope_signals)
        if signal_counts:
            signals = ", ".join(label.replace("_", " ") for label, _ in signal_counts.most_common(3))
            reason = f"Candidate annual leave language was detected, but classified as another scope or subclass: {signals}."
        else:
            reason = "Candidate annual leave language was detected, but no general-workforce additional-leave value rule fired."
    else:
        reason = "No page matched the general-workforce additional annual leave profile terms in the cached source text."
    return {
        **base_record,
        "presence": "no_source_clause_match",
        "finding": reason,
        "quantum_signals": [],
        "normalised_values": [],
        "confidence": 0.58 if out_of_scope else 0.48,
        "support_status": "source_search_no_positive_match",
        "source_ref": source_ref(agreement_id, out_of_scope[0].page if out_of_scope else None, evidence_state="source_search_no_positive_match", heading=out_of_scope[0].heading if out_of_scope else ""),
        "source_excerpts": [],
        "candidate_pages": [candidate_dict(item, agreement_id) for item in out_of_scope[:10]],
    }


def build_rows(profile: dict[str, Any], agreements: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [evidence_record(profile, row["council"], row["agreement_id"]) for row in agreements]


def comparator_set(agreements: list[dict[str, str]]) -> list[dict[str, str]]:
    baseline_ids = {row["agreement_id"] for row in BASELINE_COMPARATOR_AGREEMENTS}
    stress_ids = {row["agreement_id"] for row in AB_TEST_EXTENSION_AGREEMENTS}
    return [
        {
            "council": row["council"],
            "agreement_id": row["agreement_id"],
            "agreement_name": agreement_name(row["agreement_id"]),
            "resolved_from_agreement_id": row.get("resolved_from_agreement_id", row["agreement_id"]),
            "latest_resolution": row.get("latest_resolution", "supplied_agreement_id"),
            "cohort": (
                "A_baseline_seed"
                if row["agreement_id"] in baseline_ids
                else "B_extension_stress_test"
                if row["agreement_id"] in stress_ids
                else "C_validation_batch"
            ),
        }
        for row in agreements
    ]


def subclass_counts(rows: list[dict[str, Any]], *, source_only: bool = False) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        candidates = row.get("source_excerpts") if source_only else row.get("candidate_pages")
        for candidate in candidates or []:
            subclass = candidate.get("suggested_subclass") if isinstance(candidate, dict) else {}
            label = subclass.get("label") if isinstance(subclass, dict) else None
            if label:
                counts[str(label)] += 1
    return dict(sorted(counts.items()))


def summary_for_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    presence_counts = Counter(row["presence"] for row in rows)
    support_counts = Counter(row["support_status"] for row in rows)
    candidate_page_count = sum(int(row.get("candidate_page_count") or len(row.get("candidate_pages") or [])) for row in rows)
    source_clause_page_count = sum(int(row.get("source_clause_page_count") or len(row.get("source_excerpts") or [])) for row in rows)
    positive_candidate_page_count = source_clause_page_count
    out_of_scope_candidate_page_count = sum(
        int(row.get("out_of_scope_candidate_page_count") or 0)
        for row in rows
    )
    source_backed_rows = presence_counts.get("source_clause_observed", 0)
    remaining_rows = len(rows) - source_backed_rows
    return {
        "councils": len(rows),
        "total_pages_scanned": sum(int(row.get("page_count") or 0) for row in rows),
        "candidate_pages_found": candidate_page_count,
        "source_clause_pages": source_clause_page_count,
        "positive_candidate_pages": positive_candidate_page_count,
        "out_of_scope_candidate_pages": out_of_scope_candidate_page_count,
        "normalised_values_extracted": sum(len(row.get("normalised_values") or []) for row in rows),
        "candidate_subclass_counts": subclass_counts(rows),
        "source_subclass_counts": subclass_counts(rows, source_only=True),
        "presence_counts": dict(sorted(presence_counts.items())),
        "support_status_counts": dict(sorted(support_counts.items())),
        "source_clause_observed": source_backed_rows,
        "source_search_no_positive_match": support_counts.get("source_search_no_positive_match", 0),
        "rows_needing_absence_or_scope_automation": remaining_rows,
        "rows_with_no_candidate_pages": sum(1 for row in rows if not row.get("candidate_page_count")),
        "rows_with_only_out_of_scope_candidates": sum(
            1 for row in rows if row.get("candidate_page_count") and row.get("presence") != "source_clause_observed"
        ),
        "row_source_backed_percent": round((source_backed_rows / len(rows)) * 100, 1) if rows else 0,
        "row_remaining_automation_percent": round((remaining_rows / len(rows)) * 100, 1) if rows else 0,
        "candidate_page_positive_percent": round((positive_candidate_page_count / candidate_page_count) * 100, 1)
        if candidate_page_count
        else 0,
    }


def global_takeaway_for_rows(profile: dict[str, Any], rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    source_rows = [row for row in rows if row.get("presence") == "source_clause_observed"]
    source_subclasses: Counter[str] = Counter()
    for row in source_rows:
        row_labels = {
            str((excerpt.get("suggested_subclass") or {}).get("label"))
            for excerpt in row.get("source_excerpts") or []
            if isinstance(excerpt, dict) and (excerpt.get("suggested_subclass") or {}).get("label")
        }
        source_subclasses.update(row_labels)
    subclass_phrase = ", ".join(
        f"{label} ({count} council row{'s' if count != 1 else ''})"
        for label, count in sorted(source_subclasses.items(), key=lambda item: (-item[1], item[0]))
    )
    source_clause_observed = int(summary.get("source_clause_observed") or 0)
    councils = int(summary.get("councils") or 0)
    out_of_scope_rows = int(summary.get("rows_with_only_out_of_scope_candidates") or 0)
    no_candidate_rows = int(summary.get("rows_with_no_candidate_pages") or 0)
    needs_review = int((summary.get("candidate_subclass_counts") or {}).get("Needs Review") or 0)
    subclass_sentence = f" Source-backed subclasses are {subclass_phrase}." if subclass_phrase else ""
    return (
        f"Across the current source evidence set, {profile['label']} is a narrow above-baseline entitlement rather than "
        f"a universal council condition: {source_clause_observed} of {councils} councils have source-backed clauses."
        f"{subclass_sentence} The remaining rows are not source-backed for this entitlement: {out_of_scope_rows} have only "
        f"outside-boundary or lookalike candidates, {no_candidate_rows} have no candidate text, and {needs_review} candidates need review."
    )


def learned_pattern_retest(profile: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    retested_rows = [row for row in rows if row.get("presence") != "source_clause_observed"]
    label_counts: Counter[str] = Counter()
    subclass_counts_for_hits: Counter[str] = Counter()
    rows_with_hits: set[str] = set()
    conversion_candidates = 0
    sample_matches: list[dict[str, Any]] = []

    learned_patterns = profile.get("learned_hit_patterns", [])
    if not learned_patterns:
        return {
            "rows_retested": len(retested_rows),
            "rows_with_learned_pattern_candidates": 0,
            "candidate_pages_with_learned_patterns": 0,
            "current_rule_conversion_candidates": 0,
            "remaining_needs_review_candidates": sum(
                1
                for row in rows
                for candidate in row.get("candidate_pages") or []
                if (candidate.get("suggested_subclass") or {}).get("label") == "Needs Review"
            ),
            "learned_pattern_counts": {},
            "learned_candidate_subclass_counts": {},
            "sample_matches": [],
        }

    candidate_pages_with_hits = 0
    for row in retested_rows:
        agreement_id = str(row.get("agreement_id") or "")
        if not agreement_id:
            continue
        for page, page_text in enumerate(load_pages(agreement_id), start=1):
            learned_matches: list[tuple[int, str, re.Match[str]]] = []
            for label, pattern in learned_patterns:
                match = pattern.search(page_text)
                if match:
                    learned_matches.append((match.start(), label, match))
            if not learned_matches:
                continue
            _, label, match = sorted(learned_matches, key=lambda item: item[0])[0]
            excerpt = excerpt_around_match(page_text, match)
            learned_labels = learned_pattern_labels(profile, excerpt)
            positive_labels = [
                positive_label
                for positive_label, positive_pattern in profile["positive_patterns"]
                if positive_pattern.search(excerpt)
            ]
            positive_labels = sorted({*positive_labels, *learned_labels})
            raw_scope_signals = out_of_scope_signals(excerpt)
            if is_probable_table_of_contents(excerpt):
                raw_scope_signals.append("table_of_contents")
            scope_signals = blocking_scope_signals(positive_labels, raw_scope_signals, excerpt)
            leave_signal = has_leave_signal(excerpt)
            value_signal = has_value_signal(excerpt)
            converts = bool(positive_labels) and positive_context_valid(positive_labels, excerpt) and leave_signal and value_signal and not scope_signals
            candidate_type = "source_clause_match" if converts else "out_of_scope_or_context_match"
            score = (10 * len(positive_labels)) + (4 if leave_signal else 0) + (3 if value_signal else 0) - (5 * len(scope_signals))
            retest_candidate = PageCandidate(
                page=page,
                candidate_type=candidate_type,
                matched_terms=sorted({label, *positive_labels}),
                out_of_scope_signals=scope_signals,
                score=score,
                heading=heading_from_excerpt(excerpt),
                excerpt=excerpt,
            )
            subclass = candidate_subclass(retest_candidate)
            candidate_pages_with_hits += 1
            rows_with_hits.add(agreement_id)
            label_counts.update(learned_labels or [label])
            subclass_counts_for_hits.update([subclass["label"]])
            if converts:
                conversion_candidates += 1
            if len(sample_matches) < 30:
                sample_matches.append({
                    "council": row.get("council"),
                    "agreement_id": agreement_id,
                    "page": page,
                    "learned_patterns": learned_labels or [label],
                    "candidate_type": candidate_type,
                    "out_of_scope_signals": scope_signals,
                    "suggested_subclass": subclass,
                    "source_ref": source_ref(agreement_id, page, evidence_state=f"learned_retest_{candidate_type}", heading=retest_candidate.heading),
                })

    return {
        "rows_retested": len(retested_rows),
        "rows_with_learned_pattern_candidates": len(rows_with_hits),
        "candidate_pages_with_learned_patterns": candidate_pages_with_hits,
        "current_rule_conversion_candidates": conversion_candidates,
        "remaining_needs_review_candidates": sum(
            1
            for row in rows
            for candidate in row.get("candidate_pages") or []
            if (candidate.get("suggested_subclass") or {}).get("label") == "Needs Review"
        ),
        "learned_pattern_counts": dict(sorted(label_counts.items())),
        "learned_candidate_subclass_counts": dict(sorted(subclass_counts_for_hits.items())),
        "sample_matches": sample_matches,
    }


def ab_delta(baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "councils",
        "total_pages_scanned",
        "candidate_pages_found",
        "source_clause_pages",
        "out_of_scope_candidate_pages",
        "normalised_values_extracted",
        "source_clause_observed",
        "rows_needing_absence_or_scope_automation",
        "row_source_backed_percent",
        "row_remaining_automation_percent",
        "candidate_page_positive_percent",
    ]
    return {
        field: round(float(variant.get(field, 0)) - float(baseline.get(field, 0)), 1)
        for field in fields
    }


def build_payload(
    profile: dict[str, Any],
    *,
    generated_at: str,
    agreements: list[dict[str, str]] | None = None,
    baseline_agreements: list[dict[str, str]] | None = None,
    stress_extension_agreements: list[dict[str, str]] | None = None,
    validation_extension_agreements: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    baseline = baseline_agreements if baseline_agreements is not None else BASELINE_COMPARATOR_AGREEMENTS
    stress_extension = stress_extension_agreements if stress_extension_agreements is not None else AB_TEST_EXTENSION_AGREEMENTS
    validation_extension = validation_extension_agreements if validation_extension_agreements is not None else VALIDATION_EXTENSION_AGREEMENTS
    selected_agreements = agreements or [*baseline, *stress_extension, *validation_extension]
    rows = build_rows(profile, selected_agreements)
    baseline_rows = rows[: len(baseline)]
    stress_extension_rows = rows[len(baseline): len(baseline) + len(stress_extension)]
    stress_rows = rows[: len(baseline) + len(stress_extension)]
    validation_rows = rows[len(baseline) + len(stress_extension):]
    extension_plus_validation_rows = rows[len(baseline):]
    summary = summary_for_rows(rows)
    global_takeaway = global_takeaway_for_rows(profile, rows, summary)
    learned_retest = learned_pattern_retest(profile, rows)
    baseline_summary = summary_for_rows(baseline_rows)
    stress_extension_summary = summary_for_rows(stress_extension_rows)
    stress_summary = summary_for_rows(stress_rows)
    validation_summary = summary_for_rows(validation_rows)
    extension_plus_validation_summary = summary_for_rows(extension_plus_validation_rows)
    statistical_calibration = calibrate_binary_metric_groups(
        baseline_summary,
        {
            "stress_extension": stress_extension_summary,
            "validation_batch": validation_summary,
            "extension_plus_validation": extension_plus_validation_summary,
        },
        metric="source_clause_observed",
        metric_label="council rows with a source-backed clause",
    )
    ab_test = {
        "purpose": "Measure whether the Additional Annual Leave profile generalises beyond the original gold comparator seed and keeps improving as new agreements are added.",
        "baseline_label": "A: original 10-council comparator seed",
        "stress_extension_label": "B: independent 8-council stress extension",
        "training_variant_label": "B: original seed plus 8-council stress extension",
        "variant_label": "C: learned profile plus 5-council validation batch",
        "baseline": baseline_summary,
        "stress_extension": stress_extension_summary,
        "training_variant": stress_summary,
        "validation_batch": validation_summary,
        "extension_plus_validation": extension_plus_validation_summary,
        "variant": summary,
        "delta": ab_delta(baseline_summary, summary),
        "validation_delta": ab_delta(stress_summary, summary),
        "statistical_calibration": statistical_calibration,
        "extension_selection_reason": "The extension deliberately mixes likely true positives, purchased-leave lookalikes, carer-special-needs clauses, and specialist MCH/nurse clauses so precision and scope controls can be judged.",
        "validation_selection_reason": "The validation batch adds a new alias hit plus hard boundary tests for top-of-band payments, specialist MCH leave, and non-leave recognition language.",
        "extension_comparator_set": comparator_set(stress_extension),
        "validation_comparator_set": comparator_set(validation_extension),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": profile["artifact_id"],
        "artifact_type": "entitlement_clause_evidence",
        "wiki_role": "source_clause_evidence",
        "generated_at": generated_at,
        "scope_focus": "standard_employees",
        "entitlement_id": profile["entitlement_id"],
        "label": profile["label"],
        "definition": profile["definition"],
        "global_takeaway": global_takeaway,
        "taxonomy_path": profile["taxonomy_path"],
        "classification_boundary": profile.get("classification_boundary", {}),
        "accepted_subclasses": profile.get("accepted_subclasses", []),
        "methodology": {
            "method": "profiled_source_clause_search",
            "search_terms": profile["search_terms"],
            "policy_context_sources": profile.get("policy_context_sources", []),
            "positive_match_rule": "A candidate must match a general-workforce profile pattern, show a leave/value signal, and avoid out-of-scope shift-worker/public-holiday/purchased-leave/carer-special-needs/MCH-nurse signals.",
            "absence_rule": "No positive match means source-search absence, not final legal absence.",
            "hit_discovery_method": hit_discovery_method(profile),
            "learned_pattern_retest": learned_retest,
            "learnings_applied": [
                "Service recognition and end-of-band recognition leave are accepted as a subclass of Additional Annual Leave when the benefit is leave rather than cash.",
                "Annual-leave-management bonus leave is accepted as a subclass, including local aliases such as Wellbeing and Administration Leave.",
                "Top-of-band payment is now explicitly separated as a non-leave lookalike.",
                "Specialist MCH/nurse additional leave remains excluded from the standard-employee entitlement lane.",
                "Purchased leave remains adjacent to Additional Annual Leave but is not counted as this source-backed entitlement.",
                "Successful-hit wording is retained as learned discovery patterns and retested against non-converting rows.",
                "When multiple hits appear on one page, the engine now scores the page's candidate excerpts and keeps the strongest clause-shaped match.",
            ],
        },
        "learned_pattern_retest": learned_retest,
        "comparator_set": comparator_set(selected_agreements),
        "summary": summary,
        "ab_test": ab_test,
        "council_evidence": rows,
    }


def markdown_for_payload(payload: dict[str, Any]) -> str:
    calibration = payload["ab_test"]["statistical_calibration"]
    calibration_baseline = calibration["baseline"]
    stress_calibration = calibration["groups"]["stress_extension"]
    validation_calibration = calibration["groups"]["validation_batch"]
    extension_calibration = calibration["groups"]["extension_plus_validation"]
    stress_95 = stress_calibration["predictive_intervals"]["95_percent"]["count"]
    validation_95 = validation_calibration["predictive_intervals"]["95_percent"]["count"]
    extension_95 = extension_calibration["predictive_intervals"]["95_percent"]["count"]
    lines = [
        f"# {payload['label']} Clause Evidence",
        "",
        payload["definition"],
        "",
        "## Method",
        "",
        payload["classification_boundary"].get("canonical_definition") or payload["definition"],
        "",
        payload["methodology"]["positive_match_rule"],
        "",
        "## Summary",
        "",
        f"- Councils: {payload['summary']['councils']}",
        f"- Source-backed rows: {payload['summary']['source_clause_observed']} ({payload['summary']['row_source_backed_percent']}%)",
        f"- Rows still needing automation: {payload['summary']['rows_needing_absence_or_scope_automation']} ({payload['summary']['row_remaining_automation_percent']}%)",
        f"- Pages scanned: {payload['summary']['total_pages_scanned']}",
        f"- Candidate pages found: {payload['summary']['candidate_pages_found']}",
        f"- Source clauses observed: {payload['summary']['source_clause_observed']}",
        f"- Source searches with no positive match: {payload['summary']['source_search_no_positive_match']}",
        f"- Learned-pattern retest: {payload['learned_pattern_retest']['rows_with_learned_pattern_candidates']} non-converting rows had learned-pattern candidates; {payload['learned_pattern_retest']['current_rule_conversion_candidates']} would convert under the current rule.",
        "",
        "## A/B Measurement",
        "",
        f"- A baseline source-backed rows: {payload['ab_test']['baseline']['source_clause_observed']}/{payload['ab_test']['baseline']['councils']} ({payload['ab_test']['baseline']['row_source_backed_percent']}%)",
        f"- B stress source-backed rows: {payload['ab_test']['training_variant']['source_clause_observed']}/{payload['ab_test']['training_variant']['councils']} ({payload['ab_test']['training_variant']['row_source_backed_percent']}%)",
        f"- C validation source-backed rows: {payload['ab_test']['variant']['source_clause_observed']}/{payload['ab_test']['variant']['councils']} ({payload['ab_test']['variant']['row_source_backed_percent']}%)",
        f"- Additional councils: {len(payload['ab_test']['extension_comparator_set'])}",
        f"- Validation councils: {len(payload['ab_test']['validation_comparator_set'])}",
        "",
        "## Statistical Calibration",
        "",
        f"- Model: {calibration['model']} using {calibration['prior']['name']} prior.",
        f"- A posterior prevalence mean: {calibration_baseline['posterior_mean_percent']}% from {calibration_baseline['observed_count']}/{calibration_baseline['sample_size']} source-backed rows.",
        f"- B independent stress extension: observed {stress_calibration['observed_count']}/{stress_calibration['sample_size']}; expected {stress_calibration['expected_count']}; 95% predictive range {stress_95[0]}-{stress_95[1]}; fit confidence {stress_calibration['fit_confidence']}.",
        f"- C validation batch: observed {validation_calibration['observed_count']}/{validation_calibration['sample_size']}; expected {validation_calibration['expected_count']}; 95% predictive range {validation_95[0]}-{validation_95[1]}; fit confidence {validation_calibration['fit_confidence']}.",
        f"- B+C extension total: observed {extension_calibration['observed_count']}/{extension_calibration['sample_size']}; expected {extension_calibration['expected_count']}; 95% predictive range {extension_95[0]}-{extension_95[1]}; fit confidence {extension_calibration['fit_confidence']}.",
        "",
        "## Hit Method",
        "",
        payload["methodology"]["hit_discovery_method"]["acceptance_rule"],
        "",
        "## Council Evidence",
        "",
    ]
    for row in payload["council_evidence"]:
        ref = row["source_ref"]
        page = f" p.{ref.get('page')}" if ref.get("page") else ""
        lines.append(f"- {row['council']}: {row['presence']} ({row['agreement_id'].upper()}{page}) - {row['finding']}")
    lines.append("")
    return "\n".join(lines)


def parse_agreement_arg(raw: str) -> dict[str, str]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("Agreement must be formatted as Council=agreement_id")
    council, agreement_id = raw.split("=", 1)
    council = council.strip()
    agreement_id = agreement_id.strip().lower()
    if not council or not AGREEMENT_ID_PATTERN.fullmatch(agreement_id):
        raise argparse.ArgumentTypeError("Agreement must be formatted as Council=ae123456 or Council=ae123456__split")
    return {"council": council, "agreement_id": agreement_id}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build source-clause evidence for the Additional Annual Leave wiki entitlement.")
    parser.add_argument(
        "--agreement",
        action="append",
        type=parse_agreement_arg,
        default=[],
        metavar="Council=ae123456",
        help="Process an additional or ad hoc agreement. Repeat for multiple agreements.",
    )
    parser.add_argument(
        "--only-agreements",
        action="store_true",
        help="Process only agreements supplied with --agreement instead of the default comparator cohorts.",
    )
    parser.add_argument(
        "--all-cached",
        action="store_true",
        help="Process every agreement that has cached page text, keeping the curated comparator cohorts first.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_WIKI_ROOT / "artifacts" / "entitlement-clause-evidence",
        help="Directory for the JSON and Markdown evidence artifacts.",
    )
    parser.add_argument(
        "--artifact-suffix",
        default="",
        help="Optional suffix for ad hoc artifact ids, for example --artifact-suffix wangaratta.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generated_at = utc_now_iso()
    supplied_agreements = list(args.agreement or [])
    if args.only_agreements:
        selected_agreements = supplied_agreements
        baseline = supplied_agreements
        stress_extension: list[dict[str, str]] = []
        validation_extension: list[dict[str, str]] = []
    elif args.all_cached:
        selected_agreements = [*all_cached_agreements(), *supplied_agreements]
        baseline = BASELINE_COMPARATOR_AGREEMENTS
        stress_extension = AB_TEST_EXTENSION_AGREEMENTS
        validation_ids = {row["agreement_id"] for row in VALIDATION_EXTENSION_AGREEMENTS}
        validation_extension = [
            row
            for row in selected_agreements
            if row["agreement_id"] not in {item["agreement_id"] for item in [*baseline, *stress_extension]}
            and row["agreement_id"] in validation_ids
        ]
        extra_validation = [
            row
            for row in selected_agreements
            if row["agreement_id"] not in {item["agreement_id"] for item in [*baseline, *stress_extension, *validation_extension]}
        ]
        validation_extension = [*validation_extension, *extra_validation]
    else:
        selected_agreements = [*COMPARATOR_AGREEMENTS, *supplied_agreements]
        baseline = BASELINE_COMPARATOR_AGREEMENTS
        stress_extension = AB_TEST_EXTENSION_AGREEMENTS
        validation_extension = [*VALIDATION_EXTENSION_AGREEMENTS, *supplied_agreements]
    payload = build_payload(
        ADDITIONAL_ANNUAL_LEAVE_PROFILE,
        generated_at=generated_at,
        agreements=selected_agreements,
        baseline_agreements=baseline,
        stress_extension_agreements=stress_extension,
        validation_extension_agreements=validation_extension,
    )
    payload["run_scope"] = "all_cached_agreements" if args.all_cached else "selected_comparator_cohorts"
    if args.all_cached:
        payload["ab_test"]["variant_label"] = "All cached agreements with current learned profile"
        payload["ab_test"]["validation_selection_reason"] = "All cached agreements beyond the curated seed cohorts were processed as a scale validation pass."
        if not args.artifact_suffix:
            payload["artifact_id"] = f"{payload['artifact_id']}-all-cached"
    if args.artifact_suffix:
        suffix = re.sub(r"[^a-z0-9-]+", "-", args.artifact_suffix.strip().lower()).strip("-")
        if suffix:
            payload["artifact_id"] = f"{payload['artifact_id']}-{suffix}"
    artifact_dir = args.output_dir
    write_json(artifact_dir / f"{payload['artifact_id']}.json", payload)
    (artifact_dir / f"{payload['artifact_id']}.md").write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.entitlement_clause_evidence_build.v1",
        "generated_at": generated_at,
        "artifact_id": payload["artifact_id"],
        "artifact_path": str(artifact_dir / f"{payload['artifact_id']}.json"),
        "summary": payload["summary"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
