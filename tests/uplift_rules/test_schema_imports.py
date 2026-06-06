"""Smoke test: schema module imports and dataclasses are constructible."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from benchmarking_data_factory.uplift_rules.schema import (
    CURRENT_PROMPT_VERSION,
    ExtractionInputs,
    Provenance,
    RulesDocument,
    UpliftRule,
    UpliftRulesSuggestion,
)


class TestSchemaImports(unittest.TestCase):
    def test_uplift_rule_constructible(self):
        r = UpliftRule(
            period_label="Year 1",
            quantum="3%",
            quantum_type="percentage",
            timing_clause="First pay period after 1 July 2024",
            effective_date="2024-07-01",
            confidence=0.97,
        )
        self.assertEqual(r.period_label, "Year 1")
        self.assertEqual(r.quantum_type, "percentage")

    def test_rules_document_constructible(self):
        r = UpliftRule(
            period_label="Year 1",
            quantum="3%",
            quantum_type="percentage",
            timing_clause="First pay period after 1 July 2024",
        )
        doc = RulesDocument(
            ae_id="ae521669",
            council="Pyrenees Shire Council",
            timing_pattern="annual_fixed_date",
            rules=(r,),
        )
        self.assertEqual(doc.ae_id, "ae521669")
        self.assertEqual(len(doc.rules), 1)

    def test_provenance_constructible(self):
        inputs = ExtractionInputs(
            pdf_sha256="a" * 64,
            page_numbers=(75, 76),
            page_text_sha256="b" * 64,
            prompt_version=CURRENT_PROMPT_VERSION,
            prompt_sha256="c" * 64,
            model="claude-sonnet-4-20250514",
        )
        now = datetime.now(timezone.utc)
        prov = Provenance(
            inputs=inputs,
            code_git_sha="d" * 40,
            run_started_at=now,
            run_completed_at=now,
            run_duration_ms=0,
            llm_raw_response="",
            extraction_status="empty",
        )
        self.assertEqual(prov.inputs.prompt_version, "pass1_system_v2")

    def test_current_prompt_version(self):
        self.assertEqual(CURRENT_PROMPT_VERSION, "pass1_system_v2")


if __name__ == "__main__":
    unittest.main()
