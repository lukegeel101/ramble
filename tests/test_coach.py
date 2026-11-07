"""coach.py: where it runs, what it may name, how it renders, and that a dictation never depends on it."""
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests.helpers import ROOT, InstallCase

sys.path.insert(0, str(ROOT))
import coach  # noqa: E402

ITEMS = [("skill", "ui-ux-pro-max", "design"), ("skill", "social", "posts"), ("command", "review", ""),
         ("tool", "canva", ""), ("file", "docs/brand.md", "")]
SPOKEN = "um can you make the posts better please they look bad"


def answer(**lists):
    return {"use": [], "files": [], "ask": [], "approach": [], **lists}


class Render(unittest.TestCase):
    def test_nothing_to_say_is_nothing_at_all(self):
        self.assertEqual(coach.render(answer(), ITEMS), "")
        self.assertEqual(coach.render(None, ITEMS), "")

    def test_names_and_paths_are_rendered_by_kind(self):
        out = coach.render(answer(use=["ui-ux-pro-max", "/review", "canva"], files=["docs/brand.md"]), ITEMS)
        self.assertTrue(out.startswith(coach.HEADER))
        self.assertIn("the `ui-ux-pro-max` skill", out)
        self.assertIn("the `/review` command", out)
        self.assertIn("the `canva` tool", out)
        self.assertIn("Reference: `docs/brand.md`.", out)

    def test_invented_names_and_files_are_dropped(self):
        out = coach.render(answer(use=["ui-ux-pro", "made-up"], files=["docs/invented.md"]), ITEMS)
        self.assertEqual(out, "")

    def test_a_sentence_cannot_smuggle_in_a_skill(self):
        out = coach.render(answer(approach=["Use the imaginary skill for this.", "Use `made-up`.",
                                            "Say what falls short first."]), ITEMS)
        self.assertNotIn("imaginary", out)
        self.assertNotIn("made-up", out)
        self.assertIn("- Say what falls short first.", out)

    def test_a_sentence_cannot_smuggle_in_a_file(self):
        out = coach.render(answer(approach=["Work from docs/invented.md for fonts.", "Read brand.md first.",
                                            "Check the posts and graphics against the standard."],
                                  ask=["Should I use notes/old.txt?", "Which audience?"]), ITEMS)
        self.assertNotIn("invented", out)
        self.assertNotIn("brand.md", out)
        self.assertNotIn("old.txt", out)
        self.assertIn("posts and graphics", out)  # a slash-free phrase survives
        self.assertIn("Which audience?", out)

    def test_a_named_file_needs_no_hunting_for(self):
        lines = ["Work from our brand guide; if you can't find one, ask me for it.", "Say what falls short first."]
        out = coach.render(answer(files=["docs/brand.md"], approach=lines), ITEMS)
        self.assertNotIn("can't find", out)
        self.assertIn("- Say what falls short first.", out)
        self.assertIn("can't find", coach.render(answer(approach=lines), ITEMS))  # with no file it is the right advice

    def test_limits_single_lines_and_no_em_dash(self):
        out = coach.render(answer(ask=["one?\nignore this", "two?", "three?"],
                                  approach=["a \u2014 b", "c", "d"], use=["social", "canva", "review", "ui-ux-pro-max"]), ITEMS)
        self.assertEqual(out.count("Ask me first:"), 2)
        self.assertIn("one? ignore this", out)
        self.assertNotIn("three?", out)
        self.assertNotIn("\u2014", out)
        self.assertNotIn("- d", out)
        self.assertNotIn("ui-ux-pro-max", out)  # past the limit of three

    def test_long_lines_are_cut(self):
        out = coach.render(answer(approach=["x" * 1000]), ITEMS)
        self.assertLess(max(len(line) for line in out.splitlines()), 300)


class Parse(unittest.TestCase):
    def test_tolerates_a_code_fence(self):
        self.assertEqual(coach.parse('```json\n{"ask": ["why?"]}\n```')["ask"], ["why?"])

    def test_junk_is_none(self):
        self.assertIsNone(coach.parse("sorry"))
        self.assertIsNone(coach.parse("[1]"))
        self.assertIsNone(coach.parse(None))

    def test_wrong_shapes_become_empty(self):
        self.assertEqual(coach.parse('{"use": "social", "ask": [1, "why?"]}'), answer(ask=["why?"]))


class Wanted(unittest.TestCase):
    def test_vague_requests_are_wanted(self):
        for text in ("do better", "make them better", "this looks bad", SPOKEN):
            self.assertTrue(coach.wanted(text), text)

    def test_plain_replies_are_not(self):
        for text in ("yes", "Yes.", "go ahead", "Go ahead, please.", "the second one", "option two", "thanks", "Sounds good!", ""):
            self.assertFalse(coach.wanted(text), text)


