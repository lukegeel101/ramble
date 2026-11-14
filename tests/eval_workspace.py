#!/usr/bin/env python3
"""Opt-in real-model tests with fictional directory data; no private state or clipboard.

python3 tests/eval_workspace.py --live
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.test_workspace import DIRECTORY  # noqa: E402
from workspace import words  # noqa: E402

CASES = [
    ("channel", "Read a message in the call center ops channel.", "Read a message in the call center ops channel."),
    ("short-name", "Ask Myra Bellamy.", "Ask Mira Bellamy."),
    ("different-person", "Ask Nora Bellamy about the build.", "Ask Nora Bellamy about the build."),
    ("first-name", "Ask Mira about the build.", "Ask Mira about the build."),
    ("other-channel", "Read the call systems channel.", "Read the call systems channel."),
    ("unrelated", "Please water the plants tomorrow.", "Please water the plants tomorrow."),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", required=True, action="store_true")
    parser.add_argument("--prompt", default="cleanup", choices=("cleanup", "structured"))
    args = parser.parse_args()
    failures = 0
    with tempfile.TemporaryDirectory(prefix="ramble-workspace-eval-") as tmp:
        directory = Path(tmp) / "workspace.json"
        directory.write_text(json.dumps(DIRECTORY))
        env = {k: v for k, v in os.environ.items() if not k.startswith("RAMBLE_")}
        env.update(RAMBLE_GLOSSARY="0", RAMBLE_WORKSPACE_FILE=str(directory), RAMBLE_PROMPT=args.prompt,
                   RAMBLE_API_KEY_FILE=str(Path(tmp) / "no-key"))
        for label, raw, expected in CASES:
            result = subprocess.run([sys.executable, str(ROOT / "cleanup.py"), "run"],
                                    input=raw, text=True, capture_output=True, env=env, timeout=40)
            expected_words = words(expected)
            actual_words = words(result.stdout)
            if args.prompt == "structured":
                expected_words = [w for w in expected_words if w != "please"]
                actual_words = [w for w in actual_words if w != "please"]
            passed = result.returncode == 0 and actual_words == expected_words
            print(f'{"PASS" if passed else "FAIL"} {label}: {result.stdout!r}', flush=True)
            failures += not passed
    print(f"{len(CASES) - failures}/{len(CASES)} passed")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
