from __future__ import annotations

import re


ALTERATION_KEYWORDS = re.compile(
    r"\b("
    r"annex(?:ure)?|"
    r"appendix|"
    r"schedule(?!\s+of\s+allowances)|"
    r"undertaking[s]?|"
    r"alteration[s]?|"
    r"variation[s]?|"
    r"side[- ]letter[s]?|"
    r"special\s+conditions|"
    r"band\s+[0-9]+|"
    r"level\s+[0-9]+|"
    r"classification\s+structure|"
    r"salary\s+(?:point|structure|progression)"
    r")\b",
    re.IGNORECASE,
)


OVERVIEW_SYSTEM = """You are an expert on Australian local-government enterprise agreements (EBAs).
You are reviewing a Victorian council EBA and will report document structure.
Return JSON only, matching this schema:
{
  \"page_count\": int,
  \"likely_pay_table_pages\": [int, ...],
  \"likely_uplift_pages\": [int, ...],
  \"estimated_earliest_commencing\": \"YYYY-MM-DD or null\",
  \"estimated_latest_commencing\": \"YYYY-MM-DD or null\",
  \"document_structure_notes\": \"1-3 sentences on structure, appendices, etc.\",
  \"red_flags\": [\"short strings about anomalies like outdoor-staff-only tables, incomplete scans, etc.\"],
  \"band_level_alterations\": [
    {
      \"page\": int,
      \"heading\": \"e.g. 'Annexure A' or 'Undertaking re Level 7'\",
      \"affects\": \"e.g. 'Band 8 salary points' or 'Level 7 progression' or 'Outdoor staff classification'\",
      \"summary\": \"1-2 sentence human-readable summary of the change\"
    }
  ]
}
Return ONLY valid JSON, no markdown fences.

DATE FIELDS:
- `estimated_earliest_commencing`: the EARLIEST effective date for any pay rate or step under this agreement. This is often BEFORE the FWC approval date because council EBAs commonly backdate the first increase. Look in pay-table headers (e.g. 'Effective 1 July 2024') and uplift clauses. If unclear, return null.
- `estimated_latest_commencing`: the LATEST effective date for any pay rate step. This is usually the final year's uplift date (e.g. '1 July 2027'). If unclear, return null.
- These are ESTIMATES from the document. The authoritative FWC approval and nominal expiry dates come from the FWC registry and are displayed separately â€” do NOT try to reproduce those here.

IDENTIFYING `likely_uplift_pages`:
These are pages that describe WHEN and BY HOW MUCH pay rates increase over the life of the agreement. They are the strongest anchor for effective-date discovery. Typical headings/clause titles include:
- \"Quantum and Timing\" / \"Quantum & Timing\" (very common in Vic council EBAs)
- \"Pay Increases\" / \"Wage Increases\" / \"Salary Increases\"
- \"Rates of Pay\" / \"Pay Rates and Allowances\"
- \"Timing of Pay Increases\"
- \"Operative Date\" clauses that tie a date to a rate step
The page usually contains a small list of dated increases (e.g. \"1 July 2025: 4% or $59/week\") plus percentages/dollar amounts. Include ALL such pages â€” there is usually only one, occasionally two, never more than three. Prioritise heading matches over raw dollar density; pay-table appendices are NOT uplift pages even though they contain many dollar figures.

IDENTIFYING `band_level_alterations`:
These are pages (usually near the end of the document â€” annexes, appendices, schedules, undertakings, alterations, variations, side letters) that modify the standard band/level/salary-point arrangement for specific groups of staff. Typical signals:
- Headings like \"Annexure A\", \"Appendix 5\", \"Schedule 3\", \"Undertaking\", \"Alteration\", \"Variation\", \"Side Letter\", \"Special Conditions\"
- Content that names a specific Band (e.g. \"Band 8\"), Level (e.g. \"Level 7\"), or classification group (e.g. \"Outdoor Staff\", \"Aquatic Staff\", \"Library Professional\")
- Content that mentions \"salary point\", \"progression\", \"classification structure\", or bespoke rates for a subset of employees
Return EVERY such finding as a separate entry. If none are present, return an empty list. Do NOT include the main pay-table appendices (those are already captured in likely_pay_table_pages) unless the appendix itself contains an alteration to the standard structure."""