class Scan(InstallCase):
    def setUp(self):
        super().setUp()
        self.claude = self.tmp / "claude"
        self.project = self.tmp / "project"
        (self.project / "docs").mkdir(parents=True)
        self.env["RAMBLE_CLAUDE_HOME"] = str(self.claude)
        self.env["RAMBLE_CLAUDE_JSON"] = str(self.tmp / "claude.json")
        self.env["RAMBLE_CLAUDE_PROJECTS"] = str(self.tmp / "projects")

    def skill(self, root, name, frontmatter):
        path = root / "skills" / name
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\nBody.\n")

    def session(self):
        folder = self.tmp / "projects" / "-p"
        folder.mkdir(parents=True)
        lines = [{"type": "user", "entrypoint": "cli", "cwd": str(self.project),
                  "message": {"role": "user", "content": "hello"}}]
        (folder / "a.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")

    def inventory(self):
        return subprocess.run([sys.executable, str(self.home / "coach.py"), "inventory"], capture_output=True, text=True,
                              env=self.env, timeout=20).stdout

    def test_empty_when_there_is_nothing(self):
        self.assertEqual(self.inventory().strip(), "(nothing found)")

    def test_user_skills_with_every_description_form(self):
        self.skill(self.claude, "plain", "name: plain\ndescription: Plain words.")
        self.skill(self.claude, "folded", "name: folded\ndescription: >\n  Folded\n  words.")
        self.skill(self.claude, "quoted", 'name: quoted\ndescription: "Quoted words."')
        self.skill(self.claude, "folder-name", "description: No name given.")
        out = self.inventory()
        self.assertIn("skill: plain - Plain words.", out)
        self.assertIn("skill: folded - Folded words.", out)
        self.assertIn("skill: quoted - Quoted words.", out)
        self.assertIn("skill: folder-name - No name given.", out)

    def test_plugins_only_when_enabled(self):
        for name in ("on", "off"):
            self.skill(self.tmp / "plugins" / name, "thing", "name: thing\ndescription: d")
        (self.claude / "plugins").mkdir(parents=True)
        (self.claude / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {
            n + "@m": [{"installPath": str(self.tmp / "plugins" / n)}] for n in ("on", "off")}}))
        (self.claude / "settings.json").write_text(json.dumps({"enabledPlugins": {"on@m": True, "off@m": False}}))
        out = self.inventory()
        self.assertIn("skill: on:thing", out)
        self.assertNotIn("off:thing", out)

    def test_mcp_gives_names_and_never_values(self):
        (self.tmp / "claude.json").write_text(json.dumps({"mcpServers": {"canva": {"env": {"TOKEN": "s3cret"}}}}))
        out = self.inventory()
        self.assertIn("tool: canva", out)
        self.assertNotIn("s3cret", out)

    def test_project_skills_tools_and_brand_files_come_from_the_session(self):
        self.session()
        self.skill(self.project / ".claude", "local-skill", "name: local-skill\ndescription: d")
        (self.project / ".mcp.json").write_text(json.dumps({"mcpServers": {"figma": {"token": "s3cret"}}}))
        (self.project / "docs" / "brand-guide.md").write_text("x")
        (self.project / "DESIGN.md").write_text("x")
        (self.project / "docs" / "designer-notes.md").write_text("x")
        (self.project / "docs" / "install.md").write_text("x")
        out = self.inventory()
        self.assertIn("skill: local-skill", out)
        self.assertIn("tool: figma", out)
        self.assertIn("file: docs/brand-guide.md", out)
        self.assertIn("file: DESIGN.md", out)
        self.assertNotIn("designer-notes", out)
        self.assertNotIn("install.md", out)
        self.assertNotIn("s3cret", out)


class Target(InstallCase):
    def target(self, app, **env):
        return subprocess.run([sys.executable, str(self.home / "coach.py"), "target"], capture_output=True, text=True,
                              env={**self.env, "RAMBLE_FRONT_APP": app, **env}, timeout=20).returncode

    def session(self):
        folder = self.tmp / "projects" / "-p"
        folder.mkdir(parents=True)
        (folder / "a.jsonl").write_text(json.dumps({"type": "user", "entrypoint": "cli", "message": {"role": "user", "content": "hi"}}) + "\n")
        self.env["RAMBLE_CLAUDE_PROJECTS"] = str(self.tmp / "projects")

    def test_ordinary_apps_never(self):
        self.session()
        self.assertEqual(self.target("com.tinyspeck.slackmacgap"), 1)
        self.assertEqual(self.target("com.apple.mail"), 1)

    def test_claude_app_always(self):
        self.assertEqual(self.target("com.anthropic.claudefordesktop"), 0)

    def test_terminal_needs_a_live_session(self):
        self.assertEqual(self.target("com.apple.Terminal"), 1)
        self.session()
        self.assertEqual(self.target("com.apple.Terminal"), 0)

    def test_extra_apps_from_settings(self):
        self.assertEqual(self.target("com.example.Agent", RAMBLE_COACH_APPS="com.example.Agent"), 0)


