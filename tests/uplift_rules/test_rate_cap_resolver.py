"""Unit tests for the rate cap resolver.

These tests use the real CSV data copied into workbench. Known values as of Brief 2:
  - 2024-25 statewide cap: 2.75%
  - 2025-26 statewide cap: 3.00%
  - 2026-27 statewide cap: 2.75%
If those values change due to ESC refreshes, update the test constants.
"""
from __future__ import annotations

import unittest

from benchmarking_data_factory.uplift_rules.rate_cap.resolver import (
    RateCapResolutionError,
    classify_rate_cap_mode,
    date_to_financial_year,
    get_pending_rate_cap,
    get_year_status,
    resolve_effective_rate,
    resolve_rate_cap,
)


class TestDateToFinancialYear(unittest.TestCase):
    def test_july_is_start_of_fy(self):
        self.assertEqual(date_to_financial_year("2024-07-01"), "2024-25")

    def test_december_still_in_same_fy(self):
        self.assertEqual(date_to_financial_year("2024-12-31"), "2024-25")

    def test_january_rolls_to_prior_fy(self):
        self.assertEqual(date_to_financial_year("2025-01-15"), "2024-25")

    def test_june_end_of_fy(self):
        self.assertEqual(date_to_financial_year("2025-06-30"), "2024-25")

    def test_long_month_name(self):
        self.assertEqual(date_to_financial_year("1 July 2024"), "2024-25")

    def test_american_format(self):
        self.assertEqual(date_to_financial_year("July 1, 2024"), "2024-25")

    def test_invalid_raises(self):
        with self.assertRaises(RateCapResolutionError):
            date_to_financial_year("banana")


class TestClassifyRateCapMode(unittest.TestCase):
    def test_no_reference(self):
        self.assertEqual(classify_rate_cap_mode("3% or $55 per week"), "no_rate_cap_ref")

    def test_full_rate_cap(self):
        self.assertEqual(
            classify_rate_cap_mode("the gazetted rate cap for that year"),
            "full_rate_cap",
        )

    def test_pct_of_rate_cap(self):
        self.assertEqual(
            classify_rate_cap_mode("2.5% of the rate cap"),
            "pct_of_rate_cap",
        )

    def test_plus_delta(self):
        self.assertEqual(
            classify_rate_cap_mode("0.5% above the rate cap"),
            "rate_cap_plus_minus",
        )

    def test_minus_delta(self):
        self.assertEqual(
            classify_rate_cap_mode("0.25% below the rate cap"),
            "rate_cap_plus_minus",
        )

    def test_threshold(self):
        self.assertEqual(
            classify_rate_cap_mode("rate cap if it exceeds 2.5"),
            "rate_cap_threshold",
        )

    def test_empty_string(self):
        self.assertEqual(classify_rate_cap_mode(""), "no_rate_cap_ref")

    def test_none_input(self):
        self.assertEqual(classify_rate_cap_mode(None), "no_rate_cap_ref")

    def test_less_than_delta(self):
        self.assertEqual(
            classify_rate_cap_mode("0.5% less than the rate cap"),
            "rate_cap_plus_minus",
        )

    def test_greater_than_delta(self):
        self.assertEqual(
            classify_rate_cap_mode("0.5% greater than the rate cap"),
            "rate_cap_plus_minus",
        )

    def test_less_than_with_official_general(self):
        self.assertEqual(
            classify_rate_cap_mode(
                "a percentage increase 0.5% less than the official general rate cap for the financial year 2023/24"
            ),
            "rate_cap_plus_minus",
        )

    def test_inverted_minus(self):
        self.assertEqual(
            classify_rate_cap_mode("rate cap minus 0.5%"),
            "rate_cap_plus_minus",
        )

    def test_inverted_plus(self):
        self.assertEqual(
            classify_rate_cap_mode("rate cap plus 0.25%"),
            "rate_cap_plus_minus",
        )

    def test_pct_of_official_rate_cap(self):
        # Regression (Wyndham 2026-04-23): "90% of the official rate cap"
        # was being misclassified as full_rate_cap because FRACTION_RE
        # did not tolerate an adjective between "of the" and "rate cap".
        self.assertEqual(
            classify_rate_cap_mode("90% of the official rate cap"),
            "pct_of_rate_cap",
        )

    def test_pct_of_general_rate_cap(self):
        self.assertEqual(
            classify_rate_cap_mode("95% of the general rate cap"),
            "pct_of_rate_cap",
        )

    def test_pct_of_gazetted_local_government_rate_cap(self):
        self.assertEqual(
            classify_rate_cap_mode("80% of the gazetted Local Government rate cap"),
            "pct_of_rate_cap",
        )

    def test_base_salary_or_rate_cap_is_not_fractional_rate_cap(self):
        self.assertEqual(
            classify_rate_cap_mode("3% of Base Salary or rate cap, whichever is the greater"),
            "full_rate_cap",
        )


