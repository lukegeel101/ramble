"""Shared set-up: a throwaway install folder and an environment whose PATH starts with the stand-ins in tests/bin."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "tests" / "bin"


def make_install(dest: Path, glossary=True):
    """Copy the scripts into dest the way install.sh lays them out, with the fake recorder."""
    for name in ("dictate.sh", "cleanup.py", "context.py", "lab.py"):
        shutil.copy2(ROOT / name, dest / name)
    shutil.copytree(ROOT / "prompts", dest / "prompts")
    (dest / "recorder").mkdir()
    shutil.copy2(ROOT / "tests" / "fake-mic-record", dest / "recorder" / "mic-record")
    if glossary:
        shutil.copy2(ROOT / "glossary.example.md", dest / "glossary.md")
    return dest


class InstallCase(unittest.TestCase):
    """A test with its own install folder in self.home and a safe environment in self.env."""

    glossary = True

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ramble-test-"))
        (self.tmp / "home").mkdir()
        self.home = make_install(self.tmp / "home", self.glossary)
        self.clipboard = self.tmp / "clipboard.txt"
        self.env = {
            **{k: v for k, v in os.environ.items() if not k.startswith(("RAMBLE_", "FAKE_", "CLAUDE"))},
            "PATH": f"{BIN}:{os.environ.get('PATH', '')}",
            "RAMBLE_COPY_CMD": f"cat > '{self.clipboard}'",
            "FAKE_PBCOPY_FILE": str(self.tmp / "pbcopy-was-called.txt"),
            "RAMBLE_API_KEY_FILE": str(self.tmp / "no-such-key"),
            "RAMBLE_PYTHON": sys.executable,
            "RAMBLE_CONTEXT": "0",
            "RAMBLE_CLAUDE_PROJECTS": str(self.tmp / "no-projects"),
            "FAKE_CLAUDE_LOG": str(self.tmp / "claude-calls.jsonl"),
            "FAKE_WHISPER_LOG": str(self.tmp / "whisper-args.txt"),
        }

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
