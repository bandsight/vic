"""Unit tests for the section picker.

Covers:
- Regex constants present and compiled
- is_toc_like detection
- Tier 1 (strong heading) beats Tier 2 (dollar density) beats Tier 3 (keywords)
- TOC-like pages are never selected
- MAX_CANDIDATE_PAGES cap is enforced
- Byte-identical behaviour with the original main.py tiering for a fixture corpus
"""
from __future__ import annotations

import re
import unittest

from benchmarking_data_factory.uplift_rules.section_picker import (
    DOLLAR_PATTERN,
    MAX_CANDIDATE_PAGES,
    PAY_KEYWORDS,
    UPLIFT_KEYWORDS,
    UPLIFT_STRONG_HEADINGS,
    is_toc_like,
    rank_pay_table_pages,
    rank_uplift_pages,
    rank_uplift_pages_with_continuation,
    score_pages,
)


class TestRegexes(unittest.TestCase):
    def test_uplift_keywords_matches_common_phrases(self):
        self.assertTrue(UPLIFT_KEYWORDS.search("The wage increases for Year 1..."))
        self.assertTrue(UPLIFT_KEYWORDS.search("operative date: 1 July 2024"))
        self.assertTrue(UPLIFT_KEYWORDS.search("3.5 per cent"))
        self.assertTrue(UPLIFT_KEYWORDS.search("3%"))
        self.assertTrue(UPLIFT_KEYWORDS.search("quantum and timing"))

    def test_uplift_strong_heading_matches_section_titles(self):
        self.assertTrue(UPLIFT_STRONG_HEADINGS.search("\n12. QUANTUM AND TIMING\n"))
        self.assertTrue(UPLIFT_STRONG_HEADINGS.search("\nPAY INCREASES\n"))
        self.assertTrue(UPLIFT_STRONG_HEADINGS.search("\nRATES OF PAY\n"))

    def test_dollar_pattern_matches(self):
        self.assertTrue(DOLLAR_PATTERN.search("$1,234.56"))
        self.assertTrue(DOLLAR_PATTERN.search("1,234.56"))
        self.assertIsNone(DOLLAR_PATTERN.search("$12"))

    def test_pay_keywords_sample(self):
        self.assertTrue(PAY_KEYWORDS.search("weekly rate"))
        self.assertTrue(PAY_KEYWORDS.search("Band 5"))
        self.assertTrue(PAY_KEYWORDS.search("remuneration"))


class TestIsTocLike(unittest.TestCase):
    def test_empty_page_not_toc(self):
        self.assertFalse(is_toc_like(""))

    def test_few_dots_not_toc(self):
        self.assertFalse(is_toc_like("Clause 1. Definitions ... 3"))

    def test_many_dotted_leaders_is_toc(self):
        toc = (
            "Clause 1 .......... 3\n"
            "Clause 2 .......... 4\n"
            "Clause 3 .......... 5\n"
        )
        self.assertTrue(is_toc_like(toc))


