from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts import build_entitlement_clause_evidence as annual
from scripts import build_standard_entitlement_profile_evidence as standard
from scripts.build_entitlement_batch_scores import eligible_latest_cached_agreements
from scripts.entitlement_statistical_calibration import calibrate_binary_metric_groups
from benchmarking_data_factory.workbench.wiki_layer import page_role_for_text, source_container_type_for_text


DEFAULT_OUTPUT_DIR = ROOT / "wiki" / "artifacts" / "entitlement-locator-experiment"
ENTITLEMENT_TAXONOMY_PATH = ROOT / "data" / "governed_canonical" / "entitlement_items.csv"
GOVERNED_COUNCIL_AGREEMENTS_PATH = ROOT / "data" / "governed_canonical" / "council_agreements.csv"
LEARNED_RULE_OVERRIDES_PATH = ROOT / "data" / "review" / "entitlement_loop_rule_overrides.json"
DEFAULT_EXEMPLAR_PATH = (
    ROOT
    / "wiki"
    / "artifacts"
    / "downstream-analysis-exemplars"
    / "ballarat-entitlement-benchmark-exemplar.json"
)
LOCATOR_SCHEMA_VERSION = "wiki.entitlement_locator_experiment.v2"
PARSER_USED = "cached_page_text"
PARSER_VERSION = "workbench_pages_json_v1"
PAGE_TEXT_CACHE: dict[str, list[str]] = {}
PAGE_ROLE_CACHE: dict[tuple[str, int], str] = {}
PAGE_CONTAINER_TYPE_CACHE: dict[tuple[str, int], str] = {}
LEARNED_RULE_OVERRIDES_CACHE: dict[str, dict[str, Any]] | None = None
EXEMPLAR_CACHE: dict[str, Any] | None = None

CLAUSE_FOUND_STATES = {"clause_found_value_extracted", "clause_found_value_missing"}
HARD_SOURCE_CONTEXT_BLOCKERS = {"table_of_contents", "approval_decision_front_matter"}
FEATURE_CARD_QUANTUM_UNITS = {"days", "weeks", "hours", "months", "AUD", "percent"}
FEATURE_CARD_TIMEFRAME_RE = re.compile(
    r"\b(per\s+(?:annum|year|week|day|month|occasion)|each\s+(?:year|week|day|month|occasion)|"
    r"calendar\s+year|annual(?:ly)?|yearly|weekly|daily|monthly|rostered\s+week|life\s+of\s+(?:this\s+)?agreement|"
    r"term\s+of\s+(?:this\s+)?agreement|once\s+every\s+\d+\s+(?:days?|weeks?|months?|years?))\b",
    re.I,
)
FEATURE_CARD_SPECIALIST_COHORT_RE = re.compile(
    r"\b(MCH|maternal\s+and\s+child\s+health|nurses?|immunisation|kindergarten|early\s+childhood|"
    r"child\s+care|teacher|physical\s+and\s+community\s+services|IT\s+helpdesk|engineer)\b",
    re.I,
)
FEATURE_CARD_REFERENCE_HEAVY_RE = re.compile(
    r"\b(NES|National\s+Employment\s+Standards|Award|Modern\s+Award|Fair\s+Work\s+Act|policy|procedure|clause\s+\d+)\b",
    re.I,
)
FEATURE_CARD_LOCAL_ENTITLEMENT_RE = re.compile(
    r"\b(?:entitled|entitlement|may\s+access|will\s+be\s+granted|shall\s+receive|provides?|offers?|receive)\b"
    r"[\s\S]{0,180}\b(?:paid\s+)?(?:leave|days?|weeks?|hours?|time\s+off)\b",
    re.I,
)
FEATURE_CARD_LLM_REVIEW_FLAGS = {
    "feature_llm_timeframe_or_basis_review",
    "feature_llm_scope_or_cohort_review",
    "feature_llm_reference_context_review",
    "feature_llm_definition_noise_gate",
}
FEATURE_ANSWER_BUILDER_QUESTIONS = [
    "Is this feature actually answering the target entitlement?",
    "Is the extracted value a leave quantum, presence answer, timeframe, eligibility rule, cap, notice period, or unrelated number?",
    "Who is the employee cohort and does it match the entitlement scope?",
    "What is the timeframe or basis for the value?",
    "Is the provision paid, unpaid, additional, or access to an existing entitlement?",
    "Do comparable councils and the normal value model make this answer plausible?",
    "Can any blocker be repaired from source context before review?",
]
FEATURE_ANSWER_REQUIRED_FIELDS = [
    "entitlement_id",
    "entitlement_definition",
    "council",
    "agreement_id",
    "source_clause_id",
    "source_feature_id",
    "answer_kind",
    "value_or_presence",
    "unit",
    "timeframe_or_basis",
    "cohort",
    "condition",
    "paid_status",
    "basis",
    "normal_value_alignment",
    "resolved_blockers",
    "source_support_summary",
]


@dataclass(frozen=True)
class LocatorSpec:
    key: str
    entitlement_id: str
    label: str
    profile: dict[str, Any]
    family: str


def learned_rule_overrides() -> dict[str, dict[str, Any]]:
    global LEARNED_RULE_OVERRIDES_CACHE
    if LEARNED_RULE_OVERRIDES_CACHE is not None:
        return LEARNED_RULE_OVERRIDES_CACHE
    if not LEARNED_RULE_OVERRIDES_PATH.exists():
        LEARNED_RULE_OVERRIDES_CACHE = {}
        return LEARNED_RULE_OVERRIDES_CACHE
    payload = json.loads(LEARNED_RULE_OVERRIDES_PATH.read_text(encoding="utf-8"))
    LEARNED_RULE_OVERRIDES_CACHE = {
        str(item.get("entitlement_id") or "").strip(): item
        for item in payload.get("overrides", [])
        if isinstance(item, dict) and str(item.get("entitlement_id") or "").strip()
    }
    return LEARNED_RULE_OVERRIDES_CACHE


def learned_rule_override_for(entitlement_id: str) -> dict[str, Any]:
    return learned_rule_overrides().get(str(entitlement_id or "").strip(), {})


def exemplar_payload(path: Path = DEFAULT_EXEMPLAR_PATH) -> dict[str, Any]:
    global EXEMPLAR_CACHE
    if EXEMPLAR_CACHE is None:
        if not path.exists():
            EXEMPLAR_CACHE = {}
        else:
            EXEMPLAR_CACHE = json.loads(path.read_text(encoding="utf-8"))
    return EXEMPLAR_CACHE


def exemplar_entitlement(entitlement_id: str) -> dict[str, Any]:
    payload = exemplar_payload()
    for category in payload.get("categories") or []:
        if not isinstance(category, dict):
            continue
        for entitlement in category.get("entitlements") or []:
            if isinstance(entitlement, dict) and entitlement.get("entitlement_id") == entitlement_id:
                return entitlement
    return {}


def exemplar_comparator_councils() -> list[str]:
    payload = exemplar_payload()
    target = payload.get("gold_comparator_target") if isinstance(payload.get("gold_comparator_target"), dict) else {}
    councils = [
        str(item).strip()
        for item in target.get("comparator_councils", [])
        if str(item or "").strip()
    ]
    return councils


def answer_kind_for_quantification_type(quantification_type: str) -> str:
    return {
        "quantified_value": "quantitative",
        "quantification_required": "quantitative_review",
        "binary_presence_or_absence": "boolean",
        "qualitative_condition": "descriptive",
    }.get(str(quantification_type or "").strip(), "descriptive")


def exemplar_output_contract(entitlement_id: str) -> dict[str, Any]:
    entitlement = exemplar_entitlement(entitlement_id)
    mapping = entitlement.get("semantic_mapping") if isinstance(entitlement.get("semantic_mapping"), dict) else {}
    quantification = (
        mapping.get("quantification_semantics")
        if isinstance(mapping.get("quantification_semantics"), dict)
        else {}
    )
    comparator = mapping.get("comparator_semantics") if isinstance(mapping.get("comparator_semantics"), dict) else {}
    supportability = (
        mapping.get("supportability_semantics")
        if isinstance(mapping.get("supportability_semantics"), dict)
        else {}
    )
    quantification_type = str(quantification.get("quantification_type") or "").strip() or "qualitative_condition"
    presence_counts: dict[str, int] = {}
    for entry in comparator.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        presence = str(entry.get("presence") or "unknown").strip() or "unknown"
        presence_counts[presence] = presence_counts.get(presence, 0) + 1
    return {
        "source": "entitlements_draft_summary_report_version_2",
        "answer_kind": answer_kind_for_quantification_type(quantification_type),
        "quantification_type": quantification_type,
        "normalisation_required": bool(quantification.get("normalisation_required", True)),
        "supportable_output_requires": list(quantification.get("supportable_output_requires") or [
            "canonical entitlement id",
            "source agreement id",
            "page or clause reference",
            "presence/absence state",
            "review state",
        ]),
        "production_support_status": supportability.get("production_support_status"),
        "minimum_evidence": list(supportability.get("minimum_evidence") or []),
        "reference_presence_mix": dict(sorted(presence_counts.items())),
    }


def apply_learned_rule_override(profile: dict[str, Any]) -> dict[str, Any]:
    entitlement_id = str(profile.get("entitlement_id") or "").strip()
    override = learned_rule_override_for(entitlement_id)
    if not override:
        return profile
    merged = dict(profile)
    if isinstance(override.get("classification_boundary"), dict):
        merged["classification_boundary"] = override["classification_boundary"]
    if isinstance(override.get("accepted_subclasses"), list):
        merged["accepted_subclasses"] = override["accepted_subclasses"]
    merged["rule_origin"] = "learned_loop_override"
    merged["learned_loop_rules"] = {
        "learning_source": override.get("learning_source"),
        "loop_status": override.get("loop_status"),
        "promotion_gate": override.get("promotion_gate"),
        "expected_answer_shape": override.get("expected_answer_shape") if isinstance(override.get("expected_answer_shape"), dict) else {},
        "value_rules": override.get("value_rules") if isinstance(override.get("value_rules"), list) else [],
        "validation_queue": override.get("validation_queue") if isinstance(override.get("validation_queue"), list) else [],
        "next_loop_steps": override.get("next_loop_steps") if isinstance(override.get("next_loop_steps"), list) else [],
        "research_findings": override.get("research_findings") if isinstance(override.get("research_findings"), dict) else {},
        "feature_card_llm_review": override.get("feature_card_llm_review") if isinstance(override.get("feature_card_llm_review"), dict) else {},
    }
    return merged


SPECIALISED_LOCATOR_SPECS = [
    LocatorSpec(
        key="additional_annual_leave",
        entitlement_id=annual.ADDITIONAL_ANNUAL_LEAVE_PROFILE["entitlement_id"],
        label=annual.ADDITIONAL_ANNUAL_LEAVE_PROFILE["label"],
        profile=apply_learned_rule_override(annual.ADDITIONAL_ANNUAL_LEAVE_PROFILE),
        family="annual",
    ),
    *[
        LocatorSpec(
            key=str(profile["entitlement_id"]).replace("-", "_"),
            entitlement_id=profile["entitlement_id"],
            label=profile["label"],
            profile=apply_learned_rule_override(profile),
            family="standard",
        )
        for profile in [
            standard.FAMILY_DOMESTIC_VIOLENCE_PROFILE,
            standard.NATURAL_DISASTER_PROFILE,
            standard.COMPASSIONATE_PROFILE,
            standard.CULTURAL_CEREMONIAL_PROFILE,
            standard.EMERGENCY_SERVICES_PROFILE,
            standard.PARENTAL_PRIMARY_PROFILE,
            standard.PARENTAL_NON_PRIMARY_PROFILE,
        ]
    ],
]