class TestWyndhamStyleFractionalRateCap(unittest.TestCase):
    """Regression (2026-04-23): Wyndham's "90% of the official rate cap,
    or 3.0% or $50/week, whichever is greater" was resolving to 90% flat
    (i.e. a 90% wage increase) because (a) FRACTION_RE missed "official"
    and (b) _parse_fixed_floor_pct then picked 90% as the floor.
    """

    def test_wyndham_year_two_resolves_to_three_percent(self):
        result = resolve_effective_rate(
            "Wyndham",
            "2024-25",
            "90% of the official rate cap as advised by the Minister for Local Government, or 3.0% or $50 per week, whichever is greater",
        )
        self.assertEqual(result["mode"], "pct_of_rate_cap")
        self.assertAlmostEqual(result["raw_rate_cap"], 2.75)
        self.assertAlmostEqual(result["fixed_floor_pct"], 3.0)
        # 90% of 2.75% = 2.475% → floor max(2.475, 3.0) = 3.0%
        self.assertAlmostEqual(result["effective_rate"], 3.0)

    def test_wyndham_year_three_resolves_to_two_point_eight(self):
        result = resolve_effective_rate(
            "Wyndham",
            "2025-26",
            "90% of the official rate cap as advised by the Minister for Local Government, or 2.8% or $50 per week, whichever is greater",
        )
        self.assertEqual(result["mode"], "pct_of_rate_cap")
        # 90% of cap vs 2.8% floor — we expect the floor to win here too
        # (the 2025-26 statewide cap is well below 3.1%, so 0.9 × cap < 2.8%)
        self.assertAlmostEqual(result["fixed_floor_pct"], 2.8)
        self.assertAlmostEqual(result["effective_rate"], 2.8)

    def test_plain_pct_of_rate_cap_still_works(self):
        # Baseline: no adjective — classical pct_of_rate_cap.
        result = resolve_effective_rate(
            "Wyndham",
            "2024-25",
            "90% of the rate cap",
        )
        self.assertEqual(result["mode"], "pct_of_rate_cap")
        self.assertIsNone(result["fixed_floor_pct"])
        self.assertAlmostEqual(result["effective_rate"], 2.475)

    def test_dollar_floor_per_week_parsed_wyndham(self):
        result = resolve_effective_rate(
            "Wyndham",
            "2024-25",
            "90% of the official rate cap as advised by the Minister for Local Government, or 3.0% or $50 per week, whichever is greater",
        )
        self.assertEqual(result["dollar_floor_per_week"], 50.0)

    def test_dollar_floor_per_week_absent_when_not_specified(self):
        result = resolve_effective_rate("Wyndham", "2024-25", "3.0%")
        self.assertIsNone(result["dollar_floor_per_week"])

    def test_wyndham_threshold_difference_below_trigger_uses_base_quantum(self):
        result = resolve_effective_rate(
            "Wyndham",
            "2022-23",
            "2.0% or $35 per week, whichever is greater. Where rate capping increases above 2.5% the difference will be added to the 2.0% quantum.",
        )

        self.assertEqual(result["mode"], "rate_cap_threshold")
        self.assertAlmostEqual(result["raw_rate_cap"], 1.75)
        self.assertAlmostEqual(result["threshold"], 2.5)
        self.assertAlmostEqual(result["effective_rate"], 2.0)
        self.assertAlmostEqual(result["delta"], 0.0)

    def test_wyndham_threshold_difference_above_trigger_adds_only_excess(self):
        result = resolve_effective_rate(
            "Wyndham",
            "2023-24",
            "2.0% or $35 per week, whichever is greater. Where rate capping increases above 2.5% the difference will be added to the 2.0% quantum.",
        )

        self.assertEqual(result["mode"], "rate_cap_threshold")
        self.assertAlmostEqual(result["raw_rate_cap"], 3.5)
        self.assertAlmostEqual(result["threshold"], 2.5)
        self.assertAlmostEqual(result["effective_rate"], 3.0)
        self.assertAlmostEqual(result["delta"], 1.0)