class TestScorePagesTiering(unittest.TestCase):
    def test_heading_beats_dollar_density(self):
        # Page 5 has a strong heading, page 2 has dollar density
        pages = ["intro"] * 10
        pages[1] = "$1,234.56 and $2,345.67 and $3,456.78"  # page 2 — dollar dense
        pages[4] = "\nQUANTUM AND TIMING\nDetails here."    # page 5 — heading
        result = score_pages(pages, UPLIFT_KEYWORDS)
        self.assertEqual(result[0], 5)
        self.assertIn(2, result)
        self.assertGreater(result.index(2), 0)  # page 2 comes after heading page

    def test_dollar_beats_keyword_only(self):
        # Page 1 has keyword hits but no strong heading (embedded context, not start-of-line).
        # Page 2 has dollar density.
        pages = [
            "Please refer to the operative date schedule in Appendix B.",   # keyword only
            "$1,234.56 $2,345.67 $3,456.78 $4,567.89",                      # dollar dense
        ]
        # Sanity check: page 1 must not match the strong heading regex
        self.assertIsNone(UPLIFT_STRONG_HEADINGS.search(pages[0]))
        result = score_pages(pages, UPLIFT_KEYWORDS)
        self.assertEqual(result[0], 2)
        self.assertEqual(result[1], 1)

    def test_toc_like_pages_excluded(self):
        toc = (
            "PAY INCREASES ........... 12\n"
            "QUANTUM AND TIMING ...... 13\n"
            "RATES OF PAY ............ 14\n"
        )
        pages = [toc, "quantum and timing details"]
        result = score_pages(pages, UPLIFT_KEYWORDS)
        # TOC page 1 must not be selected despite strong heading
        self.assertNotIn(1, result)
        self.assertIn(2, result)

    def test_empty_input(self):
        self.assertEqual(score_pages([], UPLIFT_KEYWORDS), [])

    def test_no_signal_pages_return_empty(self):
        pages = ["lorem ipsum" * 5, "dolor sit amet" * 5]
        self.assertEqual(score_pages(pages, UPLIFT_KEYWORDS), [])

    def test_cap_at_max_candidate_pages(self):
        # 50 heading pages — expect the list capped at MAX_CANDIDATE_PAGES
        pages = ["\nPAY INCREASES\nDetails"] * 50
        result = score_pages(pages, UPLIFT_KEYWORDS)
        self.assertEqual(len(result), MAX_CANDIDATE_PAGES)

    def test_heading_tie_break_by_count_then_page(self):
        pages = [
            "\nPAY INCREASES\n",                                   # 1 hit
            "\nPAY INCREASES\nPAY INCREASES\n",                    # 2 hits
            "\nPAY INCREASES\nPAY INCREASES\nPAY INCREASES\n",     # 3 hits
        ]
        result = score_pages(pages, UPLIFT_KEYWORDS)
        # Highest count first, then lower count
        self.assertEqual(result[0], 3)
        self.assertEqual(result[1], 2)
        self.assertEqual(result[2], 1)


class TestRankUpliftPages(unittest.TestCase):
    def test_is_alias_for_score_pages_with_uplift_keywords(self):
        pages = [
            "intro",
            "\nQUANTUM AND TIMING\nDetails",
            "$1,234.56 $2,345.67 $3,456.78",
        ]
        self.assertEqual(rank_uplift_pages(pages), score_pages(pages, UPLIFT_KEYWORDS))


class TestRankPayTablePages(unittest.TestCase):
    def test_downranks_allowance_and_specialist_false_positives(self):
        pages = [
            (
                "APPENDIX 2 - ALLOWANCES\n"
                "$1,234.00 $1,345.00 $1,456.00 $1,567.00 meal allowance overtime call out"
            ),
            "CLASSIFICATION AND WAGE RATES\nBand 1 Level A weekly rate $1,100.00\nBand 2 Level A weekly rate $1,240.00",
            "Clinical mentoring immunisation nurse allowance $1,000.00 $1,100.00 $1,200.00",
        ]

        self.assertEqual(rank_pay_table_pages(pages), [2, 1, 3])

    def test_weekly_rate_alone_is_not_standard_banding_signal(self):
        pages = [
            "MCH Year 1 Annual Salary $99,097.78 Weekly Rate $1,905.73 Hourly Rate $50.15",
            "Banding Salary Table 35 hour week July 2024 Band 1A $61,645.61 weekly rate $1,185.49",
        ]

        self.assertEqual(rank_pay_table_pages(pages), [2, 1])

    def test_skips_hourly_only_pages(self):
        pages = [
            "Hourly rate $35.00 ordinary hours table",
            "Band 1 Level A weekly rate $1,100.00",
        ]

        self.assertEqual(rank_pay_table_pages(pages), [2])

    def test_separates_uplift_clause_pages_from_pay_tables(self):
        pages = [
            "Quantum and Timing Wage increases 1 July 2026 3.0% rate cap wage increase",
            "Band 1 Level A weekly rate $1,100.00",
        ]

        self.assertEqual(rank_pay_table_pages(pages), [2])

    def test_downranks_appendix_dollar_density_without_standard_table_signal(self):
        pages = [
            "Appendix 2 Special Conditions $1,234.00 $1,345.00 $1,456.00",
            "Band 1 Level A weekly rate $1,100.00",
        ]

        self.assertEqual(rank_pay_table_pages(pages), [2, 1])


