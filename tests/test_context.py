"""context.py: reading the newest interactive Claude Code session, skipping headless runs, and the size limits."""
import json
import os
import subprocess
import sys
import time
import unittest

from tests.helpers import InstallCase

TERMINAL = "com.apple.Terminal"


def entry(kind, text, entrypoint=None, **extra):
    e = {"type": kind, "message": {"role": kind, "content": text}, **extra}
    if entrypoint:
        e["entrypoint"] = entrypoint
    return json.dumps(e)


class Context(InstallCase):
    def setUp(self):
        super().setUp()
        self.projects = self.tmp / "projects" / "-some-project"
        self.projects.mkdir(parents=True)
        self.env.update(RAMBLE_CONTEXT="1", RAMBLE_CLAUDE_PROJECTS=str(self.tmp / "projects"))

    def session(self, name, lines, age=0):
        path = self.projects / f"{name}.jsonl"
        path.write_text("\n".join(lines) + "\n")
        t = time.time() - age
        os.utime(path, (t, t))
        return path

    def context(self, app=TERMINAL, **env):
        return subprocess.run([sys.executable, str(self.home / "context.py"), app], capture_output=True, text=True,
                              env={**self.env, **env}, timeout=10).stdout

    def test_reads_the_interactive_session(self):
        self.session("a", [entry("user", "Which option do you prefer?", "cli"),
                           entry("assistant", "Option one: archive the old logs."),
                           entry("assistant", [{"type": "text", "text": "Option two: delete them."}])])
        out = self.context()
        self.assertIn("Recent messages in the Claude Code session, oldest first:", out)
        self.assertIn('<message from="user">\nWhich option do you prefer?\n</message>', out)
        self.assertIn("Option one: archive the old logs.\n\nOption two: delete them.", out)  # one assistant turn

    def test_skips_headless_runs(self):
        self.session("interactive", [entry("user", "the interactive one", "cli")], age=60)
        self.session("headless", [entry("user", "a background job", "sdk-cli")], age=0)
        out = self.context()
        self.assertIn("the interactive one", out)
        self.assertNotIn("background job", out)

    def test_skips_stale_sessions(self):
        self.session("old", [entry("user", "from yesterday", "cli")], age=3 * 3600)
        self.assertEqual(self.context(), "")

    def test_skips_system_noise_and_sidechains(self):
        self.session("a", [entry("user", "<system-reminder>ignore me</system-reminder>", "cli"),
                           entry("user", "real question", "cli"),
                           entry("assistant", "subagent chatter", isSidechain=True)])
        out = self.context()
        self.assertIn("real question", out)
        self.assertNotIn("ignore me", out)
        self.assertNotIn("subagent chatter", out)

    def test_other_apps_get_nothing(self):
        self.session("a", [entry("user", "hello", "cli")])
        self.assertEqual(self.context("com.example.Notes"), "")

    def test_extra_apps_from_settings(self):
        self.session("a", [entry("user", "hello", "cli")])
        self.assertIn("hello", self.context("com.example.MyTerm", RAMBLE_CONTEXT_APPS="com.example.MyTerm"))

    def test_limits(self):
        lines = [entry("user", f"message {i} " + "x" * 50, "cli") if i % 2 == 0 else entry("assistant", f"message {i}")
                 for i in range(20)]
        self.session("a", lines)
        out = self.context(RAMBLE_CONTEXT_MESSAGES="3")
        self.assertEqual(out.count("<message "), 3)
        self.assertIn("message 19", out)
        self.assertNotIn("message 16", out)
        out = self.context(RAMBLE_CONTEXT_CHARS="30")
        self.assertEqual(out.count("<message "), 1)

    def test_off(self):
        self.session("a", [entry("user", "hello", "cli")])
        self.assertEqual(self.context(RAMBLE_CONTEXT="0"), "")


if __name__ == "__main__":
    unittest.main()