class TestLoddonStyleFractionalRateCap(unittest.TestCase):
    def test_loddon_year_two_uses_eighty_percent_of_gazetted_local_government_cap(self):
        result = resolve_effective_rate(
            "Loddon",
            "2023-24",
            "1.5% or $20 per week or 80% of the gazetted Local Government rate cap, whichever is the greater",
        )

        self.assertEqual(result["mode"], "pct_of_rate_cap")
        self.assertAlmostEqual(result["raw_rate_cap"], 3.5)
        self.assertAlmostEqual(result["fraction"], 0.8)
        self.assertAlmostEqual(result["fixed_floor_pct"], 1.5)
        self.assertAlmostEqual(result["effective_rate"], 2.8)
        self.assertEqual(result["dollar_floor_per_week"], 20.0)
        self.assertNotEqual(result["fixed_floor_pct"], 80.0)


class TestResolveRateCap(unittest.TestCase):
    def test_known_confirmed_year_2024_25(self):
        # 2024-25 statewide cap is 2.75% (set by government gazette Dec 2023)
        result = resolve_rate_cap("Alpine", "2024-25")
        self.assertEqual(result, 2.75)

    def test_unknown_year_raises(self):
        with self.assertRaises(RateCapResolutionError):
            resolve_rate_cap("Alpine", "2099-00")

    def test_year_status_known(self):
        # 2024-25 should be confirmed by now
        self.assertEqual(get_year_status("2024-25"), "confirmed")


