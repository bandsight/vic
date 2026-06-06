from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_entitlement_clause_evidence import (
    AGREEMENT_ID_PATTERN,
    BASELINE_COMPARATOR_AGREEMENTS,
    DEFAULT_WIKI_ROOT,
    ROOT,
    agreement_name,
    all_cached_agreements,
    compact_text,
    labelled_patterns,
    read_json,
    source_ref,
    write_json,
)
from scripts.entitlement_statistical_calibration import calibrate_binary_metric_groups


SCHEMA_VERSION = "wiki.entitlement_clause_evidence.v1"
DEFAULT_EXEMPLAR_PATH = (
    DEFAULT_WIKI_ROOT
    / "artifacts"
    / "downstream-analysis-exemplars"
    / "ballarat-entitlement-benchmark-exemplar.json"
)


NUMBER_WORDS = {
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
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
}


@dataclass(frozen=True)
class ProfileCandidate:
    page: int
    source_page: int
    candidate_type: str
    matched_terms: list[str]
    out_of_scope_signals: list[str]
    score: int
    heading: str
    excerpt: str
    clause_text: str
    quantum_signals: list[str]
    normalised_values: list[dict[str, str]]


FAMILY_DOMESTIC_VIOLENCE_PROFILE: dict[str, Any] = {
    "artifact_id": "family-domestic-violence-leave-clause-evidence",
    "entitlement_id": "leave-family-and-domestic-violence-leave",
    "label": "Family and Domestic Violence Leave",
    "definition": "Paid leave to address family and domestic violence impacts.",
    "taxonomy_path": ["Leave", "Family and Domestic Violence Leave"],
    "scope": "standard_band_core",
    "classification_boundary": {
        "canonical_definition": (
            "Employer-funded paid leave or paid support for standard employees experiencing family or domestic "
            "violence, including source-backed support-person leave where the agreement separately quantifies it."
        ),
        "included": [
            "Paid special leave for an employee experiencing family or domestic violence.",
            "Paid support-person leave where the agreement separately states a quantum.",
            "Source clauses that provide paid leave or flexibility for family violence but do not quantify a value.",
        ],
        "excluded": [
            "General parental-leave continuity references to paid family violence leave.",
            "Gender equality reporting references to family violence leave as a workplace practice.",
            "Domestic violence references inside specialist MCH, enhanced home visiting, or at-risk-family allowance clauses.",
            "Support-person access drawn only from existing personal/carer's leave unless separately quantified as FDV support leave.",
        ],
        "needs_review": [
            "Clauses that say paid leave may be considered without a stated value.",
            "Clauses where the reference report includes a support-person value but the source only mentions carer's leave.",
        ],
    },
    "accepted_subclasses": [
        {
            "subclass_id": "leave-family-domestic-violence.employee-paid-leave",
            "label": "Employee FDV Paid Leave",
            "relationship": "accepted_entitlement_subclass",
        },
        {
            "subclass_id": "leave-family-domestic-violence.support-person-paid-leave",
            "label": "Support Person FDV Paid Leave",
            "relationship": "accepted_entitlement_subclass",
        },
    ],
    "adjacent_subclasses": [
        {
            "subclass_id": "leave-family-domestic-violence.support-from-existing-carers-leave",
            "label": "Support From Existing Carer's Leave",
            "relationship": "adjacent_existing_leave_subclass",
        },
        {
            "subclass_id": "leave-family-domestic-violence.unquantified-paid-flexibility",
            "label": "Unquantified Paid Leave Or Flexibility",
            "relationship": "needs_review_source_clause",
        },
    ],
    "search_terms": [
        "family violence",
        "domestic violence",
        "family and domestic violence",
        "family violence leave",
        "domestic / family violence",
        "paid family violence leave",
    ],
    "candidate_patterns": [
        ("family_violence", re.compile(r"\bfamily\s+violence\b", re.I)),
        ("family_domestic_violence", re.compile(r"\bfamily\s+and\s+domestic\s+violence\b", re.I)),
        ("domestic_family_violence", re.compile(r"\bdomestic\s*/\s*family\s+violence\b", re.I)),
        ("domestic_violence", re.compile(r"\bdomestic\s+violence\b", re.I)),
        ("family_violence_leave", re.compile(r"\bfamily\s+violence\s+leave\b", re.I)),
        ("paid_family_violence_leave", re.compile(r"\bpaid\s+family\s+violence\s+leave\b", re.I)),
    ],
    "positive_patterns": [
        ("employee_paid_leave", re.compile(r"\b(?:access\s+to|provid(?:e|ing)|have\s+access\s+to|up\s+to|additional)\b.{0,120}\bpaid\b.{0,80}\bleave\b", re.I)),
        ("family_violence_leave_heading", re.compile(r"\b(?:family|domestic|family\s+and\s+domestic)\s+violence\s+(?:support\s+)?leave\b", re.I)),
        ("support_person_leave", re.compile(r"\bsupports?\s+a\s+person\s+experiencing\s+family\s+violence\b.{0,180}\b(?:paid|special|carer'?s)\s+leave\b", re.I)),
        ("paid_leave_or_flexibility", re.compile(r"\brequest\s+for\s+paid\s+leave\s+or\s+flexibility\b|\bpaid\s+leave\s+or\s+flexibility\b", re.I)),
    ],
    "out_of_scope_patterns": [
        ("table_of_contents", re.compile(r"\.{6,}\s+\d+", re.I)),
        ("parental_leave_continuity_reference", re.compile(r"\bpaid\s+family\s+violence\s+leave\b.{0,260}\bcontinuity\s+of\s+the\s+period\s+of\s+NES\s+unpaid\s+parental\s+leave\b", re.I)),
        ("gender_equality_reporting_reference", re.compile(r"\bgender\s+equality\b.{0,260}\bfamily\s+violence\s+leave\b", re.I)),
        ("at_risk_family_service_context", re.compile(r"\bat\s+risk\s+families\b|\benhanced\s+home\s+visiting\b", re.I)),
    ],
}


NATURAL_DISASTER_PROFILE: dict[str, Any] = {
    "artifact_id": "natural-disaster-or-emergency-leave-clause-evidence",
    "entitlement_id": "leave-natural-disaster-or-emergency-leave",
    "label": "Natural Disaster Or Emergency Leave",
    "definition": "Leave when employees are personally affected by natural disasters such as fire, flood, or evacuation.",
    "taxonomy_path": ["Leave", "Natural Disaster Or Emergency Leave"],
    "scope": "standard_band_core",
    "classification_boundary": {
        "canonical_definition": (
            "Employer-supported leave or paid time off for standard employees who are personally affected by "
            "catastrophic or natural-disaster events such as bushfire, flood, severe storm, road blockage, "
            "or loss of access to their principal residence."
        ),
        "included": [
            "Paid natural disaster leave for employees directly affected by extreme climatic events.",
            "Additional paid time off, discretionary paid leave, or paid ordinary hours for employees affected by catastrophic events.",
            "Use of accrued personal leave where the source specifically links the leave to natural-disaster residence impacts.",
            "Broad pressing-necessity or emergency leave where it supports employees needing time off work for emergencies.",
        ],
        "excluded": [
            "Volunteer emergency services or community services leave for responding to emergencies.",
            "Personal/carer's leave for caring for another person affected by an unexpected emergency.",
            "Clothing, spectacles, or property-damage reimbursement clauses.",
            "Emergency contact or right-to-disconnect operational clauses.",
        ],
        "needs_review": [
            "Broad emergency leave clauses that do not expressly name natural disasters.",
            "Discretionary paid leave clauses that do not state a quantum.",
        ],
    },
    "accepted_subclasses": [
        {
            "subclass_id": "leave-natural-disaster.paid-leave",
            "label": "Natural Disaster Paid Leave",
            "relationship": "accepted_entitlement_subclass",
        },
        {
            "subclass_id": "leave-natural-disaster.paid-time-off-unquantified",
            "label": "Unquantified Natural Disaster Paid Time Off",
            "relationship": "accepted_entitlement_subclass",
        },
        {
            "subclass_id": "leave-natural-disaster.accrued-personal-leave",
            "label": "Natural Disaster From Accrued Personal Leave",
            "relationship": "accepted_entitlement_subclass",
        },
    ],
    "adjacent_subclasses": [
        {
            "subclass_id": "leave-emergency-services-volunteer",
            "label": "Emergency Services Volunteer Leave",
            "relationship": "adjacent_leave_subclass",
        },
        {
            "subclass_id": "leave-carers-unexpected-emergency",
            "label": "Carer's Leave For Unexpected Emergency",
            "relationship": "adjacent_existing_leave_subclass",
        },
    ],
    "search_terms": [
        "natural disaster",
        "natural disaster leave",
        "disaster and emergency leave",
        "catastrophic events",
        "bushfires or floods",
        "flood or storm damage",
        "pressing necessity leave",
        "emergency leave",
        "exceptional circumstances leave",
        "family leave",
    ],
    "candidate_patterns": [
        ("natural_disaster_leave", re.compile(r"\bnatural\s+disaster\s+leave\b", re.I)),
        ("disaster_emergency_leave", re.compile(r"\bdisaster\s+and\s+emergency\s+leave\b", re.I)),
        ("catastrophic_events", re.compile(r"\bcatastrophic\s+events?\b", re.I)),
        ("bushfire_flood_event", re.compile(r"\bbushfires?\b.{0,80}\bfloods?\b|\bfloods?\b.{0,80}\bbushfires?\b", re.I)),
        ("flood_storm_damage", re.compile(r"\bflood\s*/\s*storm\s+damage\b", re.I)),
        ("residence_uninhabitable_disaster", re.compile(r"\bprincipal\s+place\s+of\s+residence\b[\s\S]{0,120}\buninhabitable\b[\s\S]{0,120}\bnatural\s+disaster\b", re.I)),
        ("pressing_necessity_leave", re.compile(r"\bpressing\s+necessity\s+leave\b", re.I)),
        ("natural_disasters_affected_areas", re.compile(r"\bnatural\s+disasters?\b.{0,120}\bstaff\s+live\s+in\s+affected\s+areas\b", re.I)),
        ("emergency_leave_natural_disaster", re.compile(r"\bemergency\s+leave\b[\s\S]{0,420}\bnatural\s+disaster|\bnatural\s+disaster\b[\s\S]{0,420}\bemergency\s+leave\b", re.I)),
        ("exceptional_circumstances_leave", re.compile(r"\bexceptional\s+circumstances\s+leave\b", re.I)),
        ("family_leave_disaster", re.compile(r"\bfamily\s+leave\b[\s\S]{0,700}\b(?:fire|floods?|severe\s+storms?|natural\s+disasters?)\b", re.I)),
    ],
    "context_patterns": [
        ("natural_disaster_context", re.compile(r"\bnatural\s+disaster|catastrophic\s+events?|bushfires?|floods?|severe\s+storms?|road\s+blockages?|pressing\s+necessity\s+leave\b|\bemergency\s+leave\b", re.I)),
        ("emergency_leave_support_context", re.compile(r"\btake\s+time\s+off\s+work\s+for\s+emergencies\b", re.I)),
    ],
    "positive_patterns": [
        ("paid_leave", re.compile(r"\bpaid\s+(?:leave|time\s+off|ordinary\s+hours)\b|\bnormal\s+day'?s\s+wage\b|\bfull\s+pay\b|\bdays?\s+pay\b", re.I)),
        ("no_leave_balance_deduction", re.compile(r"\bwithout\s+deduction\s+from\s+any\s+leave\s+balances\b", re.I)),
        ("accrued_personal_leave", re.compile(r"\baccrued\s+personal\s+leave\b|\bpersonal\s+leave\s+\(sick\s+leave\)\b", re.I)),
        ("flexible_leave_support", re.compile(r"\bsupporting\s+staff\s+through\s+a\s+flexible\s+approach\s+to\s+leave\b", re.I)),
        ("director_or_ceo_discretion", re.compile(r"\b(?:director|manager|CEO)\b.{0,160}\b(?:endorse|consider|grant|approve)\b", re.I)),
    ],
    "out_of_scope_patterns": [
        ("table_of_contents", re.compile(r"\.{6,}\s+\d+", re.I)),
        ("emergency_services_volunteer", re.compile(r"\bemergency\s+services?\s+leave\b|\bvoluntary\s+emergency\s+(?:services?\s+)?management\b|\brecognised\s+emergency\s+service\s+organisation\b", re.I)),
        ("clothing_or_spectacles_damage", re.compile(r"\bclothing\b.{0,160}\b(?:fire|disaster)\b|\bspectacles\b.{0,160}\b(?:fire|molten|corrosive)\b", re.I)),
        ("carers_unexpected_emergency", re.compile(r"\bcarer'?s\s+leave\b.{0,220}\bunexpected\s+emergency\b|\bimmediate\s+family\b.{0,220}\bunexpected\s+emergency\b", re.I)),
        ("right_to_disconnect_or_contact", re.compile(r"\bright\s+to\s+disconnect\b|\bcontact\s+employees\s+outside\b", re.I)),
        ("mch_or_client_safety", re.compile(r"\bmaternal\s*&?\s*child\s+health\b|\bclient\b.{0,120}\bemergency\s+contact\b", re.I)),
    ],
    "hit_discovery_pipeline": [
        "Resolve each comparator council to its latest known canonical agreement, then load cached page text for that agreement.",
        "Find natural-disaster, catastrophic-event, disaster/emergency, and pressing-necessity candidate pages.",
        "Reject table-of-contents, volunteer emergency-services, carer's unexpected-emergency, property-damage, and operational-contact noise.",
        "Accept source clauses that provide paid natural-disaster leave, paid time off, accrued personal leave specifically for disaster residence impacts, or broad emergency leave support.",
        "Extract benchmark values only when the source states a paid natural-disaster quantum or a linked personal-leave quantum.",
        "Compare extracted source values with the reference exemplar values and preserve source/reference differences for review.",
    ],
    "acceptance_rule": "natural-disaster/emergency-impact clause + paid leave/time-off/support value or unquantified leave support + no blocker",
}


COMPASSIONATE_PROFILE: dict[str, Any] = {
    "artifact_id": "compassionate-leave-clause-evidence",
    "entitlement_id": "leave-compassionate-leave",
    "label": "Compassionate Leave",
    "definition": "Paid leave for bereavement, compassionate circumstances, or serious illness/injury of an immediate family or household member.",
    "taxonomy_path": ["Leave", "Compassionate Leave"],
    "scope": "standard_band_core",
    "lookahead_pages": 2,
    "merge_source_candidates": True,
    "classification_boundary": {
        "canonical_definition": (
            "Employer-paid compassionate or bereavement leave for ordinary employees when an immediate family "
            "or household member dies, is seriously ill or injured, or where the source expressly includes "
            "stillbirth, neonatal death, or miscarriage in the compassionate/bereavement entitlement."
        ),
        "included": [
            "Paid compassionate leave per occasion.",
            "Paid bereavement leave per occasion where the clause is paired with compassionate leave.",
            "Named child care, nurse, or similar cohort values where the reference benchmark reports them.",
            "Special paid bereavement leave for stillbirth or neonatal death where the reference benchmark reports the value.",
        ],
        "excluded": [
            "Table-of-contents references.",
            "General personal/carer's leave accrual tables unless they state a compassionate/bereavement quantum.",
            "Family violence special compassionate leave that belongs to the FDV entitlement.",
            "Unpaid-only compassionate or bereavement leave where a paid value is not stated.",
        ],
        "needs_review": [
            "Clauses where compassionate leave is provided only by NES cross-reference without an additional value.",
            "Clauses where a special bereavement clause may belong to a neonatal-loss entitlement rather than ordinary compassionate leave.",
        ],
    },
    "accepted_subclasses": [
        {
            "subclass_id": "leave-compassionate.paid-compassionate-leave",
            "label": "Paid Compassionate Leave",
            "relationship": "accepted_entitlement_subclass",
        },
        {
            "subclass_id": "leave-compassionate.paid-bereavement-leave",
            "label": "Paid Bereavement Leave",
            "relationship": "accepted_entitlement_subclass",
        },
        {
            "subclass_id": "leave-compassionate.special-neonatal-bereavement",
            "label": "Special Stillbirth Or Neonatal Bereavement Leave",
            "relationship": "accepted_entitlement_subclass",
        },
    ],
    "adjacent_subclasses": [
        {
            "subclass_id": "leave-family-domestic-violence.employee-paid-leave",
            "label": "Family Violence Special Leave",
            "relationship": "adjacent_leave_subclass",
        },
        {
            "subclass_id": "leave-personal-carers.accrual",
            "label": "Personal/Carer's Leave Accrual",
            "relationship": "adjacent_existing_leave_subclass",
        },
    ],
    "search_terms": [
        "compassionate leave",
        "bereavement leave",
        "bereavement/compassionate leave",
        "compassionate / bereavement leave",
        "special bereavement leave",
    ],
    "candidate_patterns": [
        ("compassionate_leave", re.compile(r"\bcompassionate\s+leave\b", re.I)),
        ("bereavement_compassionate_leave", re.compile(r"\bbereavement\s*/\s*compassionate\s+leave\b", re.I)),
        ("compassionate_bereavement_leave", re.compile(r"\bcompassionate\s*/\s*bereavement\s+leave\b", re.I)),
        ("bereavement_leave", re.compile(r"\bbereavement\s+leave\b", re.I)),
        ("special_bereavement_leave", re.compile(r"\bspecial\s+bereavement\s+leave\b", re.I)),
    ],
    "context_patterns": [
        ("compassionate_context", re.compile(r"\bcompassionate\s+leave\b|\bbereavement\s*/\s*compassionate\s+leave\b|\bcompassionate\s*/\s*bereavement\s+leave\b|\bbereavement\s+leave\b", re.I)),
        ("family_or_household_context", re.compile(r"\bimmediate\s+family\b|\bhousehold\b|\bseriously\s+ill\b|\bserious\s+illness\b|\bdies?\b|\bdeath\b", re.I)),
    ],
    "positive_patterns": [
        ("paid_leave", re.compile(r"\bpaid\b.{0,120}\b(?:compassionate|bereavement)\s+leave\b|\b(?:compassionate|bereavement)\s+leave\b.{0,120}\bpaid\b", re.I)),
        ("per_occasion", re.compile(r"\bper\s+occasion\b|\beach\s+occasion\b|\bpermissible\s+occasion\b", re.I)),
        ("family_or_household", re.compile(r"\bimmediate\s+family\b|\bhousehold\b", re.I)),
        ("stillbirth_neonatal", re.compile(r"\bstill[-\s]*born\b|\bneo[-\s]*natal\b|\bstillbirth\b", re.I)),
    ],
    "out_of_scope_patterns": [
        ("table_of_contents", re.compile(r"\.{6,}\s+\d+", re.I)),
        ("family_violence_context", re.compile(r"\bfamily\s+violence\b.{0,180}\bspecial\s+compassionate\s+leave\b|\bspecial\s+compassionate\s+leave\b.{0,180}\bfamily\s+violence\b", re.I)),
        ("unpaid_only", re.compile(r"\bunpaid\s+compassionate\s+leave\b|\bunpaid\s+bereavement\s+leave\b", re.I)),
        ("annual_or_long_service_recredit", re.compile(r"\bannual\s+leave\b.{0,160}\bcompassionate\s+leave\b|\blong\s+service\s+leave\b.{0,160}\bcompassionate\s+leave\b", re.I)),
        ("legacy_award_appendix", re.compile(r"\bpart\s+[bc]\b.{0,120}\b(?:victorian\s+local\s+authorities\s+award|anf\s+[\S\s]{0,40}victorian\s+local\s+government\s+award)\b", re.I)),
    ],
    "hit_discovery_pipeline": [
        "Resolve each comparator council to its latest known canonical agreement, then load cached page text for that agreement.",
        "Find compassionate, bereavement/compassionate, compassionate/bereavement, bereavement, and special-bereavement candidate pages.",
        "Reject table-of-contents, FDV special compassionate, unpaid-only, and leave-recredit administrative noise.",
        "Accept source clauses that state paid compassionate or bereavement leave values for immediate family or household circumstances.",
        "Extract ordinary day values, named cohort values, and reference-reported stillbirth/neonatal special bereavement week values.",
        "Compare extracted source values with the reference exemplar values and preserve source/reference differences for review.",
    ],
    "acceptance_rule": "paid compassionate/bereavement leave clause + benchmark value + no blocker",
}