GENERIC_ALIAS_HINTS: dict[str, tuple[str, ...]] = {
    "leave-paid-shutdown-days-christmas-to-new-year": ("christmas to new year", "close down", "closedown", "shutdown"),
    "leave-personal-and-carers-leave": ("personal leave", "carer's leave", "carers leave", "sick leave"),
    "leave-pet-leave": ("pet leave", "companion animal", "bereavement for a pet"),
    "leave-purchased-leave-scheme": ("purchased leave", "purchase leave", "48/52", "four over five"),
    "leave-study-and-professional-development-leave": ("study leave", "professional development leave", "training leave", "examination leave"),
    "leave-union-training-leave": ("union training leave", "trade union training", "industrial training leave"),
    "leave-volunteer-or-donor-leave": ("volunteer leave", "blood donor", "donor leave", "voluntary emergency"),
    "conditions-call-out-minimum-engagement": ("call out", "call-out", "callout", "minimum engagement"),
    "conditions-work-from-home-protections": ("work from home", "working from home", "remote work", "remote working", "flexible work arrangement", "WFH"),
    "conditions-christmas-to-new-year-closure": ("christmas to new year", "close down", "closedown", "shutdown"),
    "conditions-rostered-day-off-and-accrued-time": ("rostered day off", "RDO", "accrued day off", "accrued time"),
    "financial-and-monetary-provisions-end-of-band-payments": ("end of band", "top of band", "band payment"),
    "financial-and-monetary-provisions-on-call-allowance": ("on call", "on-call", "standby", "availability allowance"),
    "financial-and-monetary-provisions-personal-leave-cash-out-and-donation-pool": ("personal leave cash out", "donation pool", "donate leave"),
    "financial-and-monetary-provisions-annual-leave-cash-out-rules": ("annual leave cash out", "cash out annual leave", "cashing out paid annual leave", "cashing out of paid annual leave", "cashed out annual leave"),
    "financial-and-monetary-provisions-dependent-care-reimbursement-and-support-payments": ("dependent care", "child care reimbursement", "care reimbursement"),
    "financial-and-monetary-provisions-first-aid-allowance": ("first aid allowance", "first aid officer"),
    "financial-and-monetary-provisions-plant-and-industry-allowances-values-and-parameters": ("plant allowance", "industry allowance", "tool allowance"),
    "financial-and-monetary-provisions-vehicle-insurance-excess-reimbursement": ("insurance excess", "vehicle excess", "excess reimbursement", "motor vehicle excess", "no claim bonus"),
    "financial-and-monetary-provisions-accident-make-up-pay": ("accident make up pay", "accident make-up pay", "workers compensation top up"),
    "work-health-and-safety-and-environmental-conditions-temperature-and-thermal-comfort-provisions": ("temperature", "thermal comfort", "heat", "inclement weather"),
    "parental-and-family-related-enhancements-extended-caring-cohorts": ("extended caring", "kinship care", "permanent care", "foster care", "significant person", "foster child", "dependent person", "frail or aged dependent"),
    "parental-and-family-related-enhancements-fertility-treatment-leave": ("fertility treatment", "IVF", "assisted reproductive", "reproductive treatment"),
    "parental-and-family-related-enhancements-prenatal-leave": ("prenatal leave", "pre-natal leave", "antenatal", "ante-natal"),
    "parental-and-family-related-enhancements-stillbirth-and-neonatal-loss-provisions": ("stillbirth", "still born", "stillborn child", "neonatal loss", "neo-natal loss", "neo natal death", "pregnancy loss", "birth of a living child", "special parental leave"),
    "parental-and-family-related-enhancements-surrogacy-and-intended-parent-support-leave": ("surrogacy", "intended parent", "permanent care placement"),
    "superannuation-superannuation-above-legislated-minimum": ("superannuation above legislated minimum", "above superannuation guarantee", "additional superannuation contribution", "additional employer superannuation", "pre-tax superannuation contribution"),
    "superannuation-superannuation-on-paid-parental-leave": ("superannuation on paid parental leave", "super on paid parental leave", "superannuation contributions during paid parental leave", "superannuation contributions while on paid parental leave", "superannuation on all paid parental leave"),
    "superannuation-superannuation-on-unpaid-parental-leave-fixed-super": ("superannuation on unpaid parental leave", "super on unpaid parental leave", "superannuation contributions during unpaid parental leave", "superannuation contributions while on unpaid parental leave", "superannuation during the unpaid portion"),
    "wellbeing-and-support-gender-affirmation-or-transition-leave": ("gender affirmation", "gender transition", "transition leave", "affirmation transition gender", "affirmation of gender"),
    "wellbeing-and-support-infectious-disease-or-pandemic-leave": ("pandemic leave", "infectious disease leave", "isolation leave", "quarantine leave"),
    "wellbeing-and-support-menstrual-and-menopause-leave": ("menstrual leave", "menopause leave", "menstrual menopause", "menstruation and menopause"),
    "wellbeing-and-support-wellbeing-days": ("wellbeing day", "wellbeing leave", "mental health day"),
    "wellbeing-and-support-employee-assistance-program": ("employee assistance program", "EAP", "counselling"),
}


GENERIC_REGEX_HINTS: dict[str, tuple[tuple[str, str], ...]] = {
    "leave-union-training-leave": (
        ("union_delegate_training", r"\bunion\b[\s\S]{0,120}\btraining\b|\btraining\b[\s\S]{0,120}\bunion\b"),
        ("industrial_training_leave", r"\bindustrial\b[\s\S]{0,80}\btraining\b"),
        ("delegate_training_leave", r"\bdelegates?\b[\s\S]{0,100}\btraining\b"),
    ),
    "leave-volunteer-or-donor-leave": (
        ("blood_donor_leave", r"\bblood\b[\s\S]{0,80}\bdonor\b|\bdonor\b[\s\S]{0,80}\bleave\b"),
        ("volunteer_day_leave", r"\bvolunteer\b[\s\S]{0,80}\b(?:day|leave|work)\b"),
    ),
    "conditions-work-from-home-protections": (
        ("working_from_home_flexible_work", r"\bworking?\s+from\s+home\b|\bwork\s+from\s+home\b|\bremote\s+work(?:ing)?\b"),
        ("flexible_work_location", r"\bflexible\s+work(?:ing)?\s+arrangements?\b[\s\S]{0,260}\b(?:home|remote|location)\b"),
    ),
    "conditions-christmas-to-new-year-closure": (
        ("christmas_closedown", r"\bchristmas\b[\s\S]{0,140}\b(?:new\s+year|closedown|close\s+down|shutdown)\b|\b(?:closedown|close\s+down|shutdown)\b[\s\S]{0,140}\bchristmas\b"),
    ),
    "financial-and-monetary-provisions-end-of-band-payments": (
        ("end_of_band_payment", r"\b(?:end|top)\s+of\s+band\b[\s\S]{0,180}\b(?:payment|allowance|bonus|lump\s+sum|\$)\b"),
    ),
    "financial-and-monetary-provisions-personal-leave-cash-out-and-donation-pool": (
        ("personal_leave_pool", r"\bpersonal\s+leave\b[\s\S]{0,140}\b(?:pool|donat|cash\s*out|cashed\s*out|gratuity)\b"),
        ("sick_leave_gratuity", r"\bsick\s+leave\b[\s\S]{0,80}\bgratuity\b"),
    ),
    "financial-and-monetary-provisions-annual-leave-cash-out-rules": (
        ("annual_leave_cashing_out", r"\bannual\s+leave\b[\s\S]{0,120}\b(?:cash\s*out|cashed\s*out|cashing\s+out)\b|\b(?:cash\s*out|cashed\s*out|cashing\s+out)\b[\s\S]{0,120}\bannual\s+leave\b"),
    ),
    "financial-and-monetary-provisions-vehicle-insurance-excess-reimbursement": (
        ("vehicle_insurance_excess", r"\b(?:vehicle|motor\s+vehicle|car)\b[\s\S]{0,120}\b(?:insurance\s+)?excess\b|\binsurance\s+excess\b[\s\S]{0,120}\b(?:vehicle|motor\s+vehicle|car)\b"),
        ("no_claim_bonus", r"\bno\s+claim\s+bonus\b"),
    ),
    "parental-and-family-related-enhancements-fertility-treatment-leave": (
        ("fertility_treatment_leave", r"\bfertility\b[\s\S]{0,100}\b(?:treatment|leave|ivf|procedure)\b|\bIVF\b[\s\S]{0,100}\b(?:leave|treatment|appointment)\b"),
    ),
    "parental-and-family-related-enhancements-prenatal-leave": (
        ("prenatal_appointment_leave", r"\bpre[-\s]*natal\b[\s\S]{0,140}\b(?:leave|appointment|medical)\b|\bantenatal\b[\s\S]{0,140}\b(?:leave|appointment|medical)\b"),
    ),
    "parental-and-family-related-enhancements-extended-caring-cohorts": (
        ("extended_caring_cohorts", r"\b(?:significant|dependent|frail|aged|foster|kinship|permanent\s+care)\b[\s\S]{0,120}\b(?:person|child|dependent|care|family|household)\b"),
        ("immediate_family_extended_definition", r"\bimmediate\s+family\b[\s\S]{0,260}\b(?:includes?|extended|foster|significant|dependent|frail|aged|household)\b"),
        ("household_family_definition", r"\b(?:household|family)\b[\s\S]{0,220}\b(?:foster|significant|dependent|frail|aged|kinship|permanent\s+care)\b"),
    ),
    "parental-and-family-related-enhancements-stillbirth-and-neonatal-loss-provisions": (
        ("stillbirth_neonatal_loss", r"\bstill[-\s]*born\b|\bstillbirth\b|\bneo[-\s]*natal\b|\bneonatal\b"),
        ("pregnancy_not_living_child", r"\bpregnancy\b[\s\S]{0,120}\b(?:ends|terminates|terminated)\b[\s\S]{0,160}\b(?:living\s+child|birth)\b"),
        ("special_parental_loss_leave", r"\bspecial\s+parental\s+leave\b[\s\S]{0,220}\b(?:pregnancy|still|neonatal|living\s+child)\b"),
    ),
    "superannuation-superannuation-above-legislated-minimum": (
        ("above_minimum_super", r"\b(?:additional|above|extra)\b[\s\S]{0,100}\bsuperannuation\b|\bsuperannuation\b[\s\S]{0,100}\b(?:additional|above|extra|pre[-\s]*tax)\b"),
        ("super_threshold_contribution", r"\b(?:\$?\s*1,?200|\$?\s*450)\b[\s\S]{0,180}\bsuperannuation\b|\bsuperannuation\b[\s\S]{0,180}\b(?:\$?\s*1,?200|\$?\s*450)\b"),
        ("casual_super_three_percent", r"\bcasual\b[\s\S]{0,180}\bsuperannuation\b[\s\S]{0,120}\b3\s*(?:%|percent)\b"),
    ),
    "superannuation-superannuation-on-paid-parental-leave": (
        ("super_parental_leave_general", r"\bsuperannuation\b[\s\S]{0,220}\bparental\s+leave\b|\bparental\s+leave\b[\s\S]{0,220}\bsuperannuation\b"),
        ("super_paid_parental_leave", r"\bsuperannuation\b[\s\S]{0,180}\bpaid\s+parental\s+leave\b|\bpaid\s+parental\s+leave\b[\s\S]{0,180}\bsuperannuation\b"),
        ("super_paid_and_unpaid_parental_leave", r"\bsuperannuation\b[\s\S]{0,180}\bpaid\s+and\s+unpaid\s+parental\s+leave\b|\bpaid\s+and\s+unpaid\s+parental\s+leave\b[\s\S]{0,180}\bsuperannuation\b"),
        ("super_any_paid_leave_parental", r"\bsuperannuation\b[\s\S]{0,140}\bany\s+paid\s+leave\b[\s\S]{0,260}\bparental\s+leave\b"),
        ("paid_parental_super_continues", r"\bparental\s+leave\b[\s\S]{0,180}\bsuperannuation\s+contributions?\b[\s\S]{0,120}\b(?:paid|continue|continues|continued)\b"),
    ),
    "superannuation-superannuation-on-unpaid-parental-leave-fixed-super": (
        ("super_parental_leave_general", r"\bsuperannuation\b[\s\S]{0,220}\bparental\s+leave\b|\bparental\s+leave\b[\s\S]{0,220}\bsuperannuation\b"),
        ("super_unpaid_parental_leave", r"\bsuperannuation\b[\s\S]{0,180}\bunpaid\s+parental\s+leave\b|\bunpaid\s+parental\s+leave\b[\s\S]{0,180}\bsuperannuation\b"),
        ("super_unpaid_portion_parental", r"\bsuperannuation\b[\s\S]{0,180}\bunpaid\s+portion\b[\s\S]{0,160}\bparental\s+leave\b"),
        ("parental_leave_fixed_super_payment", r"\bparental\s+leave\b[\s\S]{0,220}\b(?:superannuation|super)\b[\s\S]{0,140}\b(?:contribution|payment|weeks?|months?)\b"),
    ),
    "wellbeing-and-support-gender-affirmation-or-transition-leave": (
        ("affirmation_transition_gender", r"\baffirmation\b[\s\S]{0,80}\btransition\b[\s\S]{0,80}\bgender\b|\btransition\b[\s\S]{0,80}\bgender\b"),
        ("gender_affirmation_leave", r"\bgender\b[\s\S]{0,120}\b(?:affirmation|transition)\b[\s\S]{0,120}\bleave\b"),
    ),
    "wellbeing-and-support-infectious-disease-or-pandemic-leave": (
        ("pandemic_infectious_leave", r"\b(?:pandemic|infectious\s+disease|quarantine|isolation)\b[\s\S]{0,140}\b(?:leave|stand\s+down|paid)\b"),
    ),
    "wellbeing-and-support-menstrual-and-menopause-leave": (
        ("menstrual_menopause_leave", r"\b(?:menstrual|menstruation|menopause)\b[\s\S]{0,160}\b(?:leave|inability\s+to\s+perform|symptoms)\b"),
    ),
}