class TestOriginalBehaviourParity(unittest.TestCase):
    """Replicates the original find_candidate_pages logic inline and
    asserts score_pages() matches byte-for-byte across synthetic fixtures."""

    @staticmethod
    def legacy_find(page_texts: list[str], pattern: re.Pattern[str]) -> list[int]:
        # Copy of main.py find_candidate_pages body (without PDF I/O), for parity
        heading_pages: list[tuple[int, int]] = []
        dollar_pages: list[tuple[int, int]] = []
        keyword_pages: list[tuple[int, int]] = []
        for idx, text in enumerate(page_texts, start=1):
            text = text or ""
            is_toc = len(re.findall(r"\.{4,}", text)) >= 3
            heading_hits = len(UPLIFT_STRONG_HEADINGS.findall(text))
            dollar_count = len(DOLLAR_PATTERN.findall(text))
            keyword_hits = len(pattern.findall(text))
            if heading_hits > 0 and not is_toc:
                heading_pages.append((idx, heading_hits))
                continue
            if dollar_count >= 3 and not is_toc:
                dollar_pages.append((idx, dollar_count))
                continue
            if keyword_hits > 0 and not is_toc:
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
        return result[:30]

    def test_parity_on_mixed_fixture(self):
        fixture = [
            "Introduction and scope",
            "\n12. QUANTUM AND TIMING\nDetails about wage increases of 3%",
            "Boilerplate text, no signal.",
            "Rates of Pay and Allowances ......................... 45\n"
            "Quantum and Timing ................................. 47\n"
            "Classification table ............................... 48\n",  # TOC
            "$1,234.56 $2,345.67 $3,456.78 $4,567.89 per annum",
            "The nominal expiry date is 30 June 2028.",
            "\nPAY INCREASES\n$500.00 per week from 1 July 2024",
        ]
        self.assertEqual(
            score_pages(fixture, UPLIFT_KEYWORDS),
            self.legacy_find(fixture, UPLIFT_KEYWORDS),
        )

    def test_parity_on_empty_and_none_pages(self):
        fixture = ["", None, "   ", "QUANTUM AND TIMING"]
        self.assertEqual(
            score_pages(fixture, UPLIFT_KEYWORDS),
            self.legacy_find(fixture, UPLIFT_KEYWORDS),
        )


