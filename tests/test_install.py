"""install.sh: lays out the install folder and adds the Hammerspoon module without replacing init.lua."""
import os
import subprocess
import tempfile
import shutil
import unittest
from pathlib import Path

from tests.helpers import ROOT


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ramble-install-"))
        self.dest, self.hs = self.tmp / "ramble", self.tmp / "hammerspoon"
        self.hs.mkdir()
        (self.hs / "init.lua").write_text('-- my own config\nhs.alert.show("hello")\n')
        self.env = {**os.environ, "RAMBLE_HOME": str(self.dest), "HAMMERSPOON_DIR": str(self.hs),
                    "RAMBLE_SKIP_CHECKS": "1", "RAMBLE_SKIP_MODEL": "1", "RAMBLE_SKIP_BUILD": "1"}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def install(self):
        p = subprocess.run(["/bin/bash", str(ROOT / "install.sh")], capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def test_layout_and_hammerspoon(self):
        self.install()
        for name in ("dictate.sh", "cleanup.py", "context.py", "coach.py", "lab.py", "config", "glossary.md",
                     "prompts/cleanup.md", "prompts/cleanup-structured.md", "prompts/meaning.md", "prompts/coach.md", "evals/coach.json"):
            self.assertTrue((self.dest / name).exists(), name)
        self.assertTrue(os.access(self.dest / "dictate.sh", os.X_OK))
        init = (self.hs / "init.lua").read_text()
        self.assertTrue(init.startswith('-- my own config\nhs.alert.show("hello")\n'))
        self.assertEqual(init.count('require("ramble")'), 1)
        module = (self.hs / "ramble.lua").read_text()
        self.assertIn(f'local home = "{self.dest}"', module)
        self.assertEqual(len(list(self.hs.glob("init.lua.bak-*"))), 1)

    def test_again_keeps_settings_and_adds_nothing(self):
        self.install()
        (self.dest / "config").write_text("RAMBLE_CLEANUP=0\n")
        (self.dest / "glossary.md").write_text("# mine\n")
        self.install()
        self.assertEqual((self.dest / "config").read_text(), "RAMBLE_CLEANUP=0\n")
        self.assertEqual((self.dest / "glossary.md").read_text(), "# mine\n")
        self.assertEqual((self.hs / "init.lua").read_text().count('require("ramble")'), 1)

    def test_fresh_hammerspoon(self):
        (self.hs / "init.lua").unlink()
        self.install()
        self.assertIn('require("ramble")', (self.hs / "init.lua").read_text())

    def test_rejects_a_folder_with_spaces(self):
        self.env["RAMBLE_HOME"] = str(self.tmp / "with space")
        p = subprocess.run(["/bin/bash", str(ROOT / "install.sh")], capture_output=True, text=True, env=self.env)
        self.assertNotEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