CULTURAL_CEREMONIAL_PROFILE: dict[str, Any] = {
    "artifact_id": "cultural-or-ceremonial-leave-clause-evidence",
    "entitlement_id": "leave-cultural-or-ceremonial-leave",
    "label": "Cultural Or Ceremonial Leave",
    "definition": "Leave for cultural, ceremonial, religious, Sorry Business, Aboriginal or Torres Strait Islander obligations.",
    "taxonomy_path": ["Leave", "Cultural Or Ceremonial Leave"],
    "scope": "standard_band_core",
    "lookahead_pages": 2,
    "classification_boundary": {
        "canonical_definition": (
            "Paid cultural, ceremonial, or Sorry Business leave for ordinary employees, including Aboriginal "
            "and Torres Strait Islander ceremonial obligations where the source states a paid value."
        ),
        "included": [
            "Paid cultural and ceremonial leave per calendar/employment year.",
            "Paid Aboriginal or Torres Strait Islander ceremonial leave.",
            "Paid Sorry Business leave.",
            "Unpaid or existing-leave cultural support clauses retained as source-observed non-benchmark support.",
        ],
        "excluded": [
            "Table-of-contents references.",
            "General annual leave, RDO, TOIL, or leave-without-pay access where no cultural/ceremonial clause is present.",
            "NAIDOC-only references unless the source is part of a broader paid cultural/ceremonial leave clause.",
        ],
        "needs_review": [
            "Clauses where the source provides cultural support but the reference benchmark has no numeric signal.",
            "Clauses with both ordinary cultural leave and additional Aboriginal/Torres Strait Islander leave not separately benchmarked.",
        ],
    },
    "accepted_subclasses": [
        {
            "subclass_id": "leave-cultural-ceremonial.paid-cultural-leave",
            "label": "Paid Cultural/Ceremonial Leave",
            "relationship": "accepted_entitlement_subclass",
        },
        {
            "subclass_id": "leave-cultural-ceremonial.paid-sorry-business",
            "label": "Paid Sorry Business Leave",
            "relationship": "accepted_entitlement_subclass",
        },
    ],
    "adjacent_subclasses": [
        {
            "subclass_id": "leave-cultural-ceremonial.existing-or-unpaid-leave",
            "label": "Existing Or Unpaid Cultural/Ceremonial Leave Support",
            "relationship": "needs_review_source_clause",
        },
    ],
    "search_terms": [
        "cultural and ceremonial leave",
        "cultural or ceremonial leave",
        "cultural / ceremonial leave",
        "ceremonial/cultural leave",
        "sorry business leave",
        "Aboriginal or Torres Strait Islander ceremonial",
        "cultural and religious observance leave",
        "religious cultural or ceremonial activities",
    ],
    "candidate_patterns": [
        ("cultural_and_ceremonial_leave", re.compile(r"\bcultural\s+and\s+ceremonial\s+leave\b", re.I)),
        ("cultural_or_ceremonial_leave", re.compile(r"\bcultural\s+or\s+ceremonial\s+leave\b", re.I)),
        ("cultural_ceremonial_slash_leave", re.compile(r"\bcultural\s*/\s*ceremonial\s+leave\b", re.I)),
        ("ceremonial_cultural_leave", re.compile(r"\bceremonial\s*/\s*cultural\s+leave\b", re.I)),
        ("ceremonial_cultural_table_label", re.compile(r"\bceremonial\s*/\s*cultural\b", re.I)),
        ("sorry_business_leave", re.compile(r"\bsorry\s+business\s+leave\b", re.I)),
        ("atsi_ceremonial", re.compile(r"\baboriginal\s+or\s+torres\s+strait\s+islander\b.{0,120}\bceremonial\b", re.I)),
        ("cultural_religious_observance", re.compile(r"\bcultural\s+and\s+religious\s+observance\s+leave\b", re.I)),
        ("religious_cultural_ceremonial_activities", re.compile(r"\breligious,\s*cultural\s+or\s+ceremonial\s+activities\b", re.I)),
    ],
    "context_patterns": [
        ("cultural_ceremonial_context", re.compile(r"\bcultural\b.{0,80}\bceremonial\b|\bceremonial\b.{0,80}\bcultural\b|\bceremonial\s*/\s*cultural\b|\bsorry\s+business\b", re.I)),
        ("atsi_context", re.compile(r"\baboriginal\b|\btorres\s+strait\s+islander\b|\btraditional\s+law\b|\bNAIDOC\b", re.I)),
    ],
    "positive_patterns": [
        ("paid_leave", re.compile(r"\bpaid\b.{0,120}\b(?:cultural|ceremonial|sorry\s+business)\b|\b(?:cultural|ceremonial|sorry\s+business)\b.{0,120}\bpaid\b", re.I)),
        ("per_year", re.compile(r"\bper\s+(?:calendar\s+)?year\b|\beach\s+year\b|\bin\s+each\s+year\s+of\s+employment\b", re.I)),
        ("unpaid_or_existing_leave_support", re.compile(r"\bannual\s+leave\b|\baccrued\s+leave\b|\bRDOs?\b|\bTOIL\b|\bTIL\b|\bleave\s+without\s+pay\b|\bunpaid\s+leave\b", re.I)),
    ],
    "out_of_scope_patterns": [
        ("table_of_contents", re.compile(r"\.{6,}\s+\d+", re.I)),
        ("naidoc_only", re.compile(r"\bNAIDOC\b(?![\s\S]{0,260}\bcultural\b)", re.I)),
    ],
    "hit_discovery_pipeline": [
        "Resolve each comparator council to its latest known canonical agreement, then load cached page text for that agreement.",
        "Find cultural, ceremonial, Aboriginal/Torres Strait Islander ceremonial, and Sorry Business candidate pages.",
        "Reject table-of-contents and NAIDOC-only noise.",
        "Accept paid cultural/ceremonial and paid Sorry Business clauses as benchmark source values.",
        "Retain unpaid or existing-leave cultural support clauses as source-observed non-benchmark support.",
        "Compare extracted source values with the reference exemplar values and preserve source/reference differences for review.",
    ],
    "acceptance_rule": "paid cultural/ceremonial/Sorry Business clause or source-observed unpaid cultural support + no blocker",
}


EMERGENCY_SERVICES_PROFILE: dict[str, Any] = {
    "artifact_id": "emergency-services-leave-clause-evidence",
    "entitlement_id": "leave-emergency-services-leave",
    "label": "Emergency Services Leave",
    "definition": "Leave for employees who are registered emergency services volunteers or attend recognised emergency management activities.",
    "taxonomy_path": ["Leave", "Emergency Services Leave"],
    "scope": "standard_band_core",
    "lookahead_pages": 2,
    "classification_boundary": {
        "canonical_definition": (
            "Employer-paid or employer-supported leave for ordinary employees responding to emergency services, "
            "voluntary emergency management, CFA, SES, or recognised emergency service organisation call-outs."
        ),
        "included": [
            "Paid emergency services leave for volunteer emergency responders.",
            "Paid community service leave where it specifically applies to registered emergency services volunteers.",
            "Unquantified paid leave or full-pay release for emergency services duty.",
        ],
        "excluded": [
            "Disaster leave for employees personally affected by catastrophic events.",
            "Volunteer leave unrelated to emergency services.",
            "Jury service, court duty, defence reserve, or armed forces leave.",
            "Table-of-contents references.",
        ],
        "needs_review": [
            "Clauses where the source states paid emergency services leave but no quantum.",
            "Clauses where emergency services leave is only an NES cross-reference.",
        ],
    },
    "accepted_subclasses": [
        {
            "subclass_id": "leave-emergency-services.paid-quantified",
            "label": "Paid Emergency Services Leave",
            "relationship": "accepted_entitlement_subclass",
        },
        {
            "subclass_id": "leave-emergency-services.paid-unquantified",
            "label": "Unquantified Paid Emergency Services Leave",
            "relationship": "accepted_entitlement_subclass",
        },
    ],
    "adjacent_subclasses": [
        {
            "subclass_id": "leave-natural-disaster.paid-time-off-unquantified",
            "label": "Natural Disaster Or Catastrophic Event Leave",
            "relationship": "adjacent_leave_subclass",
        },
        {
            "subclass_id": "leave-volunteer-or-donor",
            "label": "General Volunteer Or Donor Leave",
            "relationship": "adjacent_leave_subclass",
        },
    ],
    "search_terms": [
        "emergency services leave",
        "emergency service organisation",
        "recognised emergency service organisation",
        "voluntary emergency management",
        "registered emergency service volunteers",
        "community service leave",
        "service with emergency services organisations",
        "volunteer emergency services",
    ],
    "candidate_patterns": [
        ("emergency_services_leave", re.compile(r"\bemergency\s+services?\s+leave\b", re.I)),
        ("community_services_emergency_services", re.compile(r"\bcommunity\s+services?\s+leave.{0,12}\bemergency\s+services?\b", re.I)),
        ("community_service_leave", re.compile(r"\bcommunity\s+service\s+leave\b", re.I)),
        ("emergency_service_organisation", re.compile(r"\brecognised\s+emergency\s+service\s+organisation\b", re.I)),
        ("voluntary_emergency_management", re.compile(r"\bvoluntary\s+emergency\s+management\b", re.I)),
        ("emergency_services_volunteers", re.compile(r"\bemergency\s+services?\s+volunteers?\b", re.I)),
        ("emergency_callout", re.compile(r"\bemergency\s+call[-\s]*out\b", re.I)),
        ("service_with_emergency_services", re.compile(r"\bservice\s+with\s+emergency\s+services?\s+organisations?\b", re.I)),
        ("volunteer_emergency_services_rest_break", re.compile(r"\bvolunteer\s+emergency\s+services\b", re.I)),
    ],
    "context_patterns": [
        ("emergency_services_context", re.compile(r"\bemergency\s+services?\b|\bemergency\s+management\b|\bCFA\b|\bSES\b|\bcountry\s+fire\s+authority\b|\bstate\s+emergency\s+service\b", re.I)),
        ("volunteer_context", re.compile(r"\bvolunteer\b|\bregistered\s+members?\b|\brecognised\s+emergency\s+service\s+organisation\b", re.I)),
    ],
    "positive_patterns": [
        ("paid_leave", re.compile(r"\bpaid\s+leave\b|\bleave\s+with\s+pay\b|\bfull\s+pay\b|\bnormal\s+salary\b|\bnormal\s+rate\s+of\s+pay\b|\bspecial\s+leave\s+with\s+pay\b|\bwithout\s+loss\s+of\s+pay\b|\bshall\s+be\s+paid\b", re.I)),
        ("recognised_emergency_body", re.compile(r"\brecognised\s+emergency\s+(?:management\s+body|service\s+organisation)\b|\bCFA\b|\bSES\b", re.I)),
        ("emergency_callout", re.compile(r"\bemergency\s+call[-\s]*out\b|\bresponding\s+to\s+an\s+emergency\b|\battend\s+emergenc", re.I)),
    ],
    "out_of_scope_patterns": [
        ("table_of_contents", re.compile(r"\.{6,}\s+\d+", re.I)),
        ("natural_disaster_employee_impact", re.compile(r"\bcatastrophic\s+events?\b|\bbushfires?\b.{0,80}\bfloods?\b|\bdisaster\s+and\s+emergency\s+leave\b", re.I)),
        ("jury_or_court_service", re.compile(r"\bjury\s+service\b|\bcourt\s+duty\b", re.I)),
        ("defence_or_armed_forces", re.compile(r"\bdefence\s+reserve\b|\barmed\s+forces\b", re.I)),
        ("blood_or_general_volunteer", re.compile(r"\bblood\s+donor\b|\bvolunteer\s+day\b|\bperforming\s+volunteer\s+work\b", re.I)),
    ],
    "hit_discovery_pipeline": [
        "Resolve each comparator council to its latest known canonical agreement, then load cached page text for that agreement.",
        "Find emergency services, community service, voluntary emergency management, and recognised emergency service organisation pages.",
        "Reject table-of-contents, personal disaster impact, jury/court, defence, blood donor, and general volunteer noise.",
        "Accept quantified paid emergency services volunteer leave and unquantified paid/full-pay release clauses.",
        "Compare extracted source values with the reference exemplar values and preserve source/reference differences for review.",
    ],
    "acceptance_rule": "emergency-services volunteer clause + paid/full-pay support value or quantified paid leave + no blocker",
}


PARENTAL_CANDIDATE_PATTERNS = [
    ("paid_parental_leave", re.compile(r"\bpaid\s+parental\s+leave\b", re.I)),
    ("primary_carer_leave", re.compile(r"\bprimary\s+(?:carer|carers|care[-\s]*giver)(?:['’`?]s)?\s+(?:parental\s+)?leave\b", re.I)),
    ("secondary_carer_leave", re.compile(r"\bsecondary\s+(?:carer|carers|care[-\s]*giver|carergiver)(?:['’`?]s)?\s+(?:parental\s+)?leave\b", re.I)),
    ("partner_leave", re.compile(r"\bpartner(?:['’`?]s)?\s+leave\b|\bpaternity\s+leave\b", re.I)),
    ("non_primary_carer_leave", re.compile(r"\bnon[-\s]+primary\s+carer(?:['’`?]s)?\s+(?:parental\s+)?leave\b", re.I)),
    ("short_parental_leave", re.compile(r"\bshort\s+parental\s+leave\b|\blong\s+parental\s+leave\b", re.I)),
    ("pre_natal_leave", re.compile(r"\bpre[-\s]*natal\s+leave\b|\bprenatal\s+leave\b", re.I)),
    ("parental_leave_council_component", re.compile(r"\bparental\s+leave\s+[–-]\s+council\s+component\b", re.I)),
]


PARENTAL_CONTEXT_PATTERNS = [
    ("parental_leave_context", re.compile(r"\bparental\s+leave\b", re.I)),
    ("primary_secondary_context", re.compile(r"\bprimary\s+(?:carer|carers|care[-\s]*giver)|\bsecondary\s+(?:carer|carers|care[-\s]*giver|carergiver)|\bnon[-\s]+primary\s+carer|\bpartner(?:['’`?]s)?\s+leave\b", re.I)),
    ("pre_natal_context", re.compile(r"\bpre[-\s]*natal\b|\bprenatal\b|\bpregnancy\s+related\s+medical\s+appointments\b", re.I)),
]


PARENTAL_POSITIVE_PATTERNS = [
    ("paid_parental_leave", re.compile(r"\bpaid\s+parental\s+leave\b", re.I)),
    ("paid_primary_carer_leave", re.compile(r"\bpaid\s+primary\s+(?:carer|care[-\s]*giver)\b|\bprimary\s+(?:carer|carers|care[-\s]*giver).{0,160}\bpaid\b", re.I)),
    ("paid_secondary_carer_leave", re.compile(r"\bpaid\s+secondary\s+(?:carer|care[-\s]*giver)\b|\bsecondary\s+(?:carer|carers|care[-\s]*giver|carergiver).{0,160}\bpaid\b|\bpartner(?:['’`?]s)?\s+leave\b.{0,160}\bpaid\b", re.I)),
    ("paid_pre_natal_leave", re.compile(r"\bpaid\s+pre[-\s]*natal\s+leave\b|\bpre[-\s]*natal\s+leave\b.{0,160}\bpaid\b|\bpaid\s+leave\b.{0,160}\bpregnan", re.I)),
]


PARENTAL_OUT_OF_SCOPE_PATTERNS = [
    ("table_of_contents", re.compile(r"\.{6,}\s+\d+", re.I)),
    ("unpaid_parental_leave_only", re.compile(r"\bunpaid\s+parental\s+leave\b(?!.{0,260}\bpaid\s+parental\s+leave\b)", re.I)),
    ("special_caregiver_or_loss_leave", re.compile(r"\bspecial\s+(?:primary\s+and\s+non[-\s]+primary\s+)?caregiver\s+leave\b|\bstill[-\s]*born\b|\bneo[-\s]*natal\s+death\b|\bpregnancy\s+ends\s+after\s+20\s+weeks\b", re.I)),
    ("surrogacy_only", re.compile(r"\bsurrogacy\s+leave\b", re.I)),
    ("safe_job_or_return_to_work", re.compile(r"\bno\s+safe\s+job\b|\breturning?\s+to\s+work\b|\breplacement\s+employees?\b", re.I)),
]


PARENTAL_HIT_DISCOVERY_PIPELINE = [
    "Resolve each comparator council to its latest known canonical agreement, then load cached page text for that agreement.",
    "Find paid parental leave, primary carer, secondary/non-primary carer, and pre-natal leave pages, combining adjacent pages where tables split across page breaks.",
    "Reject table-of-contents, unpaid-only parental leave, safe-job, return-to-work, surrogacy-only, and pregnancy-loss special caregiver noise.",
    "Accept source clauses that state paid primary or secondary/non-primary carer leave, or quantified pre-natal leave for the relevant parental role.",
    "Convert standard-hour pre-natal values to the reference day signal where the source clearly uses ordinary 7.6-hour days.",
    "Compare extracted source values with the reference exemplar values and preserve source/reference differences for review.",
]


PARENTAL_PRIMARY_PROFILE: dict[str, Any] = {
    "artifact_id": "parental-leave-primary-carer-clause-evidence",
    "entitlement_id": "leave-parental-leave-primary-carer",
    "label": "Parental Leave Primary Carer",
    "definition": "Paid leave for the primary carer associated with birth, adoption, permanent care, or surrogacy placement.",
    "taxonomy_path": ["Leave", "Parental Leave", "Primary Carer"],
    "scope": "standard_band_core",
    "parental_role": "primary",
    "lookahead_pages": 3,
    "merge_source_candidates": True,
    "classification_boundary": {
        "canonical_definition": (
            "Employer-paid parental leave for the primary carer, plus quantified paid pre-natal leave available "
            "to the pregnant employee or primary-carer pathway where the source clause states a value."
        ),
        "included": [
            "Paid primary carer, primary caregiver, maternity, or primary-adoption parental leave.",
            "Paid pre-natal leave for the pregnant employee or employee attending pregnancy-related appointments.",
            "Hour-based pre-natal leave converted to day signals where the ordinary-day relationship is explicit in the agreement pattern.",
        ],
        "excluded": [
            "Secondary/non-primary carer leave.",
            "Special caregiver, stillbirth, neonatal death, or pregnancy-loss leave unless it restates the ordinary primary entitlement.",
            "Unpaid parental leave, safe-job, return-to-work, or keeping-in-touch rules.",
        ],
        "needs_review": [
            "Clauses where pre-natal leave is flexible but unquantified.",
            "Clauses where a table split makes the primary/non-primary row boundary ambiguous.",
        ],
    },
    "accepted_subclasses": [
        {
            "subclass_id": "leave-parental-primary.paid-primary-carer",
            "label": "Paid Primary Carer Leave",
            "relationship": "accepted_entitlement_subclass",
        },
        {
            "subclass_id": "leave-parental-primary.pre-natal-paid-leave",
            "label": "Primary Carer Pre-Natal Paid Leave",
            "relationship": "accepted_entitlement_subclass",
        },
    ],
    "adjacent_subclasses": [
        {
            "subclass_id": "leave-parental-secondary.paid-secondary-carer",
            "label": "Paid Secondary/Non-Primary Carer Leave",
            "relationship": "adjacent_role_subclass",
        },
        {
            "subclass_id": "leave-parental-special-caregiver-loss",
            "label": "Special Caregiver Or Pregnancy Loss Leave",
            "relationship": "adjacent_loss_leave_subclass",
        },
    ],
    "search_terms": ["paid parental leave", "primary carer leave", "primary caregiver", "pre-natal leave"],
    "candidate_patterns": PARENTAL_CANDIDATE_PATTERNS,
    "context_patterns": PARENTAL_CONTEXT_PATTERNS,
    "positive_patterns": PARENTAL_POSITIVE_PATTERNS,
    "out_of_scope_patterns": PARENTAL_OUT_OF_SCOPE_PATTERNS,
    "hit_discovery_pipeline": PARENTAL_HIT_DISCOVERY_PIPELINE,
    "acceptance_rule": "paid primary-carer parental clause or quantified primary-role pre-natal leave + no blocker",
}