GENERIC_OUT_OF_SCOPE_HINTS: dict[str, tuple[tuple[str, str], ...]] = {
    "conditions-work-from-home-protections": (
        ("remote_response_not_work_from_home", r"\bremote\s+response\b|\bafter\s+hours\s+IT\s+helpdesk\b|\brecall\s+to\s+work\b"),
    ),
    "financial-and-monetary-provisions-end-of-band-payments": (
        ("annual_leave_not_payment", r"\badditional\s+annual\s+leave\b|\bannual\s+leave\b"),
        ("performance_review_not_payment", r"\bperformance\s+(?:and\s+development\s+)?review\b|\bclassification\s+structure\b"),
        ("volunteer_leave_not_payment", r"\bvolunteer\b|\bemergency\s+services?\b"),
    ),
    "leave-volunteer-or-donor-leave": (
        ("annual_leave_cashout_not_volunteer", r"\bannual\s+leave\b[\s\S]{0,160}\b(?:cash\s*out|cashed\s*out|cashing\s+out)\b"),
    ),
    "superannuation-superannuation-above-legislated-minimum": (
        ("baseline_super_guarantee_only", r"\bavoid\b[\s\S]{0,80}\bsuperannuation\s+guarantee\s+charge\b"),
        ("salary_sacrifice_not_above_minimum", r"\bsalary\s+sacrifice\b"),
        ("accident_pay_not_super_minimum", r"\baccident\s+(?:make[-\s]*up\s+)?pay\b"),
        ("parental_leave_super_not_above_minimum", r"\bparental\s+leave\b|\bpaid\s+leave\b"),
    ),
}


def slug_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def taxonomy_rows() -> list[dict[str, str]]:
    if not ENTITLEMENT_TAXONOMY_PATH.exists():
        return []
    with ENTITLEMENT_TAXONOMY_PATH.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def short_council_name(value: str) -> str:
    text = re.sub(r"\bRural City Council\b", "", str(value or ""), flags=re.I)
    text = re.sub(r"\bCity Council\b", "", text, flags=re.I)
    text = re.sub(r"\bShire Council\b", "", text, flags=re.I)
    text = re.sub(r"\bCouncil\b", "", text, flags=re.I)
    text = re.sub(r"^Borough of\s+", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip() or str(value or "").strip()


def has_cached_pages(agreement_id: str) -> bool:
    return (ROOT / "cache" / str(agreement_id or "").lower() / "pages.json").exists()


def governed_active_council_agreements() -> list[dict[str, str]]:
    if not GOVERNED_COUNCIL_AGREEMENTS_PATH.exists():
        return annual.all_cached_agreements()
    grouped: dict[str, list[dict[str, str]]] = {}
    with GOVERNED_COUNCIL_AGREEMENTS_PATH.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("pipeline_status") or "") != "active":
                continue
            council_key = str(row.get("council_key") or row.get("council_name") or "").strip()
            agreement_id = str(row.get("agreement_id") or "").lower()
            if not council_key or not agreement_id:
                continue
            grouped.setdefault(council_key, []).append(row)

    agreements: list[dict[str, str]] = []
    for council_key, rows in grouped.items():
        rows.sort(
            key=lambda row: (
                has_cached_pages(row.get("agreement_id", "")),
                "__" in str(row.get("agreement_id") or ""),
                str(row.get("agreement_id") or ""),
            ),
            reverse=True,
        )
        row = rows[0]
        agreement_id = str(row.get("agreement_id") or "").lower()
        agreements.append(
            {
                "council": short_council_name(row.get("council_name") or council_key),
                "council_key": council_key,
                "council_name": row.get("council_name") or council_key,
                "agreement_id": agreement_id,
                "resolved_from_agreement_id": str(row.get("base_agreement_id") or agreement_id).lower(),
                "latest_resolution": "governed_active_council_agreement",
            }
        )
    return sorted(agreements, key=lambda row: row["council"])


def phrase_pattern(phrase: str) -> re.Pattern[str] | None:
    cleaned = re.sub(r"[^0-9A-Za-z]+", " ", str(phrase or "")).strip()
    if len(cleaned) < 3:
        return None
    parts = [re.escape(part) for part in cleaned.split() if part]
    if not parts:
        return None
    return re.compile(r"\b" + r"[\s\-/]+".join(parts) + r"\b", re.I)


def taxonomy_aliases(row: dict[str, str]) -> list[str]:
    entitlement_id = row.get("entitlement_id", "")
    label = row.get("entitlement_label", "")
    aliases = [label]
    if " and " in label.lower():
        aliases.append(re.sub(r"\band\b", "or", label, flags=re.I))
        aliases.append(re.sub(r"\s+and\s+", " / ", label, flags=re.I))
    aliases.extend(GENERIC_ALIAS_HINTS.get(entitlement_id, ()))
    return sorted({item.strip() for item in aliases if item and item.strip()}, key=lambda item: (len(item), item.lower()))


def taxonomy_profile_from_row(row: dict[str, str]) -> dict[str, Any]:
    entitlement_id = row.get("entitlement_id", "")
    override = learned_rule_override_for(entitlement_id)
    aliases = taxonomy_aliases(row)
    aliases.extend(
        str(alias)
        for alias in override.get("candidate_aliases", [])
        if str(alias or "").strip()
    )
    candidate_patterns = [
        (slug_key(alias), pattern)
        for alias in aliases
        for pattern in [phrase_pattern(alias)]
        if pattern is not None
    ]
    candidate_patterns.extend(
        (label, re.compile(pattern, re.I))
        for label, pattern in GENERIC_REGEX_HINTS.get(entitlement_id, ())
    )
    if not candidate_patterns:
        fallback = phrase_pattern(entitlement_id.replace("-", " "))
        if fallback is not None:
            candidate_patterns.append((slug_key(entitlement_id), fallback))
    out_of_scope_patterns = [("table_of_contents", re.compile(r"\.{6,}\s+\d+", re.I))]
    out_of_scope_patterns.extend(
        (label, re.compile(pattern, re.I))
        for label, pattern in GENERIC_OUT_OF_SCOPE_HINTS.get(entitlement_id, ())
    )
    profile = {
        "artifact_id": f"{entitlement_id}-taxonomy-locator",
        "entitlement_id": entitlement_id,
        "label": row.get("entitlement_label") or row.get("entitlement_id"),
        "definition": row.get("definition", ""),
        "taxonomy_path": [row.get("category", ""), row.get("entitlement_label", "")],
        "scope": row.get("scope") or "standard_employees",
        "candidate_patterns": candidate_patterns,
        "context_patterns": candidate_patterns,
        "positive_patterns": candidate_patterns,
        "out_of_scope_patterns": out_of_scope_patterns,
        "accepted_subclasses": [
            {
                "subclass_id": f"{row.get('entitlement_id')}.candidate-provision",
                "label": f"{row.get('entitlement_label') or row.get('entitlement_id')} Candidate Provision",
                "relationship": "candidate_entitlement_presence",
            }
        ],
        "lookahead_pages": 1,
        "generic_taxonomy_locator": True,
    }
    return apply_learned_rule_override(profile)


def taxonomy_locator_specs() -> list[LocatorSpec]:
    specialised_ids = {spec.entitlement_id for spec in SPECIALISED_LOCATOR_SPECS}
    specs: list[LocatorSpec] = []
    for row in taxonomy_rows():
        entitlement_id = str(row.get("entitlement_id") or "")
        if not entitlement_id or entitlement_id in specialised_ids:
            continue
        specs.append(
            LocatorSpec(
                key=slug_key(entitlement_id),
                entitlement_id=entitlement_id,
                label=row.get("entitlement_label") or entitlement_id,
                profile=taxonomy_profile_from_row(row),
                family="taxonomy",
            )
        )
    return specs


LOCATOR_SPECS = [*SPECIALISED_LOCATOR_SPECS, *taxonomy_locator_specs()]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def labelled_matches(patterns: list[tuple[str, re.Pattern[str]]], text: str, *, per_pattern_limit: int = 12) -> list[tuple[int, str, re.Match[str]]]:
    matches: list[tuple[int, str, re.Match[str]]] = []
    for label, pattern in patterns:
        for index, match in enumerate(pattern.finditer(text)):
            matches.append((match.start(), label, match))
            if index + 1 >= per_pattern_limit:
                break
    return sorted(matches, key=lambda item: item[0])


def first_pattern_labels(patterns: list[tuple[str, re.Pattern[str]]], text: str) -> list[str]:
    return [label for label, pattern in patterns if pattern.search(text)]


def compact_text(text: str) -> str:
    return annual.compact_text(text)


def cached_pages(agreement_id: str) -> list[str]:
    key = str(agreement_id or "").lower()
    if key not in PAGE_TEXT_CACHE:
        PAGE_TEXT_CACHE[key] = annual.load_pages(key)
    return PAGE_TEXT_CACHE[key]


def cached_page_role(agreement_id: str, page_number: int, page_text: str) -> str:
    key = (str(agreement_id or "").lower(), int(page_number))
    if key not in PAGE_ROLE_CACHE:
        PAGE_ROLE_CACHE[key] = page_role_for_text(page_text)
    return PAGE_ROLE_CACHE[key]


def cached_page_container_type(agreement_id: str, page_number: int, page_text: str) -> str:
    key = (str(agreement_id or "").lower(), int(page_number))
    if key not in PAGE_CONTAINER_TYPE_CACHE:
        PAGE_CONTAINER_TYPE_CACHE[key] = source_container_type_for_text(page_text)
    return PAGE_CONTAINER_TYPE_CACHE[key]


def window_around(text: str, start: int, end: int, *, before: int, after: int) -> str:
    return compact_text(text[max(0, start - before): min(len(text), end + after)])


def page_window(pages: list[str], page_index: int, lookahead_pages: int) -> str:
    return compact_text("\n".join(pages[page_index: min(len(pages), page_index + 1 + lookahead_pages)]))


def discovery_patterns(spec: LocatorSpec) -> list[tuple[str, re.Pattern[str]]]:
    profile = spec.profile
    if spec.family == "annual":
        return annual.discovery_patterns(profile)
    return [
        *profile["candidate_patterns"],
        *profile.get("context_patterns", []),
    ]


def contents_indicators_for_spec(spec: LocatorSpec, pages: list[str]) -> list[dict[str, Any]]:
    indicators: list[dict[str, Any]] = []
    patterns = discovery_patterns(spec)
    for page_index, page_text in enumerate(pages[:12]):
        if not page_text:
            continue
        likely_contents_page = standard.is_probable_table_of_contents(page_text) or bool(
            re.search(r"\b(table\s+of\s+contents|contents)\b", page_text[:1600], flags=re.I)
        )
        if not likely_contents_page:
            continue
        for start, label, match in labelled_matches(patterns, page_text, per_pattern_limit=4):
            local = window_around(page_text, match.start(), match.end(), before=80, after=220)
            page_match = re.search(r"(?:\.{2,}|\s{3,})(\d{1,3})\b", local)
            indicators.append({
                "contents_page": page_index + 1,
                "matched_term": label,
                "target_page_label": int(page_match.group(1)) if page_match else None,
                "excerpt": local,
                "source_ref": annual.source_ref(
                    "contents-index",
                    page_index + 1,
                    evidence_state="contents_indicator_not_source_evidence",
                    heading=spec.label,
                ),
            })
    return indicators[:12]


def context_hits(spec: LocatorSpec, excerpt: str) -> list[str]:
    profile = spec.profile
    if spec.family == "annual":
        positives = [
            label
            for label, pattern in profile["positive_patterns"]
            if pattern.search(excerpt)
        ]
        return sorted({*positives, *annual.learned_pattern_labels(profile, excerpt)})
    patterns = profile.get("context_patterns") or profile["candidate_patterns"]
    return first_pattern_labels(patterns, excerpt)


def positive_hits(spec: LocatorSpec, excerpt: str) -> list[str]:
    return first_pattern_labels(spec.profile["positive_patterns"], excerpt)