class TestRankUpliftPagesWithContinuation(unittest.TestCase):
    def test_continuation_disabled_matches_original(self):
        # ≥5-page fixture mix; with flag off (default) results must be byte-identical
        pages = [
            "intro",
            "\nQUANTUM AND TIMING\nYear 1: 3.5% from 1 July 2025.",
            "continuation details without signal",
            "$1,234.56 $2,345.67 $3,456.78 per annum",
            "boilerplate about signatures",
        ]
        self.assertEqual(
            rank_uplift_pages(pages),
            rank_uplift_pages_with_continuation(pages),
        )

    def test_continuation_appends_next_page_when_not_already_present(self):
        # Page 2 scores heavily on heading; page 3 has no signal
        pages = [
            "intro",
            "\nQUANTUM AND TIMING\nYear 1: 3.5% from 1 July 2025.",
            "continuation details without keywords",
            "boilerplate text",
            "more boilerplate",
        ]
        result = rank_uplift_pages_with_continuation(pages, include_continuation=True)
        self.assertEqual(result[0], 2)
        self.assertIn(3, result)

    def test_continuation_does_not_duplicate_already_selected_page(self):
        # Both page 2 and page 3 are selected by the primary picker
        pages = [
            "intro",
            "\nQUANTUM AND TIMING\nYear 1: 3.5%",
            "\nPAY INCREASES\nYear 2: 3.0%",
            "boilerplate",
            "boilerplate",
        ]
        result = rank_uplift_pages_with_continuation(pages, include_continuation=True)
        self.assertEqual(result.count(3), 1)

    def test_continuation_out_of_bounds_safe(self):
        # Last page (page 5 in a 5-page list) is selected primary — no IndexError
        pages = [
            "intro",
            "boilerplate",
            "boilerplate",
            "boilerplate",
            "\nQUANTUM AND TIMING\nYear 1: 3.5%",
        ]
        result = rank_uplift_pages_with_continuation(pages, include_continuation=True)
        self.assertIn(5, result)
        self.assertNotIn(6, result)

    def test_continuation_skips_toc_like_continuations(self):
        # Page 3 is selected primary; page 4 is TOC-like — must not be appended
        toc_page = (
            "Clause 1 .......... 3\n"
            "Clause 2 .......... 4\n"
            "Clause 3 .......... 5\n"
            "Clause 4 .......... 6\n"
            "Clause 5 .......... 7\n"
        )
        pages = [
            "intro",
            "boilerplate",
            "\nQUANTUM AND TIMING\nYear 1: 3.5%",
            toc_page,
            "boilerplate",
        ]
        result = rank_uplift_pages_with_continuation(pages, include_continuation=True)
        self.assertIn(3, result)
        self.assertNotIn(4, result)

    def test_continuation_respects_max_cap(self):
        # 29 heading pages (1-indexed odd: 1, 3, 5, ..., 57) + 29 neutral pages (58 total)
        # Primary = 29 pages; 29 valid continuations available; cap at MAX_CANDIDATE_PAGES
        pages = []
        for i in range(58):
            if i % 2 == 0:
                pages.append("\nQUANTUM AND TIMING\ndetails")
            else:
                pages.append("neutral continuation text")
        result = rank_uplift_pages_with_continuation(pages, include_continuation=True)
        self.assertEqual(len(result), MAX_CANDIDATE_PAGES)

    def test_continuation_preserves_primary_ordering(self):
        # Primary ranks [5, 2, 9] (by heading hits desc). Each continuation must sit
        # directly after its primary so top-K truncation (e.g. max_pages=12 in
        # suggest.py) can't strip a primary's continuation away. Expected:
        # [5, 6, 2, 3, 9, 10].
        pages = ["neutral"] * 15
        pages[4] = "\nQUANTUM AND TIMING\nPAY INCREASES\nWAGE INCREASES"  # page 5 — 3 hits
        pages[1] = "\nQUANTUM AND TIMING\nPAY INCREASES"                   # page 2 — 2 hits
        pages[8] = "\nQUANTUM AND TIMING"                                   # page 9 — 1 hit
        result = rank_uplift_pages_with_continuation(pages, include_continuation=True)
        self.assertEqual(result, [5, 6, 2, 3, 9, 10])

    def test_continuation_survives_top_k_truncation(self):
        # Regression for Greater Shepparton: uplift clause spans pp. 44–45.
        # p. 44 is rank #1 (strong heading), but p. 45 is rank #16 because
        # many appendix pay-table pages have high dollar-density. A max_pages
        # truncation of 12 (matching suggest.py DEFAULT_MAX_PAGES) must still
        # include p. 45 because it's p. 44's continuation.
        pages = ["neutral"] * 50
        pages[43] = "\nQUANTUM AND TIMING\nClause 7.1 Year 1 3.5% effective 1 July 2024"
        pages[44] = "Year 2 3% or $40 per week whichever is greater effective 1 July 2025"
        # 20 high-dollar-density pages that should outrank p. 45 in raw scoring
        dollar_block = " ".join([f"${n}.00" for n in range(1000, 1100, 5)])
        for i in range(10, 30):
            pages[i] = dollar_block
        result = rank_uplift_pages_with_continuation(pages, include_continuation=True)[:12]
        self.assertIn(44, result)
        self.assertIn(45, result)
        # p. 45 should sit directly after p. 44 in the output
        idx_44 = result.index(44)
        self.assertEqual(result[idx_44 + 1], 45)


if __name__ == "__main__":
    unittest.main()