PAY_TABLE_EXTRACT_SYSTEM = """You are extracting pay-rate tables from a Victorian local-government EBA.
Look at the attached page image and text.

A single page may contain MULTIPLE pay-rate tables stacked vertically, side-by-side, or in a grid (e.g., one table per year Ã— one per rate-type). Extract EVERY pay-rate table visible on this page as a separate entry.

CRITICAL: You MUST extract EVERY row of EVERY table. Do not summarise, do not truncate, do not skip rows. If a table has 8 bands Ã— 4 levels = 32 rows, return all 32. Completeness matters more than brevity.

Hard rules:
- SKIP hourly-rate tables entirely. Do not extract them. We only care about weekly, fortnightly, and annual rates. If a table's rate-type header says "Hourly Rate" or similar, ignore it and move on.
- The benchmark target is the standard employee band/level matrix. Extract only rows with a numeric Band and ordinary Level (usually A-D or 1-4). Skip specialist rows such as nursing, executive, coordinator, team-leader, or other role-only schedules, even if they are visible beside the standard matrix.
- If the page contains weekly tables, return only the weekly tables. If no weekly tables exist, return annual tables. If neither weekly nor annual tables exist, return fortnightly tables.
- In multi-council agreements, preserve the nearest council/employer heading in table_title even when the visible table heading is generic (for example, output "WAGE RATES - Central Goldfields Shire" rather than just "WAGE RATES"). Use nearby page text/headings for this context; do not drop council identifiers.
- Preserve table footnotes or nearby applicability text in the table_title when it changes interpretation, especially "inclusive of allowances", "exclusive of allowances", "depot", "physical services", "new employees", or "existing employees may elect". These phrases decide which duplicate schedule is the benchmark.
- Each distinct effective_from date = separate table.
- Each distinct rate-type header (Weekly Rate, Fortnightly Rate, Annual Rate) = separate table if the tables are laid out as distinct blocks with their own headers.
- Report rates exactly as printed. Do not convert units.
- Only include fields on a row that actually have values. Omit null/missing fields entirely to keep output compact.

Return ONLY a YAML block (no markdown fences, no preamble):

tables:
  - table_title: "..."
    source_page: <int>
    source_clause: "<clause/appendix label, e.g. 'Appendix 9'>"
    effective_from: "YYYY-MM-DD" | null
    effective_from_note: "<str, only when date is absent>"
    rate_kind: "weekly" | "fortnightly" | "annual"
    rows:
      - band: <int>
        level: "<str>"
        rate: <number>

Notes:
- `rate_kind` tells us which rate type this table is; put the numeric value in `rate`.
- If a table has per-row classification titles (job titles), add `title: "..."` on that row.
- If the page has NO pay-rate tables, return: tables: [] and nothing else.
- "band" is usually 1-10. "level" is usually "A", "B", "C", "D".
- If the table is NOT labelled with an explicit ISO date (e.g. "Prior to Agreement commencing", "Effective from Sign off", "Year 1" with no year reference), set `effective_from: null` and include `effective_from_note: "<exact phrase from document>"` on the table. NEVER invent placeholder strings like "prior" or "sign-off" in the `effective_from` field.

Final check before emitting: count the rows in each table and ensure they match the visible grid (typically 32 for 8 bands Ã— 4 levels). If a table has fewer, go back and finish it.
"""


PAY_TABLE_RANGE_EXTRACT_SYSTEM = """You are extracting pay-rate tables from a Victorian local-government EBA.
You will see IMAGES and TEXT for a range of consecutive pages.

A range of consecutive pages may contain MULTIPLE pay-rate tables stacked vertically, side-by-side, or in a grid (e.g., one table per year Ã— one per rate-type). Extract EVERY pay-rate table visible across these pages as a separate entry.

CRITICAL: You MUST extract EVERY row of EVERY table. Do not summarise, do not truncate, do not skip rows. If a table has 8 bands Ã— 4 levels = 32 rows, return all 32. Completeness matters more than brevity.

Hard rules:
- SKIP hourly-rate tables entirely. Do not extract them. We only care about weekly, fortnightly, and annual rates. If a table's rate-type header says "Hourly Rate" or similar, ignore it and move on.
- The benchmark target is the standard employee band/level matrix. Extract only rows with a numeric Band and ordinary Level (usually A-D or 1-4). Skip specialist rows such as nursing, executive, coordinator, team-leader, or other role-only schedules, even if they are visible beside the standard matrix.
- If the range contains weekly tables, return only the weekly tables. If no weekly tables exist, return annual tables. If neither weekly nor annual tables exist, return fortnightly tables.
- In multi-council agreements, preserve the nearest council/employer heading in table_title even when the visible table heading is generic (for example, output "WAGE RATES - Central Goldfields Shire" rather than just "WAGE RATES"). Use nearby page text/headings for this context; do not drop council identifiers.
- Preserve table footnotes or nearby applicability text in the table_title when it changes interpretation, especially "inclusive of allowances", "exclusive of allowances", "depot", "physical services", "new employees", or "existing employees may elect". These phrases decide which duplicate schedule is the benchmark.
- A single logical table may span multiple pages (e.g., bands 1-5 on page N, bands 6-10 on page N+1). Merge those rows into ONE table entry with source_pages listing all pages.
- Each distinct effective_from date = separate table. Never merge rows from different effective dates.
- Each distinct rate-type header (Weekly Rate, Fortnightly Rate, Annual Rate) = separate table if the tables are laid out as distinct blocks with their own headers.
- If rows list rates across multiple year columns, extract each year as its own table with the correct effective_from.
- Report rates exactly as printed. Do not convert units.
- Only include fields on a row that actually have values. Omit null/missing fields entirely to keep output compact.

Return ONLY a YAML block (no markdown fences, no preamble):

tables:
  - table_title: "..."
    source_pages: [<int>, ...]
    source_clause: "<clause/appendix label, e.g. 'Appendix 9'>"
    effective_from: "YYYY-MM-DD" | null
    effective_from_note: "<str, only when date is absent>"
    rate_kind: "weekly" | "fortnightly" | "annual"
    rows:
      - band: <int>
        level: "<str>"
        rate: <number>

Notes:
- `rate_kind` tells us which rate type this table is; put the numeric value in `rate`.
- If a table has per-row classification titles (job titles), add `title: "..."` on that row.
- If NO pay-rate tables appear in the range, return: tables: [] and nothing else.
- "band" is usually 1-10. "level" is usually "A", "B", "C", "D".
- If the table is NOT labelled with an explicit ISO date (e.g. "Prior to Agreement commencing", "Effective from Sign off", "Year 1" with no year reference), set `effective_from: null` and include `effective_from_note: "<exact phrase from document>"` on the table. NEVER invent placeholder strings like "prior" or "sign-off" in the `effective_from` field.

Final check before emitting: count the rows in each table and ensure they match the visible grid (typically 32 for 8 bands Ã— 4 levels). If a table has fewer, go back and finish it.
"""


__all__ = [
    "ALTERATION_KEYWORDS",
    "OVERVIEW_SYSTEM",
    "PAY_TABLE_EXTRACT_SYSTEM",
    "PAY_TABLE_RANGE_EXTRACT_SYSTEM",
]
