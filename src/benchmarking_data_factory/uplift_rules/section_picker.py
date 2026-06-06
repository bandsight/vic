"""Section picker — scores pages by likelihood of being uplift-rules pages.

Pure functions only. No PDF I/O, no filesystem, no network. Callers supply
page texts (a list[str] where index 0 is page 1) and get back a ranked list
of page numbers.

Public API:
  - UPLIFT_KEYWORDS: regex
  - UPLIFT_STRONG_HEADINGS: regex
  - PAY_KEYWORDS: regex
  - DOLLAR_PATTERN: regex
  - score_pages(page_texts, pattern) -> list[int]   # canonical scorer
  - rank_uplift_pages(page_texts) -> list[int]      # convenience: uses UPLIFT_KEYWORDS
  - is_toc_like(page_text) -> bool
"""
from __future__ import annotations

import re

# --- Regexes (byte-identical to main.py originals) ---

PAY_KEYWORDS = re.compile(
    r"\b(band\s+\d|level\s+\d|classification|weekly\s+rate|annual\s+rate|hourly\s+rate|"
    r"pay\s+rates?|wage|remuneration|schedule\s+of\s+rates|salary\s+scale|appendix.*rate|increment\s+progression)\b",
    re.IGNORECASE,
)

UPLIFT_KEYWORDS = re.compile(
    r"(\b(?:wage\s+increases?|pay\s+increases?|annual\s+increases?|"
    r"rates?\s+of\s+pay|salary\s+increases?|operative\s+date|"
    r"effective\s+date|pay\s+period|uplift(?:s|ed|ing)?|"
    r"commencement\s+date|sign(?:-|\s*)off|"
    r"quantum\s+and\s+timing|quantum\s+&\s+timing|"
    r"timing\s+of\s+(?:pay|wage|salary)\s+increases?|"
    r"date\s+of\s+effect|nominal\s+expiry|"
    r"remuneration|"
    r"per\s+cent|percent)\b|"
    r"an\s+increase\s+of\s+|"
    r"\d+(?:\.\d+)?\s*%)",
    re.IGNORECASE,
)

UPLIFT_STRONG_HEADINGS = re.compile(
    r"(?:^|\n)\s*(?:\d+(?:\.\d+)*\.?\s+)?"
    r"(?:QUANTUM\s+AND\s+TIMING|QUANTUM\s+&\s+TIMING|"
    r"PAY\s+INCREASES?|WAGE\s+INCREASES?|SALARY\s+INCREASES?|"
    r"RATES\s+OF\s+PAY|PAY\s+RATES\s+AND\s+ALLOWANCES|"
    r"REMUNERATION|"
    r"TIMING\s+OF\s+(?:PAY|WAGE|SALARY)\s+INCREASES?)"
    r"\b",
    re.IGNORECASE,
)

DOLLAR_PATTERN = re.compile(r"\$?\d{1,3}[,.]?\d{3}\.\d{2}\b")

STANDARD_PAY_TABLE_PATTERN = re.compile(
    r"\b(?:band|banding)\s*\d+[A-Z]?\b|"
    r"\bbands?\s+\d+\s+to\s+\d+\b|"
    r"\bband\s*&\s*level\b|"
    r"\blevel\s+band\b|"
    r"\bband\s+A\s+B\s+C\s+D\b|"
    r"\bweekly\s+rates\s+of\s+pay\b|"
    r"\bschedule\s+of\s+rates\s+of\s+pay\b|"
    r"\bpay\s+rates\s+table\b|"
    r"\bannual\s+salar(?:y|ies)\s+-\s+bands?\b|"
    r"\b(?:band|banding)\s+(?:level|salary|wage|rate|table)\b|"
    r"\bclassification\s+(?:code|level|table|structure|wage|salary|rate)s?\b|"
    r"\bsalary\s+scale\b",
    re.IGNORECASE,
)

ALLOWANCE_FALSE_POSITIVE_PATTERN = re.compile(
    r"\b(?:allowances?|penalt(?:y|ies)|overtime|call\s*out|"
    r"travel|meal|tool|uniform|first\s+aid|higher\s+duties)\b",
    re.IGNORECASE,
)

