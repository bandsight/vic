"""Unit tests for the rate cap refresh module.

Tests mock `fetch_page` so no network call is made. The live CSVs are never
touched — the tests copy the real CSVs into a tmp dir and run refresh against
that copy, so test runs are idempotent and safe.
"""
from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarking_data_factory.uplift_rules.rate_cap import refresh as refresh_mod
from benchmarking_data_factory.uplift_rules.rate_cap.refresh import (
    HigherCapException,
    RefreshError,
    StandardCap,
    derive_lga_short_name,
    parse_page,
    refresh_exceptions,
    refresh_standard_caps,
    refresh_year_statuses,
    run_refresh,
)

FIXTURE_HTML = (
    Path(__file__).parent / "fixtures" / "esc_page_snapshot.html"
).read_text(encoding="utf-8")

# Source of truth for live CSVs — tests only READ these, never write
LIVE_DATA_DIR = (
    Path(__file__).parent.parent.parent
    / "src" / "benchmarking_data_factory" / "uplift_rules" / "external" / "rate-cap"
)


class TestParsePage(unittest.TestCase):
    def test_extracts_current_year_cap(self):
        standard, _, _ = parse_page(FIXTURE_HTML)
        self.assertEqual(standard.financial_year, "2025-26")
        self.assertEqual(standard.rate_cap_pct, "3.00")

    def test_extracts_exceptions(self):
        _, exceptions, _ = parse_page(FIXTURE_HTML)
        names = sorted(e.council_name for e in exceptions)
        self.assertIn("Brimbank City Council", names)
        self.assertIn("Melton City Council", names)

    def test_exception_short_names(self):
        _, exceptions, _ = parse_page(FIXTURE_HTML)
        by_council = {e.council_name: e for e in exceptions}
        self.assertEqual(by_council["Brimbank City Council"].lga_short_name, "Brimbank")
        self.assertEqual(by_council["Melton City Council"].lga_short_name, "Melton")

    def test_referenced_years_includes_history(self):
        _, _, years = parse_page(FIXTURE_HTML)
        for y in ("2023-24", "2024-25", "2025-26"):
            self.assertIn(y, years)

    def test_raises_on_missing_current_year(self):
        bad_html = "<html><body><p>Hello world.</p></body></html>"
        with self.assertRaises(RefreshError):
            parse_page(bad_html)


class TestDeriveLgaShortName(unittest.TestCase):
    def test_strips_shire_council(self):
        self.assertEqual(derive_lga_short_name("Pyrenees Shire Council"), "Pyrenees")

    def test_strips_city_council(self):
        self.assertEqual(derive_lga_short_name("Brimbank City Council"), "Brimbank")

    def test_strips_rural_city_council(self):
        self.assertEqual(
            derive_lga_short_name("Ararat Rural City Council"), "Ararat"
        )

    def test_strips_borough_council(self):
        self.assertEqual(
            derive_lga_short_name("Queenscliffe Borough Council"), "Queenscliffe"
        )


class TestRefreshStandardCaps(unittest.TestCase):
    def test_adds_new_year(self):
        existing = [
            {"period_year_label": "2024-25", "rate_cap_value": "2.75",
             "source_reference": "x", "source_type": "y",
             "effective_date_or_applicable_year": "2024-25", "notes": ""},
        ]
        new = StandardCap(financial_year="2025-26", rate_cap_pct="3.00")
        updated, messages = refresh_standard_caps(existing, new)
        self.assertEqual(len(updated), 2)
        self.assertTrue(any("Added" in m for m in messages))

    def test_idempotent_when_year_exists(self):
        existing = [
            {"period_year_label": "2025-26", "rate_cap_value": "3.00",
             "source_reference": "x", "source_type": "y",
             "effective_date_or_applicable_year": "2025-26", "notes": ""},
        ]
        new = StandardCap(financial_year="2025-26", rate_cap_pct="3.00")
        updated, messages = refresh_standard_caps(existing, new)
        self.assertEqual(len(updated), 1)
        self.assertIn("No new standard cap", messages)