class TestResolveEffectiveRate(unittest.TestCase):
    def test_no_rate_cap_ref_returns_clean_dict(self):
        result = resolve_effective_rate("Alpine", "2024-25", "3% or $55 per week")
        self.assertEqual(result["mode"], "no_rate_cap_ref")
        self.assertIsNone(result["effective_rate"])
        self.assertIsNone(result["raw_rate_cap"])
        self.assertFalse(result["unresolved"])  # we never tried to resolve

    def test_full_rate_cap_returns_cap_value(self):
        # quantum "the rate cap" in 2024-25 → 2.75%
        result = resolve_effective_rate("Alpine", "2024-25", "the rate cap")
        self.assertEqual(result["mode"], "full_rate_cap")
        self.assertEqual(result["effective_rate"], 2.75)
        self.assertEqual(result["raw_rate_cap"], 2.75)

    def test_pct_of_rate_cap(self):
        # 50% of 2.75 = 1.375
        result = resolve_effective_rate("Alpine", "2024-25", "50% of the rate cap")
        self.assertEqual(result["mode"], "pct_of_rate_cap")
        self.assertAlmostEqual(result["effective_rate"], 1.375, places=3)

    def test_above_rate_cap(self):
        # 2.75 + 0.25 = 3.0
        result = resolve_effective_rate("Alpine", "2024-25", "0.25% above the rate cap")
        self.assertEqual(result["mode"], "rate_cap_plus_minus")
        self.assertAlmostEqual(result["effective_rate"], 3.0, places=3)
        self.assertAlmostEqual(result["delta"], 0.25, places=3)

    def test_below_rate_cap(self):
        # 2.75 - 0.5 = 2.25
        result = resolve_effective_rate("Alpine", "2024-25", "0.5% below the rate cap")
        self.assertAlmostEqual(result["effective_rate"], 2.25, places=3)
        self.assertAlmostEqual(result["delta"], -0.5, places=3)

    def test_below_gazetted_rate_cap(self):
        result = resolve_effective_rate(
            "Latrobe",
            "2023-24",
            "1.3%, or $20 per week, whichever is greater; or 0.50% below the gazetted rate cap, whichever is greater",
        )
        self.assertEqual(result["mode"], "rate_cap_plus_minus")
        self.assertAlmostEqual(result["raw_rate_cap"], 3.5, places=3)
        self.assertAlmostEqual(result["effective_rate"], 3.0, places=3)
        self.assertAlmostEqual(result["delta"], -0.5, places=3)

    def test_threshold_exceeded(self):
        # Rate cap 2.75% exceeds threshold 2.0 → returns 2.75
        result = resolve_effective_rate(
            "Alpine", "2024-25", "rate cap if it exceeds 2.0 percent"
        )
        self.assertEqual(result["mode"], "rate_cap_threshold")
        self.assertEqual(result["effective_rate"], 2.75)
        self.assertEqual(result["threshold"], 2.0)

    def test_threshold_not_exceeded(self):
        # Rate cap 2.75 does NOT exceed threshold 3.0 → effective_rate stays None
        result = resolve_effective_rate(
            "Alpine", "2024-25", "rate cap if it exceeds 3.0 percent"
        )
        self.assertEqual(result["mode"], "rate_cap_threshold")
        self.assertIsNone(result["effective_rate"])
        self.assertTrue(result["unresolved"])

    def test_fixed_floor_raises_effective_rate(self):
        # 50% of 2.75 = 1.375, but 2% floor should win
        result = resolve_effective_rate(
            "Alpine", "2024-25", "50% of the rate cap or 2% whichever is greater"
        )
        self.assertAlmostEqual(result["effective_rate"], 2.0, places=3)
        self.assertIn("floor", result["resolution_note"])

    def test_base_salary_or_rate_cap_uses_fixed_percentage_floor(self):
        result = resolve_effective_rate(
            "Strathbogie",
            "2024-25",
            "3% of Base Salary or rate cap, whichever is the greater",
        )
        self.assertEqual(result["mode"], "full_rate_cap")
        self.assertAlmostEqual(result["raw_rate_cap"], 2.75, places=3)
        self.assertAlmostEqual(result["fixed_floor_pct"], 3.0, places=3)
        self.assertAlmostEqual(result["effective_rate"], 3.0, places=3)

    def test_queenscliffe_less_than_phrasing(self):
        """ae517676 Queenscliffe — 0.5% less than the rate cap for FY2023-24."""
        result = resolve_effective_rate(
            "Borough of Queenscliffe",
            "2023-24",
            "The greater of: a 2.0% increase, or a percentage increase 0.5% less than the official general rate cap for the financial year 2023/24, or $27.00 per week increase",
        )
        self.assertEqual(result["mode"], "rate_cap_plus_minus")
        self.assertAlmostEqual(result["raw_rate_cap"], 3.5, places=3)
        self.assertAlmostEqual(result["effective_rate"], 3.0, places=3)
        self.assertAlmostEqual(result["delta"], -0.5, places=3)

    def test_inverted_minus_resolves(self):
        result = resolve_effective_rate(
            "Borough of Queenscliffe", "2023-24", "rate cap minus 0.5%"
        )
        self.assertEqual(result["mode"], "rate_cap_plus_minus")
        self.assertAlmostEqual(result["delta"], -0.5, places=3)


class TestGetPendingRateCap(unittest.TestCase):
    def test_confirmed_year_returns_cap(self):
        result = get_pending_rate_cap("2024-07-01")
        self.assertIsNotNone(result)
        fy, cap = result
        self.assertEqual(fy, "2024-25")
        self.assertEqual(cap, 2.75)

    def test_bad_date_returns_none(self):
        self.assertIsNone(get_pending_rate_cap("banana"))


if __name__ == "__main__":
    unittest.main()