APPENDIX_FALSE_POSITIVE_PATTERN = re.compile(
    r"\b(?:appendix|schedule|annex(?:ure)?|undertaking|variation|side[-\s]?letter|special\s+conditions)\b",
    re.IGNORECASE,
)

SPECIALIST_COHORT_FALSE_POSITIVE_PATTERN = re.compile(
    r"\b(?:immunis(?:ation|er)|maternal|child\s+health|nurse|nursing|"
    r"clinical|mentoring|pool|school\s+crossing|parking|aged\s+care)\b",
    re.IGNORECASE,
)

# Maximum number of candidate pages returned by score_pages — preserves
# the original main.py behaviour of capping at 30.
MAX_CANDIDATE_PAGES = 30


def is_toc_like(page_text: str) -> bool:
    """True when the page has 3+ dotted-leader lines (typical of TOC)."""
    return len(re.findall(r"\.{4,}", page_text or "")) >= 3


def score_pages(page_texts: list[str], pattern: re.Pattern[str]) -> list[int]:
    """Rank pages by signal strength. Returns 1-indexed page numbers.

    Tiering (byte-identical to main.py.find_candidate_pages):
      1. STRONG HEADING match — always wins
      2. Dollar-density (>=3 dollar-like numbers) — usually pay tables
      3. Keyword matches (via `pattern`) — fallback
    TOC-like pages are skipped from every tier.
    Ties broken by (count desc, page number asc) within each tier.
    Capped at MAX_CANDIDATE_PAGES.
    """
    heading_pages: list[tuple[int, int]] = []  # (page_num, match_count)
    dollar_pages: list[tuple[int, int]] = []   # (page_num, dollar_count)
    keyword_pages: list[tuple[int, int]] = []  # (page_num, keyword_count)
    for idx, text in enumerate(page_texts, start=1):
        text = text or ""
        toc = is_toc_like(text)
        heading_hits = len(UPLIFT_STRONG_HEADINGS.findall(text))
        dollar_count = len(DOLLAR_PATTERN.findall(text))
        keyword_hits = len(pattern.findall(text))
        if heading_hits > 0 and not toc:
            heading_pages.append((idx, heading_hits))
            continue
        if dollar_count >= 3 and not toc:
            dollar_pages.append((idx, dollar_count))
            continue
        if keyword_hits > 0 and not toc:
            keyword_pages.append((idx, keyword_hits))
    heading_pages.sort(key=lambda x: (-x[1], x[0]))
    dollar_pages.sort(key=lambda x: -x[1])
    keyword_pages.sort(key=lambda x: (-x[1], x[0]))
    result: list[int] = [p for p, _ in heading_pages]
    for p, _ in dollar_pages:
        if p not in result:
            result.append(p)
    for p, _ in keyword_pages:
        if p not in result:
            result.append(p)
    return result[:MAX_CANDIDATE_PAGES]


