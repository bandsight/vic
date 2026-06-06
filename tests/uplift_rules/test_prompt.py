import unittest

from benchmarking_data_factory.uplift_rules.prompt import PROMPTS, get_prompt
from benchmarking_data_factory.uplift_rules.schema import CURRENT_PROMPT_VERSION


class TestPromptRegistry(unittest.TestCase):
    def test_current_version_is_registered(self):
        self.assertIn(CURRENT_PROMPT_VERSION, PROMPTS)

    def test_get_prompt_returns_correct_sha(self):
        p = get_prompt(CURRENT_PROMPT_VERSION)
        self.assertEqual(p.version, CURRENT_PROMPT_VERSION)
        self.assertEqual(len(p.sha256), 64)  # hex sha256

    def test_sha_is_derived_from_text(self):
        import hashlib
        p = get_prompt(CURRENT_PROMPT_VERSION)
        expected = hashlib.sha256(p.system.encode("utf-8")).hexdigest()
        self.assertEqual(p.sha256, expected)

    def test_unknown_version_raises(self):
        with self.assertRaises(KeyError):
            get_prompt("does_not_exist")

    def test_prompt_mentions_key_conventions(self):
        p = get_prompt(CURRENT_PROMPT_VERSION)
        # Regression guards — if these disappear the prompt is broken
        for needle in (
            "quantum_type",
            "source_page",
            "timing_clause",
            "YYYY-MM-DD",
            "JSON",
        ):
            self.assertIn(needle, p.system)


if __name__ == "__main__":
    unittest.main()