class TestRefreshExceptions(unittest.TestCase):
    def test_adds_new_exception(self):
        existing: list[dict[str, str]] = []
        exc = HigherCapException(
            council_name="Brimbank City Council",
            lga_short_name="Brimbank",
            financial_year="2025-26",
            approved_cap_pct="3.50",
        )
        updated, messages = refresh_exceptions(existing, [exc])
        self.assertEqual(len(updated), 1)
        self.assertTrue(any("Added exception" in m for m in messages))

    def test_idempotent_when_key_exists(self):
        existing = [
            {"council_name": "Brimbank City Council",
             "lga_short_name": "Brimbank", "financial_year": "2025-26",
             "approved_cap_pct": "3.50", "source_url": "x",
             "captured_date": "2026-04-20", "notes": ""},
        ]
        exc = HigherCapException(
            council_name="Brimbank City Council",
            lga_short_name="Brimbank",
            financial_year="2025-26",
            approved_cap_pct="3.50",
        )
        updated, messages = refresh_exceptions(existing, [exc])
        self.assertEqual(len(updated), 1)
        self.assertTrue(any("Already known" in m for m in messages))


class TestRefreshYearStatuses(unittest.TestCase):
    def test_confirms_pending_when_referenced(self):
        existing = [
            {"financial_year": "2024-25", "resolution_status": "pending_exceptions_check",
             "confirmed_date": "", "notes": ""},
        ]
        updated, messages = refresh_year_statuses(existing, ["2024-25", "2025-26"], "2025-26")
        self.assertEqual(updated[0]["resolution_status"], "confirmed")
        self.assertTrue(any("Confirmed year 2024-25" in m for m in messages))

    def test_confirms_pending_when_past(self):
        # 2023-24 is in the past relative to 2025-26, so it's confirmed via absence
        existing = [
            {"financial_year": "2023-24", "resolution_status": "pending_exceptions_check",
             "confirmed_date": "", "notes": ""},
        ]
        updated, messages = refresh_year_statuses(existing, ["2025-26"], "2025-26")
        self.assertEqual(updated[0]["resolution_status"], "confirmed")
        self.assertIn("absence", updated[0]["notes"])


class TestRunRefreshEndToEnd(unittest.TestCase):
    """Run the full pipeline with a tmp data dir — never touches live CSVs."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rate_cap_refresh_test_"))
        # Copy live CSVs into tmp so we diff against realistic data
        for name in (
            "standard-statewide-rate-caps.csv",
            "higher-cap-exceptions.csv",
            "rate-cap-year-status.csv",
        ):
            shutil.copy2(LIVE_DATA_DIR / name, self.tmp / name)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dry_run_writes_nothing(self):
        with patch.object(refresh_mod, "fetch_page", return_value=FIXTURE_HTML):
            before = {p.name: p.read_bytes() for p in self.tmp.iterdir()}
            result = run_refresh(dry_run=True, data_dir=self.tmp)
            after = {p.name: p.read_bytes() for p in self.tmp.iterdir()}
            self.assertTrue(result.dry_run)
            self.assertEqual(result.files_written, ())
            self.assertEqual(before, after, "Dry run must not modify any file")

    def test_non_dry_run_writes_files(self):
        with patch.object(refresh_mod, "fetch_page", return_value=FIXTURE_HTML):
            result = run_refresh(dry_run=False, data_dir=self.tmp)
            self.assertFalse(result.dry_run)
            self.assertEqual(len(result.files_written), 3)
            for p in result.files_written:
                self.assertTrue(p.exists())

    def test_full_run_is_idempotent(self):
        """Running refresh twice with the same HTML must produce identical files."""
        with patch.object(refresh_mod, "fetch_page", return_value=FIXTURE_HTML):
            run_refresh(dry_run=False, data_dir=self.tmp)
            snapshot_1 = {p.name: p.read_bytes() for p in self.tmp.iterdir()}
            run_refresh(dry_run=False, data_dir=self.tmp)
            snapshot_2 = {p.name: p.read_bytes() for p in self.tmp.iterdir()}
        self.assertEqual(snapshot_1, snapshot_2, "Refresh must be idempotent")

    def test_result_messages_contain_parsed_cap(self):
        with patch.object(refresh_mod, "fetch_page", return_value=FIXTURE_HTML):
            result = run_refresh(dry_run=True, data_dir=self.tmp)
            self.assertEqual(result.standard_cap.financial_year, "2025-26")
            self.assertEqual(result.standard_cap.rate_cap_pct, "3.00")


class TestNetworkFailureSurface(unittest.TestCase):
    def test_fetch_failure_raises_refresh_error_from_run_refresh(self):
        def fail(*_, **__):
            raise RefreshError("boom")
        with patch.object(refresh_mod, "fetch_page", side_effect=fail):
            with self.assertRaises(RefreshError):
                run_refresh(dry_run=True, data_dir=Path("/tmp"))


if __name__ == "__main__":
    unittest.main()
