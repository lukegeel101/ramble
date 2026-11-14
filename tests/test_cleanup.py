"""cleanup.py: the local filler strip, the glossary hint, prompt assembly, and `run` against the fake claude."""
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests.helpers import ROOT, InstallCase

sys.path.insert(0, str(ROOT))
import cleanup  # noqa: E402


class Strip(unittest.TestCase):
    def test_fillers_and_lead_in(self):
        self.assertEqual(cleanup.strip("okay so um can you uh check the logs"), "Can you check the logs")

    def test_phrases_and_repeats(self):
        self.assertEqual(cleanup.strip("I want the the tests to pass, you know, before lunch"),
                         "I want the tests to pass before lunch")

    def test_keeps_ordinary_words(self):
        self.assertEqual(cleanup.strip("summarize the umbrella ticket"), "Summarize the umbrella ticket")

    def test_only_fillers_returns_the_input(self):
        self.assertEqual(cleanup.strip("um"), "um")


class ContextNameGuard(unittest.TestCase):
    def check(self, raw, rewrite, expected, context="The component is named CopperFinchQueue."):
        self.assertEqual(cleanup.guard_context_names(raw, rewrite, context), expected)

    def test_duplicate_suffix_consumes_spoken_name_once(self):
        self.check("Please check the copper finch queue.", "Please check the CopperFinchQueue queue.",
                   "Please check the CopperFinchQueue.")

    def test_context_label_cannot_be_added(self):
        self.check("Please restart the Silver Otter cache.", "Please restart the SilverOtterCache service.",
                   "Please restart the SilverOtterCache.", "The service is named SilverOtterCache.")

    def test_different_name_is_not_replaced(self):
        self.check("Please restart the Golden Otter cache.", "Please restart the SilverOtterCache service.",
                   "Please restart the Golden Otter cache.", "The service is named SilverOtterCache.")

    def test_ordinary_description_is_not_completed_into_identifier(self):
        self.check("I saw a copper finch in the garden.", "I saw a CopperFinchQueue in the garden.",
                   "I saw a copper finch in the garden.")

    def test_valid_name_and_later_noun_are_kept(self):
        self.check("Check the copper finch queue and inspect the queue.",
                   "Check the CopperFinchQueue and inspect the queue.",
                   "Check the CopperFinchQueue and inspect the queue.")

    def test_explicit_label_is_kept(self):
        self.check("Check the copper finch queue service.", "Check the CopperFinchQueue service.",
                   "Check the CopperFinchQueue service.")

    def test_partial_joining_is_recognized(self):
        self.check("Check the CopperFinch queue.", "Check the CopperFinchQueue.", "Check the CopperFinchQueue.")

    def test_ambiguous_context_spelling_is_not_chosen(self):
        self.check("Check the http server.", "Check the HTTPServer.", "Check the http server.",
                   "Compare HTTPServer and HttpServer.")

    def test_exact_spelling_in_raw_wins_over_ambiguity(self):
        self.check("Check HTTPServer.", "Check HTTPServer.", "Check HTTPServer.",
                   "Compare HTTPServer and HttpServer.")

    def test_added_identifier_occurrence_is_rejected(self):
        self.check("Check the copper finch queue.", "Check the CopperFinchQueue and restart CopperFinchQueue.",
                   "Check the copper finch queue.")

    def test_no_context_keeps_model_cleanup(self):
        self.check("um check grafana", "Check Grafana.", "Check Grafana.", "")

    def test_other_spelling_corrections_remain_available(self):
        self.check("Check graph anna and then restart copper finch queue.",
                   "Check Grafana and then restart CopperFinchQueue.",
                   "Check Grafana and then restart CopperFinchQueue.")


class Message(unittest.TestCase):
    def test_transcript_only(self):
        self.assertEqual(cleanup.message("hello there", ""), "<transcript>\nhello there\n</transcript>\n")

    def test_context_goes_first(self):
        path = ROOT / "tests" / "_ctx.txt"
        path.write_text("Recent messages\n")
        try:
            out = cleanup.message("hello", str(path))
        finally:
            path.unlink()
        self.assertTrue(out.startswith("<context>\nRecent messages\n</context>\n\n<transcript>"))