def local_blockers(
    spec: LocatorSpec,
    excerpt: str,
    local_text: str,
    values: list[dict[str, str]],
    *,
    page_role: str = "",
) -> list[str]:
    if spec.family == "annual":
        positives = positive_hits(spec, excerpt)
        raw = annual.out_of_scope_signals(local_text)
        if annual.is_probable_table_of_contents(local_text):
            raw.append("table_of_contents")
        if page_role == "table_of_contents":
            raw.append("table_of_contents")
        if page_role == "approval_decision_front_matter":
            raw.append("approval_decision_front_matter")
        return annual.blocking_scope_signals(positives, raw, local_text)

    profile = spec.profile
    blockers = first_pattern_labels(profile["out_of_scope_patterns"], local_text)
    if standard.is_probable_table_of_contents(local_text):
        blockers.append("table_of_contents")
    if page_role == "table_of_contents":
        blockers.append("table_of_contents")
    if page_role == "approval_decision_front_matter":
        blockers.append("approval_decision_front_matter")
    blockers = sorted(set(blockers))

    entitlement_id = profile["entitlement_id"]
    if values and entitlement_id == standard.NATURAL_DISASTER_PROFILE["entitlement_id"]:
        blockers = [
            label
            for label in blockers
            if label not in {"carers_unexpected_emergency", "emergency_services_volunteer"}
        ]
    if values and entitlement_id == standard.COMPASSIONATE_PROFILE["entitlement_id"]:
        blockers = [
            label
            for label in blockers
            if label not in {"unpaid_only", "annual_or_long_service_recredit"}
        ]
    if values and entitlement_id == standard.EMERGENCY_SERVICES_PROFILE["entitlement_id"]:
        blockers = [
            label
            for label in blockers
            if label not in {
                "natural_disaster_employee_impact",
                "jury_or_court_service",
                "defence_or_armed_forces",
                "blood_or_general_volunteer",
            }
        ]
    if values and entitlement_id in {
        standard.PARENTAL_PRIMARY_PROFILE["entitlement_id"],
        standard.PARENTAL_NON_PRIMARY_PROFILE["entitlement_id"],
    }:
        blockers = [
            label
            for label in blockers
            if label not in {
                "special_caregiver_or_loss_leave",
                "unpaid_parental_leave_only",
                "safe_job_or_return_to_work",
                "surrogacy_only",
            }
        ]
    return sorted(set(blockers))


GENERIC_QUANTITY_PATTERN = re.compile(
    r"\b(?:up to|maximum of|minimum of|entitled to|access to|provides?|offers?|receive)?\s*"
    r"(?P<value>\d{1,3}(?:\.\d+)?)\s*(?P<unit>days?|weeks?|hours?|months?)\b",
    re.I,
)
GENERIC_NUMBER_WORDS = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}
GENERIC_WORD_QUANTITY_PATTERN = re.compile(
    r"\b(?:up to|maximum of|minimum of|entitled to|access to|provides?|offers?|receive)?\s*"
    r"(?P<value_word>one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?P<unit>days?|weeks?|hours?|months?)\b",
    re.I,
)
GENERIC_MONEY_PATTERN = re.compile(r"\$\s*(?P<value>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\b", re.I)
GENERIC_PERCENT_PATTERN = re.compile(r"\b(?P<value>\d{1,3}(?:\.\d+)?)\s*(?:%|percent)\b", re.I)
GENERIC_PRESENT_PATTERN = re.compile(
    r"\b(paid|leave|allowance|reimbursement|program|support|available|provided|entitled|may access|will be granted)\b",
    re.I,
)


def taxonomy_context_noise_reasons(spec: LocatorSpec, context: str) -> list[str]:
    entitlement_id = spec.entitlement_id
    text = context or ""
    lower = text.lower()
    reasons: list[str] = []
    if entitlement_id == "conditions-work-from-home-protections" and re.search(
        r"\b(remote\s+response|after\s+hours\s+IT\s+helpdesk|recall\s+to\s+work|on[-\s]*call)\b",
        text,
        flags=re.I,
    ):
        reasons.append("remote_response_or_on_call_not_work_from_home")
    if entitlement_id == "financial-and-monetary-provisions-end-of-band-payments":
        if re.search(r"\b(additional\s+annual\s+leave|annual\s+leave|volunteer|emergency\s+services?)\b", text, flags=re.I):
            reasons.append("leave_or_volunteer_not_end_of_band_payment")
        if not re.search(r"\b(payment|allowance|bonus|lump\s+sum|gratuity|\$)\b", text, flags=re.I):
            reasons.append("no_monetary_payment_language")
    if entitlement_id == "leave-volunteer-or-donor-leave" and re.search(
        r"\bannual\s+leave\b[\s\S]{0,180}\b(cash\s*out|cashed\s*out|cashing\s+out)\b",
        text,
        flags=re.I,
    ):
        reasons.append("annual_leave_cashout_not_volunteer_or_donor")
    if entitlement_id == "superannuation-superannuation-above-legislated-minimum":
        positive_marker = re.search(
            r"\b(additional|above|extra|pre[-\s]*tax|0\.5\s*%|3\s*(?:%|percent)|\$?\s*1,?200|\$?\s*450|threshold)\b",
            text,
            flags=re.I,
        )
        if re.search(r"\b(parental\s+leave|paid\s+leave|salary\s+sacrifice|accident\s+(?:make[-\s]*up\s+)?pay)\b", text, flags=re.I):
            reasons.append("other_super_context_not_above_minimum")
        if re.search(r"\bavoid\b[\s\S]{0,80}\bsuperannuation\s+guarantee\s+charge\b", text, flags=re.I) and not positive_marker:
            reasons.append("baseline_super_guarantee_only")
        if not positive_marker:
            reasons.append("no_above_minimum_super_marker")
    if entitlement_id == "financial-and-monetary-provisions-on-call-allowance":
        if re.search(r"\bremote\s+response\b", text, flags=re.I) and not re.search(r"\bon[-\s]*call\b", text, flags=re.I):
            reasons.append("remote_response_not_on_call_allowance")
    return sorted(set(reasons))


def taxonomy_value_noise_reasons(
    spec: LocatorSpec,
    context: str,
    *,
    value: str,
    unit: str,
) -> list[str]:
    entitlement_id = spec.entitlement_id
    text = context or ""
    unit_text = str(unit or "").lower()
    reasons: list[str] = []
    if entitlement_id == "leave-paid-shutdown-days-christmas-to-new-year":
        if not re.search(r"\b(christmas|new\s+year|closedown|close\s+down|shut\s*down|shutdown)\b", text, flags=re.I):
            reasons.append("no_christmas_shutdown_value_context")
        if unit_text in {"hours", "hour", "months", "month", "weeks", "week"}:
            reasons.append("not_shutdown_day_quantum")
        if re.search(r"\b(personal\s+leave|sick\s+leave|maternal\s+and\s+child\s+health|MCH)\b", text, flags=re.I):
            reasons.append("other_leave_context_not_shutdown")
    if entitlement_id == "leave-personal-and-carers-leave":
        if unit_text in {"weeks", "week", "months", "month"}:
            reasons.append("likely_cap_or_other_leave_not_annual_personal_leave")
        if re.search(
            r"\b(transmittee|transmittor|transfer|transferred|accumulated\s+sick\s+leave|termination|notice\s+period|parental\s+leave)\b",
            text,
            flags=re.I,
        ):
            reasons.append("transfer_or_other_leave_context")
        if not re.search(r"\b(personal\s+leave|carer'?s?\s+leave|sick\s+leave)\b", text, flags=re.I):
            reasons.append("no_personal_carers_value_context")
    if entitlement_id == "leave-pet-leave":
        word_for_value = next((word for word, number in GENERIC_NUMBER_WORDS.items() if number == str(value)), "")
        value_pattern = re.escape(str(value))
        if word_for_value:
            value_pattern = f"(?:{value_pattern}|{re.escape(word_for_value)})"
        pet_leave_value = re.search(
            rf"\bpet\s+leave\b[\s\S]{{0,140}}\b{value_pattern}\s+days?\b|\b{value_pattern}\s+days?\b[\s\S]{{0,140}}\bpet\s+leave\b",
            text,
            flags=re.I,
        )
        natural_disaster_value = re.search(
            rf"\bnatural\s+disaster\b[\s\S]{{0,180}}\b{value_pattern}\s+days?\b",
            text,
            flags=re.I,
        )
        if (
            natural_disaster_value
            or re.search(r"\bpersonal\s+leave\s+entitlements?\s+are\s+exhausted\b", text, flags=re.I)
            and not pet_leave_value
        ):
            reasons.append("other_leave_context_not_pet_leave")
        if unit_text in {"hours", "hour"}:
            reasons.append("notification_hours_not_pet_leave_duration")
        if re.search(r"\b(notification|notice|provide\s+\d+\s+hours|personal\s+leave)\b", text, flags=re.I) and not re.search(
            r"\b(pet\s+leave|companion\s+animal\b[\s\S]{0,120}\b(?:death|euthan|bereave))\b",
            text,
            flags=re.I,
        ):
            reasons.append("administrative_or_general_personal_leave_context")
    if entitlement_id == "leave-purchased-leave-scheme":
        if unit_text in {"aud", "percent"}:
            reasons.append("salary_calculation_not_scheme_duration")
        if re.search(r"\b(termination|notice\s+period|redundancy|severance)\b", text, flags=re.I):
            reasons.append("termination_notice_not_purchased_leave")
        if not re.search(
            r"\b(purchased\s+leave|purchase\s+leave|48/52|49/52|50/52|51/52|four\s+over\s+five|salary\s+sacrifice)\b",
            text,
            flags=re.I,
        ):
            reasons.append("no_purchased_leave_scheme_context")
    if entitlement_id == "leave-study-and-professional-development-leave":
        if re.search(
            r"\b(?:after\s+)?\d+\s+(?:months?|years?)\s+(?:service|continuous\s+service|employment)\b",
            text,
            flags=re.I,
        ):
            reasons.append("eligibility_period_not_study_leave_quantum")
        if not re.search(
            r"\b(study\s+leave|professional\s+development|education\s+assistance|examination\s+leave|approved\s+stud(?:y|ies)|training\s+course)\b",
            text,
            flags=re.I,
        ):
            reasons.append("no_study_leave_value_context")
    if entitlement_id == "leave-union-training-leave":
        positive_union_leave = re.search(
            r"\b(?:entitled|entitlement|up\s+to|shall\s+receive|provides?)\b[\s\S]{0,120}\b(?:days?|weeks?)\b"
            r"[\s\S]{0,180}\b(?:paid\s+leave|union\s+(?:training|provided)|trade\s+union\s+training|courses?|conference)",
            text,
            flags=re.I,
        ) or re.search(
            r"\b(?:days?|weeks?)\b[\s\S]{0,80}\bpaid\s+leave\b[\s\S]{0,160}\b(?:union|training|courses?|conference)",
            text,
            flags=re.I,
        )
        if unit_text in {"hours", "hour"}:
            reasons.append("hourly_contact_cap_not_leave_duration")
        if unit_text in {"aud", "percent"}:
            reasons.append("money_or_percent_not_union_training_leave")
        if re.search(
            r"\b(notice|application|apply|approval|approved|evidence|certificate|submit|submitted|provide|prior\s+to|before\s+attending|after\s+completion)\b",
            text,
            flags=re.I,
        ) and not positive_union_leave:
            reasons.append("administrative_timeframe_not_leave_quantum")
        if not re.search(r"\b(union|delegate|representative|industrial)\b[\s\S]{0,160}\b(training|conference|course|leave)\b", text, flags=re.I):
            reasons.append("no_union_training_value_context")
    return sorted(set(reasons))


def filter_taxonomy_values(spec: LocatorSpec, context: str, values: list[dict[str, str]]) -> list[dict[str, str]]:
    if not values:
        return values
    if taxonomy_context_noise_reasons(spec, context):
        return []
    entitlement_id = spec.entitlement_id
    if entitlement_id == "financial-and-monetary-provisions-vehicle-insurance-excess-reimbursement":
        return [
            value
            for value in values
            if value.get("unit") == "AUD" or value.get("value") == "available"
        ]
    if entitlement_id == "financial-and-monetary-provisions-end-of-band-payments":
        return [
            value
            for value in values
            if value.get("unit") == "AUD" or value.get("value") == "available"
        ]
    if entitlement_id == "superannuation-superannuation-above-legislated-minimum":
        return [
            value
            for value in values
            if value.get("unit") in {"AUD", "percent"} or value.get("value") == "available"
        ]
    return values


def generic_taxonomy_contexts(spec: LocatorSpec, excerpt: str) -> list[str]:
    contexts: list[str] = []
    seen: set[str] = set()
    for _label, pattern in spec.profile.get("candidate_patterns", []):
        for match in pattern.finditer(excerpt):
            start = max(0, match.start() - 240)
            end = min(len(excerpt), match.end() + 760)
            context = compact_text(excerpt[start:end])
            key = text_hash(context[:320]) if context else ""
            if context and key not in seen:
                contexts.append(context)
                seen.add(key)
            if len(contexts) >= 3:
                return contexts
    return contexts or [compact_text(excerpt[:1200])]


def taxonomy_candidate_value_record(
    spec: LocatorSpec,
    *,
    value: str,
    unit: str,
    condition: str,
) -> dict[str, str]:
    return {
        "subclass_id": f"{spec.entitlement_id}.candidate-provision",
        "subclass_label": f"{spec.label} Candidate Provision",
        "value": value,
        "unit": unit,
        "condition": condition,
        "benchmark_value": "false",
    }