PARENTAL_NON_PRIMARY_PROFILE: dict[str, Any] = {
    "artifact_id": "parental-leave-non-primary-carer-clause-evidence",
    "entitlement_id": "leave-parental-leave-non-primary",
    "label": "Parental Leave Non-Primary Carer",
    "definition": "Paid leave for the non-primary carer or partner around birth, adoption, permanent care, or surrogacy.",
    "taxonomy_path": ["Leave", "Parental Leave", "Non-Primary Carer"],
    "scope": "standard_band_core",
    "parental_role": "non_primary",
    "lookahead_pages": 3,
    "merge_source_candidates": True,
    "classification_boundary": {
        "canonical_definition": (
            "Employer-paid parental leave for the secondary or non-primary carer, plus quantified paid partner "
            "pre-natal leave where the source clause states a value."
        ),
        "included": [
            "Paid secondary carer, secondary caregiver, non-primary carer, or partner parental leave.",
            "Paid partner pre-natal leave or paid leave for an employee about to become a parent where it applies to the non-primary pathway.",
            "Hour-based partner pre-natal leave retained as hours where the reference reports hours.",
        ],
        "excluded": [
            "Primary carer leave.",
            "Special caregiver, stillbirth, neonatal death, or pregnancy-loss leave unless it restates the ordinary non-primary entitlement.",
            "Unpaid parental leave, safe-job, return-to-work, or keeping-in-touch rules.",
        ],
        "needs_review": [
            "Clauses where the reference reports ordinary non-primary weeks but the source only states special caregiver leave.",
            "General pre-natal leave available to any prospective parent where the agreement does not label the role.",
        ],
    },
    "accepted_subclasses": [
        {
            "subclass_id": "leave-parental-non-primary.paid-secondary-carer",
            "label": "Paid Secondary/Non-Primary Carer Leave",
            "relationship": "accepted_entitlement_subclass",
        },
        {
            "subclass_id": "leave-parental-non-primary.partner-pre-natal-paid-leave",
            "label": "Partner Pre-Natal Paid Leave",
            "relationship": "accepted_entitlement_subclass",
        },
    ],
    "adjacent_subclasses": [
        {
            "subclass_id": "leave-parental-primary.paid-primary-carer",
            "label": "Paid Primary Carer Leave",
            "relationship": "adjacent_role_subclass",
        },
        {
            "subclass_id": "leave-parental-special-caregiver-loss",
            "label": "Special Caregiver Or Pregnancy Loss Leave",
            "relationship": "adjacent_loss_leave_subclass",
        },
    ],
    "search_terms": ["paid parental leave", "secondary carer leave", "non-primary carer", "partner pre-natal leave"],
    "candidate_patterns": PARENTAL_CANDIDATE_PATTERNS,
    "context_patterns": PARENTAL_CONTEXT_PATTERNS,
    "positive_patterns": PARENTAL_POSITIVE_PATTERNS,
    "out_of_scope_patterns": PARENTAL_OUT_OF_SCOPE_PATTERNS,
    "hit_discovery_pipeline": PARENTAL_HIT_DISCOVERY_PIPELINE,
    "acceptance_rule": "paid secondary/non-primary parental clause or quantified partner pre-natal leave + no blocker",
}