class Cli(InstallCase):
    def cli(self, *args, stdin="", **env):
        return subprocess.run([sys.executable, str(self.home / "cleanup.py"), *args], input=stdin, capture_output=True,
                              text=True, env={**self.env, **env}, timeout=30)

    def test_hint_is_one_line_from_the_glossary(self):
        out = self.cli("hint").stdout
        self.assertIn("Grafana", out)
        self.assertNotIn("\n", out)

    def test_hint_empty_without_glossary(self):
        (self.home / "glossary.md").unlink()
        self.assertEqual(self.cli("hint").stdout, "")

    def test_prompt_has_light_touch_rules_and_glossary(self):
        out = self.cli("prompt").stdout
        self.assertIn("light touch", out)
        self.assertIn("\n<glossary>\n", out)
        self.assertIn("Project Lighthouse", out)

    def test_prompt_without_glossary(self):
        self.assertNotIn("\n<glossary>\n", self.cli("prompt", RAMBLE_GLOSSARY="0").stdout)

    def test_structured_prompt_by_short_name(self):
        out = self.cli("prompt", RAMBLE_PROMPT="structured").stdout
        self.assertIn("number them", out)
        self.assertNotIn("light touch", out)

    def test_unknown_prompt_fails(self):
        self.assertNotEqual(self.cli("prompt", RAMBLE_PROMPT="nope").returncode, 0)

    def test_no_em_dash_anywhere(self):
        for p in ROOT.rglob("*"):
            if p.is_file() and ".git" not in p.parts and p.suffix in (".md", ".py", ".sh", ".lua", ".swift", ".yml", ""):
                self.assertNotIn("\u2014", p.read_text(errors="replace"), str(p))

    def test_run_uses_claude_with_no_tools(self):
        p = self.cli("run", stdin="um please check the build")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, "CLEANED: um please check the build")
        args = json.loads(Path(self.env["FAKE_CLAUDE_LOG"]).read_text().splitlines()[0])
        self.assertEqual(args[args.index("--tools") + 1], "")
        self.assertIn("--no-session-persistence", args)
        self.assertIn("\n<glossary>\n", args[args.index("--system-prompt") + 1])

    def test_run_checks_names_before_returning_model_output(self):
        path = self.tmp / "context.txt"
        path.write_text("The component is named CopperFinchQueue.")
        result = self.cli("run", str(path), stdin="Please check the copper finch queue.",
                          FAKE_CLAUDE_RESULT="Please check the CopperFinchQueue queue.")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Please check the CopperFinchQueue.")
        self.assertIn("rejected unsupported contextual name", result.stderr)

    def test_run_fails_when_every_attempt_fails(self):
        p = self.cli("run", stdin="please check the build", FAKE_CLAUDE_MODE="fail")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(p.stdout, "")
        self.assertEqual(len(Path(self.env["FAKE_CLAUDE_LOG"]).read_text().splitlines()), 3)

    def test_run_gives_up_after_the_limit(self):
        t0 = time.time()
        p = self.cli("run", stdin="please check the build", FAKE_CLAUDE_MODE="hang", RAMBLE_CLEANUP_SECONDS="1.5",
                     RAMBLE_CLEANUP_HEDGE="0.5")
        self.assertEqual(p.returncode, 1)
        self.assertLess(time.time() - t0, 10)

    def test_hedge_answers_when_the_first_attempt_stalls(self):
        p = self.cli("run", stdin="please check the build", FAKE_CLAUDE_MODE="hang-first",
                     FAKE_CLAUDE_COUNTER=str(self.tmp / "count"), RAMBLE_CLEANUP_HEDGE="0.5")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, "CLEANED: please check the build")
        self.assertIn("attempt 2 (claude) answered", p.stderr)

    def test_run_without_claude_fails_cleanly(self):
        p = self.cli("run", stdin="please check the build", PATH="/usr/bin:/bin")
        self.assertEqual(p.returncode, 1)

    def test_run_strips_the_claude_code_session_marker(self):
        p = self.cli("run", stdin="please check the build", CLAUDECODE="1")
        self.assertEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
