import hashlib
import tempfile
import unittest
from pathlib import Path

from benchmarking_data_factory.uplift_rules.real_adapter import RealAdapter


class TestRealAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="real_adapter_test_"))
        self.pdf_path = self.tmp / "test.pdf"
        self.pdf_path.write_bytes(b"fake pdf bytes")
        self.pages = ["page one", "page two", "page three"]

        self.adapter = RealAdapter(
            pdf_path_resolver=lambda ae_id: self.pdf_path,
            page_count_fn=lambda ae_id: len(self.pages),
            page_text_fn=lambda ae_id, n: self.pages[n - 1],
            all_page_texts_fn=lambda ae_id: list(self.pages),
            call_llm_fn=self._fake_call_llm,
            default_model="claude-sonnet-4-6",
        )
        self.last_llm_kwargs = None

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_call_llm(self, system, user_blocks, max_tokens, model=None):
        # Record the call; echo back a canned JSON-ish string.
        self.last_llm_kwargs = {
            "system": system,
            "user_blocks": user_blocks,
            "max_tokens": max_tokens,
            "model": model,
        }
        return '{"council":"X","rules":[]}'

    def test_pdf_sha256_matches_file_content(self):
        expected = hashlib.sha256(b"fake pdf bytes").hexdigest()
        self.assertEqual(self.adapter.pdf_sha256("ae1"), expected)

    def test_page_count_and_text(self):
        self.assertEqual(self.adapter.page_count("ae1"), 3)
        self.assertEqual(self.adapter.page_text("ae1", 2), "page two")
        self.assertEqual(self.adapter.all_page_texts("ae1"), ["page one", "page two", "page three"])

    def test_call_llm_wraps_user_text_and_passes_kwargs(self):
        out = self.adapter.call_llm("sys prompt", "user text", max_tokens=500, model="claude-sonnet-4-6")
        self.assertIn("council", out)
        self.assertEqual(self.last_llm_kwargs["system"], "sys prompt")
        self.assertEqual(self.last_llm_kwargs["user_blocks"], [{"type": "text", "text": "user text"}])
        self.assertEqual(self.last_llm_kwargs["max_tokens"], 500)
        self.assertEqual(self.last_llm_kwargs["model"], "claude-sonnet-4-6")

    def test_call_llm_falls_back_when_model_kwarg_rejected(self):
        # Simulate a legacy call_llm that doesn't accept model=
        def legacy_call_llm(system, user_blocks, max_tokens):
            return "legacy ok"
        legacy_adapter = RealAdapter(
            pdf_path_resolver=lambda ae_id: self.pdf_path,
            page_count_fn=lambda ae_id: 1,
            page_text_fn=lambda ae_id, n: "",
            all_page_texts_fn=lambda ae_id: [""],
            call_llm_fn=legacy_call_llm,
            default_model="m",
        )
        out = legacy_adapter.call_llm("s", "u", max_tokens=100, model="m")
        self.assertEqual(out, "legacy ok")


if __name__ == "__main__":
    unittest.main()
