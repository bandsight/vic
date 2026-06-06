"""Prompt contract for conditions and benefits extraction."""
from __future__ import annotations

from benchmarking_data_factory.conditions.schema import (
    BENEFIT_CONDITION_CATEGORIES,
    BIG_TICKET_CONDITION_CATEGORIES,
    CONDITION_CATEGORY_DEFINITIONS,
    CURRENT_CONDITIONS_SCHEMA_VERSION,
    EXCLUDED_SPECIALISED_COHORTS,
    STANDARD_EMPLOYEE_SCOPE,
)


CONDITIONS_PROMPT_VERSION = "conditions_pass1_v1"


def build_conditions_extraction_prompt(ae_id: str, council: str) -> str:
    categories = "\n".join(
        f"- {category}: {CONDITION_CATEGORY_DEFINITIONS[category].definition}"
        for category in BENEFIT_CONDITION_CATEGORIES
    )
    comparison_contract = "\n".join(
        f"- {category}: {', '.join(CONDITION_CATEGORY_DEFINITIONS[category].required_comparison_keys)}"
        for category in BENEFIT_CONDITION_CATEGORIES
    )
    big_ticket = ", ".join(BIG_TICKET_CONDITION_CATEGORIES)
    excluded = "\n".join(f"- {cohort}" for cohort in EXCLUDED_SPECIALISED_COHORTS)
    return f"""Extract non-wage EBA conditions and benefits for comparison.

Agreement ID: {ae_id}
Council: {council}
Schema version: {CURRENT_CONDITIONS_SCHEMA_VERSION}
Target scope: {STANDARD_EMPLOYEE_SCOPE}

Do not extract wage uplift/pay-table rules here; those belong in pay_tables and uplift_rules.
Extract only conditions that apply to standard/general employees.
Exclude specialised cohort-only clauses unless the same entitlement also applies to standard/general employees.

Excluded specialised cohorts:
{excluded}

Categories:
{categories}

Big-ticket categories for bargaining comparison: {big_ticket}

Required comparison keys by category. Use these names where the agreement contains the data.
If a key is genuinely absent, do not invent it; note the absence in item.notes.
{comparison_contract}

Return JSON with:
- schema_version
- multi_employer
- covered_councils[]
- items[]

Each item must include:
- item_id: stable dotted id, e.g. redundancy.severance
- category: one of the categories above
- title
- summary
- materiality: big_ticket, standard, niche, or unknown
- extraction_status: extracted, not_found, ambiguous, or needs_review
- applies_to: employee_groups, employment_types, classifications, locations, exclusions, notes
- clauses[] with clause_id, heading, source_kind, part, page_start, page_end, text, text_sha256, source_ref
- council_applicability with mode, applies_to_councils, excluded_councils, source_clause_ids, notes
- values[] with value_id, label, value_type, raw_value, role, basis, numeric_value, unit, currency,
  frequency, comparator, formula, effective_from, effective_to, source_clause_ids, council_applicability,
  confidence, notes
- comparison_keys[] naming the values most useful for cross-council comparison
- source_pages[]
- confidence
- notes

Rules:
- Preserve the exact associated clause text for every extracted value.
- Prefer quantified values: dollars, percentages, multipliers, hours, days, weeks, caps, floors, thresholds.
- Do not extract cohort-only conditions from schedules or parts for specialised employee groups.
- If a clause appears in a specialised appendix but also states a general entitlement, extract only the general entitlement and note the scope.
- Pay special attention to split or multi-employer agreements. A clause or value may apply to:
  all_covered_councils, named_councils_only, or excluded_named_councils.
- For split agreements, never assume a clause applies to all councils merely because it appears in the agreement.
  Use named_councils_only when headings, tables, footnotes, schedules, definitions, or wording identify a specific employer.
- If the clause applies to all councils in a split agreement, set mode to all_covered_councils and list the source clause that proves it.
- If a clause is important but not quantifiable, store it with value_type text and explain why.
- If the agreement incorporates an award, identify whether the clause text is agreement-specific,
  incorporated_award, schedule, appendix, or FWC undertaking.
- Mark ambiguous items needs_review rather than guessing.
"""
