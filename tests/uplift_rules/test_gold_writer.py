import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from benchmarking_data_factory.uplift_rules.gold_writer import (
    build_gold_payload, write_gold,
)
from benchmarking_data_factory.uplift_rules.schema import (
    ExtractionInputs, Provenance, RulesDocument, UpliftRule, UpliftRulesSuggestion,
)


def _sample_suggestion() -> UpliftRulesSuggestion:
    inputs = ExtractionInputs(
        pdf_sha256="a" * 64,
        page_numbers=(12, 13),
        page_text_sha256="b" * 64,
        prompt_version="pass1_system_v1",
        prompt_sha256="c" * 64,
        model="claude-sonnet-4-6",
    )
    doc = RulesDocument(
        ae_id="ae999001",
        council="Example Shire Council",
        timing_pattern="annual_fixed_date",
        rules=(
            UpliftRule(
                period_label="Year 1", quantum="3.5%", quantum_type="percentage",
                timing_clause="on or after 1 July 2025", effective_date="2025-07-01",
                source_page=12, confidence=0.9,
            ),
            UpliftRule(
                period_label="Year 2", quantum="the greater of 3% or $40",
                quantum_type="pct_OR_floor",
                timing_clause="on or after 1 July 2026", effective_date="2026-07-01",
                quantum_floor="$40", source_page=12, confidence=0.85,
            ),
        ),
        notes="Two-year term",
        covered_councils=("Example Shire Council",),
        multi_employer=False,
    )
    prov = Provenance(
        inputs=inputs,
        code_git_sha="deadbeef",
        run_started_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        run_completed_at=datetime(2026, 4, 20, 10, 0, 1, tzinfo=timezone.utc),
        run_duration_ms=1000,
        llm_raw_response="{}",
        extraction_status="ok",
    )
    return UpliftRulesSuggestion(document=doc, provenance=prov, suggestion_id="sugg123")


class TestBuildGoldPayload(unittest.TestCase):
    def test_top_level_keys_match_legacy_shape(self):
        payload = build_gold_payload(_sample_suggestion())
        for key in ("uplift_rules", "timing_pattern", "notes", "file",
                    "council", "covered_councils", "multi_employer", "ae_id", "provenance"):
            self.assertIn(key, payload)

    def test_rule_key_order_matches_legacy(self):
        payload = build_gold_payload(_sample_suggestion())
        rule = payload["uplift_rules"][0]
        keys = list(rule.keys())
        self.assertEqual(keys[:3], ["period_label", "effective_date", "quantum"])
        self.assertIn("timing_clause", keys)
        self.assertIn("confidence", keys)

    def test_file_field_is_ae_id_with_pdf_suffix(self):
        payload = build_gold_payload(_sample_suggestion())
        self.assertEqual(payload["file"], "ae999001.pdf")

    def test_provenance_captures_key_fields(self):
        payload = build_gold_payload(_sample_suggestion())
        prov = payload["provenance"]
        self.assertEqual(prov["model"], "claude-sonnet-4-6")
        self.assertEqual(prov["prompt_version"], "pass1_system_v1")
        self.assertEqual(prov["code_git_sha"], "deadbeef")
        self.assertEqual(prov["suggestion_id"], "sugg123")
        self.assertTrue(prov["run_started_at"].startswith("2026-04-20"))

    def test_empty_rules_still_valid(self):
        s = _sample_suggestion()
        s_empty = UpliftRulesSuggestion(
            document=RulesDocument(
                ae_id=s.document.ae_id, council=s.document.council,
                timing_pattern="unknown", rules=(), notes="nothing found",
                covered_councils=s.document.covered_councils, multi_employer=False,
            ),
            provenance=s.provenance, suggestion_id=s.suggestion_id,
        )
        payload = build_gold_payload(s_empty)
        self.assertEqual(payload["uplift_rules"], [])
        self.assertEqual(payload["timing_pattern"], "unknown")


class TestWriteGold(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gold_write_test_"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_expected_filename(self):
        path = write_gold(_sample_suggestion(), self.tmp)
        self.assertEqual(path.name, "ae999001.rules.json")
        self.assertTrue(path.exists())

    def test_written_json_is_valid_and_round_trips(self):
        path = write_gold(_sample_suggestion(), self.tmp)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["council"], "Example Shire Council")
        self.assertEqual(len(loaded["uplift_rules"]), 2)
        self.assertEqual(loaded["uplift_rules"][1]["quantum_floor"], "$40")

    def test_overwrites_existing(self):
        path1 = write_gold(_sample_suggestion(), self.tmp)
        content1 = path1.read_text(encoding="utf-8")
        # Write again with same data — idempotent
        path2 = write_gold(_sample_suggestion(), self.tmp)
        self.assertEqual(path1, path2)
        self.assertEqual(path2.read_text(encoding="utf-8"), content1)


if __name__ == "__main__":
    unittest.main()
