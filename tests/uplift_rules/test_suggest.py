import json
import shutil
import tempfile
import unittest
from pathlib import Path

from benchmarking_data_factory.uplift_rules.adapters import FakeAdapter
from benchmarking_data_factory.uplift_rules.suggest import (
    SuggestConfig,
    suggest,
)

FIXTURE_RESPONSE = (
    Path(__file__).parent / "fixtures" / "sample_llm_response.json"
).read_text(encoding="utf-8")


def _pages_with_uplift() -> list[str]:
    """Synthetic document: two pages with strong uplift signal."""
    return [
        "Cover page — Example Shire Council Enterprise Agreement",
        "Table of Contents (dotted) .......... 2\n"
        "........................\n........................\n",
        "",
        "\n12. QUANTUM AND TIMING\nYear 1: 3.5% from 1 July 2025.",
        "Appendix A — Pay Rates 2025-26 $1,234.56 $2,345.67 $3,456.78",
        "boilerplate about signatures",
    ]


class TestSuggestHappyPath(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uplift_suggest_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_end_to_end_with_fake_adapter(self):
        adapter = FakeAdapter(
            documents={"ae100001": {"pdf": b"dummy pdf", "pages": _pages_with_uplift()}},
            llm_response=FIXTURE_RESPONSE,
        )
        cfg = SuggestConfig(cache_root=self.tmp, code_git_sha="testsha")
        result = suggest("ae100001", adapter, cfg)
        self.assertEqual(result.document.ae_id, "ae100001")
        self.assertEqual(result.document.council, "Example Shire Council")
        self.assertEqual(result.document.timing_pattern, "annual_fixed_date")
        self.assertEqual(len(result.document.rules), 2)
        self.assertEqual(result.document.rules[0].effective_date, "2025-07-01")
        self.assertEqual(result.document.rules[1].quantum_type, "pct_OR_floor")
        self.assertEqual(result.provenance.extraction_status, "ok")
        self.assertGreaterEqual(result.provenance.run_duration_ms, 0)
        self.assertEqual(result.provenance.code_git_sha, "testsha")

    def test_cache_hit_skips_llm(self):
        call_count = {"n": 0}

        def llm(_system, _user):
            call_count["n"] += 1
            return FIXTURE_RESPONSE

        adapter = FakeAdapter(
            documents={"ae100001": {"pdf": b"dummy pdf", "pages": _pages_with_uplift()}},
            llm_response=llm,
        )
        cfg = SuggestConfig(cache_root=self.tmp, code_git_sha="testsha")
        suggest("ae100001", adapter, cfg)
        suggest("ae100001", adapter, cfg)
        self.assertEqual(call_count["n"], 1, "Second call must hit the cache")

    def test_force_refresh_bypasses_cache(self):
        call_count = {"n": 0}

        def llm(_system, _user):
            call_count["n"] += 1
            return FIXTURE_RESPONSE

        adapter = FakeAdapter(
            documents={"ae100001": {"pdf": b"dummy pdf", "pages": _pages_with_uplift()}},
            llm_response=llm,
        )
        cfg = SuggestConfig(cache_root=self.tmp, code_git_sha="testsha")
        suggest("ae100001", adapter, cfg)
        suggest("ae100001", adapter, cfg, )
        cfg_force = SuggestConfig(cache_root=self.tmp, code_git_sha="testsha", force_refresh=True)
        suggest("ae100001", adapter, cfg_force)
        self.assertEqual(call_count["n"], 2, "force_refresh must skip cache read")

    def test_cache_key_changes_when_pdf_changes(self):
        adapter_v1 = FakeAdapter(
            documents={"ae100001": {"pdf": b"pdf-1", "pages": _pages_with_uplift()}},
            llm_response=FIXTURE_RESPONSE,
        )
        adapter_v2 = FakeAdapter(
            documents={"ae100001": {"pdf": b"pdf-2", "pages": _pages_with_uplift()}},
            llm_response=FIXTURE_RESPONSE,
        )
        cfg = SuggestConfig(cache_root=self.tmp, code_git_sha="testsha")
        r1 = suggest("ae100001", adapter_v1, cfg)
        r2 = suggest("ae100001", adapter_v2, cfg)
        self.assertNotEqual(r1.suggestion_id, r2.suggestion_id)


class TestSuggestErrorPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uplift_suggest_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_llm_raises_does_not_propagate(self):
        def raising_llm(_s, _u):
            raise RuntimeError("simulated network failure")
        adapter = FakeAdapter(
            documents={"ae100001": {"pdf": b"x", "pages": _pages_with_uplift()}},
            llm_response=raising_llm,
        )
        cfg = SuggestConfig(cache_root=self.tmp, code_git_sha="testsha")
        result = suggest("ae100001", adapter, cfg)
        self.assertEqual(result.provenance.extraction_status, "llm_error")
        self.assertEqual(result.document.rules, ())
        self.assertIn("simulated", result.provenance.llm_raw_response)

    def test_invalid_json_response_handled(self):
        adapter = FakeAdapter(
            documents={"ae100001": {"pdf": b"x", "pages": _pages_with_uplift()}},
            llm_response="sorry, I can't help with that",
        )
        cfg = SuggestConfig(cache_root=self.tmp, code_git_sha="testsha")
        result = suggest("ae100001", adapter, cfg)
        self.assertEqual(result.provenance.extraction_status, "llm_error")
        self.assertEqual(result.document.rules, ())

    def test_empty_response_handled(self):
        adapter = FakeAdapter(
            documents={"ae100001": {"pdf": b"x", "pages": _pages_with_uplift()}},
            llm_response="",
        )
        cfg = SuggestConfig(cache_root=self.tmp, code_git_sha="testsha")
        result = suggest("ae100001", adapter, cfg)
        self.assertEqual(result.provenance.extraction_status, "empty")

    def test_response_with_fences_is_cleaned(self):
        fenced = "```json\n" + FIXTURE_RESPONSE + "\n```"
        adapter = FakeAdapter(
            documents={"ae100001": {"pdf": b"x", "pages": _pages_with_uplift()}},
            llm_response=fenced,
        )
        cfg = SuggestConfig(cache_root=self.tmp, code_git_sha="testsha")
        result = suggest("ae100001", adapter, cfg)
        self.assertEqual(result.provenance.extraction_status, "ok")
        self.assertEqual(len(result.document.rules), 2)


class TestSuggestContinuationPages(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uplift_suggest_continuation_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_suggest_config_default_has_continuation_disabled(self):
        # Continuation enabled by default as of 2026-04-22 (multi-page rules were silently truncating).
        self.assertIs(SuggestConfig().include_continuation_pages, True)

    def test_suggest_with_continuation_enabled_passes_more_pages_to_adapter(self):
        # Page 2 is primary (heading); page 3 has no signal and is the continuation candidate.
        # With include_continuation_pages=True, both must appear in provenance.inputs.page_numbers.
        pages = [
            "Cover page for Test Council",
            "\nQUANTUM AND TIMING\nYear 1: 3% from 1 July 2025.",
            "This clause continues on this page with more details.",
            "boilerplate",
        ]
        adapter = FakeAdapter(
            documents={"ae200001": {"pdf": b"test pdf", "pages": pages}},
            llm_response=FIXTURE_RESPONSE,
        )
        cfg = SuggestConfig(
            cache_root=self.tmp,
            code_git_sha="testsha",
            include_continuation_pages=True,
        )
        result = suggest("ae200001", adapter, cfg)
        self.assertIn(2, result.provenance.inputs.page_numbers)
        self.assertIn(3, result.provenance.inputs.page_numbers)


class TestProvenanceIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uplift_suggest_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cache_replay_preserves_every_field(self):
        adapter = FakeAdapter(
            documents={"ae100001": {"pdf": b"x", "pages": _pages_with_uplift()}},
            llm_response=FIXTURE_RESPONSE,
        )
        cfg = SuggestConfig(cache_root=self.tmp, code_git_sha="testsha")
        first = suggest("ae100001", adapter, cfg)
        second = suggest("ae100001", adapter, cfg)
        self.assertEqual(first, second)  # dataclass equality — all fields match


if __name__ == "__main__":
    unittest.main()
