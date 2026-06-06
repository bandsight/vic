import unittest
from unittest.mock import patch

# Import the CLI module directly
import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_scripts_dir))
import run_uplift_rules as cli  # type: ignore


class TestIsStale(unittest.TestCase):
    def _canonical_with(self, suggestion_dict):
        return {
            "sections": {
                "uplift_rules": {
                    "data": {"suggestion": suggestion_dict},
                },
            },
        }

    def _good_suggestion(self, prompt_v="pass1_system_v1", code_sha="git123", status="ok"):
        return {
            "provenance": {
                "inputs": {"prompt_version": prompt_v},
                "code_git_sha": code_sha,
                "extraction_status": status,
            },
        }

    def test_no_suggestion_is_stale(self):
        self.assertTrue(cli._is_stale({}, "v1", "sha"))
        self.assertTrue(cli._is_stale({"sections": {}}, "v1", "sha"))
        self.assertTrue(cli._is_stale({"sections": {"uplift_rules": {}}}, "v1", "sha"))

    def test_matching_version_and_sha_ok_is_fresh(self):
        c = self._canonical_with(self._good_suggestion("v1", "sha1", "ok"))
        self.assertFalse(cli._is_stale(c, "v1", "sha1"))

    def test_stale_on_prompt_version_mismatch(self):
        c = self._canonical_with(self._good_suggestion("v0", "sha1", "ok"))
        self.assertTrue(cli._is_stale(c, "v1", "sha1"))

    def test_stale_on_code_sha_mismatch(self):
        c = self._canonical_with(self._good_suggestion("v1", "sha-old", "ok"))
        self.assertTrue(cli._is_stale(c, "v1", "sha-new"))

    def test_stale_on_llm_error_status(self):
        c = self._canonical_with(self._good_suggestion("v1", "sha1", "llm_error"))
        self.assertTrue(cli._is_stale(c, "v1", "sha1"))

    def test_stale_on_empty_status(self):
        c = self._canonical_with(self._good_suggestion("v1", "sha1", "empty"))
        self.assertTrue(cli._is_stale(c, "v1", "sha1"))


class TestMainCliArgParse(unittest.TestCase):
    def test_requires_one_target(self):
        with self.assertRaises(SystemExit):
            cli.main_cli([])

    def test_mutually_exclusive_targets(self):
        with self.assertRaises(SystemExit):
            cli.main_cli(["--ae-id", "ae1", "--all-missing"])


class TestDryRun(unittest.TestCase):
    """Dry run must not touch LLM or write anything."""

    def test_dry_run_single_id(self):
        # Fake main.list_pdfs + get_canonical so we don't need fitz
        fake_main = type("FakeMain", (), {
            "list_pdfs": staticmethod(lambda: ["ae111111"]),
            "get_canonical": staticmethod(lambda aid: {}),
        })
        with patch.dict(sys.modules, {"main": fake_main}), \
             patch.object(cli, "_resolve_git_sha", return_value="sha-test"):
            code = cli.main_cli(["--ae-id", "ae111111", "--dry-run", "--quiet"])
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
