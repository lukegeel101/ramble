"""lab.py: scoring helpers and the meaning check against the fake claude."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests.helpers import ROOT, InstallCase

sys.path.insert(0, str(ROOT))
import lab  # noqa: E402


class Words(unittest.TestCase):
    def test_spoken_symbols_and_numbers(self):
        self.assertEqual(lab.words("Open example dot com slash docs since PR seven fifty one"),
                         lab.words("Open example.com/docs since PR751"))
        self.assertEqual(lab.words("twenty one"), ["21"])

    def test_wer(self):
        self.assertEqual(lab.wer("check the build now", "check the build now"), 0.0)
        self.assertEqual(lab.wer("check the build now", "check build now"), 0.25)
        self.assertIsNone(lab.wer("", "anything"))


class Cli(InstallCase):
    def lab(self, *args, **env):
        return subprocess.run([sys.executable, str(self.home / "lab.py"), *args], capture_output=True, text=True,
                              env={**self.env, **env}, timeout=60, cwd=self.tmp)

    def files(self, raw, out):
        (self.tmp / "raw.txt").write_text(raw)
        (self.tmp / "out.txt").write_text(out)
        return str(self.tmp / "raw.txt"), str(self.tmp / "out.txt")

    def test_same_words_pass_without_a_model_call(self):
        p = self.lab("check", *self.files("um check the build", "Check the build."), "--json")
        self.assertEqual(json.loads(p.stdout)["model"], "same words")

    def test_meaning_issues_are_reported(self):
        issue = {"type": "added", "severity": "major", "said": "", "became": "and deploy it", "why": "never said"}
        p = self.lab("check", *self.files("check the build", "Check the build and deploy it."), "--json",
                     FAKE_CLAUDE_MEANING=json.dumps({"issues": [issue]}))
        self.assertEqual(json.loads(p.stdout)["issues"], [issue])
        p = self.lab("check", *self.files("check the build", "Check the build and deploy it."),
                     FAKE_CLAUDE_MEANING=json.dumps({"issues": [issue]}))
        self.assertIn('major added: "" -> "and deploy it"', p.stdout)

    def test_meaning_check_starts_claude_outside_the_install_folder(self):
        log = self.tmp / "cwd.txt"
        self.lab("check", *self.files("check the build", "Deploy it."), FAKE_CLAUDE_CWD_LOG=str(log))
        self.assertEqual(Path(log.read_text().strip()).name, "ramble-empty")

    def test_unreadable_answer_is_an_error(self):
        p = self.lab("check", *self.files("check the build", "Deploy it."), "--json", FAKE_CLAUDE_MEANING="sorry")
        self.assertEqual(p.returncode, 1)
        self.assertTrue(json.loads(p.stdout)["error"])

    def test_compare_runs_every_variant(self):
        raw, _ = self.files("um so please check the Grafana alerts from last night", "")
        p = self.lab("compare", raw, "--ref", "please check the Grafana alerts from last night", "--json")
        result = json.loads(p.stdout)
        keys = [v["key"] for v in result["cleanups"]]
        self.assertEqual(keys, ["live", "again", "structured", "noglossary", "strip"])
        strip = next(v for v in result["cleanups"] if v["key"] == "strip")
        self.assertEqual(strip["score"]["wer"], 0.0)
        self.assertIn("meaning", result["cleanups"][0])

    def test_coach_eval_passes_and_fails(self):
        # The fake answers the same for every case, so silent cases pass and suggest cases fail, and it says so.
        p = self.lab("coach", "--runs", "1")
        self.assertEqual(p.returncode, 1)
        self.assertIn("should have suggested something", p.stdout)
        self.assertIn("run 1: ok", p.stdout)
        self.assertRegex(p.stdout, r"\d+ of \d+ runs passed")

    def test_last_needs_a_dictation(self):
        self.assertEqual(self.lab("last").returncode, 1)


if __name__ == "__main__":
    unittest.main()