def generic_values_for_taxonomy(spec: LocatorSpec, excerpt: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def append(value: str, unit: str, condition: str) -> None:
        key = (value, unit, condition)
        if key in seen:
            return
        seen.add(key)
        records.append(
            taxonomy_candidate_value_record(
                spec,
                value=value,
                unit=unit,
                condition=condition,
            )
        )

    contexts = generic_taxonomy_contexts(spec, excerpt)
    for context in contexts:
        if taxonomy_context_noise_reasons(spec, context):
            continue
        for match in GENERIC_QUANTITY_PATTERN.finditer(context):
            value_context = compact_text(context[max(0, match.start() - 220): min(len(context), match.end() + 360)])
            if taxonomy_value_noise_reasons(
                spec,
                value_context,
                value=match.group("value"),
                unit=match.group("unit").lower(),
            ):
                continue
            append(
                match.group("value"),
                match.group("unit").lower(),
                "candidate quantified provision near entitlement language",
            )
            if len(records) >= 4:
                return records
        for match in GENERIC_WORD_QUANTITY_PATTERN.finditer(context):
            value = GENERIC_NUMBER_WORDS[match.group("value_word").lower()]
            unit = match.group("unit").lower()
            value_context = compact_text(context[max(0, match.start() - 220): min(len(context), match.end() + 360)])
            if taxonomy_value_noise_reasons(spec, value_context, value=value, unit=unit):
                continue
            append(
                value,
                unit,
                "candidate quantified provision near entitlement language",
            )
            if len(records) >= 4:
                return records
        for match in GENERIC_PERCENT_PATTERN.finditer(context):
            value_context = compact_text(context[max(0, match.start() - 220): min(len(context), match.end() + 360)])
            if taxonomy_value_noise_reasons(spec, value_context, value=match.group("value"), unit="percent"):
                continue
            append(
                match.group("value"),
                "percent",
                "candidate percentage provision near entitlement language",
            )
            if len(records) >= 4:
                return records
        for match in GENERIC_MONEY_PATTERN.finditer(context):
            value_context = compact_text(context[max(0, match.start() - 220): min(len(context), match.end() + 360)])
            if taxonomy_value_noise_reasons(spec, value_context, value=match.group("value"), unit="AUD"):
                continue
            append(
                match.group("value").replace(",", ""),
                "AUD",
                "candidate monetary provision near entitlement language",
            )
            if len(records) >= 4:
                return records

    output_contract = exemplar_output_contract(spec.entitlement_id)
    if any(GENERIC_PRESENT_PATTERN.search(context) for context in contexts) or (
        contexts and output_contract.get("answer_kind") in {"boolean", "descriptive"}
    ):
        append("available", "candidate provision", "taxonomy locator candidate")
    return filter_taxonomy_values(spec, " ".join(contexts), records)


def values_for_spec(spec: LocatorSpec, council: str, excerpt: str) -> list[dict[str, str]]:
    if spec.family == "annual":
        return annual.clause_values_for_council(council, excerpt)
    if spec.family == "taxonomy":
        return generic_values_for_taxonomy(spec, excerpt)
    return standard.values_for_profile(spec.profile, excerpt)


def generic_heading_from_excerpt(spec: LocatorSpec, excerpt: str) -> str:
    patterns = spec.profile.get("candidate_patterns", [])
    lines = [compact_text(line) for line in excerpt.splitlines() if compact_text(line)]
    for line in lines[:40]:
        if any(pattern.search(line) for _label, pattern in patterns):
            return line[:120]
    return spec.label


def heading_for_spec(spec: LocatorSpec, excerpt: str) -> str:
    if spec.family == "annual":
        return annual.heading_from_excerpt(excerpt)
    if spec.family == "taxonomy":
        return generic_heading_from_excerpt(spec, excerpt)
    return standard.candidate_heading(spec.profile, excerpt)


def classify_state(
    *,
    values: list[dict[str, str]],
    blockers: list[str],
    candidate_labels: list[str],
    context_labels: list[str],
    positive_labels: list[str],
) -> str:
    if "table_of_contents" in blockers:
        return "adjacent_or_blocked_clause_found"
    if HARD_SOURCE_CONTEXT_BLOCKERS.intersection(blockers):
        return "adjacent_or_blocked_clause_found"
    if values:
        return "clause_found_value_extracted"
    if blockers:
        return "adjacent_or_blocked_clause_found"
    if context_labels or positive_labels or candidate_labels:
        return "clause_found_value_missing"
    return "weak_candidate_clause_found"


def is_weak_generic_candidate(spec: LocatorSpec, terms: set[str], values: list[dict[str, str]]) -> bool:
    if values:
        return False
    if spec.entitlement_id == standard.EMERGENCY_SERVICES_PROFILE["entitlement_id"]:
        emergency_terms = {
            "emergency_services_context",
            "emergency_services_leave",
            "community_services_emergency_services",
            "emergency_service_organisation",
            "voluntary_emergency_management",
            "emergency_services_volunteers",
            "emergency_callout",
            "recognised_emergency_body",
        }
        return not bool(terms.intersection(emergency_terms))
    return False


def candidate_score(state: str, values: list[dict[str, str]], blockers: list[str], positive_labels: list[str], context_labels: list[str]) -> int:
    base = {
        "clause_found_value_extracted": 90,
        "clause_found_value_missing": 62,
        "adjacent_or_blocked_clause_found": 30,
        "weak_candidate_clause_found": 18,
    }[state]
    benchmark_values = sum(1 for value in values if value.get("benchmark_value") == "true")
    return base + (8 * benchmark_values) + (2 * len(values)) + (3 * len(positive_labels)) + (2 * len(context_labels)) - (8 * len(blockers))


def clause_number_from_heading(heading: str) -> str:
    match = re.match(r"\s*(\d+(?:\.\d+)*)", heading or "")
    return match.group(1) if match else ""


def review_status_for_state(state: str, values: list[dict[str, str]], blockers: list[str]) -> str:
    if state == "clause_found_value_extracted" and not blockers:
        if any(value.get("benchmark_value") == "true" for value in values):
            return "auto_extracted_benchmark_value"
        return "auto_extracted_non_benchmark_support"
    if state == "clause_found_value_missing":
        return "needs_quantification_review"
    if state == "adjacent_or_blocked_clause_found":
        return "needs_scope_review"
    return "routing_signal_only"


def learned_feature_card_review(spec: LocatorSpec) -> dict[str, Any]:
    rules = spec.profile.get("learned_loop_rules") if isinstance(spec.profile.get("learned_loop_rules"), dict) else {}
    review = rules.get("feature_card_llm_review")
    return review if isinstance(review, dict) else {}


def value_requires_context_basis(values: list[dict[str, str]]) -> bool:
    return any(str(value.get("unit") or "") in FEATURE_CARD_QUANTUM_UNITS for value in values)


def has_timeframe_context(text: str, values: list[dict[str, str]]) -> bool:
    haystack = " ".join([
        str(text or ""),
        *[str(value.get("condition") or "") for value in values],
        *[str(value.get("unit") or "") for value in values],
    ])
    return bool(FEATURE_CARD_TIMEFRAME_RE.search(haystack))


def feature_card_llm_context_flags(
    spec: LocatorSpec,
    *,
    values: list[dict[str, str]],
    source_text: str,
    excerpt: str,
) -> list[str]:
    review = learned_feature_card_review(spec)
    if not review or not values:
        return []
    flags: list[str] = []
    required_fields = {
        str(item or "").strip().lower()
        for item in review.get("required_context_fields", [])
        if str(item or "").strip()
    }
    decision_counts = review.get("decision_counts") if isinstance(review.get("decision_counts"), dict) else {}
    review_text = source_text or excerpt or ""
    needs_basis = {"timeframe", "unit_basis", "condition"}.intersection(required_fields)
    if needs_basis and value_requires_context_basis(values) and not has_timeframe_context(review_text, values):
        flags.append("feature_llm_timeframe_or_basis_review")
    if "cohort" in required_fields and FEATURE_CARD_SPECIALIST_COHORT_RE.search(review_text):
        flags.append("feature_llm_scope_or_cohort_review")
    if (
        FEATURE_CARD_REFERENCE_HEAVY_RE.search(review_text)
        and str(review.get("alignment_status") or "").strip() in {"mixed", "weak", "cannot_tell"}
    ):
        flags.append("feature_llm_reference_context_review")
    wrong_or_noise = int(decision_counts.get("wrong_entitlement_or_noise") or 0)
    promote = int(decision_counts.get("promote_candidate") or 0)
    if wrong_or_noise > promote and str(review.get("alignment_status") or "").strip() in {"mixed", "weak", "cannot_tell"}:
        local_positive = bool(FEATURE_CARD_LOCAL_ENTITLEMENT_RE.search(review_text))
        local_noise = bool(FEATURE_CARD_REFERENCE_HEAVY_RE.search(review_text) or FEATURE_CARD_SPECIALIST_COHORT_RE.search(review_text))
        if local_noise or not local_positive:
            flags.append("feature_llm_definition_noise_gate")
    return sorted(set(flags))


def review_status_for_candidate(
    state: str,
    values: list[dict[str, str]],
    blockers: list[str],
    process_rule_flags: list[str],
) -> str:
    if state == "clause_found_value_extracted" and FEATURE_CARD_LLM_REVIEW_FLAGS.intersection(process_rule_flags):
        return "needs_feature_card_llm_review"
    return review_status_for_state(state, values, blockers)


def interpretation_status_for_state(state: str, values: list[dict[str, str]], blockers: list[str]) -> str:
    if values:
        return "candidate_features_found"
    if state == "clause_found_value_missing":
        return "feature_review_required"
    if state == "adjacent_or_blocked_clause_found" and blockers:
        return "feature_review_required"
    return "source_container_only"


def process_rule_flags_for_candidate(
    *,
    spec: LocatorSpec,
    state: str,
    values: list[dict[str, str]],
    blockers: list[str],
    page_role: str,
    source_text: str,
    excerpt: str,
) -> list[str]:
    flags: list[str] = []
    if page_role == "table_of_contents" or "table_of_contents" in blockers:
        flags.append("routing_only_table_of_contents")
    if page_role == "approval_decision_front_matter":
        flags.append("front_matter_context_not_clause_source")
    if page_role == "undertaking_source_term":
        flags.append("undertaking_source_term_requires_review")
    if re.search(r"\b(?:NES|National Employment Standards|Fair Work Act|Award|Modern Award|policy|procedure)\b", source_text or excerpt, flags=re.I):
        flags.append("reference_heavy_context")
    if state == "clause_found_value_missing":
        flags.append("quantification_or_amount_not_stated_review")
    if state == "adjacent_or_blocked_clause_found":
        flags.append("scope_boundary_review")
    if values:
        flags.append("feature_value_extracted")
    flags.extend(feature_card_llm_context_flags(
        spec,
        values=values,
        source_text=source_text,
        excerpt=excerpt,
    ))
    return sorted(set(flags))


def stable_id(prefix: str, parts: list[str]) -> str:
    return f"{prefix}-" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def text_hash(text: str) -> str:
    return hashlib.sha256(compact_text(text).encode("utf-8")).hexdigest()


NUMBER_WORDS = {
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "10": "ten",
    "11": "eleven",
    "12": "twelve",
    "13": "thirteen",
    "14": "fourteen",
    "15": "fifteen",
    "16": "sixteen",
    "17": "seventeen",
    "18": "eighteen",
    "19": "nineteen",
    "20": "twenty",
    "38": "thirty eight",
}


def evidence_span_for_value(value: dict[str, str], excerpt: str, match: re.Match[str]) -> dict[str, Any]:
    raw_value = str(value.get("value") or "")
    unit = str(value.get("unit") or "")
    alternatives = [re.escape(raw_value)]
    if raw_value in NUMBER_WORDS:
        alternatives.append(re.escape(NUMBER_WORDS[raw_value]))
    unit_heads = [head for head in ["day", "week", "hour", "month"] if head in unit.lower()]
    if raw_value and unit_heads:
        pattern = rf"\b(?:{'|'.join(alternatives)})\s+(?:{'|'.join(unit_heads)})s?\b"
        span_match = re.search(pattern, excerpt, flags=re.I)
        if span_match:
            start = max(0, span_match.start() - 160)
            end = min(len(excerpt), span_match.end() + 260)
            return {
                "evidence_span_start": start,
                "evidence_span_end": end,
                "evidence_span_text": compact_text(excerpt[start:end]),
                "evidence_span_text_hash": text_hash(excerpt[start:end]),
                "span_basis": "normalised_value_window",
            }
    if raw_value and raw_value not in {"available", "unquantified", "unlimited"}:
        span_match = re.search(rf"\b(?:{'|'.join(alternatives)})\b", excerpt, flags=re.I)
        if span_match:
            start = max(0, span_match.start() - 160)
            end = min(len(excerpt), span_match.end() + 260)
            return {
                "evidence_span_start": start,
                "evidence_span_end": end,
                "evidence_span_text": compact_text(excerpt[start:end]),
                "evidence_span_text_hash": text_hash(excerpt[start:end]),
                "span_basis": "normalised_value_window",
            }
    alias_text = compact_text(match.group(0))
    alias_match = re.search(re.escape(alias_text), excerpt, flags=re.I) if alias_text else None
    alias_start = alias_match.start() if alias_match else 0
    alias_end = alias_match.end() if alias_match else min(len(excerpt), len(alias_text))
    fallback_start = max(0, alias_start - 160)
    fallback_end = min(len(excerpt), alias_end + 260)
    return {
        "evidence_span_start": fallback_start,
        "evidence_span_end": fallback_end,
        "evidence_span_text": compact_text(excerpt[fallback_start:fallback_end]) or match.group(0),
        "evidence_span_text_hash": text_hash(compact_text(excerpt[fallback_start:fallback_end]) or match.group(0)),
        "span_basis": "locator_alias_window",
    }


def value_label(value: dict[str, str]) -> str:
    value_text = compact_text(value.get("value", ""))
    unit = compact_text(value.get("unit", ""))
    if value_text and unit:
        return f"{value_text} {unit}"
    return value_text or unit or compact_text(value.get("subclass_label", ""))


def classification_boundary_for_spec(spec: LocatorSpec) -> dict[str, Any]:
    boundary = spec.profile.get("classification_boundary") if isinstance(spec.profile.get("classification_boundary"), dict) else {}
    return {
        "canonical_definition": (
            boundary.get("canonical_definition")
            or spec.profile.get("definition")
            or f"For standard employees, does the agreement provide {spec.label}?"
        ),
        "included": list(boundary.get("included") or []),
        "excluded": list(boundary.get("excluded") or []),
        "needs_review": list(boundary.get("needs_review") or []),
    }


def compact_rule_items(items: list[Any], *, limit: int = 4) -> list[str]:
    return [compact_text(item)[:220] for item in items if compact_text(item)][:limit]


def feature_answer_builder_status(
    *,
    state: str,
    blockers: list[str],
    process_rule_flags: list[str],
    value: dict[str, str],
) -> str:
    if state != "clause_found_value_extracted":
        return "source_context_required"
    hard_flags = set(process_rule_flags).intersection(FEATURE_CARD_LLM_REVIEW_FLAGS)
    if blockers or hard_flags:
        return "llm_answer_builder_required"
    if str(value.get("value") or "").strip().lower() in {"available", "unquantified"}:
        return "llm_answer_builder_required"
    return "ready_for_deterministic_promotion_gate"


def feature_answer_builder_contract(
    spec: LocatorSpec,
    *,
    feature_id: str,
    clause_id: str,
    council: str,
    agreement_id: str,
    output_contract: dict[str, Any],
    value: dict[str, str],
    span: dict[str, Any],
    state: str,
    blockers: list[str],
    process_rule_flags: list[str],
) -> dict[str, Any]:
    status = feature_answer_builder_status(
        state=state,
        blockers=blockers,
        process_rule_flags=process_rule_flags,
        value=value,
    )
    boundary = classification_boundary_for_spec(spec)
    review = learned_feature_card_review(spec)
    normal_model = compact_text(review.get("normal_value_model")) if isinstance(review, dict) else ""
    initial_blockers = sorted({
        *blockers,
        *[flag for flag in process_rule_flags if flag in FEATURE_CARD_LLM_REVIEW_FLAGS],
    })
    return {
        "schema_version": "wiki.feature_answer_builder_contract.v1",
        "doctrine": (
            "Feature Cards are evidence candidates, not final facts. "
            "Semantic answer-building happens before deterministic governance."
        ),
        "created_with": "feature_card",
        "status": status,
        "semantic_questions": FEATURE_ANSWER_BUILDER_QUESTIONS,
        "required_answer_fields": FEATURE_ANSWER_REQUIRED_FIELDS,
        "candidate_answer": {
            "entitlement_id": spec.entitlement_id,
            "entitlement_label": spec.label,
            "entitlement_definition": boundary["canonical_definition"],
            "council": council,
            "agreement_id": agreement_id,
            "source_clause_id": clause_id,
            "source_feature_id": feature_id,
            "answer_kind": output_contract.get("answer_kind"),
            "quantification_type": output_contract.get("quantification_type"),
            "value_or_presence": value_label(value) or "value not stated",
            "value": value.get("value", ""),
            "unit": value.get("unit", ""),
            "condition": value.get("condition", ""),
            "subclass_id": value.get("subclass_id", ""),
            "subclass_label": value.get("subclass_label", ""),
            "evidence_span_text_hash": span.get("evidence_span_text_hash"),
        },
        "definition_context": {
            "canonical_definition": boundary["canonical_definition"],
            "included": compact_rule_items(boundary["included"]),
            "excluded": compact_rule_items(boundary["excluded"]),
            "needs_review": compact_rule_items(boundary["needs_review"]),
        },
        "normal_value_model": normal_model,
        "initial_blockers": initial_blockers,
        "repair_policy": {
            "blocked_is_work_queue": True,
            "repair_before_review": True,
            "deterministic_promotion_after_semantic_answer": True,
        },
        "deterministic_gate_policy": {
            "feature_card_is_not_final_answer": True,
            "allowed_after": "structured_answer_candidate",
            "required": [
                "source-backed answer",
                "entitlement definition aligned",
                "value meaning classified",
                "cohort, timeframe, condition, and paid status resolved where applicable",
                "normal value or comparator plausibility checked",
                "unresolved blockers absent",
            ],
        },
    }


def feature_cards_for_values(
    spec: LocatorSpec,
    *,
    clause_id: str,
    council: str,
    agreement_id: str,
    page_number: int,
    source: dict[str, Any],
    excerpt: str,
    match: re.Match[str],
    values: list[dict[str, str]],
    state: str,
    blockers: list[str],
    source_container_type: str,
    process_rule_flags: list[str],
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    output_contract = exemplar_output_contract(spec.entitlement_id)
    for index, value in enumerate(values):
        span = evidence_span_for_value(value, excerpt, match)
        feature_id = stable_id("feature", [
            clause_id,
            spec.entitlement_id,
            str(index),
            str(value.get("subclass_id") or ""),
            str(value.get("value") or ""),
            str(value.get("unit") or ""),
        ])
        review_status = review_status_for_candidate(state, [value], blockers, process_rule_flags)
        answer_builder = feature_answer_builder_contract(
            spec,
            feature_id=feature_id,
            clause_id=clause_id,
            council=council,
            agreement_id=agreement_id,
            output_contract=output_contract,
            value=value,
            span=span,
            state=state,
            blockers=blockers,
            process_rule_flags=process_rule_flags,
        )
        cards.append({
            "feature_id": feature_id,
            "clause_id": clause_id,
            "agreement_id": agreement_id,
            "council_id": council,
            "source_file_id": agreement_id,
            "source_file": f"cache/{agreement_id}/pages.json",
            "source_file_hash": "not_available_in_locator_cache",
            "parser_used": PARSER_USED,
            "parser_version": PARSER_VERSION,
            "page_number_physical": page_number,
            "page_number_marked_if_available": source.get("page"),
            "block_id": stable_id("block", [agreement_id, str(page_number), str(match.start() // 160)]),
            "page_ref": source,
            "source_container_type": source_container_type,
            "process_rule_flags": process_rule_flags,
            "measure_id": spec.entitlement_id,
            "benefit_label": spec.label,
            "answer_kind": output_contract["answer_kind"],
            "quantification_type": output_contract["quantification_type"],
            "supportable_output_requires": output_contract["supportable_output_requires"],
            "subclass_id": value.get("subclass_id", ""),
            "subclass_label": value.get("subclass_label", ""),
            "value": value.get("value", ""),
            "unit": value.get("unit", ""),
            "condition": value.get("condition", ""),
            "benchmark_value": value.get("benchmark_value", "false"),
            "normalised_value": value,
            "evidence_span_start": span["evidence_span_start"],
            "evidence_span_end": span["evidence_span_end"],
            "evidence_span_text": span["evidence_span_text"],
            "evidence_span_text_hash": span["evidence_span_text_hash"],
            "span_basis": span["span_basis"],
            "extraction_method": "normalised_value_from_clause_window_v1",
            "answer_builder": answer_builder,
            "answer_builder_status": answer_builder["status"],
            "review_status": review_status,
            "governance_status": "ungoverned_experiment",
        })
    return cards


def reference_relationship(snippet: str, target_kind: str) -> str:
    lower = snippet.lower()
    if "meaning" in lower or "definition" in lower or "defined" in lower:
        return "definition_dependency"
    if "subject to" in lower or "except where" in lower:
        return "conditional_dependency"
    if "additional to" in lower or "in addition to" in lower or target_kind == "external_nes":
        return "statutory_floor_dependency"
    if "calculated" in lower or "accordance with" in lower:
        return "calculation_dependency"
    return "cross_reference"


def reference_links_for_excerpt(clause_id: str, excerpt: str) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    reference_patterns: list[tuple[str, str, re.Pattern[str]]] = [
        ("to_clause", "internal_clause", re.compile(r"\bclauses?\s+(\d+(?:\.\d+)*)\b", flags=re.I)),
        ("to_schedule", "schedule", re.compile(r"\bschedule\s+([A-Z]|\d+(?:\.\d+)*)\b", flags=re.I)),
        ("to_external", "external_nes", re.compile(r"\b(NES|National\s+Employment\s+Standards)\b", flags=re.I)),
        ("to_external", "external_fair_work_act", re.compile(r"\b(FWA|Fair\s+Work\s+Act(?:\s+2009)?)\b", flags=re.I)),
        ("to_external", "external_award", re.compile(r"\b(Award|Modern\s+Award)\b", flags=re.I)),
    ]
    for target_field, target_kind, pattern in reference_patterns:
        for match in pattern.finditer(excerpt):
            target = compact_text(match.group(1))
            start = max(0, match.start() - 140)
            end = min(len(excerpt), match.end() + 180)
            snippet = compact_text(excerpt[start:end])
            key = (target_field, target.lower(), reference_relationship(snippet, target_kind))
            if key in seen:
                continue
            seen.add(key)
            links.append({
                "reference_id": stable_id("ref", [clause_id, target_field, target, snippet[:120]]),
                "from_clause_id": clause_id,
                target_field: target,
                "relationship": reference_relationship(snippet, target_kind),
                "text": snippet,
                "text_hash": text_hash(snippet),
            })
            if len(links) >= 20:
                return links
    return links


def clause_card_for_candidate(
    spec: LocatorSpec,
    *,
    council: str,
    agreement_id: str,
    page_number: int,
    label: str,
    match: re.Match[str],
    excerpt: str,
    heading: str,
    state: str,
    score: int,
    values: list[dict[str, str]],
    blockers: list[str],
    matched_terms: list[str],
    local_text: str,
    page_role: str,
    source_container_type: str,
) -> dict[str, Any]:
    card_parts = [
        agreement_id,
        spec.entitlement_id,
        str(page_number),
        label,
        str(match.start()),
        str(match.end()),
    ]
    clause_id = stable_id("clause", card_parts)
    source = annual.source_ref(
        agreement_id,
        page_number,
        evidence_state=f"locator_experiment_{state}",
        heading=heading,
    )
    process_rule_flags = process_rule_flags_for_candidate(
        spec=spec,
        state=state,
        values=values,
        blockers=blockers,
        page_role=page_role,
        source_text=local_text,
        excerpt=excerpt,
    )
    feature_values = [] if HARD_SOURCE_CONTEXT_BLOCKERS.intersection(blockers) else values
    return {
        "clause_id": clause_id,
        "agreement_id": agreement_id,
        "council_id": council,
        "source_file_id": agreement_id,
        "source_file": f"cache/{agreement_id}/pages.json",
        "source_file_hash": "not_available_in_locator_cache",
        "parser_used": PARSER_USED,
        "parser_version": PARSER_VERSION,
        "page_number_physical": page_number,
        "page_number_marked_if_available": source.get("page"),
        "block_id": stable_id("block", [agreement_id, str(page_number), str(match.start() // 160)]),
        "page_ref": source,
        "clause_number": clause_number_from_heading(heading),
        "heading_path": [heading] if heading else [],
        "source_container_type": source_container_type,
        "process_rule_flags": process_rule_flags,
        "interpretation_status": interpretation_status_for_state(state, values, blockers),
        "raw_clause_text": excerpt,
        "raw_clause_text_hash": text_hash(excerpt),
        "locator_span_start": match.start(),
        "locator_span_end": match.end(),
        "locator_span_text": match.group(0),
        "locator_span_text_hash": text_hash(match.group(0)),
        "source_page_span_start_char": match.start(),
        "source_page_span_end_char": match.end(),
        "matched_span_start": match.start(),
        "matched_span_end": match.end(),
        "matched_span_text": match.group(0),
        "clause_family": spec.entitlement_id,
        "benefit_label": spec.label,
        "benefit_labels": [spec.label],
        "semantic_tags": matched_terms,
        "feature_cards": feature_cards_for_values(
            spec,
            clause_id=clause_id,
            council=council,
            agreement_id=agreement_id,
            page_number=page_number,
            source=source,
            excerpt=excerpt,
            match=match,
            values=feature_values,
            state=state,
            blockers=blockers,
            source_container_type=source_container_type,
            process_rule_flags=process_rule_flags,
        ),
        "reference_links": reference_links_for_excerpt(clause_id, excerpt),
        "normalised_values": values,
        "extraction_method": "alias_window_span_locator_v1",
        "confidence": score,
        "review_status": review_status_for_candidate(state, values, blockers, process_rule_flags),
        "governance_status": "ungoverned_experiment",
        "notes": "Generated by the recall-first locator experiment; promote only after source review.",
        "supersedes": [],
        "related_clause_ids": [],
    }


def locator_candidate(
    spec: LocatorSpec,
    *,
    council: str,
    agreement_id: str,
    page_number: int,
    label: str,
    match: re.Match[str],
    combined_text: str,
    page_role: str,
    source_container_type: str,
) -> dict[str, Any]:
    excerpt = window_around(combined_text, match.start(), match.end(), before=900, after=9000)
    local_text = window_around(combined_text, match.start(), match.end(), before=450, after=1300)
    values = values_for_spec(spec, council, excerpt)
    candidate_labels = [label]
    context_labels = context_hits(spec, excerpt)
    positive_labels = positive_hits(spec, excerpt)
    blockers = local_blockers(spec, excerpt, local_text, values, page_role=page_role)
    terms = {*candidate_labels, *context_labels, *positive_labels}
    if is_weak_generic_candidate(spec, terms, values):
        state = "weak_candidate_clause_found"
    else:
        state = classify_state(
            values=values,
            blockers=blockers,
            candidate_labels=candidate_labels,
            context_labels=context_labels,
            positive_labels=positive_labels,
        )
    score = candidate_score(state, values, blockers, positive_labels, context_labels)
    heading = heading_for_spec(spec, excerpt)
    matched_terms = sorted({*candidate_labels, *context_labels, *positive_labels})
    return {
        "state": state,
        "page": page_number,
        "page_label": f"p.{page_number}",
        "heading": heading,
        "matched_terms": matched_terms,
        "blocker_signals": blockers,
        "score": score,
        "normalised_values": values,
        "value_signals": standard.quantum_signals(values),
        "excerpt": excerpt,
        "source_ref": annual.source_ref(
            agreement_id,
            page_number,
            evidence_state=f"locator_experiment_{state}",
            heading=heading,
        ),
        "clause_card": clause_card_for_candidate(
            spec,
            council=council,
            agreement_id=agreement_id,
            page_number=page_number,
            label=label,
            match=match,
            excerpt=excerpt,
            heading=heading,
            state=state,
            score=score,
            values=values,
            blockers=blockers,
            matched_terms=matched_terms,
            local_text=local_text,
            page_role=page_role,
            source_container_type=source_container_type,
        ),
    }


def candidate_preview(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": candidate.get("state"),
        "page": candidate.get("page"),
        "page_label": candidate.get("page_label"),
        "heading": candidate.get("heading"),
        "matched_terms": candidate.get("matched_terms") if isinstance(candidate.get("matched_terms"), list) else [],
        "blocker_signals": candidate.get("blocker_signals") if isinstance(candidate.get("blocker_signals"), list) else [],
        "score": candidate.get("score"),
        "normalised_values": candidate.get("normalised_values") if isinstance(candidate.get("normalised_values"), list) else [],
        "value_signals": candidate.get("value_signals") if isinstance(candidate.get("value_signals"), list) else [],
        "excerpt": compact_text(candidate.get("excerpt"))[:1800],
        "source_ref": candidate.get("source_ref") if isinstance(candidate.get("source_ref"), dict) else {},
    }


def locate_in_agreement(spec: LocatorSpec, council: str, agreement_id: str) -> dict[str, Any]:
    pages = cached_pages(agreement_id)
    candidates: list[dict[str, Any]] = []
    seen_windows: set[tuple[int, str, int]] = set()
    lookahead_pages = int(spec.profile.get("lookahead_pages") or 1)
    patterns = discovery_patterns(spec)
    contents_indicators = contents_indicators_for_spec(spec, pages)

    for page_index, page_text in enumerate(pages):
        if not page_text:
            continue
        page_number = page_index + 1
        page_role = cached_page_role(agreement_id, page_number, page_text)
        source_container_type = cached_page_container_type(agreement_id, page_number, page_text)
        combined_text = page_window(pages, page_index, lookahead_pages)
        for start, label, match in labelled_matches(patterns, page_text):
            window_key = (page_number, label, start // 160)
            if window_key in seen_windows:
                continue
            seen_windows.add(window_key)
            candidates.append(locator_candidate(
                spec,
                council=council,
                agreement_id=agreement_id,
                page_number=page_number,
                label=label,
                match=match,
                combined_text=combined_text,
                page_role=page_role,
                source_container_type=source_container_type,
            ))

    candidates = sorted(candidates, key=lambda item: (item["score"], item["state"] == "clause_found_value_extracted"), reverse=True)
    best = candidates[0] if candidates else None
    values = standard.dedupe_values([
        value
        for candidate in candidates
        if candidate["state"] == "clause_found_value_extracted"
        for value in candidate["normalised_values"]
    ])
    clause_found = any(candidate["state"] in CLAUSE_FOUND_STATES for candidate in candidates)
    value_extracted = bool(values)
    if value_extracted:
        row_state = "clause_found_value_extracted"
    elif clause_found:
        row_state = "clause_found_value_missing"
    elif candidates:
        row_state = "adjacent_or_blocked_clause_found"
    else:
        row_state = "no_candidate_clause_found"
    clause_cards = [
        candidate["clause_card"]
        for candidate in candidates[:8]
        if "clause_card" in candidate
    ]
    feature_cards = [
        feature
        for card in clause_cards
        for feature in card.get("feature_cards", [])
    ]
    reference_links = [
        link
        for card in clause_cards
        for link in card.get("reference_links", [])
    ]
    return {
        "council": council,
        "agreement_id": agreement_id,
        "agreement_name": annual.agreement_name(agreement_id),
        "page_count": len(pages),
        "state": row_state,
        "clause_found": clause_found,
        "value_extracted": value_extracted,
        "candidate_count": len(candidates),
        "contents_indicator_count": len(contents_indicators),
        "contents_indicators": contents_indicators,
        "locator_confidence": best["score"] if best else 0,
        "best_candidate": candidate_preview(best) if best else None,
        "normalised_values": values,
        "value_signals": standard.quantum_signals(values),
        "clause_cards": clause_cards,
        "feature_cards": feature_cards,
        "reference_links": reference_links,
        "candidate_pages": [candidate_preview(candidate) for candidate in candidates[:8]],
    }


def rows_for_spec(spec: LocatorSpec, agreements: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        locate_in_agreement(spec, row["council"], row["agreement_id"])
        for row in agreements
    ]


def summary_for_locator_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    state_counts: dict[str, int] = {}
    for row in rows:
        state_counts[row["state"]] = state_counts.get(row["state"], 0) + 1
    total = len(rows)
    clause_found = sum(1 for row in rows if row["clause_found"])
    value_extracted = sum(1 for row in rows if row["value_extracted"])
    return {
        "councils": total,
        "locator_clause_found": clause_found,
        "locator_value_extracted": value_extracted,
        "locator_clause_found_percent": round((clause_found / total) * 100, 1) if total else 0.0,
        "locator_value_extracted_percent": round((value_extracted / total) * 100, 1) if total else 0.0,
        "candidate_pages_found": sum(int(row["candidate_count"]) for row in rows),
        "contents_indicators_found": sum(int(row["contents_indicator_count"]) for row in rows),
        "rows_with_contents_indicators": sum(1 for row in rows if row["contents_indicator_count"]),
        "state_counts": dict(sorted(state_counts.items())),
    }


def metric_calibration(
    baseline_summary: dict[str, Any],
    target_summary: dict[str, Any],
    *,
    metric: str,
    metric_label: str,
) -> dict[str, Any]:
    calibration = calibrate_binary_metric_groups(
        baseline_summary,
        {"scale_group": target_summary},
        metric=metric,
        metric_label=metric_label,
    )
    return {
        "baseline": calibration["baseline"],
        "score": calibration["groups"]["scale_group"],
        "confidence_definition": calibration["confidence_definition"],
    }


def pattern_labels(patterns: Any) -> list[str]:
    labels: list[str] = []
    for item in patterns or []:
        if isinstance(item, (list, tuple)) and item:
            labels.append(str(item[0]))
    return sorted({label for label in labels if label})


def serialisable_rule_contract(spec: LocatorSpec) -> dict[str, Any]:
    profile = spec.profile
    boundary = profile.get("classification_boundary") if isinstance(profile.get("classification_boundary"), dict) else {}
    learned_loop_rules = profile.get("learned_loop_rules") if isinstance(profile.get("learned_loop_rules"), dict) else {}
    output_contract = exemplar_output_contract(spec.entitlement_id)
    rule_origin = profile.get("rule_origin")
    if not rule_origin:
        rule_origin = "authored_profile" if boundary else "generic_taxonomy_fallback"
    definition = boundary.get("canonical_definition") or profile.get("definition") or ""
    included = list(boundary.get("included") or [])
    excluded = list(boundary.get("excluded") or [])
    needs_review = list(boundary.get("needs_review") or [])
    if not included:
        included = [
            f"Source-backed clauses that create, extend, quantify, or materially condition {spec.label} for standard employees.",
            "Clauses with enough local context to identify value, unit, condition, and employee scope.",
        ]
    if not excluded:
        excluded = [
            "Table of contents, headings, definitions, or incidental mentions without an operative entitlement.",
            "Specialist cohort-only provisions unless the entitlement definition intentionally includes that cohort.",
            "Cross-references to NES, Award, Act, policy, or another clause where the agreement does not add a local entitlement.",
            "Administrative process text that does not change entitlement access, value, condition, or scope.",
        ]
    if not needs_review:
        needs_review = [
            "Clauses that mention the entitlement but do not state whether it is paid, unpaid, additional, or merely existing-leave access.",
            "Discretionary or approval-dependent provisions where no normalised value is stated.",
            "Values that are unusual compared with other councils in the feature set.",
            "Clauses where reference edges may change the meaning of value, unit, condition, or scope.",
        ]
    accepted_subclasses = [
        {
            "subclass_id": item.get("subclass_id", ""),
            "label": item.get("label", ""),
            "relationship": item.get("relationship", ""),
        }
        for item in profile.get("accepted_subclasses", [])
        if isinstance(item, dict)
    ]
    return {
        "entitlement_id": spec.entitlement_id,
        "label": spec.label,
        "rule_origin": rule_origin,
        "definition": definition,
        "taxonomy_path": profile.get("taxonomy_path", []),
        "scope": profile.get("scope") or "standard_employees",
        "classification_boundary": {
            "canonical_definition": definition,
            "included": included,
            "excluded": excluded,
            "needs_review": needs_review,
        },
        "accepted_subclasses": accepted_subclasses,
        "locator_signals": {
            "candidate_labels": pattern_labels(profile.get("candidate_patterns")),
            "positive_labels": pattern_labels(profile.get("positive_patterns")),
            "context_labels": pattern_labels(profile.get("context_patterns")),
        },
        "learned_loop_rules": {
            "learning_source": learned_loop_rules.get("learning_source"),
            "loop_status": learned_loop_rules.get("loop_status"),
            "promotion_gate": learned_loop_rules.get("promotion_gate"),
            "expected_answer_shape": learned_loop_rules.get("expected_answer_shape") if isinstance(learned_loop_rules.get("expected_answer_shape"), dict) else {},
            "value_rules": learned_loop_rules.get("value_rules") if isinstance(learned_loop_rules.get("value_rules"), list) else [],
            "validation_queue": learned_loop_rules.get("validation_queue") if isinstance(learned_loop_rules.get("validation_queue"), list) else [],
            "next_loop_steps": learned_loop_rules.get("next_loop_steps") if isinstance(learned_loop_rules.get("next_loop_steps"), list) else [],
            "research_findings": learned_loop_rules.get("research_findings") if isinstance(learned_loop_rules.get("research_findings"), dict) else {},
            "feature_card_llm_review": learned_loop_rules.get("feature_card_llm_review") if isinstance(learned_loop_rules.get("feature_card_llm_review"), dict) else {},
        },
        "output_contract": output_contract,
        "ai_improvement_questions": [
            "What is this entitlement really asking us to identify?",
            "Does this clause fit the inclusion boundary or trigger an exclusion?",
            "What value, unit, condition, and employee scope would be normal for this entitlement?",
            "Do other councils with feature cards support or contradict this interpretation?",
            "What source PDF context, external reference, or statutory floor needs checking?",
            "What definition, inclusion, exclusion, alias, or value rule should be improved for the next run?",
        ],
    }


def profile_payload(spec: LocatorSpec, target_agreements: list[dict[str, str]]) -> dict[str, Any]:
    baseline_rows = rows_for_spec(spec, annual.BASELINE_COMPARATOR_AGREEMENTS)
    target_rows = rows_for_spec(spec, target_agreements)
    baseline_summary = summary_for_locator_rows(baseline_rows)
    target_summary = summary_for_locator_rows(target_rows)
    return {
        "key": spec.key,
        "entitlement_id": spec.entitlement_id,
        "label": spec.label,
        "rule_contract": serialisable_rule_contract(spec),
        "output_contract": exemplar_output_contract(spec.entitlement_id),
        "baseline_summary": baseline_summary,
        "target_summary": target_summary,
        "metrics": {
            "locator_clause_found": metric_calibration(
                baseline_summary,
                target_summary,
                metric="locator_clause_found",
                metric_label="council rows with a locator-found clause",
            ),
            "locator_value_extracted": metric_calibration(
                baseline_summary,
                target_summary,
                metric="locator_value_extracted",
                metric_label="council rows with extracted values",
            ),
        },
        "target_rows": target_rows,
    }


def target_agreement_pool(scope: str) -> list[dict[str, str]]:
    if scope == "all_cached":
        return governed_active_council_agreements()
    if scope == "gold_exemplar_v2":
        exemplar_councils = {short_council_name(council) for council in exemplar_comparator_councils()}
        return [
            row
            for row in governed_active_council_agreements()
            if row["council"] in exemplar_councils
        ]
    return eligible_latest_cached_agreements()


def profile_payloads(
    target_agreements: list[dict[str, str]],
    *,
    progress: bool = False,
    entitlement_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    specs = [
        spec for spec in LOCATOR_SPECS
        if not entitlement_ids or spec.entitlement_id in entitlement_ids
    ]
    total = len(specs)
    for index, spec in enumerate(specs, start=1):
        started_at = time.perf_counter()
        if progress:
            print(
                json.dumps(
                    {
                        "event": "entitlement_locator_profile_started",
                        "index": index,
                        "total": total,
                        "entitlement_id": spec.entitlement_id,
                        "label": spec.label,
                    }
                ),
                file=sys.stderr,
                flush=True,
            )
        profile = profile_payload(spec, target_agreements)
        profiles.append(profile)
        if progress:
            print(
                json.dumps(
                    {
                        "event": "entitlement_locator_profile_completed",
                        "index": index,
                        "total": total,
                        "entitlement_id": spec.entitlement_id,
                        "seconds": round(time.perf_counter() - started_at, 2),
                        "target_rows": len(profile.get("target_rows") or []),
                    }
                ),
                file=sys.stderr,
                flush=True,
            )
    return profiles


def build_payload(
    batch_size: int | None,
    offset: int,
    generated_at: str,
    *,
    scope: str = "eligible_next",
    progress: bool = False,
    entitlement_ids: set[str] | None = None,
) -> dict[str, Any]:
    eligible = target_agreement_pool(scope)
    effective_batch_size = len(eligible) - offset if batch_size is None else batch_size
    target_agreements = eligible[offset: offset + effective_batch_size]
    artifact_scope = {
        "all_cached": "all-cached",
        "gold_exemplar_v2": "gold-exemplar-v2",
    }.get(scope, "next")
    if entitlement_ids:
        fingerprint = hashlib.sha1("|".join(sorted(entitlement_ids)).encode("utf-8")).hexdigest()[:8]
        artifact_scope = f"{artifact_scope}-filtered-{len(entitlement_ids)}-{fingerprint}"
    return {
        "schema_version": LOCATOR_SCHEMA_VERSION,
        "artifact_id": f"entitlement-locator-experiment-{artifact_scope}-{effective_batch_size}-offset-{offset}",
        "generated_at": generated_at,
        "scope_focus": "standard_employees",
        "run_scope": scope,
        "entitlement_filter": sorted(entitlement_ids) if entitlement_ids else [],
        "experiment": {
            "method_name": "Clause Evidence Graph",
            "purpose": "Parallel recall-first clause locator built from pre-scanned cached agreement page text.",
            "layer_stack": [
                "Agreement PDF/DOCX",
                "Page text and contents indicators",
                "Clause card source containers",
                "Feature cards for atomic benchmarkable facts",
                "Reference links for clause/schedule/NES dependencies",
                "Entitlement engine measurements",
                "Wiki/report/search/comparison views",
            ],
            "entitlement_engine_role": (
                "The entitlement engine sits above the Clause Evidence Graph. It does not own source truth. It queries clause containers, "
                "feature cards, evidence spans, and reference edges, then converts governed feature cards into normalised benchmark measures. "
                "Where governance is absent or incomplete, it emits explicit uncertainty states rather than pretending a benchmark fact exists."
            ),
            "whole_document_clause_carding": (
                "The preferred source-spine strategy is to clause-card the whole agreement at lightweight depth, while creating feature cards "
                "only for specific benchmarkable spans or rules. This supports search, absence review, and cross-reference analysis without "
                "forcing every clause into premature entitlement interpretation."
            ),
            "recommended_augmentation_layers": [
                "parser_adapter_ensemble",
                "evidence_coordinates_and_text_hashes",
                "strict_clause_feature_reference_schemas",
                "structured_output_llm_candidate_extraction",
                "reference_edge_extraction",
                "evaluation_truth_sets_and_regression_harnesses",
                "table_specific_extraction_lane",
                "graph_retrieval_over_clause_evidence_graph",
                "human_in_the_loop_scope_review",
                "read_only_or_proposal_only_agent_tools",
            ],
            "llm_boundary": (
                "LLMs may propose feature cards, semantic tags, and reference-edge labels under strict schemas. "
                "Schema-invalid output is a failed extraction attempt, not data."
            ),
            "doctrine": [
                "The Clause Evidence Graph owns source-backed structure and evidence.",
                "The Entitlement Engine owns benchmark interpretation.",
                "The Reporting Layer owns presentation.",
                "Governance decides what is safe to promote.",
            ],
            "locator_rule": (
                "Scan every page for each entitlement's candidate/context aliases, create local windows around every hit, "
                "classify clause-found separately from value-extracted, record contents-page indicators as non-evidence routing signals, "
                "apply blockers only to a local hit window, emit clause cards as source containers, feature cards as atomic benchmark facts, "
                "and reference links as structured clause/schedule/NES dependencies for review/governance, "
                "and exclude cached approval-decision PDFs that the intake register marks as not agreement text."
            ),
            "states": [
                "clause_found_value_extracted",
                "clause_found_value_missing",
                "adjacent_or_blocked_clause_found",
                "no_candidate_clause_found",
            ],
        },
        "batch_size": effective_batch_size,
        "offset": offset,
        "available_eligible_councils": len(eligible),
        "available_target_councils": len(eligible),
        "target_comparator_set": [
            {
                "council": row["council"],
                "agreement_id": row["agreement_id"],
                "agreement_name": annual.agreement_name(row["agreement_id"]),
                "resolved_from_agreement_id": row.get("resolved_from_agreement_id", row["agreement_id"]),
                "latest_resolution": row.get("latest_resolution", "supplied_agreement_id"),
                "council_key": row.get("council_key"),
                "council_name": row.get("council_name", row.get("council")),
                "cohort": {
                    "all_cached": "all_cached_latest_council_agreements",
                    "gold_exemplar_v2": "entitlements_draft_summary_report_v2_comparator_councils",
                }.get(scope, "locator_experiment_scale_group"),
            }
            for row in target_agreements
        ],
        "profiles": profile_payloads(target_agreements, progress=progress, entitlement_ids=entitlement_ids),
    }


def score_status(score: dict[str, Any]) -> str:
    return "inside_95" if score["inside_95_predictive_interval"] else "outside_95"


def markdown_for_payload(payload: dict[str, Any]) -> str:
    lines = [
        "# Entitlement Locator Experiment",
        "",
        payload["experiment"]["purpose"],
        "",
        payload["experiment"]["locator_rule"],
        "",
        "## Target Councils",
        "",
    ]
    for row in payload["target_comparator_set"]:
        lines.append(f"- {row['council']}: {row['agreement_id'].upper()}")
    lines.extend([
        "",
        "## Locator Scores",
        "",
        "| Entitlement | Metric | A observed | Expected in scale | Scale observed | 80% range | 95% range | Fit confidence | Status |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | ---: | --- |",
    ])
    for profile in payload["profiles"]:
        for metric_payload in profile["metrics"].values():
            baseline = metric_payload["baseline"]
            score = metric_payload["score"]
            interval_80 = score["predictive_intervals"]["80_percent"]["count"]
            interval_95 = score["predictive_intervals"]["95_percent"]["count"]
            lines.append(
                f"| {profile['label']} | {score['metric_label']} | "
                f"{baseline['observed_count']}/{baseline['sample_size']} | "
                f"{score['expected_count']} | "
                f"{score['observed_count']}/{score['sample_size']} | "
                f"{interval_80[0]}-{interval_80[1]} | "
                f"{interval_95[0]}-{interval_95[1]} | "
                f"{score['fit_confidence']} | {score_status(score)} |"
            )
    lines.extend([
        "",
        "## State Counts",
        "",
        "| Entitlement | Clause found | Value extracted | States |",
        "| --- | ---: | ---: | --- |",
    ])
    for profile in payload["profiles"]:
        summary = profile["target_summary"]
        states = ", ".join(f"{key}: {value}" for key, value in summary["state_counts"].items())
        lines.append(
            f"| {profile['label']} | {summary['locator_clause_found']}/{summary['councils']} | "
            f"{summary['locator_value_extracted']}/{summary['councils']} | "
            f"{states}; contents rows: {summary['rows_with_contents_indicators']} |"
        )
    lines.extend([
        "",
        "## Sample Miss/Value-Missing Rows",
        "",
    ])
    for profile in payload["profiles"]:
        lines.append(f"### {profile['label']}")
        interesting = [
            row
            for row in profile["target_rows"]
            if row["state"] in {"clause_found_value_missing", "adjacent_or_blocked_clause_found"}
        ][:8]
        if not interesting:
            lines.append("")
            lines.append("No sample value-missing or blocked rows.")
            lines.append("")
            continue
        lines.append("")
        for row in interesting:
            candidate = row.get("best_candidate") or {}
            page = f" p.{candidate.get('page')}" if candidate.get("page") else ""
            heading = f" - {candidate.get('heading')}" if candidate.get("heading") else ""
            lines.append(f"- {row['council']}: {row['state']} ({row['agreement_id'].upper()}{page}){heading}")
        lines.append("")
    return "\n".join(lines)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the parallel entitlement clause locator experiment.")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--all-eligible", action="store_true")
    parser.add_argument("--all-cached", action="store_true", help="Process the full cached latest-council pool, including comparator councils.")
    parser.add_argument(
        "--gold-exemplar-v2",
        action="store_true",
        help="Process only the ten comparator councils named in entitlements draft summary report version 2.",
    )
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--entitlement-id", action="append", default=[], help="Limit the locator run to one or more entitlement ids.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scope = "gold_exemplar_v2" if args.gold_exemplar_v2 else ("all_cached" if args.all_cached else "eligible_next")
    batch_size = None if args.all_eligible or args.all_cached or args.gold_exemplar_v2 else args.batch_size
    payload = build_payload(
        batch_size,
        args.offset,
        utc_now_iso(),
        scope=scope,
        progress=True,
        entitlement_ids=set(args.entitlement_id) if args.entitlement_id else None,
    )
    artifact_dir = args.output_dir
    write_json(artifact_dir / f"{payload['artifact_id']}.json", payload)
    (artifact_dir / f"{payload['artifact_id']}.md").write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.entitlement_locator_experiment_build.v1",
        "generated_at": payload["generated_at"],
        "artifact_id": payload["artifact_id"],
        "artifact_path": str(artifact_dir / f"{payload['artifact_id']}.json"),
        "target_councils": [row["council"] for row in payload["target_comparator_set"]],
    }, indent=2))


if __name__ == "__main__":
    main()
