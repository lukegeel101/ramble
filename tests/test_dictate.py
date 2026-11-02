"""dictate.sh end to end with stand-ins: fake recorder, fake whisper-cli, fake claude, and a file for the clipboard."""
import os
import subprocess
import time
import unittest
from pathlib import Path

from tests.helpers import InstallCase

SPOKEN = "okay so um can you check whether the Grafana alerts fired last night and tell me which ones"


class Dictate(InstallCase):
    def sh(self, *args, **env):
        return subprocess.run(["/bin/bash", str(self.home / "dictate.sh"), *args], capture_output=True, text=True,
                              env={**self.env, "FAKE_WHISPER_TEXT": SPOKEN, **env}, timeout=60)

    def dictate(self, **env):
        self.assertEqual(self.sh("toggle", **env).stdout.strip(), "RECORDING")
        self.assertEqual(self.sh("status", **env).stdout.strip(), "RECORDING")
        time.sleep(0.3)
        return self.sh("toggle", **env)

    def tearDown(self):
        # Never leave a recorder running, even when a test fails half way.
        pidfile = self.home / "state" / "recorder.pid"
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), 9)
            except (OSError, ValueError):
                pass
        self.assertFalse(os.path.exists(self.env["FAKE_PBCOPY_FILE"]), "the real clipboard command was reached")
        super().tearDown()

    def test_full_dictation_is_cleaned_and_copied(self):
        p = self.dictate()
        self.assertEqual(p.stdout.strip(), f"COPIED: CLEANED: {SPOKEN}")
        self.assertEqual(self.clipboard.read_text(), f"CLEANED: {SPOKEN}")
        self.assertEqual((self.home / "state" / "last-raw.txt").read_text(), SPOKEN)
        self.assertTrue((self.home / "recordings" / "last.wav").exists())
        self.assertEqual(self.sh("status").stdout.strip(), "IDLE")
        log = (self.home / "dictate.log").read_text()
        self.assertIn("recording started (native)", log)

    def test_whisper_gets_the_glossary_hint(self):
        self.dictate()
        args = Path(self.env["FAKE_WHISPER_LOG"]).read_text().splitlines()
        self.assertIn("--prompt", args)
        self.assertIn("Grafana", args[args.index("--prompt") + 1])

    def test_no_hint_when_turned_off(self):
        self.dictate(RAMBLE_HINT="0")
        self.assertNotIn("--prompt", Path(self.env["FAKE_WHISPER_LOG"]).read_text().splitlines())

    def test_config_file_is_read(self):
        (self.home / "config").write_text("RAMBLE_CLEANUP=0\n")
        p = self.dictate()
        self.assertEqual(p.stdout.strip(), f"COPIED: {SPOKEN}")
        self.assertFalse(os.path.exists(self.env["FAKE_CLAUDE_LOG"]))

    def test_failed_cleanup_copies_the_transcript_as_heard(self):
        p = self.dictate(FAKE_CLAUDE_MODE="fail")
        self.assertEqual(p.stdout.strip(), f"RAW: {SPOKEN}")
        self.assertEqual(self.clipboard.read_text(), SPOKEN)

    def test_short_dictation_is_stripped_locally(self):
        p = self.dictate(FAKE_WHISPER_TEXT="um run the tests")
        self.assertEqual(p.stdout.strip(), "COPIED: Run the tests")
        self.assertFalse(os.path.exists(self.env["FAKE_CLAUDE_LOG"]))

    def test_nothing_heard(self):
        p = self.dictate(FAKE_WHISPER_TEXT="[BLANK_AUDIO]")
        self.assertEqual(p.stdout.strip(), "ERROR: nothing heard")
        self.assertFalse(self.clipboard.exists())

    def test_raw_copies_the_last_transcript(self):
        self.assertEqual(self.sh("raw").stdout.strip(), "ERROR: no dictation yet")
        self.dictate()
        self.assertEqual(self.sh("raw").stdout.strip(), f"RAW: {SPOKEN}")
        self.assertEqual(self.clipboard.read_text(), SPOKEN)

    def test_busy_while_another_command_holds_the_lock(self):
        lock = self.home / "state" / "lock"
        lock.mkdir(parents=True)
        sleeper = subprocess.Popen(["sleep", "30"])
        try:
            (lock / "pid").write_text(str(sleeper.pid))
            self.assertEqual(self.sh("status").stdout.strip(), "BUSY")
            self.assertEqual(self.sh("toggle").stdout.strip(), "BUSY")
        finally:
            sleeper.kill()
            sleeper.wait()
        self.assertEqual(self.sh("status").stdout.strip(), "IDLE")  # a dead owner's lock is taken over

    def test_stop_when_idle(self):
        self.assertEqual(self.sh("stop").stdout.strip(), "IDLE")

    def test_usage(self):
        self.assertEqual(self.sh("nonsense").returncode, 2)


if __name__ == "__main__":
    unittest.main()