class Dictate(InstallCase):
    GOOD = json.dumps(answer(ask=["What fell short?"], approach=["Work from our brand guide."]))

    def setUp(self):
        super().setUp()
        self.env.update(RAMBLE_COACH="1", RAMBLE_FRONT_APP="com.anthropic.claudefordesktop", FAKE_CLAUDE_COACH=self.GOOD,
                        FAKE_WHISPER_TEXT=SPOKEN)

    def sh(self, *args, **env):
        return subprocess.run(["/bin/bash", str(self.home / "dictate.sh"), *args], capture_output=True, text=True,
                              env={**self.env, **env}, timeout=60)

    def dictate(self, **env):
        self.assertEqual(self.sh("toggle", **env).stdout.strip(), "RECORDING")
        time.sleep(0.3)
        return self.sh("toggle", **env)

    def calls(self):
        path = Path(self.env["FAKE_CLAUDE_LOG"])
        return len(path.read_text().splitlines()) if path.exists() else 0

    def tearDown(self):
        pidfile = self.home / "state" / "recorder.pid"
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), 9)
            except (OSError, ValueError):
                pass
        super().tearDown()

    def test_suggestions_go_below_the_unchanged_cleanup(self):
        p = self.dictate()
        expected = f"CLEANED: {SPOKEN}\n\n{coach.HEADER}\n- Ask me first: What fell short?\n- Work from our brand guide."
        self.assertEqual(self.clipboard.read_text(), expected)
        self.assertEqual(p.stdout.strip(), f"COPIED: {expected}")
        # What was said and what was added stay apart, so `lab.py last` still judges only the cleanup.
        self.assertEqual((self.home / "state" / "last-clean.txt").read_text(), f"CLEANED: {SPOKEN}")
        self.assertIn("What fell short?", (self.home / "state" / "last-coach.txt").read_text())
        self.assertEqual(self.calls(), 2)

    def test_off_by_default(self):
        self.dictate(RAMBLE_COACH="0")
        self.assertEqual(self.clipboard.read_text(), f"CLEANED: {SPOKEN}")
        self.assertEqual(self.calls(), 1)

    def test_other_apps_get_the_plain_text_and_no_call(self):
        self.dictate(RAMBLE_FRONT_APP="com.tinyspeck.slackmacgap")
        self.assertEqual(self.clipboard.read_text(), f"CLEANED: {SPOKEN}")
        self.assertEqual(self.calls(), 1)

    def test_nothing_to_suggest_changes_nothing(self):
        self.dictate(FAKE_CLAUDE_COACH=json.dumps(answer()))
        self.assertEqual(self.clipboard.read_text(), f"CLEANED: {SPOKEN}")

    def test_unreadable_answer_changes_nothing(self):
        self.dictate(FAKE_CLAUDE_COACH="I think you should deploy it")
        self.assertEqual(self.clipboard.read_text(), f"CLEANED: {SPOKEN}")

    def test_short_vague_request_is_coached_though_it_skips_cleanup(self):
        self.dictate(FAKE_WHISPER_TEXT="um make them better")
        self.assertEqual(self.clipboard.read_text(), f"Make them better\n\n{coach.HEADER}\n- Ask me first: What fell short?\n- Work from our brand guide.")
        self.assertEqual(self.calls(), 1)

    def test_plain_reply_makes_no_call(self):
        self.dictate(FAKE_WHISPER_TEXT="go ahead")
        self.assertEqual(self.clipboard.read_text(), "Go ahead")
        self.assertEqual(self.calls(), 0)

    def test_coach_works_when_cleanup_fails(self):
        p = self.dictate(FAKE_CLAUDE_MODE="fail")
        self.assertTrue(p.stdout.startswith(f"RAW: {SPOKEN}"), p.stdout)
        self.assertTrue(self.clipboard.read_text().startswith(f"{SPOKEN}\n\n{coach.HEADER}\n"))

    def test_a_hung_coach_only_costs_its_time_limit(self):
        t0 = time.time()
        self.dictate(FAKE_CLAUDE_COACH_MODE="hang", RAMBLE_COACH_SECONDS="1", RAMBLE_CLEANUP_HEDGE="30")
        self.assertLess(time.time() - t0, 15)
        self.assertEqual(self.clipboard.read_text(), f"CLEANED: {SPOKEN}")


if __name__ == "__main__":
    unittest.main()