def rank_pay_table_pages(page_texts: list[str]) -> list[int]:
    """Rank pay-table pages with false-positive pages down-ranked.

    The generic scorer intentionally treats dollar density as a strong signal.
    For pay-table extraction that catches real tables, but it also promotes
    allowance appendices, specialist-cohort clauses and hourly-only pages. This
    ranker keeps standard band/classification table signals first, keeps
    ambiguous pay pages as fallbacks, and drops hourly-only pages because the
    governed pay-table workflow skips hourly rates. Uplift-only pages are left
    to the separate uplift candidate list rather than mixed into pay tables.
    """
    base_pages = score_pages(page_texts, PAY_KEYWORDS)
    standard_pages: list[tuple[int, int]] = []
    fallback_pages: list[tuple[int, int]] = []
    downranked_pages: list[tuple[int, int]] = []
    for page_num in base_pages:
        text = page_texts[page_num - 1] if 0 < page_num <= len(page_texts) else ""
        text = text or ""
        dollar_count = len(DOLLAR_PATTERN.findall(text))
        pay_hits = len(PAY_KEYWORDS.findall(text))
        uplift_hits = len(UPLIFT_KEYWORDS.findall(text))
        standard_signal = bool(STANDARD_PAY_TABLE_PATTERN.search(text))
        allowance_signal = bool(ALLOWANCE_FALSE_POSITIVE_PATTERN.search(text))
        appendix_signal = bool(APPENDIX_FALSE_POSITIVE_PATTERN.search(text))
        specialist_signal = bool(SPECIALIST_COHORT_FALSE_POSITIVE_PATTERN.search(text))
        hourly_signal = bool(re.search(r"\bhourly\s+rate\b", text, re.IGNORECASE))
        weekly_or_annual_signal = bool(re.search(r"\b(?:weekly|annual)\s+(?:rate|salary|wage)\b", text, re.IGNORECASE))
        standard_banding_score = (
            int(standard_signal)
            + int(bool(re.search(r"\bband(?:ing)?\s*\d", text, re.IGNORECASE)))
            + int(bool(re.search(r"\b(?:weekly\s+rates\s+of\s+pay|pay\s+rates\s+table|band\s*&\s*level|level\s+band)\b", text, re.IGNORECASE)))
        )
        if hourly_signal and not weekly_or_annual_signal and not standard_signal:
            continue
        if uplift_hits > pay_hits and not standard_signal:
            continue
        signal_score = dollar_count + (pay_hits * 3)
        false_positive_score = (
            int(allowance_signal)
            + int(appendix_signal and dollar_count >= 3 and not standard_signal)
            + int(specialist_signal)
        )
        if standard_banding_score and not (specialist_signal and standard_banding_score < 2):
            standard_pages.append((page_num, signal_score + standard_banding_score))
        elif false_positive_score:
            downranked_pages.append((page_num, signal_score - false_positive_score))
        else:
            fallback_pages.append((page_num, signal_score))

    standard_pages.sort(key=lambda x: (-x[1], x[0]))
    fallback_pages.sort(key=lambda x: (-x[1], x[0]))
    downranked_pages.sort(key=lambda x: (-x[1], x[0]))
    result: list[int] = []
    for bucket in (standard_pages, fallback_pages, downranked_pages):
        for page_num, _ in bucket:
            if page_num not in result:
                result.append(page_num)
    return result[:MAX_CANDIDATE_PAGES]


def rank_uplift_pages(page_texts: list[str]) -> list[int]:
    """Convenience: rank pages using the canonical UPLIFT_KEYWORDS pattern."""
    return score_pages(page_texts, UPLIFT_KEYWORDS)


def rank_uplift_pages_with_continuation(
    page_texts: list[str],
    *,
    include_continuation: bool = False,
) -> list[int]:
    """Like rank_uplift_pages, but when include_continuation=True, inserts each
    primary page's immediate successor (page p+1) directly after it in the
    ranked list. This ensures that when a caller truncates to a top-K window
    (e.g. max_pages=12 in suggest.py), the continuation of a high-ranking
    primary page survives the cut — crucial for clauses that wrap across a
    page break (e.g. Greater Shepparton's uplift clause spans pp. 44–45, where
    p. 44 ranked #1 but p. 45 was pushed to #16 by appendix pay-table pages).

    A continuation is skipped when:
      - it would be out of bounds,
      - it already appears earlier in the result (don't duplicate),
      - it is TOC-like.
    Capped at MAX_CANDIDATE_PAGES overall.
    """
    if not include_continuation:
        return rank_uplift_pages(page_texts)

    primary = rank_uplift_pages(page_texts)

    result: list[int] = []
    seen: set[int] = set()
    for p in primary:
        if p not in seen:
            result.append(p)
            seen.add(p)
        continuation = p + 1
        # Out of bounds: continuation page does not exist
        if continuation > len(page_texts):
            continue
        # Already placed (either as earlier primary or as earlier continuation)
        if continuation in seen:
            continue
        # Continuation page is TOC-like; page_texts[p] is 0-indexed position p,
        # which corresponds to 1-indexed page p+1 (the continuation candidate).
        if is_toc_like(page_texts[p]):
            continue
        result.append(continuation)
        seen.add(continuation)

    return result[:MAX_CANDIDATE_PAGES]


__all__ = [
    "DOLLAR_PATTERN",
    "MAX_CANDIDATE_PAGES",
    "PAY_KEYWORDS",
    "rank_pay_table_pages",
    "UPLIFT_KEYWORDS",
    "UPLIFT_STRONG_HEADINGS",
    "is_toc_like",
    "rank_uplift_pages",
    "rank_uplift_pages_with_continuation",
    "score_pages",
]
