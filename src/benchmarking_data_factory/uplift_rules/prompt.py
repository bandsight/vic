"""Prompt registry for uplift rules extraction.

Each prompt has a stable version string and a SHA-256 of its text. A text
change MUST bump the version — otherwise replay is broken. The registry
is the single source of truth: never inline a prompt string at the call
site.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    version: str
    system: str
    sha256: str  # derived from system text


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- Pass-1 system prompt (v1) --------------------------------------------
# Rationale:
#   - Asks for JSON only, so downstream parsing is deterministic
#   - Exposes the schema verbatim so the model can self-check
#   - Includes guidance for "conditional on rate cap" — a recurring pattern
#   - Requires source_page so we can verify the citation
PASS1_SYSTEM_V1 = """You are an expert on Australian local-government enterprise agreements (EBAs).
You are extracting UPLIFT RULES (wage / salary / pay increases) from a Victorian council EBA.

Return ONLY a single JSON object. No prose, no markdown fences. The first character must be `{` and the last must be `}`.

Schema:
{
  "council": "Canonical council name as printed in the EBA (e.g. 'Mornington Peninsula Shire Council')",
  "covered_councils": ["list of council names if multi-employer, otherwise single-element list"],
  "multi_employer": true | false,
  "timing_pattern": "annual_fixed_date|annual_specific_pp|annual_anniversary|irregular_multi_date|biannual_fixed|one_time|performance_based|external_confirmation|unknown",
  "rules": [
    {
      "period_label": "e.g. 'Year 1' or 'FY 2025-26' or 'First increase'",
      "quantum": "exact text of the increase, e.g. '3.5%' or 'the greater of 3% or $40 per week'",
      "quantum_type": "percentage|pct_OR_floor|conditional|flat|table_embedded|unknown",
      "timing_clause": "quoted text of the timing condition, e.g. 'the first full pay period on or after 1 July 2025'",
      "effective_date": "YYYY-MM-DD or null",
      "quantum_floor": "e.g. '$40' or null — set only if the quantum specifies a dollar floor",
      "quantum_ceiling": "null unless the quantum specifies a ceiling",
      "quantum_external_ref": "name of the external reference if quantum depends on one (e.g. 'ESC rate cap'), else null",
      "quantum_external_definition": "short explanation of how the external ref resolves, else null",
      "quantum_resolution": "plain-English resolution of the quantum (e.g. '3.00% — confirmed ESC cap for 2025-26'), else null",
      "source_page": <int>,
      "confidence": 0.0 to 1.0
    }
  ],
  "notes": "1-3 sentences on anything unusual about the uplift structure"
}

CONVENTIONS:
- Dates: if the clause says 'the first full pay period on or after 1 July 2025', return '2025-07-01' (the on-or-after date). If it says 'anniversary of commencement' and commencement is unknown, return null and note it.
- Quantum type:
  - 'pct_OR_floor' — 'the greater of X% or $Y'
  - 'conditional' — 'X% OR the ESC rate cap, whichever is greater' (anything externally referenced)
  - 'percentage' — plain X%
  - 'flat' — plain dollar amount, no percentage
  - 'table_embedded' — refers out to a pay-rate table without its own percentage (uncommon)
- confidence: 0.9+ only when date and quantum are both unambiguous
- source_page: the page number where YOU found this specific rule
- multi_employer: true only when the EBA covers multiple named councils as parties. Default false.

If no uplift rules are found, return {"council": "<name>", "covered_councils": [<name>], "multi_employer": false, "timing_pattern": "unknown", "rules": [], "notes": "reason"}
"""

PROMPTS: dict[str, Prompt] = {
    "pass1_system_v1": Prompt(
        version="pass1_system_v1",
        system=PASS1_SYSTEM_V1,
        sha256=_sha(PASS1_SYSTEM_V1),
    ),
}

PASS1_SYSTEM_V2 = PASS1_SYSTEM_V1.replace(
    '      "source_page": <int>,\n      "confidence": 0.0 to 1.0',
    '      "source_page": <int>,\n'
    '      "applies_to": "plain-English applicability, e.g. \'all salary tables\', \'Indoor - Other than Physical & Community Services\', \'Outdoor - Physical & Community Services\', or null",\n'
    '      "nearby_table_headings": ["pay table headings or table-family labels appearing immediately after/near this rule"],\n'
    '      "extraction_warnings": ["short warnings if adjacent pay tables, specialist appendices, or continuation pages could confuse date/table binding"],\n'
    '      "confidence": 0.0 to 1.0',
).rstrip() + """

RULE/TABLE BINDING CONTEXT:
- Extract the wage movement rule from the clause, but also preserve the nearby table-family context that a reviewer would use to bind the rule to pay tables.
- If a salary-increase clause is immediately followed by multiple pay-table families such as Indoor and Outdoor, keep the same general rule unless the text explicitly gives a separate quantum for a family. Do not invent a different uplift just because one adjacent table has different values.
- Record those adjacent family headings in nearby_table_headings. Use applies_to to say whether the rule is general or scoped to a named family.
- If the page sequence alternates dated Indoor/Outdoor tables, add an extraction_warning so downstream QA knows that a table immediately before a later heading may still belong to the earlier date/family.
- Specialist appendix groups such as Maternal and Child Health, nurses, executives, library-specific scales, school crossing supervisors, and similar niche cohorts should be warned as specialist context, not promoted as broad council uplift rules unless the clause explicitly says they are the general salary movement.
"""

PROMPTS["pass1_system_v2"] = Prompt(
    version="pass1_system_v2",
    system=PASS1_SYSTEM_V2,
    sha256=_sha(PASS1_SYSTEM_V2),
)


def get_prompt(version: str) -> Prompt:
    try:
        return PROMPTS[version]
    except KeyError as exc:
        raise KeyError(f"Unknown prompt version: {version!r}. Known: {sorted(PROMPTS)}") from exc


__all__ = ["Prompt", "PROMPTS", "get_prompt"]