PROFILES = {
    FAMILY_DOMESTIC_VIOLENCE_PROFILE["entitlement_id"]: FAMILY_DOMESTIC_VIOLENCE_PROFILE,
    "fdv": FAMILY_DOMESTIC_VIOLENCE_PROFILE,
    NATURAL_DISASTER_PROFILE["entitlement_id"]: NATURAL_DISASTER_PROFILE,
    "natural-disaster": NATURAL_DISASTER_PROFILE,
    COMPASSIONATE_PROFILE["entitlement_id"]: COMPASSIONATE_PROFILE,
    "compassionate": COMPASSIONATE_PROFILE,
    CULTURAL_CEREMONIAL_PROFILE["entitlement_id"]: CULTURAL_CEREMONIAL_PROFILE,
    "cultural": CULTURAL_CEREMONIAL_PROFILE,
    EMERGENCY_SERVICES_PROFILE["entitlement_id"]: EMERGENCY_SERVICES_PROFILE,
    "emergency-services": EMERGENCY_SERVICES_PROFILE,
    PARENTAL_PRIMARY_PROFILE["entitlement_id"]: PARENTAL_PRIMARY_PROFILE,
    "parental-primary": PARENTAL_PRIMARY_PROFILE,
    PARENTAL_NON_PRIMARY_PROFILE["entitlement_id"]: PARENTAL_NON_PRIMARY_PROFILE,
    "parental-non-primary": PARENTAL_NON_PRIMARY_PROFILE,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_pages(agreement_id: str) -> list[str]:
    path = ROOT / "cache" / agreement_id / "pages.json"
    if not path.exists():
        return []
    payload = read_json(path)
    return payload if isinstance(payload, list) else []


def normalise_number_words(text: str) -> str:
    normalised = compact_text(text).lower()
    for word, value in NUMBER_WORDS.items():
        normalised = re.sub(rf"\b{word}\s*\(\s*{value}\s*\)", value, normalised, flags=re.I)
        normalised = re.sub(rf"\b{word}\b", value, normalised, flags=re.I)
    return normalised


def first_pattern_labels(patterns: list[tuple[str, re.Pattern[str]]], text: str) -> list[str]:
    return [label for label, pattern in patterns if pattern.search(text)]


def is_probable_table_of_contents(text: str) -> bool:
    dot_leaders = len(re.findall(r"\.{6,}", text))
    numbered_entries = len(re.findall(r"\b\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z /&,'()\-]{4,80}\s+\.{3,}\s+\d+", text))
    return dot_leaders >= 3 or numbered_entries >= 4


def value_signature(value: str, unit: str) -> str:
    if re.fullmatch(r"day", unit, flags=re.I):
        return f"{value} day"
    if re.fullmatch(r"paid day", unit, flags=re.I):
        return f"{value} paid day"
    if re.search(r"\bpaid\s+day", unit, flags=re.I):
        return f"{value} paid days"
    if re.search(r"\bday", unit, flags=re.I):
        return f"{value} days"
    if re.fullmatch(r"week", unit, flags=re.I):
        return f"{value} week"
    if re.search(r"\bweek", unit, flags=re.I):
        return f"{value} weeks"
    if re.search(r"\bhour", unit, flags=re.I):
        return f"{value} hours"
    return f"{value} {unit}".strip()


def fdv_value_record(
    value: str,
    unit: str,
    condition: str,
    subclass_label: str,
    *,
    benchmark_value: bool = True,
) -> dict[str, str]:
    subclass_id = (
        "leave-family-domestic-violence.support-person-paid-leave"
        if "support" in subclass_label.lower()
        else "leave-family-domestic-violence.employee-paid-leave"
    )
    if not benchmark_value:
        subclass_id = "leave-family-domestic-violence.support-from-existing-carers-leave"
    return {
        "value": value,
        "unit": unit,
        "condition": condition,
        "subclass_id": subclass_id,
        "subclass_label": subclass_label,
        "benchmark_value": "true" if benchmark_value else "false",
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


def fdv_values(text: str) -> list[dict[str, str]]:
    normalised = normalise_number_words(text)
    values: list[dict[str, str]] = []

    employee_patterns = [
        (
            r"\b(?:minimum\s+)?(10|20)\s+days?\s+per\s+(?:year|annum)\b.{0,120}\bpaid\s+(?:special\s+)?(?:family\s+violence\s+)?leave\b",
            "days per annum",
        ),
        (
            r"\b(?:access\s+to|providing)\s+(?:(?:a\s+)?minimum\s+(?:of\s+)?|up\s+to\s+)?(10|20)\s+days?\s+(?:per\s+(?:year|annum)\s+)?of\s+paid\s+special\s+leave\b",
            "days per annum",
        ),
        (
            r"\bup\s+to\s+(10|20)\s+days?\s+paid\s+leave\s+per\s+annum\b",
            "days per annum",
        ),
        (
            r"\b(10|20)\s+days?\s+paid\s+special\s+leave\s+per\s+(?:year|annum)\b",
            "days per annum",
        ),
        (
            r"\b(?:family\s+violence\s+leave|family\s+violence)\b.{0,260}\b(10|20)\s+days?\s+paid\s+leave\b|\b(10|20)\s+days?\s+paid\s+leave\b.{0,260}\b(?:family\s+violence\s+leave|family\s+violence)\b",
            "days per annum",
        ),
        (
            r"\badditional\s+(10|20)\s+days?\s+paid\s+special\s+leave\s+in\s+a\s+12-month\s+period\b",
            "days per 12-month period",
        ),
        (
            r"\b(10|20)\s+paid\s+days?\s+per\s+year\s+of\s+paid\s+special\s+leave\b",
            "days per annum",
        ),
        (
            r"\baccess\s+to\s+(10|20)\s+days?\s+per\s+annum\s+non-cumulative\s+of\s+paid\s+family\s+violence\s+leave\b",
            "days per annum",
        ),
        (
            r"\badditional\s+paid\s+leave\s*\(\s*up\s+to\s+(10|20)\s+days?\s+per\s+annum\s*\)",
            "days per annum",
        ),
        (
            r"\bentitled\s+to\s+a\s+minimum\s+of\s+(10|20)\s+days?\s+of\s+paid\s+family\s+violence\s+leave\s+per\s+year\b",
            "days per annum",
        ),
        (
            r"\bfamily\s+(?:and\s+domestic\s+)?violence\b.{0,520}\bmay\s+access\s+up\s+to\s+(10|20)\s+additional\s+days?\s+paid\s+leave\b",
            "additional days paid leave per annum",
        ),
        (
            r"\bmay\s+access\s+up\s+to\s+(10|20)\s+additional\s+days?\s+paid\s+leave\b.{0,520}\bfamily\s+(?:and\s+domestic\s+)?violence\b",
            "additional days paid leave per annum",
        ),
        (
            r"\bexperiencing\s+family\s+violence\b.{0,320}\baccess\s+to\s+(10|20)\s+days?\s+per\s+(?:year|annum|instance)\b",
            "days per annum",
        ),
        (
            r"\bexperiencing\s+family\s+violence\b.{0,320}\btake\s+(10|20)\s+days?\s+paid\s+special\s+leave\b",
            "days paid special leave",
        ),
        (
            r"\bpaid\s+family\s+and\s+domestic\s+violence\s+leave\s+up\s+to\s+(10|20)\s+days?\b",
            "days per annum",
        ),
        (
            r"\bpaid\s+family/?domestic\s+violence\s+leave\s+up\s+to\s+(10|20)\s+days?\b",
            "days per annum",
        ),
        (
            r"\bfamily\s+violence/special\s+leave\b.{0,360}\badditional\s+discretion(?:al|ary)\s+paid\s+special\s+leave\s+up\s+to\s+a\s+maximum\s+of\s+(10|20)\s+days?\s+per\s+annum\b",
            "days per annum",
        ),
        (
            r"\badditional\s+discretion(?:al|ary)\s+paid\s+special\s+leave\s+up\s+to\s+a\s+maximum\s+of\s+(10|20)\s+days?\s+per\s+annum\b.{0,360}\bfamily\s+violence\b",
            "days per annum",
        ),
        (
            r"\bprovision\s+of\s+up\s+to\s+(10|20)\s+days?\s+per\s+annum\s+non-cumulative\s+leave\b",
            "days per annum",
        ),
        (
            r"\bfamily\s+(?:and\s+domestic\s+)?violence\b.{0,900}\bentitled\s+to\s+up\s+to\s+(10|15|20)\s+days?\s+paid\s+special\s+leave\b",
            "days per annum",
        ),
        (
            r"\bfamily\s+(?:and\s+domestic\s+)?violence\b.{0,900}\baccess\s+to\s+up\s+to\s+(10|15|20)\s+days?\s+of\s+paid\s+special\s+leave\s+per\s+year\b",
            "days per annum",
        ),
        (
            r"\bfamily\s+(?:and\s+domestic\s+)?violence\b.{0,900}\baccess\s+to\s+(10|15|20)\s+days?\s*(?:\([^)]+\)\s*)?per\s+financial\s+year\b.{0,120}\bpaid\s+special\s+leave\b",
            "days per financial year",
        ),
        (
            r"\bfamily\s+(?:and\s+domestic\s+)?violence\b.{0,900}\badditional\s+paid\s+leave\s*\(\s*of\s+up\s+to\s+(10|15|20)\s+days?\s+per\s+annum\b",
            "days per annum",
        ),
        (
            r"\bfamily\s+(?:and\s+domestic\s+)?violence\b.{0,900}\bentitled\s+to\s+access\s+up\s+to\s+(10|15|20)\s+days?\s+of\s+paid\s+family\s+and\s+domestic\s+violence\s+leave\b",
            "days per anniversary year",
        ),
        (
            r"\bexperiencing\s+family\s+violence\b.{0,260}\baccess\s+to\s+up\s+to\s+(10|15|20)\s+days?\s+paid\s+special\s+leave\b",
            "days per 12-month period",
        ),
        (
            r"\badditional\s+paid\s+leave\b.{0,80}\bup\s+to\s+(10|15|20)\s+days?\s+per\s+annum\b",
            "days per annum",
        ),
        (
            r"\bfamily\s+(?:and\s+domestic\s+)?violence\b.{0,1500}\b(?:access\s+to|entitled\s+to|provid(?:e|ing)|will\s+have\s+access\s+to|may\s+take)\s+(?:a\s+maximum\s+of\s+|up\s+to\s+)?(10|15|20)\s+days?\b.{0,120}\bpaid\b.{0,120}\bleave\b",
            "days per annum",
        ),
        (
            r"\bfamily\s+(?:and\s+domestic\s+)?violence\b.{0,1500}\b(10|15|20)\s+days?\b.{0,80}\bpaid\b.{0,80}\bleave\b",
            "days per annum",
        ),
        (
            r"\bfamily\s+(?:and\s+domestic\s+)?violence\b.{0,1500}\bpaid\s+leave\b.{0,80}\b(10|15|20)\s+days?\b",
            "days per annum",
        ),
        (
            r"\bfamily\s+violence\s+leave\b.{0,520}\bpermanent\s+full\s+time\s+staff\s+will\s+be\s+entitled\s+to\s+(10|15|20)\s+days?\b",
            "days per annum",
        ),
    ]
    for pattern, unit in employee_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            if re.search(r"\bcash\s+out\b", match.group(0), flags=re.I):
                continue
            value = next(group for group in match.groups() if group)
            values.append(fdv_value_record(
                value,
                unit,
                "employee experiencing family or domestic violence",
                "Employee FDV Paid Leave",
            ))

    support_patterns = [
        r"\bsupports?\s+a\s+person\s+experiencing\s+family\s+violence\b.{0,160}\bup\s+to\s+(5)\s+days?\s+paid\s+leave\b",
        r"\bup\s+to\s+(5)\s+days?\s+paid\s+leave\b.{0,160}\bsupports?\s+a\s+person\s+experiencing\s+family\s+violence\b",
        r"\bsupports?\s+a\s+person\s+experiencing\s+family\s+violence\b.{0,320}\bsupport\s+leave\b.{0,320}\b(5)\s+days?\s+paid\s+leave\s+per\s+annum\b",
        r"\bfamily\s+(?:and\s+domestic\s+)?violence\b.{0,520}\bmay\s+take\s+(2)\s+days?\s+paid\s+leave\s+per\s+year\s+to\s+accompany\b",
    ]
    for pattern in support_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            values.append(fdv_value_record(
                match.group(1),
                "days per annum",
                "employee supporting a person experiencing family violence",
                "Support Person FDV Paid Leave",
            ))

    existing_carers_patterns = [
        r"\bsupports?\s+(?:a\s+member|a\s+person)\b.{0,180}\bfamily\s+violence\b.{0,180}\b(?:use|take)\s+(5)\s+days?\s+from\s+(?:their\s+)?existing\s+personal/?carer'?s\s+leave\b",
        r"\bsupports?\s+(?:a\s+person|member)\b.{0,180}\bfamily\s+violence\b.{0,180}\bmay\s+take\s+carer'?s\s+leave\b",
    ]
    for pattern in existing_carers_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            value = match.group(1) if match.groups() else "available"
            values.append(fdv_value_record(
                value,
                "existing carer's leave access",
                "support for another person is drawn from existing carer's/personal leave",
                "Support From Existing Carer's Leave",
                benchmark_value=False,
            ))

    if re.search(r"\bwill\s+consider\s+any\s+request\s+for\s+paid\s+leave\s+or\s+flexibility\b", normalised, flags=re.I):
        values.append({
            "value": "unquantified",
            "unit": "paid leave or flexibility",
            "condition": "employee experiencing family violence",
            "subclass_id": "leave-family-domestic-violence.unquantified-paid-flexibility",
            "subclass_label": "Unquantified Paid Leave Or Flexibility",
            "benchmark_value": "false",
        })

    unquantified_paid_patterns = [
        (
            r"\bexperiencing\s+family\s+violence\b.{0,320}\baccess\s+to\s+paid\s+personal\s+emergency\s+assistance\b",
            "paid personal emergency assistance",
        ),
        (
            r"\bexperiencing\s+family/domestic\s+violence\b.{0,320}\bentitled\s+to\s+paid\s+special\s+leave\s+at\s+the\s+approval\b",
            "paid special leave at director approval",
        ),
        (
            r"\bfamily\s+(?:and\s+domestic\s+)?violence\b.{0,420}\bpaid\s+special\s+leave\s+at\s+the\s+approval\b",
            "paid special leave at director approval",
        ),
    ]
    for pattern, unit in unquantified_paid_patterns:
        if re.search(pattern, normalised, flags=re.I):
            values.append({
                "value": "unquantified",
                "unit": unit,
                "condition": "employee experiencing family or domestic violence",
                "subclass_id": "leave-family-domestic-violence.unquantified-paid-flexibility",
                "subclass_label": "Unquantified Paid Leave Or Flexibility",
                "benchmark_value": "false",
            })

    if re.search(r"\bfamily\s+and\s+domestic\s+violence\b.{0,520}\baccess\s+to\s+paid\s+special\s+leave\s+without\s+limit\b", normalised, flags=re.I):
        values.append(fdv_value_record(
            "unlimited",
            "paid special leave",
            "employee experiencing family or domestic violence",
            "Employee FDV Paid Leave",
        ))

    return dedupe_values(values)


def natural_disaster_value_record(
    value: str,
    unit: str,
    condition: str,
    subclass_id: str,
    subclass_label: str,
    *,
    benchmark_value: bool = True,
) -> dict[str, str]:
    return {
        "value": value,
        "unit": unit,
        "condition": condition,
        "subclass_id": subclass_id,
        "subclass_label": subclass_label,
        "benchmark_value": "true" if benchmark_value else "false",
    }


def natural_disaster_values(text: str) -> list[dict[str, str]]:
    normalised = normalise_number_words(text)
    values: list[dict[str, str]] = []

    paid_day_patterns = [
        r"\btotal\s+of\s+(5)\s+days?\s+of\s+paid\s+leave\b",
        r"\b(5)\s+paid\s+days?\b",
        r"\bpaid\s+leave\s+of\s+(5)\s+days?\b",
        r"\bfamily\s+emergency\s+leave\b.{0,260}\bup\s+to\s+(3)\s+days?\b.{0,360}\bnatural\s+disasters?\b",
        r"\bup\s+to\s+(3)\s+days?\b.{0,220}\bfamily\s+emergency\s+leave\b.{0,360}\bnatural\s+disasters?\b",
        r"\bleave\s+of\s+absence\s+of\s+up\s+to\s+(3)\s+ordinary\s+days?\s+per\s+annum\b.{0,520}\bnatural\s+disasters?\b",
        r"\bup\s+to\s+(5)\s+days?\s+per\s+annum\b.{0,320}\bemergency\s+situation\b.{0,160}\b(?:house\s+fire|burglary|flood)\b",
        r"\bpressing\s+necessity\s+leave\s+of\s+(3)\s+days?\s+per\s+year\b.{0,360}\b(?:fire|flood|severe\s+storms?|natural\s+disasters?)\b",
        r"\bemergency\s+leave\b.{0,260}\bpaid\s+up\s+to\s+(3)\s+days?\s+pay\b.{0,320}\bnatural\s+disaster\b",
        r"\bleave\s+of\s+absence\s+of\s+up\s+to\s+(3)\s+ordinary\s+days?\s+per\s+annum\b.{0,120}\bfull\s+pay\b.{0,520}\b(?:fire|floods?|severe\s+storms?|natural\s+disasters?)\b",
        r"\bfamily\s+and\s+emergency\s+leave\b.{0,360}\badditional\s+(5)\s+days?\s+paid\s+leave\s+per\s+year\b",
        r"\bspecial\s+leave\b.{0,120}\bleave\s+of\s+up\s+to\s+(5)\s+days?\s+per\s+annum\s+on\s+full\s+pay\b.{0,260}\b(?:house\s+fire|burglary|flood)\b",
        r"\bpressing\s+necessity\s+leave\b.{0,360}\bprovide\s+up\s+to\s+(2)\s+days?\s+paid\s+leave\s+per\s+annum\b",
        r"\bhome\s+emergency\s+leave\b.{0,520}\bentitled\s+to\s+(1)\s+day\s+of\s+paid\s+leave\s+per\s+occasion\b",
        r"\bspecial\s+disaster\s+leave\b.{0,120}\bup\s+to\s+(3)\s+days?\s+per\s+calendar\s+year\s+is\s+payable\b",
        r"\bspecial\s+leave\b.{0,160}\badditional\s+(5)\s+days?\s+non-accumulative\s+special\s+leave\b.{0,360}\b(?:fire|floods?|severe\s+storms?|natural\s+disaster)\b",
    ]
    for pattern in paid_day_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            values.append(natural_disaster_value_record(
                match.group(1),
                "paid days",
                "employee directly affected by natural disaster or extreme climatic event",
                "leave-natural-disaster.paid-leave",
                "Natural Disaster Paid Leave",
            ))

    personal_leave_patterns = [
        r"\bup\s+to\s+(2)\s+weeks?\s+of\s+accrued\s+personal\s+leave\b",
        r"\bup\s+to\s+(2)\s+weeks?\s+of\s+personal\s+leave\b",
    ]
    for pattern in personal_leave_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            if re.search(r"\bnatural\s+disaster\b|\bfire\s+or\s+flood\b|\bprincipal\s+place\s+of\s+residence\b", normalised, flags=re.I):
                values.append(natural_disaster_value_record(
                    match.group(1),
                    "weeks",
                    "principal residence uninhabitable due to natural disaster; drawn from accrued personal leave",
                    "leave-natural-disaster.accrued-personal-leave",
                    "Natural Disaster From Accrued Personal Leave",
                ))

    unquantified_patterns = [
        (
            r"\badditional\s+paid\s+time\s+off\b",
            "additional paid time off after review of the employee's disaster impact",
        ),
        (
            r"\bpaid\s+ordinary\s+hours\b.{0,220}\bnatural\s+disaster\s+leave\b|\bnatural\s+disaster\s+leave\b.{0,220}\bpaid\s+ordinary\s+hours\b",
            "paid ordinary hours may be considered for natural disaster leave",
        ),
        (
            r"\bpaid\s+ordinary\s+hours\b.{0,420}\bnatural\s+disaster\b.{0,420}\bcatastrophic\s+events\b|\bnatural\s+disaster\b.{0,420}\bpaid\s+ordinary\s+hours\b.{0,420}\bcatastrophic\s+events\b",
            "paid ordinary hours may be considered for employees impacted by catastrophic natural-disaster events",
        ),
        (
            r"\bdiscretionary\s+leave\b.{0,260}\badditional\s+paid\s+leave\b.{0,260}\bnatural\s+disasters\b",
            "discretionary additional paid leave for staff living in natural-disaster affected areas",
        ),
        (
            r"\bdiscretionary\s+leave\s+will\s+also\s+be\s+considered\b.{0,320}\bnatural\s+disasters\b",
            "discretionary leave will be considered for staff living in natural-disaster affected areas",
        ),
        (
            r"\bpressing\s+necessity\s+leave\b.{0,260}\btake\s+time\s+off\s+work\s+for\s+emergencies\b",
            "pressing necessity leave supports staff who need time off work for emergencies",
        ),
        (
            r"\bexceptional\s+circumstances\s+leave\b.{0,520}\bprevented\s+from\s+attending\s+work\b.{0,260}\bnatural\s+disaster\s+or\s+severe\s+storm\b",
            "exceptional circumstances leave may be approved when a natural disaster or severe storm prevents attendance",
        ),
        (
            r"\bpersonal\s+emergency\s+leave\b.{0,420}\bfire\s*/\s*flood\s*/\s*storm\s+or\s+any\s+other\s+natural\s+disaster\b",
            "personal emergency leave payments may be considered for fire, flood, storm, or natural disaster",
        ),
        (
            r"\bdisaster\s+leave\b.{0,420}\bflexible\s+approach\b.{0,220}\baccess\s+to\s+personal\s+leave\b",
            "flexible personal-leave access where natural disaster prevents travel to work",
        ),
        (
            r"\bspecial\s+leave\s+with\s+pay\b.{0,900}\bdirectly\s+affected\s+by\s+a\s+pressing\s+emergency\b",
            "special leave with pay may be granted where the employee is directly affected by a pressing emergency",
        ),
    ]
    for pattern, condition in unquantified_patterns:
        if re.search(pattern, normalised, flags=re.I):
            values.append(natural_disaster_value_record(
                "unquantified",
                "paid leave/time off support",
                condition,
                "leave-natural-disaster.paid-time-off-unquantified",
                "Unquantified Natural Disaster Paid Time Off",
                benchmark_value=False,
            ))

    if re.search(r"\bnormal\s+day'?s\s+wage\b.{0,180}\bwithout\s+deduction\s+from\s+any\s+leave\s+balances\b", normalised, flags=re.I):
        values.append(natural_disaster_value_record(
            "unquantified",
            "normal day's wage without leave-balance deduction",
            "employee unable to attend work because they are directly affected by extreme climatic events",
            "leave-natural-disaster.paid-time-off-unquantified",
            "Unquantified Natural Disaster Paid Time Off",
            benchmark_value=False,
        ))

    if re.search(r"\bordinary\s+day\S{0,4}s\s+pay\b.{0,180}\bwithout\s+deduction\s+from\s+any\s+leave\s+balances\b", normalised, flags=re.I):
        values.append(natural_disaster_value_record(
            "1",
            "paid day",
            "employee directly affected by extreme climatic event resulting in natural disaster",
            "leave-natural-disaster.paid-leave",
            "Natural Disaster Paid Leave",
        ))

    percent_match = re.search(
        r"\bexceptional\s+circumstances\s+leave\b.{0,900}\bleave\s+may\s+be\s+approved\s+for\s+(50)\s+percent\s+of\s+the\s+time\s+off\s+work\b",
        normalised,
        flags=re.I,
    )
    if percent_match and re.search(r"\bnatural\s+disaster\b|\bsevere\s+storm\b", normalised, flags=re.I):
        values.append(natural_disaster_value_record(
            percent_match.group(1),
            "percent of time off work",
            "exceptional circumstances leave for natural disaster or severe storm attendance prevention",
            "leave-natural-disaster.paid-time-off-unquantified",
            "Unquantified Natural Disaster Paid Time Off",
            benchmark_value=False,
        ))

    return dedupe_values(values)


def compassionate_value_record(
    value: str,
    unit: str,
    condition: str,
    subclass_id: str,
    subclass_label: str,
    *,
    benchmark_value: bool = True,
) -> dict[str, str]:
    return {
        "value": value,
        "unit": unit,
        "condition": condition,
        "subclass_id": subclass_id,
        "subclass_label": subclass_label,
        "benchmark_value": "true" if benchmark_value else "false",
    }


def compassionate_values(text: str) -> list[dict[str, str]]:
    normalised = normalise_number_words(text)
    values: list[dict[str, str]] = []

    standard_day_patterns = [
        r"\ban\s+employee\s+is\s+entitled\s+to\s+(4)\s+days?.{0,8}\s+of\s+paid\s+compassionate\s+leave\s+per\s+occasion\b",
        r"\bif\s+directly\s+responsible\s+for\s+managing\s+funeral\s+arrangements\b.{0,220}\bentitled\s+to\s+(5)\s+days?\b",
        r"\bdirectly\s+responsible\s+for\s+managing\s+funeral\s+arrangements\b.{0,260}\bentitled\s+to\s+(5)\s+days?\b",
        r"\b(3|5)\s+days?\s+paid\s+compassionate\s*/?\s*bereavement\s+leave\s+will\s+be\s+granted\b",
        r"\b(3|5)\s+days?\s+paid\s+bereavement\s*/?\s*compassionate\s+leave\s+will\s+be\s+granted\b",
        r"\bpaid\s+bereavement\s*/?\s*compassionate\s+leave\b.{0,220}\bnormal\s+hours\s+worked\s+in\s+(7)\s+working\s+days\b",
        r"\bentitled\s+to\s+(5)\s+days?\s+of\s+paid\s+compassionate\s+leave\s+for\s+each\s+occasion\b",
        r"\bemployees\b.{0,80}\bentitled\s+to\s+(4)\s+days?\s+paid\s+compassionate\s+leave\b",
        r"\ban\s+employee\s+may\s+take\s+up\s+to\s+(5)\s+days?\s+of\s+compassionate\s+leave\s+per\s+permissible\s+occasion\b",
        r"\bcompassionate\s+leave\s+of\s+up\s+to\s+(5)\s+days?\s+on\s+each\s+occasion\s+may\s+be\s+granted\b",
        r"\bcompassionate\s+leave\s+of\s+(3)\s+days?\b.{0,80}\bon\s+each\s+occasion\s+may\s+be\s+granted\b",
        r"\bentitled\s+to\s+(4)\s+days?\s+bereavement\s*/?\s*compassionate\s+leave\s+paid\s+on\s+each\s+occasion\b",
        r"\bfull-time\s+and\s+part-time\s+employees\s+are\s+entitled\s+to\s+(3|5)\s+days?\s+of\s+paid\s+compassionate\s+leave\s+per\s+occasion\b",
        r"\b(?:an\s+)?employee\s+is\s+entitled\s+to\s+(3|5)\s+days?\s+compassionate\s+leave\s+on\s+each\s+occasion\b",
        r"\bemployees\s+are\s+entitled\s+to\s+apply\s+for\s+up\s+to\s+(5)\s+days?\s+compassionate\s+leave,\s+paid\s+on\s+each\s+occasion\b",
        r"\ban\s+employee\s+is\s+entitled\s+to\s+(5)\s+days?\s+bereavement\s*/\s*compassionate\s+leave\s+paid\s+on\s+each\s+occasion\b",
        r"\ban\s+employee\s+is\s+entitled\s+to\s+(3)\s+days?\s+bereavement\s*/\s*compassionate\s+leave\b.{0,120}\bpaid\s+on\s+each\s+occasion\b",
        r"\ban\s+employee\s+is\s+entitled\s+to\s+(3)\s+days?\s+compassionate\s*/\s*bereavement\s+leave\b.{0,120}\bpaid\b",
        r"\bup\s+to\s+(5)\s+paid\s+days?\b.{0,220}\bof\s+bereavement\s*/\s*compassionate\s+leave\b",
        r"\b(5)\s+days?\s+of\s+paid\s+compassionate\s+leave\s+per\s+occasion\b",
        r"\b(5)\s+days?\s+compassionate\s+leave\b.{0,120}\beach\s+occasion\b",
        r"\b(5)\s+days?\s+bereavement\s*/\s*compassionate\s+leave\b.{0,120}\bpaid\s+on\s+each\s+occasion\b",
        r"\b(3)\s+days?\s+bereavement\s*/\s*compassionate\s+leave\b.{0,140}\bpaid\s+on\s+each\s+occasion\b",
        r"\bup\s+to\s+(3)\s+days?.{0,12}\s+paid\b.{0,260}\bcompassionate\b",
        r"\bpermanent\s+employees\s+are\s+entitled\s+to\s+(3|5)\s+days?\s+paid\s+bereavement\s+leave\s+per\s+occasion\b",
        r"\b(?:an\s+)?employee\s+is\s+entitled\s+to\s+(3|5)\s+days?[?'’]?\s+compassionate\s*/?\s*bereavement\s+leave,\s*paid\s+on\s+each\s+occasion\b",
        r"\b(?:an\s+)?employee\s+is\s+entitled\s+to\s+(3|5)\s+days?[?'’]?\s+bereavement\s*/?\s*compassionate\s+leave,\s*paid\s+on\s+each\s+occasion\b",
        r"\b(?:an\s+)?employee\s+is\s+entitled\s+to\s+(3|5)\s+days?[?'’]?\s+compassionate\s*/?\s*bereavement\s+leave\b.{0,160}\bpaid\s+on\s+each\s+occasion\b",
        r"\bup\s+to\s+a\s+maximum\s+of\s+(5)\s+days?[?'’]?\s+on\s+each\s+occasion\b.{0,220}\bpaid\s+compassionate\s+leave\b",
        r"\b(3|5)\s+days?\s*\(\s*pro\s+rata\s*\)\s+bereavement\s*/?\s*compassionate\s+leave\b",
        r"\b(5)\s+days?[?'’]?\s+paid\s+bereavement\s+leave\b",
        r"\bemployees?\s+other\s+than\s+casuals\s+will\s+be\s+granted\s+up\s+to\s+(5)\s+days?\s+of\s+compassionate\s+leave\b",
    ]
    for pattern in standard_day_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            values.append(compassionate_value_record(
                match.group(1),
                "days",
                "paid compassionate or bereavement leave per occasion",
                "leave-compassionate.paid-compassionate-leave",
                "Paid Compassionate Leave",
            ))

    week_patterns = [
        r"\bentitled\s+to\s+up\s+to\s+(1)\s+week\s+of\s+compassionate\s+leave\s+on\s+each\s+occasion\b",
        r"\bpaid\s+bereavement\s*/?\s*compassionate\s+leave\b.{0,220}\bnormal\s+hours\s+worked\s+in\s+(1)\s+week\b",
        r"\bpaid\s+compassionate\s*/?\s*bereavement\s+leave\b.{0,220}\bnormal\s+hours\s+worked\s+in\s+(1)\s+week\b",
    ]
    for pattern in week_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            values.append(compassionate_value_record(
                match.group(1),
                "week",
                "paid compassionate or bereavement leave per occasion",
                "leave-compassionate.paid-compassionate-leave",
                "Paid Compassionate Leave",
            ))

    cohort_day_patterns = [
        r"\bcompassionate\s+leave\s+of\s+(3)\s+days?\s*\(\s*(4)\s+days?\s+for\s+child\s+care\s+workers?\s*\)",
        r"\b(3)\s+days?\s+compassionate\s*/\s*bereavement\s+leave\s*\(\s*(4)\s+days?\s+for\s+child\s+care\s+workers?\s*\)",
        r"\b(3)\s+days?\s+bereavement\s*/\s*compassionate\s+leave,\s*\(\s*(4)\s+days?\s+for\s+child\s+care\s+workers?\s*\)",
    ]
    for pattern in cohort_day_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            values.append(compassionate_value_record(
                match.group(1),
                "days",
                "paid compassionate or bereavement leave per occasion",
                "leave-compassionate.paid-compassionate-leave",
                "Paid Compassionate Leave",
            ))
            values.append(compassionate_value_record(
                match.group(2),
                "days",
                "paid compassionate or bereavement leave for child care workers",
                "leave-compassionate.paid-compassionate-leave",
                "Paid Compassionate Leave",
            ))

    table_cohort_patterns = [
        r"\bup\s+to\s+(4)\s+days?.{0,12}\s+paid\b.{0,360}\bnurses?\b.{0,180}\bcompassionate\b",
        r"\bup\s+to\s+(4)\s+days?.{0,12}\s+paid\b.{0,280}\bcompassionate\b.{0,160}\bnurses?\b",
        r"\bcompassionate\b.{0,160}\bnurses?\b.{0,220}\b(4)\s+days?\s+leave\s+applies\s+to\s+each\s+occasion\b",
    ]
    for pattern in table_cohort_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            values.append(compassionate_value_record(
                match.group(1),
                "days",
                "paid compassionate or bereavement leave for nurses",
                "leave-compassionate.paid-compassionate-leave",
                "Paid Compassionate Leave",
            ))

    additional_day_patterns = [
        r"\badditional\s+(3)\s+days?\s+paid\s+bereavement\s+or\s+compassionate\s+days?\b",
        r"\badditional\s+(5)\s+days?.{0,12}\s+bereavement\s+leave\b",
    ]
    for pattern in additional_day_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            values.append(compassionate_value_record(
                match.group(1),
                "days",
                "additional paid bereavement or compassionate leave",
                "leave-compassionate.paid-bereavement-leave",
                "Paid Bereavement Leave",
            ))

    table_day_patterns = [
        (
            r"\bamounts?\s+of\s+compassionate\s+leave\b.{0,420}\bspouse/partner\s+or\s+child\s+(20)\s+days\b",
            "paid compassionate leave for spouse/partner or child",
        ),
        (
            r"\bamounts?\s+of\s+compassionate\s+leave\b.{0,520}\bparent\s+(10)\s+days\b",
            "paid compassionate leave for parent",
        ),
        (
            r"\bamounts?\s+of\s+compassionate\s+leave\b.{0,620}\bother\s+significant\s+relationship\s+(5)\s+days\b",
            "paid compassionate leave for other significant relationship",
        ),
        (
            r"\bmaximum\s+number\s+of\s+days\s+paid\s+compassionate\s+leave\s+per\s+occasion\b.{0,360}\bimmediate\s+family\b.{0,160}\b(5)\s+days\b",
            "paid compassionate leave for immediate family",
        ),
        (
            r"\bmaximum\s+number\s+of\s+days\s+paid\s+compassionate\s+leave\s+per\s+occasion\b.{0,560}\bsignificant\s+other\b.{0,160}\b(2)\s+days\b",
            "paid compassionate leave for significant other",
        ),
    ]
    for pattern, condition in table_day_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            values.append(compassionate_value_record(
                match.group(1),
                "days",
                condition,
                "leave-compassionate.paid-compassionate-leave",
                "Paid Compassionate Leave",
            ))

    special_week_patterns = [
        r"\bpaid\s+special\s+bereavement\s+leave\b.{0,220}\bmaximum\s+of\s+(8)\s+weeks?\b",
        r"\bstill[-\s]*born\s+or\s+neo[-\s]*natal\s+death\b.{0,220}\bmaximum\s+of\s+(8)\s+weeks?\b",
    ]
    for pattern in special_week_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            values.append(compassionate_value_record(
                match.group(1),
                "weeks",
                "paid special bereavement leave for stillbirth or neonatal death",
                "leave-compassionate.special-neonatal-bereavement",
                "Special Stillbirth Or Neonatal Bereavement Leave",
            ))

    if (
        re.search(r"\bbereavement\s*/?\s*compassionate\s+leave\s+is\s+provided\s+for\s+in\s+the\s+NES\b", normalised, flags=re.I)
        and re.search(r"\bentitled\s+to\s+payment\s+for\s+bereavement\s*/?\s*compassionate\s+leave\b|\bpaid\s+compassionate\s+leave\b|\bpaid\s+bereavement\s+leave\b", normalised, flags=re.I)
    ):
        values.append(compassionate_value_record(
            "NES",
            "paid compassionate/bereavement leave cross-reference",
            "paid compassionate or bereavement leave provided through NES cross-reference",
            "leave-compassionate.nes-cross-reference",
            "NES Compassionate/Bereavement Leave Cross-Reference",
            benchmark_value=False,
        ))

    return dedupe_values(values)


def cultural_value_record(
    value: str,
    unit: str,
    condition: str,
    subclass_id: str,
    subclass_label: str,
    *,
    benchmark_value: bool = True,
) -> dict[str, str]:
    return {
        "value": value,
        "unit": unit,
        "condition": condition,
        "subclass_id": subclass_id,
        "subclass_label": subclass_label,
        "benchmark_value": "true" if benchmark_value else "false",
    }


def cultural_ceremonial_values(text: str) -> list[dict[str, str]]:
    normalised = normalise_number_words(text)
    values: list[dict[str, str]] = []

    paid_day_patterns = [
        r"\bceremonial\s+leave\b.{0,320}\bentitled\s+to\s+(1)\s+paid\s+day\b",
        r"\bemployees\s+are\s+entitled\s+to\s+(1)\s+day\s+of\s+paid\s+cultural\s+and\s+ceremonial\s+leave\s+per\s+calendar\s+year\b",
        r"\bup\s+to\s+(1)\s+day\s+in\s+each\s+year\s+of\s+employment\s+will\s+be\s+with\s+pay\b",
        r"\bentitled\s+(?:to\s+)?(?:up\s+to\s+)?(1)\s+day\s+of\s+paid\s+leave\s+per\s+year\b",
        r"\b(1)\s+paid\s+day\b.{0,220}\bcultural\b.{0,120}\bceremonial\b",
        r"\bcultural\b.{0,120}\bceremonial\b.{0,220}\b(1)\s+paid\s+day\b",
        r"\ball\s+employees:\s+(1)\s+paid\b.{0,220}\bceremonial\s*/\s*cultural\b",
        r"\b(1)\s+day\s+paid\s+per\s+calendar\s+year\s+to\s+participate\s+in\s+NAIDOC\b",
    ]
    for pattern in paid_day_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            values.append(cultural_value_record(
                match.group(1),
                "paid day",
                "paid cultural or ceremonial leave per year",
                "leave-cultural-ceremonial.paid-cultural-leave",
                "Paid Cultural/Ceremonial Leave",
            ))

    sorry_business_patterns = [
        r"\bup\s+to\s+(3)\s+days?\s+per\s+year\s+of\s+paid\s+sorry\s+business\s+leave\b",
        r"\bpaid\s+sorry\s+business\s+leave\b.{0,160}\bup\s+to\s+(3)\s+days?\s+per\s+year\b",
    ]
    for pattern in sorry_business_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            values.append(cultural_value_record(
                match.group(1),
                "paid days",
                "paid Sorry Business leave per year",
                "leave-cultural-ceremonial.paid-sorry-business",
                "Paid Sorry Business Leave",
            ))

    unpaid_day_patterns = [
        r"\baboriginal\s+or\s+torres\s+strait\s+islander\b.{0,520}\bup\s+to\s+(10)\s+working\s+days?\W*unpaid\s+leave\b",
        r"\bup\s+to\s+(10)\s+working\s+days?\W*unpaid\s+leave\b.{0,520}\baboriginal\s+or\s+torres\s+strait\s+islander\b",
        r"\baboriginal\s+or\s+torres\s+strait\s+islander\b.{0,420}\bup\s+to\s+(10)\s+working\s+days?[?'â€™]?\s+unpaid\s+leave\b",
        r"\bup\s+to\s+(10)\s+working\s+days?[?'â€™]?\s+unpaid\s+leave\b.{0,420}\baboriginal\s+or\s+torres\s+strait\s+islander\b",
        r"\bcultural\s+and\s+religious\s+observance\s+leave\b.{0,520}\bup\s+to\s+(10)\s+days?[?'â€™]?\s+leave\s+without\s+pay\s+per\s+annum\b",
    ]
    for pattern in unpaid_day_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            values.append(cultural_value_record(
                match.group(1),
                "working days unpaid leave" if "working" in match.group(0) else "days leave without pay per annum",
                "cultural or ceremonial observance may use unpaid leave",
                "leave-cultural-ceremonial.existing-or-unpaid-leave",
                "Existing Or Unpaid Cultural/Ceremonial Leave Support",
                benchmark_value=False,
            ))

    if not values and re.search(r"\bcultural\b.{0,120}\bceremonial\b|\bceremonial\b.{0,120}\bcultural\b", normalised, flags=re.I):
        if re.search(r"\bleave\s+without\s+pay\b|\bunpaid\s+leave\b|\bannual\s+leave\b|\baccrued\s+leave\b|\bRDOs?\b|\bTOIL\b|\bTIL\b|\btime\s+off\s+in\s+lieu\b", normalised, flags=re.I):
            values.append(cultural_value_record(
                "available",
                "existing or unpaid leave support",
                "cultural or ceremonial observance may use existing accrued leave or unpaid leave",
                "leave-cultural-ceremonial.existing-or-unpaid-leave",
                "Existing Or Unpaid Cultural/Ceremonial Leave Support",
                benchmark_value=False,
            ))

    return dedupe_values(values)


def emergency_services_value_record(
    value: str,
    unit: str,
    condition: str,
    subclass_id: str,
    subclass_label: str,
    *,
    benchmark_value: bool = True,
) -> dict[str, str]:
    return {
        "value": value,
        "unit": unit,
        "condition": condition,
        "subclass_id": subclass_id,
        "subclass_label": subclass_label,
        "benchmark_value": "true" if benchmark_value else "false",
    }


def emergency_services_values(text: str) -> list[dict[str, str]]:
    normalised = normalise_number_words(text)
    values: list[dict[str, str]] = []

    quantified_patterns = [
        (
            r"\bpaid\s+up\s+to\s+(2)\s+weeks?\b|\bwill\s+be\s+paid\s+up\s+to\s+(2)\s+weeks?\b",
            "weeks",
            "paid emergency services leave for registered emergency management activity",
        ),
        (
            r"\bpaid\s+leave\s+up\s+to\s+a\s+maximum\s+of\s+(1)\s+week\b",
            "week",
            "paid community service leave for registered emergency services volunteers",
        ),
        (
            r"\bup\s+to\s+(1)\s+week.{0,8}\s+paid\s+leave\b",
            "week",
            "paid emergency services leave outside the Shire but within Victoria",
        ),
        (
            r"\bpaid\s+leave\s+up\s+to\s+(5)\s+working\s+days?\s+for\s+each\s+occasion\b",
            "days",
            "paid emergency services leave for each occasion",
        ),
        (
            r"\bfirst\s+(5)\s+days?\s+of\s+leave\s+each\s+calendar\s+year\s+shall\s+be\s+paid\b",
            "paid days",
            "paid emergency services leave each calendar year",
        ),
        (
            r"\bpaid\s+leave\b.{0,160}\bequivalent\s+to\s+(10)\s+working\s+days?\s+per\s+year\b.{0,260}\bemergency\b",
            "working days per year",
            "paid leave for emergency services response",
        ),
        (
            r"\bemergency\b.{0,260}\bpaid\s+leave\b.{0,160}\bequivalent\s+to\s+(10)\s+working\s+days?\s+per\s+year\b",
            "working days per year",
            "paid leave for emergency services response",
        ),
        (
            r"\bemergency\s+services?\s+leave\b.{0,520}\bleave\s+cannot\s+exceed\s+(2)\s+days?\b",
            "days per emergency attendance",
            "emergency services leave maximum without further approval",
        ),
        (
            r"\bemergency\s+services?\s+leave\b.{0,1400}\bleave\s+cannot\s+exceed\s+(2)\s+days?\b",
            "days per emergency attendance",
            "emergency services leave maximum without further approval",
        ),
        (
            r"\bup\s+to\s+(5)\s+days?\s+of\s+leave\s+with\s+pay\s+per\s+annum\s+community\s+service\s+leave\b.{0,240}\bemergency\s+response\s+activities\b",
            "days per annum",
            "paid community service leave for emergency response activities",
        ),
        (
            r"\bminimum\s+(10)[-\s]*hour\s+rest\s+break\b.{0,260}\bwithin\s+rostered\s+hours\b.{0,80}\bpaid\s+by\s+the\s+council\b",
            "hour paid rest break",
            "paid rest break after volunteer emergency services active service",
        ),
        (
            r"\bemergency\s+services?\s+leave\b.{0,1400}\bleave\s+cannot\s+exceed\s+(3)\s+days?\b",
            "days per emergency attendance",
            "emergency services leave maximum without further approval",
        ),
        (
            r"\bemergency\s+services?\s+leave\b.{0,1400}\bgranted\s+(3)\s+days?\s+paid\s+leave\s+at\s+(?:their\s+)?normal\s+rate\s+of\s+pay\b",
            "days per emergency attendance",
            "paid emergency services leave when approved",
        ),
        (
            r"\bservice\s+with\s+emergency\s+services?\s+organisations?\b.{0,520}\bgrant\s+up\s+to\s+(3)\s+days?[?'â€™]?\s+paid\s+leave\s+per\s+emergency\b",
            "days per emergency",
            "paid emergency services leave per emergency",
        ),
        (
            r"\bservice\s+with\s+emergency\s+services?\s+organisations?\b.{0,520}\bgrant\s+up\s+to\s+(3)\s+days?\W*paid\s+leave\s+per\s+emergency\b",
            "days per emergency",
            "paid emergency services leave per emergency",
        ),
        (
            r"\bemergency\s+services?\s+leave\b.{0,700}\bpaid\s+leave,\s+equivalent\s+to\s+(10)\s+working\s+days?\s+per\s+calendar\s+year\b",
            "working days per year",
            "paid emergency services leave per calendar year",
        ),
    ]
    for pattern, unit, condition in quantified_patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            value = next(group for group in match.groups() if group)
            values.append(emergency_services_value_record(
                value,
                unit,
                condition,
                "leave-emergency-services.paid-quantified",
                "Paid Emergency Services Leave",
                benchmark_value=(value != "unquantified"),
            ))

    unquantified_patterns = [
        (
            r"\bemergency\s+services?\s+volunteers?\b.{0,220}\bspecial\s+leave\s+with\s+pay\b",
            "registered emergency services volunteers responding to an emergency call-out",
        ),
        (
            r"\bemergency\s+service\s+activities\b.{0,520}\bspecial\s+leave\s+with\s+pay\b",
            "special leave with pay for emergency service activities",
        ),
        (
            r"\bvolunteer\s+member\b.{0,180}\bemergency\s+service\b.{0,220}\bleave\s+can\s+be\s+granted\s+on\s+full\s+pay\b",
            "volunteer emergency services member attending emergencies in work time",
        ),
        (
            r"\bemergency\s+service\s+agency\b.{0,220}\bleave\s+can\s+be\s+granted\s+on\s+full\s+pay\b",
            "volunteer emergency services member attending emergencies in work time",
        ),
        (
            r"\bentitled\s+to\s+leave\s+for\b.{0,260}\bvoluntary\s+emergency\s+management\s+activity\b",
            "voluntary emergency management activity leave",
        ),
        (
            r"\bemergency\s+services?\s+leave\b.{0,900}\bpaid\s+emergency\s+services?\s+leave\b",
            "paid emergency services leave application",
        ),
        (
            r"\brelease(?:d)?\s+affected\s+staff\s+to\s+attend\s+to\s+an\s+emergency\b.{0,900}\bpaid\s+emergency\s+services?\s+leave\b",
            "released staff attending an emergency situation",
        ),
        (
            r"\bgranted\s+paid\s+leave\s+during\s+normal\s+working\s+hours\b.{0,260}\bemergency\s+response\b",
            "emergency response attendance during normal working hours",
        ),
        (
            r"\bcontinue\s+to\s+pay\s+the\s+employee\s+at\s+(?:their|his\s+or\s+her)\s+(?:ordinary|normal)\s+rate\s+of\s+pay\b.{0,360}\bemergency\b",
            "ordinary or normal pay while attending an emergency",
        ),
        (
            r"\bwhere\s+leave\s+is\s+granted\b.{0,360}\bcontinue\s+to\s+pay\s+the\s+employee\b.{0,360}\bemergency\b",
            "paid voluntary emergency management activity leave",
        ),
        (
            r"\bemergency\s+services?\s+leave\b.{0,360}\bfull\s+pay\b",
            "emergency services leave on full pay",
        ),
        (
            r"\bcontinue\s+to\s+pay\s+the\s+employee\s+their\s+base\s+rate\s+of\s+pay\b.{0,360}\bemergency\s+situation\b",
            "base-rate pay where an emergency situation requires attendance",
        ),
        (
            r"\bgrant\s+leave\s+with\s+pay\b.{0,260}\bactive\s+participation\s+in\s+these\s+organisations\b",
            "active participation in emergency services organisations",
        ),
        (
            r"\bapprove\s+leave\s+with\s+pay\b.{0,260}\ballow\s+active\s+participation\s+in\s+these\s+organisations\b",
            "active participation in emergency services organisations",
        ),
        (
            r"\bprovide\s+paid\s+leave\s+for\s+volunteers\b.{0,260}\bemergency\s+services?\s+leave\s+policy\b",
            "paid emergency services volunteer leave under policy",
        ),
        (
            r"\bpaid\s+(?:their\s+)?normal\s+salary\s+for\s+the\s+duration\b.{0,260}\bemergency\s+duties\b",
            "normal salary while required to perform emergency duties",
        ),
        (
            r"\bif\s+approved\b.{0,180}\bgranted\s+paid\s+leave\s+at\s+(?:their\s+)?normal\s+rate\s+of\s+pay\b.{0,420}\bemergency\b",
            "normal-rate paid emergency services leave when approved",
        ),
        (
            r"\bapply\s+for\s+paid\s+community\s+service\s+leave\b.{0,260}\bparticipate\s+in\s+emergency\s+assistance\b",
            "paid community service leave for emergency assistance",
        ),
        (
            r"\bcouncil\s+will\s+continue\s+to\s+pay\s+the\s+employee\b.{0,120}\bnormal\s+rate\s+of\s+pay\b.{0,120}\bemergency\s+services?\s+leave\b",
            "normal-rate pay while on emergency services leave",
        ),
        (
            r"\bwill\s+allow\s+paid\s+leave\s+during\s+normal\s+working\s+hours\b.{0,360}\bemergency\s+situation\b",
            "paid leave during normal working hours for emergency services members",
        ),
        (
            r"\bvolunteer\s+member\b.{0,220}\bcfa\b.{0,120}\bses\b.{0,220}\bleave\s+can\s+be\s+granted\s+at\s+full\s+pay\b",
            "full-pay emergency services leave for CFA/SES volunteers",
        ),
        (
            r"\bgranted\s+paid\s+additional\s+leave\b.{0,260}\bactive\s+participation\s+in\s+these\s+organisations\b",
            "paid additional leave for active participation in emergency services organisations",
        ),
    ]
    for pattern, condition in unquantified_patterns:
        if re.search(pattern, normalised, flags=re.I):
            values.append(emergency_services_value_record(
                "unquantified",
                "paid emergency services leave support",
                condition,
                "leave-emergency-services.paid-unquantified",
                "Unquantified Paid Emergency Services Leave",
                benchmark_value=False,
            ))

    return dedupe_values(values)


def parental_value_record(
    value: str,
    unit: str,
    condition: str,
    subclass_id: str,
    subclass_label: str,
    *,
    benchmark_value: bool = True,
) -> dict[str, str]:
    return {
        "value": value,
        "unit": unit,
        "condition": condition,
        "subclass_id": subclass_id,
        "subclass_label": subclass_label,
        "benchmark_value": "true" if benchmark_value else "false",
    }


def hours_to_parental_signal(hours: str, role: str) -> tuple[str, str]:
    numeric = float(hours)
    if numeric == 5.0:
        return "5", "hours"
    if numeric == 7.6:
        return "1", "day"
    if numeric == 20.0:
        return ("3", "days") if role == "primary" else ("20", "hours")
    if numeric == 22.8:
        return "3", "days"
    if numeric == 38.0:
        return "5", "days"
    return str(int(numeric) if numeric.is_integer() else numeric), "hours"


PRIMARY_PARENTAL_WEEKS = r"(?:14|15|16|17|18|19|20|26)"
NON_PRIMARY_PARENTAL_WEEKS = r"(?:1|2|3|4|5|6|8|10|15|16|18|20)"


def add_parental_alias_values(values: list[dict[str, str]], normalised: str, role: str) -> None:
    """Capture role-specific parental quantums from table rows and council-specific aliases."""
    if role == "primary":
        patterns: list[tuple[str, str]] = [
            (rf"\bprimary\s+(?:carer|carers|care[-\s]*giver)(?:['’`?]s)?\s+leave\b.{{0,420}}\b(?P<value>{PRIMARY_PARENTAL_WEEKS})\s+(?:calendar\s+)?weeks?\b.{{0,180}}\b(?:paid|pay|ordinary|normal)", "weeks"),
            (rf"\b(?P<value>{PRIMARY_PARENTAL_WEEKS})\s+(?:calendar\s+)?weeks?\s+(?:paid\s+)?primary\s+(?:carer|carers|care[-\s]*giver)(?:['’`?]s)?\s+leave\b", "weeks"),
            (rf"\bprimary\s+(?:carer|care[-\s]*giver)\b.{{0,520}}\b(?:entitled|receive|payment|pay|paid).{{0,180}}\b(?P<value>{PRIMARY_PARENTAL_WEEKS})\s+weeks?\S{{0,3}}\s+(?:pay|paid|leave)\b", "weeks"),
            (rf"\bcouncil\s+will\s+pay\s+(?P<value>{PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+of\s+parental\s+leave\b.{{0,220}}\bprimary\s+carer\b", "weeks"),
            (rf"\bprimary\s+carer\b.{{0,420}}\bcouncil\s+will\s+pay\s+(?P<value>{PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+of\s+parental\s+leave\b", "weeks"),
            (rf"\bprimary\s+care[-\s]*giver\s+leave\s+(?P<value>{PRIMARY_PARENTAL_WEEKS})\s+weeks?\b", "weeks"),
            (rf"\btype\s+of\s+leave\s+paid\s+leave\s+primary\s+care[-\s]*giver\s+leave\s+(?P<value>{PRIMARY_PARENTAL_WEEKS})\s+weeks?\b", "weeks"),
            (rf"\bprimary\s+(?:carer|care[-\s]*giver)\b.{{0,520}}\bwill\s+be\s+paid\s+for\s+the\s+first\s+(?P<value>{PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+of\s+their\s+leave\b", "weeks"),
            (rf"\bfirst\s+(?P<value>{PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+of\s+parental\s+leave\s+for\s+the\s+primary\s+care\s+giver\s+is\s+paid\s+leave\b", "weeks"),
            (rf"\bprimary\s+carer\b.{{0,320}}\bentitled\s+to:?\s*(?:[a-z]\)\s*)?(?P<value>{PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+of\s+payment\b", "weeks"),
            (rf"\bprimary\s+carer\s+leave\b.{{0,700}}\bpayments?\s+based\s+upon\s+(?P<value>{PRIMARY_PARENTAL_WEEKS})\s+weeks?\S{{0,3}}\s+pay\b", "weeks"),
            (rf"\bpaid\s+parental/adoption\s+leave\b.{{0,240}}\bpayment\s+representing\s+(?P<value>{PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+pay\b", "weeks"),
            (rf"\bprimary\s+care[-\s]*giver\b.{{0,500}}\b(?P<value>{PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+(?:leave\s+)?at\s+full\s+pay\b", "weeks"),
            (rf"\bat\s+least\s+12\s+months\s+service\b.{{0,260}}\b(?P<value>15)\s+weeks\b.{{0,260}}\bsecondary\s+care[-\s]*giver\b", "weeks"),
            (r"\bentitlement\s+to\s+paid\s+parental\s+leave\b.{0,520}\b(?P<value>16)\s+weeks\s+paid\s+parental\s+leave\b", "weeks"),
            (r"\bemployer\s+is\s+not\s+required\s+to\s+pay\s+more\s+than\s+the\s+monetary\s+value\s+of\s+(?P<value>16)\s+weeks?\S{0,3}\s+pay\b", "weeks"),
        ]
        condition = "primary carer paid parental leave"
        subclass_id = "leave-parental-primary.paid-primary-carer"
        subclass_label = "Paid Primary Carer Leave"
    else:
        patterns = [
            (rf"\bsecondary\s+(?:carer|carers|care[-\s]*giver|carergiver)(?:['’`?]s)?\s+leave\b.{{0,520}}\b(?:entitled\s+to|up\s+to|maximum\s+of|payment\s+representing|of)\s+(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+(?:calendar\s+)?weeks?\S{{0,3}}\s+(?:paid|pay|leave)\b", "weeks"),
            (rf"\bsecondary\s+(?:carer|carers|care[-\s]*giver|carergiver)(?:['’`?]s)?\s+leave\b.{{0,520}}\bentitled\s+to\s+(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+calendar\s+weeks?\b.{{0,220}}\bpaid\s+leave\b", "weeks"),
            (rf"\b(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+paid\s+secondary\s+(?:carer|carers|care[-\s]*giver|carergiver)(?:['’`?]s)?\s+leave\b", "weeks"),
            (rf"\bsecondary\s+(?:carer|care[-\s]*giver|carergiver)\b.{{0,520}}\bentitled\s+to\s+(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+paid\b", "weeks"),
            (rf"\bsecondary\s+carer\b.{{0,360}}\bshall\s+be\s+paid\s+(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+of\s+such\s+leave\b", "weeks"),
            (rf"\bpartner(?:['’`?]s)?\s+leave\b.{{0,520}}\b(?:up\s+to\s+)?(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+paid\b", "weeks"),
            (rf"\b(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+paid\s+partner(?:['’`?]s)?\s+leave\b", "weeks"),
            (rf"\b(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+paid\s+leave\s*[-–]\s*for\s+secondary\s+care\s+givers\b", "weeks"),
            (rf"\bnon[-\s]+primary\s+carer\b.{{0,520}}\bentitled\s+to\s+(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\S{{0,3}}\s+paid\b", "weeks"),
            (rf"\bshort\s+parental\s+leave\b.{{0,260}}\bentitled\s+to\s+(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\S{{0,3}}\s+paid\b", "weeks"),
            (r"\bmaximum\s+of\s+(?P<value>8)\s+weeks?\s+can\s+be\s+paid\s+if\s+taken\s+concurrently\s+with\s+the\s+other\s+parent\b", "weeks"),
            (r"\bsecondary\s+care[-\s]*giver\s+more\s+than\s+12\s+months\s+service\s+(?P<value>5)\s+weeks\b", "weeks"),
            (r"\bsecondary\s+care[-\s]*giver\s+leave\s+(?P<value>10)\s+weeks\b", "weeks"),
            (rf"\bparental\s*\(\s*secondary\s+carer\s*\)\s+leave\b.{{0,1500}}\bpayment\s+representing\s+(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\S{{0,3}}\s+pay\b", "weeks"),
            (rf"\bwhere\s+an\s+employee\s+is\s+eligible\s+for\s+parental\s*\(\s*secondary\s+carer\s*\)\s+leave\b.{{0,520}}\bcouncil\s+will\s+pay\b.{{0,220}}\bpayment\s+representing\s+(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\S{{0,3}}\s+pay\b", "weeks"),
            (rf"\bpaid\s+partner\s+leave\b.{{0,240}}\bpayment\s+representing\s+(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+pay\b", "weeks"),
            (rf"\bpaternity\s+leave\s*\(\s*secondary\s+carers\s+leave\s*\).{{0,240}}\b(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\s+paid\b", "weeks"),
            (rf"\bpaid\s+component\s+of\s+(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\S{{0,3}}\s+secondary\s+carers\s+leave\b", "weeks"),
            (rf"\bpaid\s+secondary\s+carer\s+parental\s+leave\s+of\s+(?P<value>{NON_PRIMARY_PARENTAL_WEEKS})\s+weeks?\b", "weeks"),
            (r"\bparental\s+leave\s+for\s+the\s+secondary\s+carer\s+is\s+a\s+total\s+of\s+(?P<value>20)\s+days\b", "days"),
            (r"\bsecondary\s+carer\)\s+will\s+be\s+entitled\s+to\s+payment\s+equal\b.{0,220}\b(?:\w+\s*\(\s*)?(?P<value>5)\s*\)?\s+week\s+period\b", "weeks"),
            (r"\bentitlement\s+to\s+paid\s+parental\s+leave\b.{0,520}\b(?P<value>16)\s+weeks\s+paid\s+parental\s+leave\b", "weeks"),
            (r"\bpaid\s+parental\s+leave\b.{0,420}\beligible\s+employees\s+are\s+entitled\s+to\s+(?P<value>16)\s+weeks?\s+of\s+parental\s+leave\s+at\s+their\s+ordinary\s+rate\s+of\s+pay\b", "weeks"),
            (r"\bemployees\s+with\s+more\s+than\s+12\s+months\S*\s+continuous\s+employment\b.{0,220}\bentitled\s+to\s+(?P<value>16)\s+weeks?\s+paid\s+parental\s*/\s*adoption\s+leave\b", "weeks"),
        ]
        condition = "secondary/non-primary carer paid parental leave"
        subclass_id = "leave-parental-non-primary.paid-secondary-carer"
        subclass_label = "Paid Secondary/Non-Primary Carer Leave"

    for pattern, unit in patterns:
        for match in re.finditer(pattern, normalised, flags=re.I):
            local = normalised[max(0, match.start() - 180):match.end() + 180]
            if re.search(r"\bmiscarriage\b|\bsurrogacy\s+leave\b|\bpregnancy\s+terminates\b|\bpregnancy\s+ends\s+after\s+20\s+weeks\b|\bpregnancy\s+outcome\s+after\s+20\s+weeks\b|\bafter\s+20\s+weeks['’]?\s+gestation\b", local, flags=re.I):
                continue
            values.append(parental_value_record(
                match.group("value"),
                unit,
                condition,
                subclass_id,
                subclass_label,
            ))


def add_parental_week_values(values: list[dict[str, str]], normalised: str, role: str) -> None:
    if role == "primary":
        patterns = [
            r"\bprimary\s+carer\s+parental\s+leave\s+(14|16|17|18|19|20)\s+weeks?\b",
            r"\bprimary\s+caregiver\s+parental\s+leave\s*-\s*(14|16|17|18|19|20)\s+weeks?\b",
            r"\bprimary\s+care\s+giver\b.{0,220}\b(14|16|17|18|19|20)\s+weeks?\s+leave\s+at\s+full\s+pay\b",
            r"\bprimary\s+caregiver\s+leave\b.{0,260}\bpaid\s+for\s+the\s+first\s+(14|16|17|18|19|20)\s+weeks?\s+of\s+their\s+leave\b",
            r"\bpaid\s+primary\s+caregiver\s+leave\b.{0,260}\bpaid\s+for\s+the\s+first\s+(14|16|17|18|19|20)\s+weeks?\s+of\s+their\s+leave\b",
            r"\bprimary\s+carer\b.{0,420}\bshall\s+be\s+entitled\s+to\s+(14|16|17|18|19|20|26)\s+weeks?[?'’]?\s+paid\s+leave\b",
            r"\bprimary\s+carer\b.{0,420}\bentitled\s+to\s+(14|16|17|18|19|20|26)\s+weeks?[?'’]?\s+paid\s+leave\b",
            r"\bparental\s+leave\s+paid\s+entitlements\b.{0,520}\bprimary\s+carer\b.{0,520}\b(14|16|17|18|19|20|26)\s+weeks?[?'’]?\s+paid\s+leave\b",
            r"\bprimary\s+carer/maternity\s+leave\s+(14|16|17|18|19|20)\s+weeks?\b",
            r"\bprimary\s+carer(?:'?s)?\s+parental\s+leave\b.{0,220}\b(?:payment\s+of\s+)?(14|16|17|18|19|20)\s+weeks?\s+(?:full\s+)?paid\s+leave\b",
            r"\bprimary\s+carer.{0,4}s\s+parental\s+leave\b.{0,220}\breceive\s+payment\s+of\s+(14|16|17|18|19|20)\s+weeks?\s+(?:full\s+)?paid\s+leave\b",
            r"\bprimary\s+carer.{0,4}s\s+parental\s+leave\s*\(\s*(14|16|17|18|19|20)\s+weeks?\s*\)",
            r"\bprimary\s+carer\b.{0,180}\beligible\s+to\s+access\s+(14|16|17|18|19|20)\s+weeks?\b",
            r"\bprimary\s+carer\s+permanent\s+employee\s+(14|16|17|18|19|20)\s+weeks?\b",
            r"\bentitled\s+to\s+a\s+period\s+of\s+paid\s+leave\b.{0,220}\b(14|16|17|18|19|20)\s+weeks?\b",
            r"\bup\s+to\s+(14|16|17|18|19|20)\s+weeks?\s+paid\s+primary\s+carer\s+leave\b",
            r"\b(14|16|17|18|19|20)\s+weeks?\s+of\s+paid\s+primary\s+carer\s+parental\s+leave\b",
            r"\b(14|16|17|18|19|20)\s+weeks?\s+paid\s+primary\s+carer'?s\s+leave\b",
            r"\b(14|16|17|18|19|20)\s+weeks?\s+paid\s+primary\b",
            r"\b(14|16|17|18|19|20)\s+weeks?\s+if\s+they\s+are\s+the\s+primary\s+carer\b",
            r"\bprimary\s+caregiver\s+parental\s+leave\s*-\s*(14|16|17|18|19|20)\s+weeks?\s+normal\s+pay\b",
            r"\bpaid\s+parental\s+leave\b.{0,420}\bprimary\s+(?:carer|caregiver|care\s+giver)\b.{0,420}\b(14|16|17|18|19|20)\s+weeks?\b",
            r"\bprimary\s+carer\S{0,3}\s+leave\s+(14|16|17|18|19|20|26)\s+weeks?\b",
            r"\bpaid\s+entitlements?\s*[-?]\s*employer\s+funded\s+paid\s+parental\s+leave\s*\(\s*primary\s+carer\s*\)\b.{0,700}\ba\s+lump\s+sum\s+of\s+(14|16|17|18|19|20|26)\s+weeks?\S{0,3}\s+pay\b",
            r"\bparental\s+leave\s*(?:[-??])?\s*primary\s+carer\b.{0,420}\bshall\s+be\s+paid\s+for\s+the\s+first\s+(14|16|17|18|19|20|26)\s+weeks?\b",
            r"\bprimary\s+carer\b.{0,520}\bshall\s+be\s+paid\s+for\s+the\s+first\s+(14|16|17|18|19|20|26)\s+weeks?\b",
            r"\bprimary\s+carer\b.{0,520}\bpaid\s+for\s+the\s+first\s+(14|16|17|18|19|20|26)\s+weeks?\b",
            r"\bprimary\s+carer\b.{0,760}\ba\s+lump\s+sum\s+of\s+(14|16|17|18|19|20|26)\s+weeks?\S{0,3}\s+pay\b",
            r"\b(14|16|17|18|19|20|26)\s+weeks?\s+of\s+that\s+leave\s+being\s+paid\b",
            r"\bmaximum\s+of\s+(14|16|17|18|19|20|26)\s+weeks?\S{0,3}\s+leave\s+paid\s+by\s+council\b.{0,240}\bprimary\s+carer\b",
            r"\bprimary\s+carer\b.{0,520}\ba\s+lump\s+sum\s+of\s+(14|16|17|18|19|20|26)\s+weeks?[?'’]?\s+pay\b",
            r"\bwhere\s+an\s+employee\s+is\s+eligible\s+for\s+parental\s*\(\s*primary\s+carer\s*\)\s+leave\b.{0,520}\b(14|16|17|18|19|20|26)\s+weeks?[?'’]?\s+pay\b",
        ]
        patterns.extend([
            r"\bprimary\s+carer[?'â€™]s?\s+leave\s+(14|16|17|18|19|20|26)\s+weeks?\b",
            r"\bprimary\s+care[-\s]*giver\b.{0,520}\bmaximum\s+of\s+(14|16|17|18|19|20|26)\s+weeks?[?'â€™]?\s+leave\s+paid\s+by\s+council\b",
            r"\bprimary\s+carer\b.{0,520}\bmaximum\s+of\s+(14|16|17|18|19|20|26)\s+weeks?\s+paid\s+leave\b",
            r"\bemployees?\s+who\s+are\s+entitled\s+to\s+take\s+parental\s+leave\s+as\s+a\s+primary\s+carer\b.{0,520}\bmaximum\s+of\s+(14|16|17|18|19|20|26)\s+weeks?\s+paid\s+leave\b",
            r"\beligible\s+employees?\s+are\s+entitled\s+to\s+(14|16|17|18|19|20|26)\s+weeks?\s+of\s+parental\s+leave\s+at\s+their\s+ordinary\s+rate\s+of\s+pay\b",
            r"\bentitled\s+to\s+(14|16|17|18|19|20|26)\s+weeks?\s+paid\s+parental\s*/?\s*adoption\s+leave\b",
            r"\bentitled\s+to\s+(14|16|17|18|19|20|26)\s+weeks?\s+paid\s+parental\s+leave\b",
            r"\bparental\s+leave\s+paid\s+entitlements\b.{0,520}\b(14|16|17|18|19|20|26)\s+weeks?[?'â€™]?\s+paid\s+leave\b",
        ])
        for pattern in patterns:
            for match in re.finditer(pattern, normalised, flags=re.I):
                values.append(parental_value_record(
                    match.group(1),
                    "weeks",
                    "primary carer paid parental leave",
                    "leave-parental-primary.paid-primary-carer",
                    "Paid Primary Carer Leave",
                ))
    else:
        patterns = [
            r"\bsecondary\s+carer\s+parental\s+leave\s+(2|3|4|6)\s+weeks?\b",
            r"\bsecondary\s+caregiver\s+parental\s+leave\s*-\s*(2|3|4|6)\s+weeks?\b",
            r"\bsecondary\s+caregiver\s+leave\b.{0,260}\bpaid\s+for\s+the\s+first\s+(2|3|4|6)\s+weeks?\s+of\s+their\s+leave\b",
            r"\bpaid\s+secondary\s+caregiver\s+leave\b.{0,260}\bpaid\s+for\s+the\s+first\s+(2|3|4|6)\s+weeks?\s+of\s+their\s+leave\b",
            r"\bpartner\s+leave\s+as\s+secondary\s+carer\b.{0,320}\bentitled\s+to\s+(2|3|4|6)\s+weeks?[?'’]?\s+paid\s+leave\b",
            r"\bsecondary\s+carer/paternity\s+leave\s+(2|3|4|6)\s+weeks?\b",
            r"\bnon[-\s]+primary\s+carer'?s\s+leave\b.{0,180}\b(2|3|4|6)\s+weeks?\b",
            r"\b(2|3|4|6)\s+weeks?\s+paid\s+non[-\s]+primary\s+carer'?s\s+leave\b",
            r"\b(2|3|4|6)\s+weeks?\s+paid\s+non[-\s]+primary\b",
            r"\b(2|3|4|6)\s+weeks?\s+paid\s+non[-\s]+.{0,120}\bprimary\s+carer",
            r"\b(2|3|4|6)\s+weeks?\s+paid\s+secondary\s+carer'?s\s+parental\s+leave\b",
            r"\b(2|3|4|6)\s+weeks?\s+paid\s+secondary\s+carer.{0,4}s\s+parental\s+leave\b",
            r"\bsecondary\s+carer.{0,4}s\s+parental\s+leave\s*\(\s*(2|3|4|6)\s+weeks?\s*\)",
            r"\bentitled\s+to\s+(2|3|4|6)\s+weeks?\s+paid\s+secondary\s+carer\s+leave\b",
            r"\bsecondary\s+carer\s+employees\b.{0,120}\bentitled\s+to\s+(2|3|4|6)\s+weeks?\s+paid\s+parental\s+leave\b",
            r"\bsecondary\s+caregiver\s+parental\s+leave\s*-\s*(2|3|4|6)\s+weeks?\s+normal\s+pay\b",
            r"\bpaid\s+secondary\s+carer\s+leave\b.{0,160}\bmaximum\s+of\s+(2|3|4|6)\s+working\s+weeks?\b",
            r"\bpaid\s+parental\s+leave\b.{0,420}\bsecondary\s+(?:carer|caregiver|care\s+giver)\b.{0,420}\b(2|3|4|6)\s+weeks?\b",
            r"\bsecondary\s+carer\S{0,3}\s+leave\s+(2|3|4|6)\s+weeks?\b",
            r"\bsecondary\s+care[-\s]*giver\b.{0,520}\bentitled\s+to\s+a\s+maximum\s+of\s+(2|3|4|6)\s+weeks?\S{0,3}\s+leave\s+paid\s+by\s+council\b",
            r"\bemployees?\s+will\s+be\s+entitled\s+to\s+a\s+maximum\s+of\s+(2|3|4|6)\s+weeks?\S{0,3}\s+leave\s+paid\s+by\s+council\b.{0,260}\bsecondary\s+(?:carer|care[-\s]*giver)\b",
            r"\bpaid\s+entitlements?\s*[-?]\s*employer\s+funded\s+secondary\s+carer\s+leave\b.{0,700}\bentitled\s+to\s+(2|3|4|6)\s+weeks?\s+paid\s+leave\b",
            r"\bpartner\s+leave\b.{0,760}\bmaximum\s+of\s+(2|3|4|6)\s+weeks?\s+paid\s+partner\s+leave\b",
            r"\bparental\s+leave\s*(?:[-??])?\s*secondary\s+carer\b.{0,420}\bshall\s+be\s+paid\s+for\s+the\s+first\s+(2|3|4|6)\s+weeks?\b",
            r"\bsecondary\s+carer\b.{0,520}\bshall\s+be\s+paid\s+for\s+the\s+first\s+(2|3|4|6)\s+weeks?\b",
            r"\bsecondary\s+carer\b.{0,760}\bpayment\s+representing\s+(2|3|4|6)\s+weeks?\S{0,3}\s+pay\b",
            r"\bwhere\s+an\s+employee\s+is\s+eligible\s+for\s+parental\s*\(\s*secondary\s+carer\s*\)\s+leave\b.{0,520}\bpayment\s+representing\s+(2|3|4|6)\s+weeks?[?'’]?\s+pay\b",
            r"\bsecondary\s+carer\b.{0,520}\bentitled\s+to\s+(2|3|4|6)\s+weeks?\s+paid\s+leave\b",
        ]
        patterns.extend([
            r"\bsecondary\s+carer[?'â€™]s?\s+leave\s+(2|3|4|6)\s+weeks?\b",
            r"\bpartner\s+leave\b.{0,420}\bmaximum\s+of\s+(2|3|4|6)\s+weeks?\s+paid\s+partner\s+leave\b",
            r"\bpaid\s+partner\s+leave\b.{0,220}\bmaximum\s+of\s+(2|3|4|6)\s+weeks?\b",
            r"\bsecondary\s+care[-\s]*giver\b.{0,520}\bmaximum\s+of\s+(2|3|4|6)\s+weeks?[?'â€™]?\s+leave\s+paid\s+by\s+council\b",
            r"\bpartner\s+leave\b.{0,420}\b(2|3|4|6)\s+weeks?[?'â€™]?\s+paid\s+leave\b",
            r"\bsecondary\s+carer\b.{0,520}\bpayment\s+representing\s+(2|3|4|6)\s+weeks?[?'â€™]?\s+pay\b",
        ])
        for pattern in patterns:
            for match in re.finditer(pattern, normalised, flags=re.I):
                special_window = normalised[max(0, match.start() - 180):match.end() + 180]
                if re.search(r"\bspecial\s+(?:primary\s+and\s+non[-\s]+primary\s+)?caregiver\b|\bpregnancy\s+ends\s+after\s+20\s+weeks\b|\bstill[-\s]*born\b|\bneo[-\s]*natal\b", special_window, flags=re.I):
                    continue
                values.append(parental_value_record(
                    match.group(1),
                    "weeks",
                    "secondary/non-primary carer paid parental leave",
                    "leave-parental-non-primary.paid-secondary-carer",
                    "Paid Secondary/Non-Primary Carer Leave",
                ))


def add_parental_prenatal_values(values: list[dict[str, str]], normalised: str, role: str) -> None:
    if role == "primary":
        day_patterns = [
            r"\bpre[-\s]*natal\s+leave\b.{0,260}\bpregnant\b.{0,260}\bup\s+to\s+(10|5|3|2)\s+days?\b",
            r"\bpregnant\b.{0,260}\baccess\s+to\s+paid\s+leave\s+of\s+up\s+to\s+(10|5|3|2)\s+days?\b",
            r"\bemployee\s+may\s+access\s+up\s+to\s+(2)\s+days?\s+paid\s+leave\s+to\s+attend\s+medical\s+appointments\s+associated\s+with\s+the\s+pregnancy\b",
        ]
        for pattern in day_patterns:
            for match in re.finditer(pattern, normalised, flags=re.I):
                values.append(parental_value_record(
                    match.group(1),
                    "days",
                    "paid pre-natal leave for the pregnant employee",
                    "leave-parental-primary.pre-natal-paid-leave",
                    "Primary Carer Pre-Natal Paid Leave",
                ))
        hour_patterns = [
            r"\bpaid\s+pre[-\s]*natal\s+leave\s+totalling\s+up\s+to\s+(\d+(?:\.\d+)?)\s+hours?\b",
            r"\baccess\s+to\s+paid\s+leave\s+totaling\s+(\d+(?:\.\d+)?)\s+hours?\s+per\s+pregnancy\b",
            r"\bmay\s+take\s+up\s+to\s+(\d+(?:\.\d+)?)\s+hours?\s+paid\s+leave\b",
            r"\bemployee\s+is\s+entitled\s+to\s+up\s+to\s+(\d+(?:\.\d+)?)\s+hours?\s+paid\s+pre[-\s]*natal\s+leave\b",
        ]
        for pattern in hour_patterns:
            for match in re.finditer(pattern, normalised, flags=re.I):
                value, unit = hours_to_parental_signal(match.group(1), role)
                values.append(parental_value_record(
                    value,
                    unit,
                    "paid pre-natal leave for the pregnant employee",
                    "leave-parental-primary.pre-natal-paid-leave",
                    "Primary Carer Pre-Natal Paid Leave",
                ))
    else:
        day_patterns = [
            r"\bpartner\s+is\s+pregnant\b.{0,260}\bup\s+to\s+(3|1)\s+days?\s+paid\s+leave\b",
            r"\bpartner\s+who\s+is\s+pregnant\b.{0,260}\bperiod\s+equal\s+to\s+a\s+total\s+of\s+(1)\s+ordinary\s+day\b",
            r"\bpartner\s+who\s+is\s+pregnant\b.{0,260}\bpaid\s+leave\b.{0,120}\b(1)\s+ordinary\s+day\b",
            r"\bregardless\s+of\s+gender\b.{0,160}\bentitled\s+to\s+(5)\s+days?\s+paid\s+leave\s+to\s+assist\b",
        ]
        for pattern in day_patterns:
            for match in re.finditer(pattern, normalised, flags=re.I):
                values.append(parental_value_record(
                    match.group(1),
                    "day" if match.group(1) == "1" else "days",
                    "paid partner pre-natal leave",
                    "leave-parental-non-primary.partner-pre-natal-paid-leave",
                    "Partner Pre-Natal Paid Leave",
                ))
        hour_patterns = [
            r"\bpartner\s+who\s+is\s+pregnant\b.{0,260}\btotal\s+of\s+(\d+(?:\.\d+)?)\s+hours?\b",
            r"\bpartner\s+is\s+entitled\s+to\s+up\s+to\s+(\d+(?:\.\d+)?)\s+hours?\s+paid\s+pre[-\s]*natal\s+leave\b",
            r"\babout\s+to\s+become\s+a\s+parent\b.{0,180}\bmay\s+take\s+up\s+to\s+(\d+(?:\.\d+)?)\s+hours?\s+paid\s+leave\b",
            r"\bany\s+employee\s+whose\s+partner\s+is\s+pregnant\b.{0,260}\bentitled\s+to\s+(\d+(?:\.\d+)?)\s+hours?\s+leave\b",
            r"\bpartner\s+is\s+pregnant\b.{0,320}\baccess\s+to\s+paid\s+leave\s+up\s+to\s+(\d+(?:\.\d+)?)\s+hours?\b",
            r"\bpartner\s+is\s+pregnant\b.{0,320}\bwill\s+have\s+access\s+to\s+paid\s+leave\s+up\s+to\s+(\d+(?:\.\d+)?)\s+hours?\b",
        ]
        for pattern in hour_patterns:
            for match in re.finditer(pattern, normalised, flags=re.I):
                value, unit = hours_to_parental_signal(match.group(1), role)
                values.append(parental_value_record(
                    value,
                    unit,
                    "paid partner or non-primary pre-natal leave",
                    "leave-parental-non-primary.partner-pre-natal-paid-leave",
                    "Partner Pre-Natal Paid Leave",
                ))


def parental_values(profile: dict[str, Any], text: str) -> list[dict[str, str]]:
    role = profile["parental_role"]
    normalised = normalise_number_words(text)
    values: list[dict[str, str]] = []
    add_parental_week_values(values, normalised, role)
    add_parental_alias_values(values, normalised, role)
    add_parental_prenatal_values(values, normalised, role)
    values = dedupe_values(values)
    signatures = {value_signature(item["value"], item["unit"]) for item in values}
    if role == "primary" and {"16 weeks", "20 weeks"}.issubset(signatures):
        has_explicit_twenty_week_primary = bool(re.search(
            r"\b20\s+weeks?\s+paid\s+primary\b|\bprimary\s+(?:carer|care[-\s]*giver)\b.{0,260}\b20\s+weeks?\s+paid\b",
            normalised,
            flags=re.I,
        ))
        if not has_explicit_twenty_week_primary:
            values = [item for item in values if value_signature(item["value"], item["unit"]) != "20 weeks"]
    signatures = {value_signature(item["value"], item["unit"]) for item in values}
    if role != "primary":
        remove_signatures: set[str] = set()
        if {"1 weeks", "2 weeks"}.issubset(signatures):
            remove_signatures.add("1 weeks")
        if {"2 weeks", "4 weeks"}.issubset(signatures):
            remove_signatures.add("2 weeks")
        if {"10 weeks", "20 weeks"}.issubset(signatures):
            remove_signatures.add("20 weeks")
        if {"6 weeks", "15 weeks"}.issubset(signatures) and re.search(
            r"\btransition\s+from\s+secondary\s+carer\s+leave\s+to\s+parental\s+leave\b",
            normalised,
            flags=re.I,
        ):
            remove_signatures.add("15 weeks")
        if remove_signatures:
            values = [
                item for item in values
                if value_signature(item["value"], item["unit"]) not in remove_signatures
            ]
    return values


def values_for_profile(profile: dict[str, Any], text: str) -> list[dict[str, str]]:
    entitlement_id = profile["entitlement_id"]
    if entitlement_id == FAMILY_DOMESTIC_VIOLENCE_PROFILE["entitlement_id"]:
        return fdv_values(text)
    if entitlement_id == NATURAL_DISASTER_PROFILE["entitlement_id"]:
        return natural_disaster_values(text)
    if entitlement_id == COMPASSIONATE_PROFILE["entitlement_id"]:
        return compassionate_values(text)
    if entitlement_id == CULTURAL_CEREMONIAL_PROFILE["entitlement_id"]:
        return cultural_ceremonial_values(text)
    if entitlement_id == EMERGENCY_SERVICES_PROFILE["entitlement_id"]:
        return emergency_services_values(text)
    if entitlement_id in {
        PARENTAL_PRIMARY_PROFILE["entitlement_id"],
        PARENTAL_NON_PRIMARY_PROFILE["entitlement_id"],
    }:
        return parental_values(profile, text)
    raise ValueError(f"No value extractor configured for profile: {entitlement_id}")


def quantum_signals(values: list[dict[str, str]]) -> list[str]:
    signals = {
        value_signature(item["value"], item["unit"])
        for item in values
        if item.get("value") and item.get("value") not in {"available", "unquantified"}
    }
    return sorted(signals, key=lambda item: (len(item), item))


def candidate_heading(profile: dict[str, Any], text: str) -> str:
    if profile["entitlement_id"] == NATURAL_DISASTER_PROFILE["entitlement_id"]:
        heading_patterns = [
            r"\b(\d+(?:\.\d+)*\.?\s+Natural\s+Disaster\s+Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Disaster\s+And\s+Emergency\s+Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Emergency\s+Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Pressing\s+Necessity\s+Leave)\b",
            r"\b(Natural\s+Disaster\s+Leave)\b",
            r"\b(Disaster\s+And\s+Emergency\s+Leave)\b",
            r"\b(Pressing\s+Necessity\s+Leave)\b",
        ]
    elif profile["entitlement_id"] == COMPASSIONATE_PROFILE["entitlement_id"]:
        heading_patterns = [
            r"\b(\d+(?:\.\d+)*\.?\s+Compassionate\s*/\s*Bereavement\s+Leave\s+Entitlement)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Bereavement\s*/\s*Compassionate\s+Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Compassionate\s*/\s*Bereavement\s+Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Compassionate\s+Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Special\s+Bereavement\s+Leave)\b",
            r"\b(Bereavement\s*/\s*Compassionate\s+Leave)\b",
            r"\b(Compassionate\s*/\s*Bereavement\s+Leave\s+Entitlement)\b",
            r"\b(Compassionate\s+Leave)\b",
            r"\b(Special\s+Bereavement\s+Leave)\b",
        ]
    elif profile["entitlement_id"] == CULTURAL_CEREMONIAL_PROFILE["entitlement_id"]:
        heading_patterns = [
            r"\b(\d+(?:\.\d+)*\.?\s+Cultural\s+And\s+Ceremonial\s+Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Cultural\s+Or\s+Ceremonial\s+Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Cultural\s*/\s*Ceremonial\s+Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Ceremonial\s*/\s*Cultural\s+Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Sorry\s+Business\s+Leave)\b",
            r"\b(Cultural\s+And\s+Ceremonial\s+Leave)\b",
            r"\b(Cultural\s+Or\s+Ceremonial\s+Leave)\b",
            r"\b(Cultural\s*/\s*Ceremonial\s+Leave)\b",
            r"\b(Ceremonial\s*/\s*Cultural\s+Leave)\b",
            r"\b(Sorry\s+Business\s+Leave)\b",
        ]
    elif profile["entitlement_id"] == EMERGENCY_SERVICES_PROFILE["entitlement_id"]:
        heading_patterns = [
            r"\b(\d+(?:\.\d+)*\.?\s+Emergency\s+Services?\s+Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Community\s+Services?\s+Leave.{0,12}Emergency\s+Services?)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Community\s+Service\s+Leave)\b",
            r"\b(Emergency\s+Services?\s+Leave)\b",
            r"\b(Community\s+Services?\s+Leave.{0,12}Emergency\s+Services?)\b",
            r"\b(Community\s+Service\s+Leave)\b",
        ]
    elif profile["entitlement_id"] in {
        PARENTAL_PRIMARY_PROFILE["entitlement_id"],
        PARENTAL_NON_PRIMARY_PROFILE["entitlement_id"],
    }:
        heading_patterns = [
            r"\b(\d+(?:\.\d+)*\.?\s+Paid\s+Parental\s+Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Parental\s+Leave\s+[–-]\s+Council\s+Component)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Primary\s+(?:Carer|Caregiver)(?:'?s)?\s+(?:Parental\s+)?Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Secondary\s+(?:Carer|Caregiver)(?:'?s)?\s+(?:Parental\s+)?Leave)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Pre[-\s]*Natal\s+Leave)\b",
            r"\b(Paid\s+Parental\s+Leave)\b",
            r"\b(Parental\s+Leave\s+[–-]\s+Council\s+Component)\b",
            r"\b(Pre[-\s]*Natal\s+Leave)\b",
        ]
    else:
        heading_patterns = [
            r"\b(\d+(?:\.\d+)*\.?\s+Family\s+(?:and\s+Domestic\s+)?Violence(?:\s+Leave|\s+Support)?)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Domestic\s*/\s*Family\s+Violence)\b",
            r"\b(\d+(?:\.\d+)*\.?\s+Special\s+Compassionate\s+Leave)\b",
            r"\b(Family\s+(?:and\s+Domestic\s+)?Violence(?:\s+Leave|\s+Support)?)\b",
            r"\b(Domestic\s*/\s*Family\s+Violence)\b",
        ]
    for pattern in heading_patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return compact_text(match.group(1))
    return ""


def best_source_page(profile: dict[str, Any], page: int, page_text: str, next_text: str, values: list[dict[str, str]]) -> int:
    if not values:
        return page
    current_values = values_for_profile(profile, page_text)
    if any(item.get("benchmark_value") == "true" for item in current_values):
        return page
    next_values = values_for_profile(profile, next_text)
    if any(item.get("benchmark_value") == "true" for item in next_values):
        return page + 1
    return page


def first_match(profile: dict[str, Any], text: str) -> tuple[str, re.Match[str]] | None:
    matches: list[tuple[int, str, re.Match[str]]] = []
    for label, pattern in profile["candidate_patterns"]:
        match = pattern.search(text)
        if match:
            matches.append((match.start(), label, match))
    if not matches:
        return None
    _, label, match = sorted(matches, key=lambda item: item[0])[0]
    return label, match


def excerpt_around(text: str, match: re.Match[str], *, before: int = 500, after: int = 4500) -> str:
    start = max(0, match.start() - before)
    end = min(len(text), match.end() + after)
    return compact_text(text[start:end])


def page_candidates(profile: dict[str, Any], agreement_id: str) -> list[ProfileCandidate]:
    pages = load_pages(agreement_id)
    candidates: list[ProfileCandidate] = []
    lookahead_pages = int(profile.get("lookahead_pages") or 1)
    for index, page_text in enumerate(pages, start=1):
        match_result = first_match(profile, page_text)
        if not match_result:
            continue
        label, match = match_result
        next_text = pages[index] if index < len(pages) else ""
        combined_pages = pages[index - 1:min(len(pages), index + lookahead_pages)]
        combined = compact_text("\n".join(combined_pages))
        excerpt = excerpt_around(combined, match)
        positive_labels = first_pattern_labels(profile["positive_patterns"], excerpt)
        out_of_scope = first_pattern_labels(profile["out_of_scope_patterns"], excerpt)
        if is_probable_table_of_contents(excerpt):
            out_of_scope.append("table_of_contents")
        out_of_scope = sorted(set(out_of_scope))
        values = values_for_profile(profile, excerpt)
        if profile["entitlement_id"] == NATURAL_DISASTER_PROFILE["entitlement_id"] and values:
            # Adjacent clauses often follow the disaster clause on the same extracted page.
            # Keep true disaster values while still blocking pure adjacent-clause hits.
            out_of_scope = [
                label
                for label in out_of_scope
                if label not in {"carers_unexpected_emergency", "emergency_services_volunteer"}
            ]
        if profile["entitlement_id"] == COMPASSIONATE_PROFILE["entitlement_id"] and values:
            # Compassionate clauses often state paid permanent entitlements beside unpaid casual notes.
            out_of_scope = [
                label
                for label in out_of_scope
                if label not in {"unpaid_only", "annual_or_long_service_recredit"}
            ]
        if profile["entitlement_id"] == EMERGENCY_SERVICES_PROFILE["entitlement_id"] and values:
            # Community-service clauses often bundle emergency, jury, volunteer, and disaster leave together.
            out_of_scope = [
                label
                for label in out_of_scope
                if label not in {
                    "natural_disaster_employee_impact",
                    "jury_or_court_service",
                    "defence_or_armed_forces",
                    "blood_or_general_volunteer",
                }
            ]
        if profile["entitlement_id"] in {
            PARENTAL_PRIMARY_PROFILE["entitlement_id"],
            PARENTAL_NON_PRIMARY_PROFILE["entitlement_id"],
        } and values:
            # Parental tables commonly run into unpaid/special-loss subclauses on adjacent pages.
            # Once a role-specific value is extracted, keep the row and retain the noisy pages below.
            out_of_scope = [
                label
                for label in out_of_scope
                if label not in {
                    "special_caregiver_or_loss_leave",
                    "unpaid_parental_leave_only",
                    "safe_job_or_return_to_work",
                    "surrogacy_only",
                }
            ]
        has_benchmark_value = any(item.get("benchmark_value") == "true" for item in values)
        has_source_value = bool(values)
        context_patterns = profile.get("context_patterns")
        if context_patterns:
            has_profile_section = bool(first_pattern_labels(context_patterns, excerpt))
        else:
            has_profile_section = bool(re.search(r"\bfamily\s+(?:and\s+domestic\s+)?violence\b|\bdomestic\s*/\s*family\s+violence\b", excerpt, flags=re.I))
        candidate_type = (
            "source_clause_match"
            if has_profile_section and has_source_value and not out_of_scope
            else "out_of_scope_or_context_match"
        )
        score = (
            (20 if has_benchmark_value else 0)
            + (8 if has_source_value else 0)
            + (8 * len(positive_labels))
            + (4 if has_profile_section else 0)
            - (20 * len(out_of_scope))
        )
        candidates.append(ProfileCandidate(
            page=index,
            source_page=best_source_page(profile, index, page_text, next_text, values),
            candidate_type=candidate_type,
            matched_terms=sorted({label, *positive_labels}),
            out_of_scope_signals=out_of_scope,
            score=score,
            heading=candidate_heading(profile, excerpt),
            excerpt=excerpt,
            clause_text=excerpt,
            quantum_signals=quantum_signals(values),
            normalised_values=values,
        ))
    return sorted(candidates, key=lambda item: (item.candidate_type == "source_clause_match", item.score, -item.page), reverse=True)


def benchmark_values(values: list[dict[str, str]]) -> set[str]:
    return {
        value_signature(item["value"], item["unit"])
        for item in values
        if item.get("benchmark_value") == "true"
    }


def reference_entitlement(profile: dict[str, Any], exemplar_path: Path = DEFAULT_EXEMPLAR_PATH) -> dict[str, Any]:
    exemplar = read_json(exemplar_path)
    entitlement_id = profile["entitlement_id"]
    for category in exemplar.get("categories") or []:
        for entitlement in category.get("entitlements") or []:
            if entitlement.get("entitlement_id") == entitlement_id:
                return entitlement
    raise ValueError(f"Reference entitlement not found: {entitlement_id}")


def reference_entries_by_council(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entitlement = reference_entitlement(profile)
    entries = (
        entitlement.get("semantic_mapping", {})
        .get("comparator_semantics", {})
        .get("entries", [])
    )
    return {str(entry.get("council")): entry for entry in entries}


def compare_to_reference(reference_entry: dict[str, Any] | None, values: list[dict[str, str]]) -> dict[str, Any]:
    expected = set(reference_entry.get("quantum_signals") or []) if reference_entry else set()
    observed = benchmark_values(values)
    if not reference_entry:
        status = "no_reference_entry"
    elif not expected and observed:
        status = "source_value_without_reference_quantum"
    elif expected and not observed:
        status = "reference_value_not_source_backed"
    elif expected.issubset(observed):
        status = "reference_values_matched"
    elif expected.intersection(observed):
        status = "reference_values_partially_matched"
    else:
        status = "reference_values_conflict"
    return {
        "status": status,
        "reference_finding": reference_entry.get("finding") if reference_entry else "",
        "reference_quantum_signals": sorted(expected),
        "source_quantum_signals": sorted(observed),
        "missing_reference_quantum_signals": sorted(expected - observed),
        "extra_source_quantum_signals": sorted(observed - expected),
    }


def preferred_source_candidate(profile: dict[str, Any], candidates: list[ProfileCandidate]) -> ProfileCandidate | None:
    if not candidates:
        return None
    preferred_subclasses: list[str] = []
    if profile["entitlement_id"] == PARENTAL_PRIMARY_PROFILE["entitlement_id"]:
        preferred_subclasses = ["leave-parental-primary.paid-primary-carer"]
    elif profile["entitlement_id"] == PARENTAL_NON_PRIMARY_PROFILE["entitlement_id"]:
        preferred_subclasses = ["leave-parental-non-primary.paid-secondary-carer"]
    for subclass_id in preferred_subclasses:
        for candidate in candidates:
            if any(value.get("subclass_id") == subclass_id for value in candidate.normalised_values):
                return candidate
    return candidates[0]


def source_values_for_record(profile: dict[str, Any], candidates: list[ProfileCandidate]) -> list[dict[str, str]]:
    if not candidates:
        return []
    if not profile.get("merge_source_candidates"):
        return candidates[0].normalised_values
    return dedupe_values([
        value
        for candidate in candidates
        for value in candidate.normalised_values
    ])


def source_excerpts_for_record(
    profile: dict[str, Any],
    candidates: list[ProfileCandidate],
    preferred: ProfileCandidate,
    agreement_id: str,
) -> list[dict[str, Any]]:
    if not profile.get("merge_source_candidates"):
        return [candidate_dict(profile, preferred, agreement_id)]
    ordered = [preferred] + [
        candidate
        for candidate in candidates
        if candidate != preferred and candidate.normalised_values
    ]
    return [candidate_dict(profile, candidate, agreement_id) for candidate in ordered[:6]]


def finding_for_values(
    profile: dict[str, Any],
    candidate: ProfileCandidate | None,
    values: list[dict[str, str]] | None = None,
) -> str:
    if candidate is None:
        return f"No source clause matched the {profile['label'].lower()} profile in cached text."
    values = candidate.normalised_values if values is None else values
    benchmark = [
        item
        for item in values
        if item.get("benchmark_value") == "true"
    ]
    if benchmark:
        return "; ".join(
            f"{item['value']} {item['unit']} for {item['condition']}"
            for item in benchmark
        )
    if any(item.get("subclass_id") == "leave-cultural-ceremonial.existing-or-unpaid-leave" for item in values):
        return "Source clause provides cultural or ceremonial observance support through existing accrued leave or unpaid leave, but no paid benchmark value."
    if any(item.get("subclass_id") == "leave-emergency-services.paid-unquantified" for item in values):
        return "Source clause provides paid emergency services leave support, but does not state a quantified benchmark value."
    if profile["entitlement_id"] == NATURAL_DISASTER_PROFILE["entitlement_id"] and values:
        return "Source clause provides natural-disaster or emergency leave support, but does not state a quantified benchmark value."
    if any(item.get("subclass_label") == "Unquantified Paid Leave Or Flexibility" for item in values):
        return "Source clause provides paid leave or flexibility for family violence, but does not state a quantified leave value."
    return f"Source {profile['label'].lower()} clause observed, but the benchmark value needs reviewer normalisation."


def candidate_dict(profile: dict[str, Any], candidate: ProfileCandidate, agreement_id: str) -> dict[str, Any]:
    return {
        "page": candidate.page,
        "page_label": f"p.{candidate.page}",
        "source_page": candidate.source_page,
        "source_page_label": f"p.{candidate.source_page}",
        "candidate_type": candidate.candidate_type,
        "matched_terms": candidate.matched_terms,
        "out_of_scope_signals": candidate.out_of_scope_signals,
        "score": candidate.score,
        "heading": candidate.heading,
        "clause_label": candidate.heading or profile["label"],
        "excerpt": candidate.excerpt,
        "clause_text": candidate.clause_text,
        "quantum_signals": candidate.quantum_signals,
        "normalised_values": candidate.normalised_values,
        "source_ref": source_ref(
            agreement_id,
            candidate.source_page,
            evidence_state=candidate.candidate_type,
            heading=candidate.heading,
        ),
    }


def evidence_record(profile: dict[str, Any], council: str, agreement_id: str, reference_entries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    candidates = page_candidates(profile, agreement_id)
    source_candidates = [candidate for candidate in candidates if candidate.candidate_type == "source_clause_match"]
    best = preferred_source_candidate(profile, source_candidates)
    reference_entry = reference_entries.get(council)
    values = source_values_for_record(profile, source_candidates)
    comparison = compare_to_reference(reference_entry, values)
    if best:
        confidence = 0.84 if comparison["status"] == "reference_values_matched" else 0.7
        support_status = "source_clause_supported"
        presence = "source_clause_observed"
        ref = source_ref(agreement_id, best.source_page, evidence_state="source_clause_observed", heading=best.heading)
        source_excerpts = source_excerpts_for_record(profile, source_candidates, best, agreement_id)
    else:
        confidence = 0.45
        support_status = "source_search_no_positive_match"
        presence = "no_source_clause_match"
        fallback = candidates[0] if candidates else None
        ref = source_ref(
            agreement_id,
            fallback.source_page if fallback else None,
            evidence_state="source_search_no_positive_match",
            heading=fallback.heading if fallback else "",
        )
        source_excerpts = []
    return {
        "council": council,
        "agreement_id": agreement_id,
        "agreement_name": agreement_name(agreement_id),
        "page_count": len(load_pages(agreement_id)),
        "candidate_page_count": len(candidates),
        "source_clause_page_count": len(source_candidates),
        "out_of_scope_candidate_page_count": len(candidates) - len(source_candidates),
        "presence": presence,
        "finding": finding_for_values(profile, best, values),
        "quantum_signals": quantum_signals(values),
        "normalised_values": values,
        "reference_comparison": comparison,
        "confidence": confidence,
        "support_status": support_status,
        "source_ref": ref,
        "source_excerpts": source_excerpts,
        "candidate_pages": [candidate_dict(profile, candidate, agreement_id) for candidate in candidates[:10]],
    }


def build_rows(profile: dict[str, Any], agreements: list[dict[str, str]]) -> list[dict[str, Any]]:
    reference_entries = reference_entries_by_council(profile)
    return [
        evidence_record(profile, row["council"], row["agreement_id"], reference_entries)
        for row in agreements
    ]


def summary_for_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    presence_counts = Counter(row["presence"] for row in rows)
    support_counts = Counter(row["support_status"] for row in rows)
    comparison_counts = Counter(row["reference_comparison"]["status"] for row in rows)
    source_backed_rows = presence_counts.get("source_clause_observed", 0)
    source_quantum_rows = sum(
        1
        for row in rows
        if (row.get("reference_comparison") or {}).get("source_quantum_signals")
    )
    value_matched_rows = comparison_counts.get("reference_values_matched", 0)
    partial_rows = comparison_counts.get("reference_values_partially_matched", 0)
    return {
        "councils": len(rows),
        "total_pages_scanned": sum(int(row.get("page_count") or 0) for row in rows),
        "candidate_pages_found": sum(int(row.get("candidate_page_count") or 0) for row in rows),
        "source_clause_pages": sum(int(row.get("source_clause_page_count") or 0) for row in rows),
        "normalised_values_extracted": sum(len(row.get("normalised_values") or []) for row in rows),
        "presence_counts": dict(sorted(presence_counts.items())),
        "support_status_counts": dict(sorted(support_counts.items())),
        "reference_comparison_counts": dict(sorted(comparison_counts.items())),
        "source_clause_observed": source_backed_rows,
        "source_quantum_observed_rows": source_quantum_rows,
        "reference_value_matched_rows": value_matched_rows,
        "reference_value_partial_rows": partial_rows,
        "reference_value_unmatched_rows": len(rows) - value_matched_rows - partial_rows,
        "row_source_backed_percent": round((source_backed_rows / len(rows)) * 100, 1) if rows else 0,
        "source_quantum_observed_percent": round((source_quantum_rows / len(rows)) * 100, 1) if rows else 0,
        "reference_value_match_percent": round((value_matched_rows / len(rows)) * 100, 1) if rows else 0,
    }


def global_takeaway(profile: dict[str, Any], rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    mismatches = [
        row
        for row in rows
        if row["reference_comparison"]["status"] != "reference_values_matched"
    ]
    mismatch_text = "; ".join(
        f"{row['council']}: {row['reference_comparison']['status'].replace('_', ' ')}"
        for row in mismatches
    )
    suffix = f" Remaining review points: {mismatch_text}." if mismatch_text else ""
    return (
        f"Across the Ballarat comparator cohort, {profile['label']} is source-backed in "
        f"{summary['source_clause_observed']} of {summary['councils']} councils. "
        f"The profile fully recreates the reference quantums for {summary['reference_value_matched_rows']} councils "
        f"and preserves source-backed differences where the reference numbers are not visible in the cached clauses."
        f"{suffix}"
    )


def hit_discovery_method(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "unit_of_analysis": "cached agreement page text from cache/<agreement_id>/pages.json",
        "pipeline": profile.get("hit_discovery_pipeline") or [
            "Resolve each comparator council to its latest known canonical agreement, then load cached page text for that agreement.",
            "Find family/domestic violence candidate pages and combine adjacent page text where the clause spans a page break.",
            "Reject table-of-contents, parental-leave continuity, gender-equality reporting, and specialist-context noise.",
            "Accept source clauses that provide quantified paid FDV leave or unquantified paid leave/flexibility.",
            "Extract benchmark values only when the source clause states a paid FDV quantum for the employee or a separately quantified support-person entitlement.",
            "Compare extracted source values with the reference exemplar values and preserve differences as reviewable reasoning.",
        ],
        "candidate_patterns": labelled_patterns(profile["candidate_patterns"]),
        "positive_patterns": labelled_patterns(profile["positive_patterns"]),
        "out_of_scope_patterns": labelled_patterns(profile["out_of_scope_patterns"]),
        "classification_boundary": profile["classification_boundary"],
        "accepted_subclasses": profile["accepted_subclasses"],
        "adjacent_subclasses": profile["adjacent_subclasses"],
        "acceptance_rule": profile.get("acceptance_rule") or "family/domestic violence clause + quantified paid leave value or explicit paid leave/flexibility + no blocker",
        "absence_rule": "No positive match means source-search absence, not final legal absence.",
        "reference_reconciliation_rule": "Reference numbers are matched only when the cached source clause states the same quantum; otherwise the artifact records missing reference values or partial matches.",
    }


def statistical_calibration_for_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_clause_observed": calibrate_binary_metric_groups(
            summary,
            {},
            metric="source_clause_observed",
            metric_label="council rows with a source-backed clause",
        ),
        "source_quantum_observed": calibrate_binary_metric_groups(
            summary,
            {},
            metric="source_quantum_observed_rows",
            metric_label="council rows with a source-backed quantum",
        ),
        "reference_value_matched": calibrate_binary_metric_groups(
            summary,
            {},
            metric="reference_value_matched_rows",
            metric_label="council rows whose source quantum matches the reference",
        ),
    }


def build_payload(
    profile: dict[str, Any],
    *,
    generated_at: str,
    agreements: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    selected_agreements = agreements or BASELINE_COMPARATOR_AGREEMENTS
    rows = build_rows(profile, selected_agreements)
    summary = summary_for_rows(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": profile["artifact_id"],
        "artifact_type": "entitlement_clause_evidence",
        "wiki_role": "source_clause_evidence",
        "generated_at": generated_at,
        "scope_focus": "standard_employees",
        "cohort_scope": profile["scope"],
        "entitlement_id": profile["entitlement_id"],
        "label": profile["label"],
        "definition": profile["definition"],
        "global_takeaway": global_takeaway(profile, rows, summary),
        "taxonomy_path": profile["taxonomy_path"],
        "classification_boundary": profile["classification_boundary"],
        "accepted_subclasses": profile["accepted_subclasses"],
        "adjacent_subclasses": profile["adjacent_subclasses"],
        "methodology": {
            "method": "profiled_source_clause_search",
            "search_terms": profile["search_terms"],
            "hit_discovery_method": hit_discovery_method(profile),
        },
        "comparator_set": [
            {
                "council": row["council"],
                "agreement_id": row["agreement_id"],
                "agreement_name": agreement_name(row["agreement_id"]),
                "resolved_from_agreement_id": row.get("resolved_from_agreement_id", row["agreement_id"]),
                "latest_resolution": row.get("latest_resolution", "supplied_agreement_id"),
                "cohort": "A_reference_comparator_seed",
            }
            for row in selected_agreements
        ],
        "summary": summary,
        "statistical_calibration": statistical_calibration_for_summary(summary),
        "council_evidence": rows,
    }


def markdown_for_payload(payload: dict[str, Any]) -> str:
    source_clause_calibration = payload["statistical_calibration"]["source_clause_observed"]["baseline"]
    source_quantum_calibration = payload["statistical_calibration"]["source_quantum_observed"]["baseline"]
    lines = [
        f"# {payload['label']} Clause Evidence",
        "",
        payload["definition"],
        "",
        "## Method",
        "",
        payload["methodology"]["hit_discovery_method"]["acceptance_rule"],
        "",
        "## Summary",
        "",
        f"- Councils: {payload['summary']['councils']}",
        f"- Source-backed rows: {payload['summary']['source_clause_observed']} ({payload['summary']['row_source_backed_percent']}%)",
        f"- Reference value matches: {payload['summary']['reference_value_matched_rows']} ({payload['summary']['reference_value_match_percent']}%)",
        f"- Partial reference matches: {payload['summary']['reference_value_partial_rows']}",
        f"- Normalised values extracted: {payload['summary']['normalised_values_extracted']}",
        "",
        "## Statistical Calibration",
        "",
        f"- Source-clause prevalence posterior mean: {source_clause_calibration['posterior_mean_percent']}% from {source_clause_calibration['observed_count']}/{source_clause_calibration['sample_size']} A-cohort rows.",
        f"- Source-quantum prevalence posterior mean: {source_quantum_calibration['posterior_mean_percent']}% from {source_quantum_calibration['observed_count']}/{source_quantum_calibration['sample_size']} A-cohort rows.",
        "",
        "## Takeaway",
        "",
        payload["global_takeaway"],
        "",
        "## Council Evidence",
        "",
    ]
    for row in payload["council_evidence"]:
        ref = row["source_ref"]
        page = f" p.{ref.get('page')}" if ref.get("page") else ""
        status = row["reference_comparison"]["status"]
        lines.append(f"- {row['council']}: {row['presence']} ({row['agreement_id'].upper()}{page}) - {status} - {row['finding']}")
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
    parser = argparse.ArgumentParser(description="Build source-clause evidence for standard-employee entitlement profiles.")
    parser.add_argument(
        "--profile",
        default="fdv",
        choices=sorted(PROFILES),
        help="Profile to build.",
    )
    parser.add_argument(
        "--all-cached",
        action="store_true",
        help="Process every agreement with cached page text instead of the 10-council reference comparator.",
    )
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
        help="Process only agreements supplied with --agreement.",
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
        help="Optional suffix for ad hoc artifact ids.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = dict(PROFILES[args.profile])
    supplied_agreements = list(args.agreement or [])
    if args.only_agreements:
        agreements = supplied_agreements
    elif args.all_cached:
        agreements = [*all_cached_agreements(), *supplied_agreements]
        if not args.artifact_suffix:
            profile["artifact_id"] = f"{profile['artifact_id']}-all-cached"
    else:
        agreements = [*BASELINE_COMPARATOR_AGREEMENTS, *supplied_agreements]
    if args.artifact_suffix:
        suffix = re.sub(r"[^a-z0-9-]+", "-", args.artifact_suffix.strip().lower()).strip("-")
        if suffix:
            profile["artifact_id"] = f"{profile['artifact_id']}-{suffix}"

    payload = build_payload(profile, generated_at=utc_now_iso(), agreements=agreements)
    artifact_dir = args.output_dir
    write_json(artifact_dir / f"{payload['artifact_id']}.json", payload)
    (artifact_dir / f"{payload['artifact_id']}.md").write_text(markdown_for_payload(payload), encoding="utf-8")
    print(json.dumps({
        "schema_version": "wiki.entitlement_clause_evidence_build.v1",
        "generated_at": payload["generated_at"],
        "artifact_id": payload["artifact_id"],
        "artifact_path": str(artifact_dir / f"{payload['artifact_id']}.json"),
        "summary": payload["summary"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
