"""Canonical schema for non-wage EBA conditions and benefits.

Item 1 in the bargaining comparison model is already represented by
pay_tables/uplift_rules. This schema covers the remaining quantifiable
conditions and benefits while preserving clause-level provenance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional


CURRENT_CONDITIONS_SCHEMA_VERSION = "conditions_v1"

STANDARD_EMPLOYEE_SCOPE = "standard_general_employees"

EXCLUDED_SPECIALISED_COHORTS: tuple[str, ...] = (
    "maternal_and_child_health_nurses",
    "immunisation_nurses",
    "pool_services_employees",
    "child_care_early_years_employees",
    "library_specific_employees",
    "tourism_visitor_services_employees",
    "senior_officers",
    "apprentices_trainees_cadets",
    "school_crossing_supervisors",
    "aged_disability_home_care_specific_employees",
)

ConditionCategory = Literal[
    "overtime_penalties_rosters",
    "allowances_reimbursements",
    "paid_parental_family_leave",
    "redundancy_redeployment",
    "superannuation",
    "annual_leave_loading",
    "personal_carers_sick_leave",
    "long_service_leave",
    "family_domestic_violence_leave",
    "study_professional_development",
    "other_conditions_benefits",
]

BIG_TICKET_CONDITION_CATEGORIES: tuple[ConditionCategory, ...] = (
    "overtime_penalties_rosters",
    "allowances_reimbursements",
    "paid_parental_family_leave",
    "redundancy_redeployment",
)

BENEFIT_CONDITION_CATEGORIES: tuple[ConditionCategory, ...] = (
    *BIG_TICKET_CONDITION_CATEGORIES,
    "superannuation",
    "annual_leave_loading",
    "personal_carers_sick_leave",
    "long_service_leave",
    "family_domestic_violence_leave",
    "study_professional_development",
    "other_conditions_benefits",
)

ClauseSourceKind = Literal[
    "agreement_clause",
    "schedule",
    "appendix",
    "incorporated_award",
    "fwc_undertaking",
    "derived_note",
    "unknown",
]

ValueType = Literal[
    "money",
    "percentage",
    "multiplier",
    "hours",
    "days",
    "weeks",
    "months",
    "years",
    "boolean",
    "text",
    "formula",
]

ValueBasis = Literal[
    "per_hour",
    "per_day",
    "per_week",
    "per_fortnight",
    "per_annum",
    "per_kilometre",
    "per_shift",
    "per_incident",
    "ordinary_time",
    "base_rate",
    "weekly_rate",
    "annual_rate",
    "not_applicable",
    "unknown",
]

QuantifierRole = Literal[
    "entitlement",
    "cap",
    "floor",
    "threshold",
    "rate",
    "loading",
    "minimum_payment",
    "notice",
    "eligibility",
    "indexation",
    "offset",
    "unknown",
]

CouncilApplicabilityMode = Literal[
    "all_covered_councils",
    "named_councils_only",
    "excluded_named_councils",
    "single_council",
    "unknown",
]


@dataclass(frozen=True)
class CategoryDefinition:
    """Human and machine contract for one incoming condition category."""

    category: ConditionCategory
    definition: str
    include_when: str
    exclude_when: str
    required_comparison_keys: tuple[str, ...]
    allowed_value_types: tuple[ValueType, ...]
    required_clause: bool = True


@dataclass(frozen=True)
class CouncilApplicability:
    """Council/employer applicability for single and split agreements."""

    mode: CouncilApplicabilityMode = "unknown"
    applies_to_councils: tuple[str, ...] = ()
    excluded_councils: tuple[str, ...] = ()
    source_clause_ids: tuple[str, ...] = ()
    notes: str = ""


CONDITION_CATEGORY_DEFINITIONS: dict[ConditionCategory, CategoryDefinition] = {
    "overtime_penalties_rosters": CategoryDefinition(
        category="overtime_penalties_rosters",
        definition=(
            "Rules that change payment or time-off treatment when standard/general employees work "
            "outside ordinary hours, outside the span of hours, on weekends/public holidays, on call, "
            "call-back, standby, or under RDO/TOIL arrangements."
        ),
        include_when=(
            "The clause applies to all employees or the ordinary indoor/outdoor/general workforce and "
            "contains rates, multipliers, minimum payments, banking rules, caps, or ordinary-hours spans."
        ),
        exclude_when="The clause applies only to a specialised cohort or only restates an incorporated award with no agreement-specific term.",
        required_comparison_keys=(
            "weekday_overtime_first_rate",
            "weekday_overtime_after_rate",
            "public_holiday_rate",
            "minimum_call_back_hours",
            "toil_conversion_basis",
            "rdo_bank_cap",
        ),
        allowed_value_types=("multiplier", "hours", "days", "weeks", "text", "formula"),
    ),
    "allowances_reimbursements": CategoryDefinition(
        category="allowances_reimbursements",
        definition=(
            "Monetary allowances, loadings, reimbursements, expense payments, or in-kind benefits "
            "available to standard/general employees in addition to base salary."
        ),
        include_when="The clause gives a dollar amount, percentage, formula, reimbursement rule, indexation rule, or eligibility threshold.",
        exclude_when="The allowance is limited to a specialised cohort, specific appendix workforce, or a non-standard classification only.",
        required_comparison_keys=(
            "meal_allowance_amount",
            "first_aid_allowance_amount",
            "vehicle_km_rate",
            "on_call_allowance_amount",
            "availability_allowance_amount",
            "higher_duties_basis",
            "allowance_indexation_basis",
        ),
        allowed_value_types=("money", "percentage", "hours", "text", "formula"),
    ),
    "paid_parental_family_leave": CategoryDefinition(
        category="paid_parental_family_leave",
        definition=(
            "Paid and unpaid parental, partner/secondary-carer, adoption, surrogacy, prenatal, "
            "stillbirth/neonatal death, return-to-work, and additional family-carer leave for "
            "standard/general employees."
        ),
        include_when="The clause sets paid weeks/days/hours, payment options, eligibility, concurrent leave, or superannuation treatment.",
        exclude_when="The clause only applies to a specialised cohort or only repeats the NES without an agreement-specific benefit.",
        required_comparison_keys=(
            "primary_carer_paid_weeks",
            "secondary_carer_paid_weeks",
            "half_pay_available",
            "prenatal_paid_hours",
            "additional_carer_paid_days",
            "super_on_paid_parental_leave",
        ),
        allowed_value_types=("weeks", "days", "hours", "boolean", "text", "formula"),
    ),
    "redundancy_redeployment": CategoryDefinition(
        category="redundancy_redeployment",
        definition=(
            "Redundancy, redeployment, retraining, salary maintenance, notice, severance, "
            "outplacement, job-search leave, and related termination support for standard/general employees."
        ),
        include_when="The clause sets notice periods, severance formulas, caps, lump sums, trial periods, or support dollar limits.",
        exclude_when="The clause concerns fixed-term/senior officer/special project termination only and does not apply generally.",
        required_comparison_keys=(
            "notice_weeks_by_service",
            "age_notice_extra_weeks",
            "severance_weeks_per_year",
            "max_severance_weeks",
            "redundancy_lump_sum",
            "salary_maintenance_months",
            "outplacement_support_cap",
            "redeployment_trial_months",
        ),
        allowed_value_types=("money", "weeks", "months", "years", "days", "text", "formula"),
    ),
    "superannuation": CategoryDefinition(
        category="superannuation",
        definition=(
            "Employer superannuation obligations or benefits beyond base pay, including contribution "
            "rates, choice fund rules, salary sacrifice, and super paid during leave or absences."
        ),
        include_when="The clause states contribution percentages, extra employer contributions, salary sacrifice, or super on paid/unpaid leave.",
        exclude_when="The clause only names a fund without a quantifiable or materially comparable entitlement.",
        required_comparison_keys=(
            "employer_contribution_rate",
            "additional_employer_contribution_rate",
            "super_on_paid_parental_leave",
            "super_on_unpaid_parental_leave",
            "super_on_workers_comp_weeks",
        ),
        allowed_value_types=("percentage", "weeks", "boolean", "text", "formula"),
    ),
    "annual_leave_loading": CategoryDefinition(
        category="annual_leave_loading",
        definition=(
            "Annual leave, annual leave loading, cashing out, directed leave, excessive accruals, "
            "additional leave, and shiftworker annual leave for standard/general employees."
        ),
        include_when="The clause states days/weeks/hours of leave, loading percentage, cash-out rules, or accrual thresholds.",
        exclude_when="The clause only restates the NES with no agreement-specific value.",
        required_comparison_keys=(
            "annual_leave_weeks",
            "leave_loading_rate",
            "max_accrual_threshold",
            "cash_out_allowed",
            "additional_shiftworker_leave_days",
        ),
        allowed_value_types=("weeks", "days", "hours", "percentage", "boolean", "text", "formula"),
    ),
    "personal_carers_sick_leave": CategoryDefinition(
        category="personal_carers_sick_leave",
        definition=(
            "Personal, sick, carer's, compassionate, bereavement, pressing necessity, and leave "
            "donation/pooling arrangements for standard/general employees."
        ),
        include_when="The clause states annual accruals, transferable balances, evidence-free days, donated leave, or advance leave.",
        exclude_when="The clause is cohort-only or contains no agreement-specific entitlement.",
        required_comparison_keys=(
            "personal_leave_days_per_year",
            "evidence_free_days",
            "transferable_sick_leave_days",
            "compassionate_leave_days",
            "leave_donation_available",
        ),
        allowed_value_types=("days", "hours", "weeks", "boolean", "text", "formula"),
    ),
    "long_service_leave": CategoryDefinition(
        category="long_service_leave",
        definition="Long service leave accrual, access, portability, pro-rata payment, and transfer rules for standard/general employees.",
        include_when="The clause improves on, clarifies, or quantifies LSL access, accrual, portability, or redundancy payment treatment.",
        exclude_when="The clause only points to legislation and gives no comparable agreement-specific value.",
        required_comparison_keys=(
            "lsl_weeks_per_service_years",
            "early_access_after_years",
            "portable_service_recognised",
            "pro_rata_on_redundancy_after_years",
        ),
        allowed_value_types=("weeks", "years", "boolean", "text", "formula"),
    ),
    "family_domestic_violence_leave": CategoryDefinition(
        category="family_domestic_violence_leave",
        definition="Paid family and domestic violence leave and related workplace safety supports for standard/general employees.",
        include_when="The clause states paid days/hours, evidence rules, confidentiality, safety changes, or flexible work supports.",
        exclude_when="The clause only repeats the NES with no agreement-specific entitlement or support.",
        required_comparison_keys=(
            "paid_fdv_leave_days",
            "fdv_leave_paid",
            "evidence_required",
            "workplace_safety_adjustments_available",
        ),
        allowed_value_types=("days", "hours", "boolean", "text", "formula"),
    ),
    "study_professional_development": CategoryDefinition(
        category="study_professional_development",
        definition="Study leave, exam leave, training leave, fee reimbursement, union/delegate training, and professional development for standard/general employees.",
        include_when="The clause states paid days/hours, exam leave, reimbursement percentage/cap, or training leave quantum.",
        exclude_when="The entitlement is limited to a specialist occupation or registration group.",
        required_comparison_keys=(
            "study_leave_days_per_year",
            "exam_leave_days",
            "fee_reimbursement_rate",
            "training_leave_days",
            "professional_development_hours",
        ),
        allowed_value_types=("days", "hours", "percentage", "money", "boolean", "text", "formula"),
    ),
    "other_conditions_benefits": CategoryDefinition(
        category="other_conditions_benefits",
        definition="Other material standard/general employee benefits not captured by the named categories.",
        include_when="The clause is quantifiable, generally applicable, and likely to matter in bargaining comparison.",
        exclude_when="The clause is procedural, non-quantified, cohort-only, or immaterial for cross-council comparison.",
        required_comparison_keys=("benefit_value", "eligibility_threshold", "cap_or_limit"),
        allowed_value_types=("money", "percentage", "multiplier", "hours", "days", "weeks", "months", "years", "boolean", "text", "formula"),
        required_clause=True,
    ),
}


@dataclass(frozen=True)
class ClauseReference:
    """Exact clause source for an extracted condition or value."""

    clause_id: str
    heading: str
    source_kind: ClauseSourceKind = "agreement_clause"
    part: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    text: str = ""
    text_sha256: Optional[str] = None
    source_ref: Optional[str] = None
    council_applicability: CouncilApplicability = field(default_factory=CouncilApplicability)


@dataclass(frozen=True)
class AppliesTo:
    """Workforce scope for an entitlement."""

    employee_groups: tuple[str, ...] = ()
    employment_types: tuple[str, ...] = ()
    classifications: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class ConditionValue:
    """One normalised, comparable quantum from a clause."""

    value_id: str
    label: str
    value_type: ValueType
    raw_value: str
    role: QuantifierRole = "entitlement"
    basis: ValueBasis = "unknown"
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    frequency: Optional[str] = None
    comparator: Optional[str] = None
    formula: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    source_clause_ids: tuple[str, ...] = ()
    council_applicability: CouncilApplicability = field(default_factory=CouncilApplicability)
    confidence: float = 0.0
    notes: str = ""


@dataclass(frozen=True)
class ConditionItem:
    """A bargaining condition with clause provenance and comparable values."""

    item_id: str
    category: ConditionCategory
    title: str
    summary: str
    clauses: tuple[ClauseReference, ...] = ()
    values: tuple[ConditionValue, ...] = ()
    applies_to: AppliesTo = field(default_factory=AppliesTo)
    council_applicability: CouncilApplicability = field(default_factory=CouncilApplicability)
    comparison_keys: tuple[str, ...] = ()
    source_pages: tuple[int, ...] = ()
    materiality: Literal["big_ticket", "standard", "niche", "unknown"] = "unknown"
    extraction_status: Literal["extracted", "not_found", "ambiguous", "needs_review"] = "needs_review"
    confidence: float = 0.0
    notes: str = ""


@dataclass(frozen=True)
class ConditionsDocument:
    """All non-wage conditions and benefits extracted from one agreement."""

    ae_id: str
    council: str
    schema_version: str = CURRENT_CONDITIONS_SCHEMA_VERSION
    covered_councils: tuple[str, ...] = ()
    multi_employer: bool = False
    items: tuple[ConditionItem, ...] = ()
    missing_categories: tuple[ConditionCategory, ...] = ()
    extraction_notes: str = ""


def empty_conditions_data() -> dict[str, Any]:
    """Default payload stored in canonical.sections.clauses.data."""

    return {
        "schema_version": CURRENT_CONDITIONS_SCHEMA_VERSION,
        "target_scope": STANDARD_EMPLOYEE_SCOPE,
        "excluded_specialised_cohorts": list(EXCLUDED_SPECIALISED_COHORTS),
        "multi_employer": False,
        "covered_councils": [],
        "categories": list(BENEFIT_CONDITION_CATEGORIES),
        "big_ticket_categories": list(BIG_TICKET_CONDITION_CATEGORIES),
        "category_definitions": {
            category: asdict(definition)
            for category, definition in CONDITION_CATEGORY_DEFINITIONS.items()
        },
        "items": [],
        "missing_categories": [],
        "extraction_notes": "",
    }


def condition_document_to_dict(document: ConditionsDocument) -> dict[str, Any]:
    return asdict(document)


def validate_condition_item(item: dict[str, Any]) -> list[str]:
    """Return schema/definition violations for an incoming condition item."""

    errors: list[str] = []
    category = item.get("category")
    if category not in CONDITION_CATEGORY_DEFINITIONS:
        return [f"Unknown condition category: {category!r}"]

    definition = CONDITION_CATEGORY_DEFINITIONS[category]
    clauses = item.get("clauses")
    if definition.required_clause and not clauses:
        errors.append(f"{category}: at least one source clause is required")
    elif isinstance(clauses, list):
        for index, clause in enumerate(clauses):
            if not isinstance(clause, dict):
                errors.append(f"{category}: clauses[{index}] must be an object")
                continue
            if not clause.get("clause_id"):
                errors.append(f"{category}: clauses[{index}].clause_id is required")
            if not clause.get("text"):
                errors.append(f"{category}: clauses[{index}].text is required")

    values = item.get("values")
    if not isinstance(values, list):
        errors.append(f"{category}: values must be a list")
        return errors

    allowed_types = set(definition.allowed_value_types)
    available_keys = set(item.get("comparison_keys") or ())
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            errors.append(f"{category}: values[{index}] must be an object")
            continue
        value_type = value.get("value_type")
        if value_type not in allowed_types:
            errors.append(f"{category}: values[{index}].value_type {value_type!r} is not allowed")
        if not value.get("raw_value"):
            errors.append(f"{category}: values[{index}].raw_value is required")
        if not value.get("source_clause_ids"):
            errors.append(f"{category}: values[{index}].source_clause_ids is required")
        value_id = value.get("value_id")
        if isinstance(value_id, str) and value_id:
            available_keys.add(value_id)

    # Required comparison keys are aspirational because agreements vary, but if the
    # extractor has no matching key/value at all the item is not comparable.
    if definition.required_comparison_keys and not (available_keys & set(definition.required_comparison_keys)):
        errors.append(
            f"{category}: at least one recognised comparison key is required "
            f"({', '.join(definition.required_comparison_keys)})"
        )

    return errors


def _validate_council_applicability(
    value: Any,
    *,
    path: str,
    covered_councils: set[str],
    multi_employer: bool,
) -> list[str]:
    errors: list[str] = []
    if value is None:
        if multi_employer:
            errors.append(f"{path}: council_applicability is required for split agreements")
        return errors
    if not isinstance(value, dict):
        return [f"{path}: council_applicability must be an object"]

    valid_modes = {
        "all_covered_councils",
        "named_councils_only",
        "excluded_named_councils",
        "single_council",
        "unknown",
    }
    mode = value.get("mode")
    if mode not in valid_modes:
        errors.append(f"{path}: invalid council_applicability.mode {mode!r}")

    applies_to = value.get("applies_to_councils") or []
    excluded = value.get("excluded_councils") or []
    if not isinstance(applies_to, list):
        errors.append(f"{path}: applies_to_councils must be a list")
        applies_to = []
    if not isinstance(excluded, list):
        errors.append(f"{path}: excluded_councils must be a list")
        excluded = []

    if multi_employer and mode == "unknown":
        errors.append(f"{path}: split agreement applicability cannot be unknown")
    if mode == "named_councils_only" and not applies_to:
        errors.append(f"{path}: named_councils_only requires applies_to_councils")
    if mode == "excluded_named_councils" and not excluded:
        errors.append(f"{path}: excluded_named_councils requires excluded_councils")
    if mode == "single_council" and multi_employer:
        errors.append(f"{path}: use named_councils_only or all_covered_councils for split agreements")

    if covered_councils:
        unknown_applies = sorted(set(map(str, applies_to)) - covered_councils)
        unknown_excluded = sorted(set(map(str, excluded)) - covered_councils)
        if unknown_applies:
            errors.append(f"{path}: applies_to_councils not in covered_councils: {', '.join(unknown_applies)}")
        if unknown_excluded:
            errors.append(f"{path}: excluded_councils not in covered_councils: {', '.join(unknown_excluded)}")
    return errors


def validate_conditions_payload(payload: dict[str, Any]) -> list[str]:
    """Validate the canonical sections.clauses.data payload."""

    errors: list[str] = []
    if payload.get("target_scope") != STANDARD_EMPLOYEE_SCOPE:
        errors.append(f"target_scope must be {STANDARD_EMPLOYEE_SCOPE!r}")
    covered_councils = set(map(str, payload.get("covered_councils") or []))
    multi_employer = bool(payload.get("multi_employer"))
    items = payload.get("items")
    if not isinstance(items, list):
        return [*errors, "items must be a list"]
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"items[{index}] must be an object")
            continue
        errors.extend(f"items[{index}].{error}" for error in validate_condition_item(item))
        errors.extend(
            _validate_council_applicability(
                item.get("council_applicability"),
                path=f"items[{index}]",
                covered_councils=covered_councils,
                multi_employer=multi_employer,
            )
        )
        for value_index, value in enumerate(item.get("values") or []):
            if isinstance(value, dict):
                errors.extend(
                    _validate_council_applicability(
                        value.get("council_applicability"),
                        path=f"items[{index}].values[{value_index}]",
                        covered_councils=covered_councils,
                        multi_employer=multi_employer,
                    )
                )
    return errors
