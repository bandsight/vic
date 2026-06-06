from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCATOR_INPUT = (
    ROOT
    / "wiki"
    / "artifacts"
    / "entitlement-locator-experiment"
    / "entitlement-locator-experiment-all-cached-79-offset-0.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "entitlement-cards"
DEFAULT_REPORT_LEARNING = ROOT / "data" / "review" / "entitlement_report_learning.json"
SCHEMA_VERSION = "wiki.entitlement_cards.v1"

STRONG_REVIEW_STATUSES = {
    "auto_extracted_benchmark_value",
    "auto_extracted_non_benchmark_support",
}
INFORMATIONAL_PROCESS_FLAGS = {
    "feature_value_extracted",
    "reference_heavy_context",
}
HARD_CLAUSE_PROCESS_FLAGS = {
    "front_matter_context_not_clause_source",
    "quantification_or_amount_not_stated_review",
    "routing_only_table_of_contents",
    "scope_boundary_review",
    "undertaking_source_term_requires_review",
}
KINDS_THAT_NEED_QUANTUM = {"quantitative", "quantitative_review"}
TIMEFRAME_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("per_year", re.compile(r"\b(per\s+(?:annum|year)|each\s+year|calendar\s+year|annual(?:ly)?|yearly)\b", re.I)),
    ("per_occasion", re.compile(r"\b(per|each)\s+occasion\b|\bon\s+each\s+occasion\b", re.I)),
    ("per_week", re.compile(r"\b(per\s+week|weekly|rostered\s+week)\b", re.I)),
    ("per_day", re.compile(r"\b(per\s+day|daily)\b", re.I)),
    ("per_month", re.compile(r"\b(per\s+month|monthly)\b", re.I)),
    ("agreement_term", re.compile(r"\b(life|term)\s+of\s+(?:this\s+)?agreement\b", re.I)),
    ("once_every_period", re.compile(r"\bonce\s+every\s+\d+\s+(?:days?|weeks?|months?|years?)\b", re.I)),
    ("service_period", re.compile(r"\bafter\s+\d+\s+(?:months?|years?)\b|\b\d+\s+(?:months?|years?)\s+(?:service|continuous\s+service)\b", re.I)),
    ("cap_or_floor", re.compile(r"\b(up\s+to|maximum\s+of|minimum\s+of|at\s+least)\s+\d+", re.I)),
]
GENERIC_SENTENCE_CONDITIONS = {
    "candidate quantified provision near entitlement language",
    "source clause condition",
}
GENERIC_MEASUREMENT_SUFFIXES = [
    "candidate provision",
    "values and parameters",
    "value and parameters",
    "values",
    "parameters",
    "rules",
    "rule",
    "provisions",
    "provision",
]
GENERIC_MEASUREMENT_TOKENS = {
    "and",
    "or",
    "the",
    "of",
    "for",
    "to",
    "per",
    "total",
    "candidate",
    "provision",
    "provisions",
    "rules",
    "rule",
    "values",
    "parameters",
}
GENERIC_UNIT_TOKENS = {
    "day",
    "days",
    "week",
    "weeks",
    "hour",
    "hours",
    "month",
    "months",
    "year",
    "years",
    "annum",
    "daily",
    "weekly",
    "monthly",
    "yearly",
    "non",
    "cumulative",
    "additional",
}
REPORTABLE_FACT_ROLES = {
    "entitlement_quantum",
    "monetary_amount",
    "percentage_rate",
    "availability",
    "amount_not_stated",
}
TIER_CONDITION_PATTERN = re.compile(
    r"\b(after|at\s+least|minimum|continuous\s+service|years?\s+(?:of\s+)?service|band|tier|level|grade)\b",
    re.I,
)
OPERATIVE_PERIOD_PATTERN = re.compile(
    r"\b(?:from|until|to|between|before|after|effective|commencing|operative|expires?)\b[^.;]{0,90}\b(?:20\d{2}|\d{1,2}\s+[A-Z][a-z]+\s+20\d{2})\b",
    re.I,
)
WORK_PATTERN_BASIS_PATTERN = re.compile(
    r"\b(ordinary\s+(?:hours|weekly\s+hours|rate)|full[-\s]*time|part[-\s]*time|rostered\s+hours|hours?\s+per\s+week)\b",
    re.I,
)
SCHEME_OR_REFERENCE_PERIOD_PATTERN = re.compile(
    r"\b(application|notice|election|agreement|scheme|period|term|before|after|within|retain|retained|balance|minimum\s+balance)\b",
    re.I,
)


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


