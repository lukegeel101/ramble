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
