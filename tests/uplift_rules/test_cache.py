import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from benchmarking_data_factory.uplift_rules.cache import (
    SuggestionCache,
    compute_suggestion_id,
)
from benchmarking_data_factory.uplift_rules.schema import (
    ExtractionInputs,
    Provenance,
    RulesDocument,
    UpliftRule,
    UpliftRulesSuggestion,
)


def _sample_suggestion(pdf_sha="a" * 64, page_numbers=(1, 2), model="m") -> UpliftRulesSuggestion:
    inputs = ExtractionInputs(
        pdf_sha256=pdf_sha,
        page_numbers=page_numbers,
        page_text_sha256="b" * 64,
        prompt_version="pass1_system_v1",
        prompt_sha256="c" * 64,
        model=model,
    )
    suggestion_id = compute_suggestion_id(inputs)
    doc = RulesDocument(
        ae_id="ae000001",
        council="Example Shire Council",
        timing_pattern="annual_fixed_date",
        rules=(
            UpliftRule(
                period_label="Year 1",
                quantum="3.5%",
                quantum_type="percentage",
                timing_clause="on or after 1 July 2025",
                effective_date="2025-07-01",
                source_page=12,
                confidence=0.9,
            ),
        ),
        notes="test",
    )
    prov = Provenance(
        inputs=inputs,
        code_git_sha="deadbeef",
        run_started_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        run_completed_at=datetime(2026, 4, 20, 0, 0, 1, tzinfo=timezone.utc),
        run_duration_ms=1000,
        llm_raw_response="{}",
        extraction_status="ok",
    )
    return UpliftRulesSuggestion(document=doc, provenance=prov, suggestion_id=suggestion_id)


class TestComputeSuggestionId(unittest.TestCase):
    def test_stable_across_calls(self):
        inputs = ExtractionInputs("p", (1, 2), "t", "v1", "ps", "m")
        self.assertEqual(compute_suggestion_id(inputs), compute_suggestion_id(inputs))

    def test_changes_when_any_field_changes(self):
        a = ExtractionInputs("p", (1, 2), "t", "v1", "ps", "m")
        for mutation in [
            ExtractionInputs("pX", (1, 2), "t", "v1", "ps", "m"),
            ExtractionInputs("p", (1, 3), "t", "v1", "ps", "m"),
            ExtractionInputs("p", (1, 2), "tX", "v1", "ps", "m"),
            ExtractionInputs("p", (1, 2), "t", "v2", "ps", "m"),
            ExtractionInputs("p", (1, 2), "t", "v1", "psX", "m"),
            ExtractionInputs("p", (1, 2), "t", "v1", "ps", "mX"),
        ]:
            self.assertNotEqual(
                compute_suggestion_id(a),
                compute_suggestion_id(mutation),
            )

    def test_page_order_matters(self):
        a = ExtractionInputs("p", (1, 2), "t", "v", "ps", "m")
        b = ExtractionInputs("p", (2, 1), "t", "v", "ps", "m")
        self.assertNotEqual(compute_suggestion_id(a), compute_suggestion_id(b))


class TestSuggestionCache(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uplift_cache_test_"))
        self.cache = SuggestionCache(self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_returns_none_on_miss(self):
        self.assertIsNone(self.cache.get("nope"))
        self.assertFalse(self.cache.has("nope"))

    def test_put_then_get_round_trip(self):
        s = _sample_suggestion()
        self.cache.put(s)
        self.assertTrue(self.cache.has(s.suggestion_id))
        retrieved = self.cache.get(s.suggestion_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.suggestion_id, s.suggestion_id)
        self.assertEqual(retrieved.document.council, "Example Shire Council")
        self.assertEqual(len(retrieved.document.rules), 1)
        self.assertEqual(retrieved.document.rules[0].effective_date, "2025-07-01")

    def test_put_is_idempotent(self):
        s = _sample_suggestion()
        p1 = self.cache.put(s)
        content1 = p1.read_bytes()
        self.cache.put(s)
        content2 = p1.read_bytes()
        self.assertEqual(content1, content2)

    def test_round_trip_preserves_datetimes(self):
        s = _sample_suggestion()
        self.cache.put(s)
        retrieved = self.cache.get(s.suggestion_id)
        self.assertEqual(retrieved.provenance.run_started_at, s.provenance.run_started_at)
        self.assertEqual(retrieved.provenance.run_duration_ms, 1000)


if __name__ == "__main__":
    unittest.main()