def label_key(value: Any) -> str:
    text = clean_text(value).lower()
    text = text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def compact_text(value: Any, *, limit: int = 900) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def stable_id(prefix: str, parts: list[Any]) -> str:
    return f"{prefix}-" + hashlib.sha1("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:16]


def value_label(value: dict[str, Any]) -> str:
    value_text = clean_text(value.get("value"))
    unit = clean_text(value.get("unit"))
    if value_text and unit:
        return f"{value_text} {unit}"
    return value_text or unit or clean_text(value.get("subclass_label")) or "value not stated"


def numeric_value(value: Any) -> float | None:
    match = re.search(r"(?<![A-Za-z])(\d+(?:\.\d+)?)", clean_text(value))
    return float(match.group(1)) if match else None


def format_numeric(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def pluralise_token(token: str, amount: float | None) -> str:
    if amount == 1:
        return token
    if token.endswith("s"):
        return token
    return f"{token}s"


def normalise_unit_text(unit: Any, amount: Any) -> str:
    text = clean_text(unit)
    numeric = numeric_value(amount)
    lower_text = text.lower()
    for singular in ["day", "week", "hour", "month", "year"]:
        lower_text = lower_text.replace(f"{singular}(s)", pluralise_token(singular, numeric))
    noun_patterns = {
        r"\bday(s)?\b": pluralise_token("day", numeric),
        r"\bweek(s)?\b": pluralise_token("week", numeric),
        r"\bhour(s)?\b": pluralise_token("hour", numeric),
        r"\bmonth(s)?\b": pluralise_token("month", numeric),
        r"\byear(s)?\b": pluralise_token("year", numeric),
    }
    for pattern, replacement in noun_patterns.items():
        lower_text = re.sub(pattern, replacement, lower_text)
    lower_text = re.sub(r"\s+", " ", lower_text).strip()
    lower_text = re.sub(r"\baud\b", "AUD", lower_text)
    return lower_text


def canonical_unit_text(unit: Any) -> str:
    text = clean_text(unit).lower()
    text = text.replace("day(s)", "day")
    text = text.replace("week(s)", "week")
    text = text.replace("hour(s)", "hour")
    text = text.replace("month(s)", "month")
    text = text.replace("year(s)", "year")
    text = re.sub(r"\bdays\b", "day", text)
    text = re.sub(r"\bweeks\b", "week", text)
    text = re.sub(r"\bhours\b", "hour", text)
    text = re.sub(r"\bmonths\b", "month", text)
    text = re.sub(r"\byears\b", "year", text)
    return re.sub(r"\s+", " ", text).strip()


def alpha_tokens(text: Any) -> list[str]:
    return re.findall(r"[a-z]+", clean_text(text).lower())


def clean_measurement_phrase(text: Any) -> str:
    phrase = clean_text(text).replace("/", " and ")
    phrase = re.sub(r"\([^)]*\)", "", phrase)
    phrase = re.sub(r"\s+", " ", phrase).strip(" .,:;")
    lower_phrase = phrase.lower()
    for suffix in GENERIC_MEASUREMENT_SUFFIXES:
        if lower_phrase.endswith(f" {suffix}"):
            phrase = phrase[: -len(suffix)].rstrip(" -/,")
            lower_phrase = phrase.lower()
    return phrase.lower()


def descriptive_unit(unit: str) -> bool:
    tokens = [token for token in alpha_tokens(unit) if token not in GENERIC_UNIT_TOKENS and token not in GENERIC_MEASUREMENT_TOKENS]
    return len(tokens) >= 2


def measurement_tokens(text: str) -> set[str]:
    return {
        token
        for token in alpha_tokens(text)
        if token not in GENERIC_MEASUREMENT_TOKENS and token not in GENERIC_UNIT_TOKENS
    }


def measurement_phrase(profile: dict[str, Any], values: list[dict[str, Any]]) -> str:
    subclass_labels = [
        clean_measurement_phrase(value.get("subclass_label"))
        for value in values
        if clean_measurement_phrase(value.get("subclass_label"))
        and "candidate provision" not in clean_text(value.get("subclass_label")).lower()
    ]
    if subclass_labels:
        return subclass_labels[0]
    return clean_measurement_phrase(profile.get("label"))


def meaningful_condition(value: dict[str, Any]) -> str:
    condition = clean_text(value.get("condition"))
    if not condition:
        return ""
    lower_condition = condition.lower()
    if lower_condition in GENERIC_SENTENCE_CONDITIONS:
        return ""
    if lower_condition.startswith("candidate ") and "entitlement language" in lower_condition:
        return ""
    return condition.lower()


def list_phrase(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def finalise_sentence(text: str) -> str:
    sentence = clean_text(text).strip(" .")
    if not sentence:
        return "Source value is stated."
    if sentence[:1].isalpha():
        sentence = sentence[:1].upper() + sentence[1:]
    return f"{sentence}."


def value_core_phrase(value: dict[str, Any], measured_thing: str) -> str:
    amount = clean_text(value.get("value"))
    unit = normalise_unit_text(value.get("unit"), amount)
    if not amount and not unit:
        return measured_thing or "value not stated"
    if descriptive_unit(unit):
        return " ".join(part for part in [amount, unit] if part).strip()
    if measured_thing and unit in {"day", "days", "week", "weeks", "hour", "hours", "month", "months", "year", "years"} and "leave" in measured_thing:
        return f"{amount} {unit} {measured_thing}".strip()
    if measured_thing and unit:
        return f"{amount} {unit} of {measured_thing}".strip()
    if measured_thing:
        return f"{amount} of {measured_thing}".strip()
    return " ".join(part for part in [amount, unit] if part).strip()


def condition_suffix_for_phrase(phrase: str, condition: str) -> str:
    condition = clean_text(condition).lower()
    if not condition:
        return ""
    operative_match = OPERATIVE_PERIOD_PATTERN.search(condition)
    if operative_match:
        return clean_text(operative_match.group(0)).lower()
    basis_match = re.search(r"\bper\s+(?:annum|year|occasion|week|month|day)\b", condition, re.I)
    if basis_match and basis_match.group(0).lower() not in phrase.lower():
        return basis_match.group(0).lower()
    phrase_tokens = measurement_tokens(phrase)
    condition_tokens = measurement_tokens(condition)
    if condition_tokens and len(condition_tokens - phrase_tokens) < 2:
        return ""
    return condition


def value_phrase_with_condition(value: dict[str, Any], measured_thing: str) -> str:
    phrase = value_core_phrase(value, measured_thing)
    condition = meaningful_condition(value)
    suffix = condition_suffix_for_phrase(phrase, condition)
    if suffix and " per " not in phrase and len(suffix) <= 60:
        return f"{phrase} {suffix}".strip()
    return phrase


def shared_unit(values: list[dict[str, Any]]) -> str:
    units = {
        canonical_unit_text(value.get("unit"))
        for value in values
        if clean_text(value.get("unit"))
    }
    return units.pop() if len(units) == 1 else ""


def summarised_value_phrase(values: list[dict[str, Any]], measured_thing: str, *, allow_range: bool = False) -> str:
    if not values:
        return "available"
    if len(values) == 1:
        return value_phrase_with_condition(values[0], measured_thing)

    common_unit = shared_unit(values)
    numeric_values = [numeric_value(value.get("value")) for value in values]
    if allow_range and common_unit and all(amount is not None for amount in numeric_values):
        min_value = min(amount for amount in numeric_values if amount is not None)
        max_value = max(amount for amount in numeric_values if amount is not None)
        rendered_unit = normalise_unit_text(common_unit, max_value)
        if descriptive_unit(common_unit):
            if min_value == max_value:
                return f"{format_numeric(min_value)} {rendered_unit}"
            return f"{format_numeric(min_value)} to {format_numeric(max_value)} {rendered_unit}"
        if measured_thing and rendered_unit in {"day", "days"} and "leave" in measured_thing:
            if min_value == max_value:
                return f"{format_numeric(min_value)} {rendered_unit} {measured_thing}"
            return f"{format_numeric(min_value)} to {format_numeric(max_value)} {rendered_unit} {measured_thing}"
        if measured_thing:
            if min_value == max_value:
                return f"{format_numeric(min_value)} {rendered_unit} of {measured_thing}"
            return f"{format_numeric(min_value)} to {format_numeric(max_value)} {rendered_unit} of {measured_thing}"

    phrases = [value_phrase_with_condition(value, measured_thing) for value in values[:4]]
    return list_phrase(phrases)


def dedupe_values(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    output: list[dict[str, Any]] = []
    for value in values:
        key = (
            clean_text(value.get("value")).lower(),
            clean_text(value.get("unit")).lower(),
            clean_text(value.get("condition")).lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def value_key(value: dict[str, Any]) -> tuple[str, str, str]:
    return (
        clean_text(value.get("value")).lower(),
        clean_text(value.get("unit")).lower(),
        clean_text(value.get("condition")).lower(),
    )


def row_values(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [value for value in wiki_as_list(row.get("normalised_values")) if isinstance(value, dict)]


def row_clause_cards(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [card for card in wiki_as_list(row.get("clause_cards")) if isinstance(card, dict)]


def row_feature_cards(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [card for card in wiki_as_list(row.get("feature_cards")) if isinstance(card, dict)]


def review_statuses(row: dict[str, Any], cards: list[dict[str, Any]] | None = None) -> set[str]:
    source_cards = cards if cards is not None else [*row_clause_cards(row), *row_feature_cards(row)]
    statuses = {
        clean_text(card.get("review_status"))
        for card in source_cards
        if clean_text(card.get("review_status"))
    }
    return statuses or {clean_text(row.get("review_status")) or "missing_review_status"}


def process_flags(row: dict[str, Any], cards: list[dict[str, Any]] | None = None) -> set[str]:
    flags: set[str] = set()
    source_cards = cards if cards is not None else [*row_clause_cards(row), *row_feature_cards(row)]
    for card in source_cards:
        flags.update(clean_text(flag) for flag in wiki_as_list(card.get("process_rule_flags")) if clean_text(flag))
    return flags


def answer_kind(profile: dict[str, Any]) -> str:
    contract = profile.get("output_contract") if isinstance(profile.get("output_contract"), dict) else {}
    if not contract:
        rule_contract = profile.get("rule_contract") if isinstance(profile.get("rule_contract"), dict) else {}
        contract = rule_contract.get("output_contract") if isinstance(rule_contract.get("output_contract"), dict) else {}
    return clean_text(contract.get("answer_kind")) or "descriptive"


def availability_candidate_value(value: dict[str, Any]) -> bool:
    label = value_label(value).lower()
    unit = clean_text(value.get("unit")).lower()
    raw = clean_text(value.get("value")).lower()
    return (
        raw == "available"
        or "candidate provision" in label
        or unit == "candidate provision"
    )


def reference_only_value(value: dict[str, Any]) -> bool:
    label = value_label(value).lower()
    has_number = bool(re.search(r"\d", label))
    return not has_number and bool(re.search(r"\b(cross[-\s]*reference|nes|award|fair\s+work|external)\b", label, re.I))


def reportable_values(profile: dict[str, Any], row: dict[str, Any]) -> list[dict[str, Any]]:
    values = dedupe_values(row_values(row))
    if answer_kind(profile) not in KINDS_THAT_NEED_QUANTUM:
        return values
    return [
        value
        for value in values
        if not availability_candidate_value(value) and not reference_only_value(value)
    ]


def feature_value(feature: dict[str, Any]) -> dict[str, Any]:
    normalised = feature.get("normalised_value")
    if isinstance(normalised, dict):
        return normalised
    return {
        "value": feature.get("value"),
        "unit": feature.get("unit"),
        "condition": feature.get("condition"),
        "subclass_label": feature.get("subclass_label"),
    }


def feature_matches_value(feature: dict[str, Any], value: dict[str, Any]) -> bool:
    feature_item = feature_value(feature)
    feature_value_text = clean_text(feature_item.get("value")).lower()
    value_text = clean_text(value.get("value")).lower()
    if feature_value_text != value_text:
        return False
    feature_unit = clean_text(feature_item.get("unit")).lower()
    value_unit = clean_text(value.get("unit")).lower()
    if feature_unit and value_unit and feature_unit != value_unit:
        return False
    feature_condition = clean_text(feature_item.get("condition")).lower()
    value_condition = clean_text(value.get("condition")).lower()
    return not feature_condition or not value_condition or feature_condition == value_condition


def matching_features_for_value(features: list[dict[str, Any]], value: dict[str, Any]) -> list[dict[str, Any]]:
    return [feature for feature in features if feature_matches_value(feature, value)]


def feature_is_strong(feature: dict[str, Any]) -> bool:
    statuses = review_statuses({}, [feature])
    flags = process_flags({}, [feature])
    return not (statuses - STRONG_REVIEW_STATUSES) and not (flags - INFORMATIONAL_PROCESS_FLAGS)


def matching_features_for_values(row: dict[str, Any], values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = row_feature_cards(row)
    if not values:
        return []
    matching = [
        feature
        for feature in features
        if any(feature_matches_value(feature, value) for value in values)
    ]
    return matching or features


def value_and_feature_haystack(value: dict[str, Any], features: list[dict[str, Any]]) -> str:
    return " ".join([
        value_label(value),
        clean_text(value.get("condition")),
        clean_text(value.get("subclass_label")),
        *[clean_text(feature.get("subclass_label")) for feature in features],
        *[clean_text(feature.get("evidence_span_text")) for feature in features[:3]],
    ]).lower()


def value_fact_role(profile: dict[str, Any], value: dict[str, Any], features: list[dict[str, Any]]) -> tuple[str, str]:
    haystack = value_and_feature_haystack(value, features)
    unit = clean_text(value.get("unit")).lower()
    condition = clean_text(value.get("condition")).lower()
    subclass = clean_text(value.get("subclass_label")).lower()
    label = value_label(value).lower()
    if re.search(r"\b(amount|quantum|duration)\s+(?:not\s+)?(?:unstated|not\s+stated|not\s+fixed)\b", haystack, re.I):
        return "amount_not_stated", "source clause creates the entitlement but does not state a fixed amount"
    if reference_only_value(value):
        return "reference_only", "value only cross-references an external source"
    if availability_candidate_value(value):
        return "availability", "yes/no availability outcome"
    if "candidate provision" in subclass or condition in GENERIC_SENTENCE_CONDITIONS:
        return "unknown_candidate", "candidate value needs semantic role classification before promotion"
    if WORK_PATTERN_BASIS_PATTERN.search(haystack):
        return "work_pattern_basis", "value appears to describe working-hours or rate basis context"
    if re.search(r"\b(application|scheme|period|term|notice|election)\b", condition, re.I):
        return "rule_parameter", "value appears to be a scheme or application period"
    if re.search(r"\b(retain|retained|balance|minimum\s+balance|cash\s*out)\b", haystack, re.I) and SCHEME_OR_REFERENCE_PERIOD_PATTERN.search(haystack):
        return "rule_parameter", "value appears to be a rule parameter rather than a standalone entitlement quantum"
    if unit in {"aud", "$"} or "aud" in unit:
        return "monetary_amount", "monetary amount"
    if "percent" in unit or "%" in label:
        return "percentage_rate", "percentage rate"
    if re.search(r"\b(days?|weeks?|hours?|months?|years?)\b", unit):
        return "entitlement_quantum", "duration or time quantum"
    if numeric_value(value.get("value")) is not None:
        return "numeric_parameter", "numeric value has no trusted reportable role yet"
    return "descriptive_value", "descriptive value"


def operative_period_for_value(value: dict[str, Any], features: list[dict[str, Any]]) -> str:
    sources = [
        clean_text(value.get("condition")),
        *[clean_text(feature.get("evidence_span_text")) for feature in features[:2]],
    ]
    for source in sources:
        match = OPERATIVE_PERIOD_PATTERN.search(source)
        if match:
            return clean_text(match.group(0))
    return ""


def fact_atoms(profile: dict[str, Any], values: list[dict[str, Any]], features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    measured_thing = measurement_phrase(profile, values)
    for value in values:
        source_features = matching_features_for_value(features, value)
        role, rationale = value_fact_role(profile, value, source_features)
        operative_period = operative_period_for_value(value, source_features)
        atoms.append({
            "fact_role": role,
            "role_rationale": rationale,
            "is_reportable_answer": role in REPORTABLE_FACT_ROLES,
            "value_text": value_label(value),
            "value": value.get("value"),
            "unit": value.get("unit"),
            "condition": value.get("condition"),
            "operative_period": operative_period,
            "measured_thing": measured_thing,
            "source_feature_ids": [
                clean_text(feature.get("feature_id"))
                for feature in source_features
                if clean_text(feature.get("feature_id"))
            ],
            "_value_record": value,
        })
    return atoms


def public_fact_atoms(atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in atom.items() if not key.startswith("_")}
        for atom in atoms
    ]


def report_learning_index(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for item in wiki_as_list(payload.get("entitlements")):
        if not isinstance(item, dict):
            continue
        for key in [item.get("entitlement_key"), label_key(item.get("label"))]:
            if clean_text(key):
                index[clean_text(key)] = item
    return index


def report_expectation_for_profile(profile: dict[str, Any], report_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not report_index:
        return {}
    key = label_key(profile.get("label"))
    if key in report_index:
        return report_index[key]
    for report_key, item in report_index.items():
        if report_key.startswith(key) or key.startswith(report_key):
            return item
    return {}


def atom_expected_kind(atom: dict[str, Any]) -> str:
    role = clean_text(atom.get("fact_role"))
    if role == "entitlement_quantum":
        return "duration_or_time"
    if role == "monetary_amount":
        return "money"
    if role == "percentage_rate":
        return "percentage"
    if role == "availability":
        return "availability_or_condition"
    if role == "amount_not_stated":
        return "amount_not_stated"
    return role or "unknown"


def report_alignment(profile: dict[str, Any], atoms: list[dict[str, Any]], expectation: dict[str, Any]) -> dict[str, Any]:
    if not expectation:
        return {"status": "not_matched_to_report_learning", "flags": []}
    flags: list[str] = []
    expected_kind = clean_text(expectation.get("expected_answer_kind"))
    atom_kinds = sorted({atom_expected_kind(atom) for atom in atoms})
    compatible_kinds = {expected_kind}
    if expected_kind == "duration_or_time":
        compatible_kinds.add("amount_not_stated")
    if expected_kind in {"availability_or_condition", "descriptive"}:
        compatible_kinds.update({"availability_or_condition", "amount_not_stated"})
    if expected_kind and any(kind not in compatible_kinds for kind in atom_kinds):
        flags.append("fact_kind_differs_from_report_expectation")

    ranges = wiki_as_list((expectation.get("quantum_profile") or {}).get("ranges") if isinstance(expectation.get("quantum_profile"), dict) else [])
    for atom in atoms:
        value_number = numeric_value(atom.get("value"))
        if value_number is None:
            continue
        kind = atom_expected_kind(atom)
        unit = alignment_unit_family(atom.get("unit"))
        basis = alignment_basis_family(" ".join([
            clean_text(atom.get("unit")),
            clean_text(atom.get("value_text")),
        ]))
        unit_matching = [
            item
            for item in ranges
            if isinstance(item, dict)
            and clean_text(item.get("kind")) == kind
            and alignment_unit_family(item.get("unit")) == unit
        ]
        basis_matching = [
            item
            for item in unit_matching
            if basis and alignment_basis_family(item.get("basis")) == basis
        ]
        matching = basis_matching or unit_matching
        same_kind_ranges = [
            item for item in ranges if isinstance(item, dict) and clean_text(item.get("kind")) == kind
        ]
        if same_kind_ranges and not matching:
            if duration_value_within_report_ranges(value_number, atom.get("unit"), basis, same_kind_ranges):
                continue
            flags.append("unit_not_seen_in_report_expectation")
            continue
        if (
            matching
            and not any(value_within_report_range(value_number, item) for item in matching)
            and not duration_value_within_report_ranges(value_number, atom.get("unit"), basis, matching)
        ):
            flags.append("value_outside_report_observed_range")

    return {
        "status": "aligned" if not flags else "review_against_report_learning",
        "flags": sorted(set(flags)),
        "report_entitlement_label": expectation.get("label"),
        "report_definition": clean_text(expectation.get("definition")),
        "expected_answer_kind": expected_kind,
        "observed_value_kinds": expectation.get("observed_value_kinds") or {},
        "observed_timeframes": wiki_as_list(expectation.get("observed_timeframes")),
        "observed_conditions": wiki_as_list(expectation.get("observed_conditions")),
        "quantum_ranges": ranges[:8],
        "conversion_hints": wiki_as_list((expectation.get("quantum_profile") or {}).get("conversion_hints") if isinstance(expectation.get("quantum_profile"), dict) else []),
    }


def alignment_unit_family(unit: Any) -> str:
    text = normalise_unit_text(unit, 2).lower()
    if "aud" in text or "$" in text:
        return "AUD"
    if "percent" in text or "%" in text:
        return "percent"
    for singular, plural in [
        ("day", "days"),
        ("week", "weeks"),
        ("hour", "hours"),
        ("month", "months"),
        ("year", "years"),
    ]:
        if re.search(rf"\b{singular}s?\b", text):
            return plural
    return text


def alignment_basis_family(basis: Any) -> str:
    text = clean_text(basis).lower()
    if not text:
        return ""
    if re.search(r"\b(per\s+annum|per\s+year|annually|annual|each\s+year)\b", text):
        return "per year"
    if re.search(r"\b(per\s+occasion|per\s+event|per\s+instance|each\s+occasion)\b", text):
        return "per occasion"
    if re.search(r"\bper\s+week\b", text):
        return "per week"
    if re.search(r"\bper\s+fortnight\b", text):
        return "per fortnight"
    if re.search(r"\bper\s+month\b", text):
        return "per month"
    if re.search(r"\bper\s+day\b", text):
        return "per day"
    if re.search(r"\blife\s+of\s+(the\s+)?agreement\b", text):
        return "life of agreement"
    return ""


def value_within_report_range(value: float, item: dict[str, Any]) -> bool:
    try:
        min_value = float(item.get("min", value))
        max_value = float(item.get("max", value))
    except (TypeError, ValueError):
        return True
    bound = clean_text(item.get("bound")) or "observed"
    if bound == "upper":
        return value <= max_value
    if bound == "lower":
        return value >= min_value
    return min_value <= value <= max_value


def duration_value_within_report_ranges(value: float, unit: Any, basis: str, ranges: list[dict[str, Any]]) -> bool:
    value_in_days = duration_value_in_days(value, unit)
    if value_in_days is None:
        return False
    for item in ranges:
        if clean_text(item.get("kind")) != "duration_or_time":
            continue
        item_basis = alignment_basis_family(item.get("basis"))
        if basis and item_basis and basis != item_basis:
            continue
        item_factor = duration_day_factor(item.get("unit"))
        if item_factor is None:
            continue
        try:
            min_value = float(item.get("min", value)) * item_factor
            max_value = float(item.get("max", value)) * item_factor
        except (TypeError, ValueError):
            continue
        bound = clean_text(item.get("bound")) or "observed"
        if bound == "upper" and value_in_days <= max_value:
            return True
        if bound == "lower" and value_in_days >= min_value:
            return True
        if bound == "observed" and min_value <= value_in_days <= max_value:
            return True
    return False


def duration_value_in_days(value: float, unit: Any) -> float | None:
    factor = duration_day_factor(unit)
    if factor is None:
        return None
    return value * factor


def duration_day_factor(unit: Any) -> float | None:
    family = alignment_unit_family(unit)
    if family == "days":
        return 1.0
    if family == "weeks":
        return 5.0
    return None


def reportable_answer_atoms(profile: dict[str, Any], atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reportable = [atom for atom in atoms if atom.get("is_reportable_answer")]
    if answer_kind(profile) in KINDS_THAT_NEED_QUANTUM:
        return [
            atom
            for atom in reportable
            if atom.get("fact_role") != "availability"
        ]
    return reportable


def atom_value_records(atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        atom["_value_record"]
        for atom in atoms
        if isinstance(atom.get("_value_record"), dict)
    ]


def tiered_fact_set(atoms: list[dict[str, Any]]) -> bool:
    if len(atoms) <= 1:
        return False
    roles = {clean_text(atom.get("fact_role")) for atom in atoms}
    if len(roles) != 1:
        return False
    values = atom_value_records(atoms)
    if not values or not shared_unit(values):
        return False
    conditions = [clean_text(atom.get("condition")) for atom in atoms]
    return bool(conditions) and all(TIER_CONDITION_PATTERN.search(condition) for condition in conditions)


def operative_period_fact_set(atoms: list[dict[str, Any]]) -> bool:
    if len(atoms) <= 1:
        return False
    roles = {clean_text(atom.get("fact_role")) for atom in atoms}
    if len(roles) != 1:
        return False
    values = atom_value_records(atoms)
    if not values or not shared_unit(values):
        return False
    return all(clean_text(atom.get("operative_period")) for atom in atoms)


def fact_role_review_required(atoms: list[dict[str, Any]]) -> bool:
    if len(atoms) <= 1:
        return False
    roles = {clean_text(atom.get("fact_role")) for atom in atoms}
    if len(roles) > 1:
        return True
    return not (tiered_fact_set(atoms) or operative_period_fact_set(atoms))


def dedupe_features(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, str, str], str]] = set()
    output: list[dict[str, Any]] = []
    for feature in features:
        evidence_key = (
            clean_text(feature.get("evidence_span_text_hash"))
            or compact_text(feature.get("evidence_span_text"), limit=240).lower()
            or clean_text(feature.get("feature_id"))
        )
        key = (value_key(feature_value(feature)), evidence_key)
        if key in seen:
            continue
        seen.add(key)
        output.append(feature)
    return output


def selected_clause_cards(row: dict[str, Any], features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clauses = row_clause_cards(row)
    if not clauses or not features:
        return clauses
    feature_clause_ids = {
        clean_text(feature.get("clause_id"))
        for feature in features
        if clean_text(feature.get("clause_id"))
    }
    selected = [
        clause
        for clause in clauses
        if clean_text(clause.get("clause_id")) in feature_clause_ids
    ]
    return selected or clauses


def entitlement_source_bundle(profile: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    candidate_values = reportable_values(profile, row)
    candidate_features = matching_features_for_values(row, candidate_values)
    strong_features = [feature for feature in candidate_features if feature_is_strong(feature)]
    strong_values = [
        value
        for value in candidate_values
        if any(feature_matches_value(feature, value) for feature in strong_features)
    ]
    values = dedupe_values(strong_values) if strong_values else candidate_values
    features = [
        feature
        for feature in (strong_features if strong_values else candidate_features)
        if any(feature_matches_value(feature, value) for value in values)
    ]
    features = dedupe_features(features)
    atoms = fact_atoms(profile, values, features)
    return {
        "values": values,
        "fact_atoms": atoms,
        "answer_atoms": reportable_answer_atoms(profile, atoms),
        "features": features,
        "clauses": selected_clause_cards(row, features),
        "raw_values": dedupe_values(row_values(row)),
    }


def infer_timeframe_or_basis(values: list[dict[str, Any]], clauses: list[dict[str, Any]], features: list[dict[str, Any]]) -> str:
    haystack = " ".join([
        *[clean_text(value.get("condition")) for value in values],
        *[clean_text(value.get("unit")) for value in values],
        *[clean_text(feature.get("evidence_span_text")) for feature in features[:4]],
        *[clean_text(clause.get("raw_clause_text")) for clause in clauses[:2]],
    ])
    matches = [label for label, pattern in TIMEFRAME_PATTERNS if pattern.search(haystack)]
    if matches:
        return ", ".join(sorted(set(matches)))
    if any(clean_text(value.get("unit")).lower() in {"days", "weeks", "hours", "months"} for value in values):
        return "source clause duration"
    if any(clean_text(value.get("unit")).lower() in {"aud", "percent"} for value in values):
        return "source clause basis"
    return "not applicable"


def cohort_for_profile(rule_contract: dict[str, Any]) -> str:
    return clean_text(rule_contract.get("scope")) or "standard_employees"


def quantum_text(values: list[dict[str, Any]]) -> str:
    labels = [value_label(value) for value in values]
    if not labels:
        return "value not stated"
    return "; ".join(labels[:4])


def simple_sentence(profile: dict[str, Any], values: list[dict[str, Any]], *, allow_range: bool = False) -> str:
    label = value_label(values[0]) if values else "available"
    lower = label.lower()
    measured_thing = measurement_phrase(profile, values)
    if lower in {"available", "candidate provision", "available candidate provision"}:
        return finalise_sentence(f"{measured_thing or 'provision'} provision available")
    if "not stated" in lower or "amount" in lower and "not" in lower:
        return finalise_sentence(f"amount unstated for {measured_thing or 'provision'}")
    sentence = summarised_value_phrase(values, measured_thing, allow_range=allow_range)
    return finalise_sentence(sentence)


def clause_source_rows(clauses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for clause in clauses[:4]:
        rows.append({
            "clause_id": clause.get("clause_id"),
            "page": clause.get("page_number_physical"),
            "heading_path": clause.get("heading_path") if isinstance(clause.get("heading_path"), list) else [],
            "review_status": clause.get("review_status"),
            "raw_clause_text": compact_text(clause.get("raw_clause_text"), limit=1200),
            "raw_clause_text_hash": clause.get("raw_clause_text_hash"),
            "reference_links": wiki_as_list(clause.get("reference_links"))[:8],
        })
    return rows


def feature_source_rows(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in features[:8]:
        answer_builder = feature.get("answer_builder") if isinstance(feature.get("answer_builder"), dict) else {}
        rows.append({
            "feature_id": feature.get("feature_id"),
            "clause_id": feature.get("clause_id"),
            "page": feature.get("page_number_physical"),
            "review_status": feature.get("review_status"),
            "answer_builder_status": feature.get("answer_builder_status") or answer_builder.get("status") or "legacy_feature_without_answer_builder_contract",
            "value": feature.get("value"),
            "unit": feature.get("unit"),
            "condition": feature.get("condition"),
            "evidence_span_text": compact_text(feature.get("evidence_span_text"), limit=600),
            "evidence_span_text_hash": feature.get("evidence_span_text_hash"),
            "answer_builder": {
                "schema_version": answer_builder.get("schema_version"),
                "status": answer_builder.get("status") or "legacy_feature_without_answer_builder_contract",
                "doctrine": answer_builder.get("doctrine"),
                "initial_blockers": wiki_as_list(answer_builder.get("initial_blockers")),
                "required_answer_fields": wiki_as_list(answer_builder.get("required_answer_fields")),
                "deterministic_gate_policy": (
                    answer_builder.get("deterministic_gate_policy")
                    if isinstance(answer_builder.get("deterministic_gate_policy"), dict)
                    else {}
                ),
            },
        })
    return rows


def row_gate_failures(profile: dict[str, Any], row: dict[str, Any], rule_contract: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    bundle = entitlement_source_bundle(profile, row)
    values = bundle["values"]
    atoms = bundle["fact_atoms"]
    answer_atoms = bundle["answer_atoms"]
    raw_values = bundle["raw_values"]
    clauses = bundle["clauses"]
    features = bundle["features"]
    feature_statuses = review_statuses(row, features)
    feature_flags = process_flags(row, features)
    hard_clause_flags = process_flags(row, clauses).intersection(HARD_CLAUSE_PROCESS_FLAGS)
    blocking_flags = sorted((feature_flags | hard_clause_flags) - INFORMATIONAL_PROCESS_FLAGS)
    if row.get("state") != "clause_found_value_extracted":
        failures.append("cell_not_value_extracted")
    if not clean_text(rule_contract.get("definition")):
        failures.append("missing_entitlement_definition")
    if not clauses:
        failures.append("missing_clause_card")
    if not features:
        failures.append("missing_feature_card")
    if not raw_values:
        failures.append("missing_normalised_value")
    if raw_values and not values and answer_kind(profile) in KINDS_THAT_NEED_QUANTUM:
        if any(availability_candidate_value(value) for value in raw_values):
            failures.append("availability_candidate_not_reportable_quantum")
        if any(reference_only_value(value) for value in raw_values):
            failures.append("reference_only_value_not_reportable_quantum")
    if values and not answer_atoms:
        failures.append("missing_reportable_fact_atom")
    if answer_atoms and fact_role_review_required(answer_atoms):
        failures.append("multi_value_fact_role_review_required")
    if feature_statuses - STRONG_REVIEW_STATUSES:
        failures.append("review_status_not_strong")
    if blocking_flags:
        failures.append("blocking_process_rule_flags")
    return sorted(set(failures))


def entitlement_gate_failures(profile: dict[str, Any], row: dict[str, Any]) -> list[str]:
    rule_contract = profile.get("rule_contract") if isinstance(profile.get("rule_contract"), dict) else {}
    failures = row_gate_failures(profile, row, rule_contract)
    bundle = entitlement_source_bundle(profile, row)
    values = atom_value_records(bundle["answer_atoms"]) or bundle["values"]
    if len(values) > 1 and any(not clean_text(value.get("condition")) for value in values):
        failures.append("multi_value_card_needs_conditions")
    return sorted(set(failures))


def entitlement_card_for_row(
    profile: dict[str, Any],
    row: dict[str, Any],
    *,
    generated_at: str,
    report_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    rule_contract = profile.get("rule_contract") if isinstance(profile.get("rule_contract"), dict) else {}
    failures = entitlement_gate_failures(profile, row)
    if failures:
        return None
    bundle = entitlement_source_bundle(profile, row)
    answer_atoms = bundle["answer_atoms"]
    values = atom_value_records(answer_atoms)
    features = [
        feature
        for feature in bundle["features"]
        if any(feature_matches_value(feature, value) for value in values)
    ] or bundle["features"]
    clauses = selected_clause_cards(row, features)
    entitlement_id = clean_text(profile.get("entitlement_id"))
    council = clean_text(row.get("council"))
    agreement_id = clean_text(row.get("agreement_id"))
    card_id = stable_id("entitlement-card", [entitlement_id, council, agreement_id, quantum_text(values)])
    definition = clean_text(rule_contract.get("definition"))
    expectation = report_expectation_for_profile(profile, report_index or {})
    learning_alignment = report_alignment(profile, answer_atoms, expectation)
    return {
        "entitlement_card_id": card_id,
        "schema_version": "wiki.entitlement_card.v1",
        "status": "proposed_governed",
        "standard": "analysis_reporting_candidate",
        "generated_at": generated_at,
        "entitlement_id": entitlement_id,
        "entitlement_label": profile.get("label"),
        "entitlement_definition": definition,
        "taxonomy_path": rule_contract.get("taxonomy_path") or [],
        "council": council,
        "agreement_id": agreement_id,
        "agreement_name": row.get("agreement_name"),
        "simple_sentence": simple_sentence(profile, values, allow_range=tiered_fact_set(answer_atoms)),
        "quantum": {
            "value_text": quantum_text(values),
            "values": values,
            "fact_atoms": public_fact_atoms(answer_atoms),
            "fact_roles": sorted({clean_text(atom.get("fact_role")) for atom in answer_atoms if clean_text(atom.get("fact_role"))}),
            "timeframe_or_basis": infer_timeframe_or_basis(values, clauses, features),
            "cohort": cohort_for_profile(rule_contract),
            "condition": "; ".join(clean_text(value.get("condition")) for value in values if clean_text(value.get("condition"))) or "source clause condition",
            "report_learning_alignment": learning_alignment,
        },
        "source_clauses": clause_source_rows(clauses),
        "source_features": feature_source_rows(features),
        "source_refs": {
            "clause_card_ids": sorted({clean_text(card.get("clause_id")) for card in clauses if clean_text(card.get("clause_id"))}),
            "feature_card_ids": sorted({clean_text(card.get("feature_id")) for card in features if clean_text(card.get("feature_id"))}),
            "pages": sorted({card.get("page_number_physical") for card in [*clauses, *features] if card.get("page_number_physical") is not None}),
        },
        "evidence_standard": {
            "meets_standard": True,
            "review_needed": False,
            "requirements": [
                "entitlement definition present",
                "source clause card present",
                "selected source feature card present",
                "selected reportable value present",
                "selected value is classified as a reportable fact atom",
                "multi-value cards have an explicit tier relationship",
                "semantic answer-building has been considered before deterministic promotion",
                "selected feature status is strong",
                "selected feature has no blocking process rule flags",
            ],
            "fact_roles": sorted({clean_text(atom.get("fact_role")) for atom in answer_atoms if clean_text(atom.get("fact_role"))}),
            "report_learning_alignment": learning_alignment,
            "review_statuses": sorted(review_statuses(row, features)),
            "process_rule_flags": sorted(process_flags(row, features)),
            "answer_builder_statuses": sorted({
                clean_text(feature.get("answer_builder_status"))
                or clean_text((feature.get("answer_builder") or {}).get("status") if isinstance(feature.get("answer_builder"), dict) else "")
                or "legacy_feature_without_answer_builder_contract"
                for feature in features
            }),
        },
        "promotion": {
            "proposed_status": "proposed_governed_entitlement_card",
            "reporting_ready": True,
            "review_queue_policy": "if_review_needed_card_is_not_emitted",
        },
    }


def blocked_cell(row: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    bundle = entitlement_source_bundle(profile, row)
    return {
        "entitlement_id": profile.get("entitlement_id"),
        "entitlement_label": profile.get("label"),
        "council": row.get("council"),
        "agreement_id": row.get("agreement_id"),
        "state": row.get("state"),
        "gate_failures": entitlement_gate_failures(profile, row),
        "review_statuses": sorted(review_statuses(row, bundle["features"])),
        "process_rule_flags": sorted(process_flags(row, bundle["features"])),
        "all_review_statuses": sorted(review_statuses(row)),
        "all_process_rule_flags": sorted(process_flags(row)),
        "reportable_value_labels": [value_label(value) for value in bundle["values"]],
        "fact_atoms": public_fact_atoms(bundle["fact_atoms"])[:8],
        "feature_card_ids": [card.get("feature_id") for card in bundle["features"] if card.get("feature_id")],
        "clause_card_ids": [card.get("clause_id") for card in bundle["clauses"] if card.get("clause_id")],
    }


def build_payload(
    locator_payload: dict[str, Any],
    *,
    generated_at: str,
    source_path: Path,
    report_learning_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cards: list[dict[str, Any]] = []
    blocked_samples: list[dict[str, Any]] = []
    failure_counts: Counter[str] = Counter()
    source_cells = 0
    value_cells = 0
    report_index = report_learning_index(report_learning_payload)
    for profile in wiki_as_list(locator_payload.get("profiles")):
        if not isinstance(profile, dict):
            continue
        for row in wiki_as_list(profile.get("target_rows")):
            if not isinstance(row, dict):
                continue
            source_cells += 1
            if row.get("state") == "clause_found_value_extracted":
                value_cells += 1
            card = entitlement_card_for_row(profile, row, generated_at=generated_at, report_index=report_index)
            if card:
                cards.append(card)
                continue
            blocked = blocked_cell(row, profile)
            for failure in blocked["gate_failures"]:
                failure_counts[failure] += 1
            if len(blocked_samples) < 200 and blocked["gate_failures"] != ["cell_not_value_extracted"]:
                blocked_samples.append(blocked)
    status_counts = Counter(card.get("status") for card in cards)
    cards.sort(key=lambda item: (str(item.get("entitlement_label") or ""), str(item.get("council") or "")))
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": f"entitlement-cards-{locator_payload.get('artifact_id', 'unknown')}",
        "generated_at": generated_at,
        "source_artifact": {
            "locator_artifact_id": locator_payload.get("artifact_id"),
            "path": str(source_path),
            "generated_at": locator_payload.get("generated_at"),
        },
        "method": {
            "name": "strict_entitlement_card_promotion_proposal",
            "asset_name": "Entitlement Card",
            "doctrine": (
                "Entitlement cards are proposed governed analysis/reporting facts. "
                "If the machine thinks the row needs review, the card is not emitted."
            ),
            "hard_gates": [
                "source cell must be clause_found_value_extracted",
                "entitlement definition must be present",
                "clause card, selected feature card, and selected reportable value must be present",
                "selected feature review statuses must be strong auto-extracted statuses",
                "selected feature blocking process-rule flags are disallowed",
                "selected values must classify as reportable fact atoms",
                "multi-value cards must be a tiered set or distinct operative-period values",
                "availability or reference-only placeholders are ignored only when a separately supported reportable value exists",
            ],
        },
        "summary": {
            "source_cells": source_cells,
            "value_extracted_cells": value_cells,
            "entitlement_cards": len(cards),
            "blocked_cells": source_cells - len(cards),
            "blocked_value_cells": value_cells - len(cards),
            "status_counts": dict(sorted(status_counts.items())),
            "gate_failure_counts": dict(sorted(failure_counts.items())),
            "report_learning_matched_cards": sum(
                1
                for card in cards
                if card.get("evidence_standard", {}).get("report_learning_alignment", {}).get("status") != "not_matched_to_report_learning"
            ),
            "report_learning_review_cards": sum(
                1
                for card in cards
                if card.get("evidence_standard", {}).get("report_learning_alignment", {}).get("flags")
            ),
        },
        "cards": cards,
        "blocked_samples": blocked_samples,
    }


def markdown_for_payload(payload: dict[str, Any]) -> str:
    lines = [
        "# Entitlement Cards",
        "",
        payload["method"]["doctrine"],
        "",
        "## Summary",
        "",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Proposed Cards", ""])
    for card in payload["cards"][:80]:
        lines.extend([
            f"### {card['entitlement_label']} / {card['council']}",
            "",
            f"- Sentence: {card['simple_sentence']}",
            f"- Quantum: {card['quantum']['value_text']}",
            f"- Basis: {card['quantum']['timeframe_or_basis']}",
            f"- Clauses: `{', '.join(card['source_refs']['clause_card_ids'])}`",
            "",
        ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build strict Entitlement Cards from locator feature cards.")
    parser.add_argument("--input", type=Path, default=DEFAULT_LOCATOR_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-learning", type=Path, default=DEFAULT_REPORT_LEARNING)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = args.input.resolve()
    report_learning = load_json(args.report_learning.resolve()) if args.report_learning and args.report_learning.exists() else None
    payload = build_payload(
        load_json(source_path),
        generated_at=utc_now_iso(),
        source_path=source_path,
        report_learning_payload=report_learning,
    )
    output_dir = args.output_dir.resolve()
    json_path = output_dir / f"{payload['artifact_id']}.json"
    md_path = output_dir / f"{payload['artifact_id']}.md"
    write_json(json_path, payload)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.entitlement_cards_build.v1",
        "generated_at": payload["generated_at"],
        "artifact_id": payload["artifact_id"],
        "artifact_path": str(json_path),
        "markdown_path": str(md_path),
        "summary": payload["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
