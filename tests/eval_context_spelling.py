#!/usr/bin/env python3
"""Opt-in live cleanup evaluation using synthetic text only; never reads dictation state.

python3 tests/eval_context_spelling.py --live --repeats 3
python3 tests/eval_context_spelling.py --live --prompt structured
Uses the existing Claude CLI login, not API key files, and never touches the clipboard.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
CASES = [
    ("spaced-name", "The service is named SilverOtterCache.",
     "Please restart the Silver Otter cache.", "Please restart the SilverOtterCache."),
    ("no-duplicated-suffix", "The component is named CopperFinchQueue.",
     "Please check the copper finch queue.", "Please check the CopperFinchQueue."),
    ("ordinary-description", "The component is named CopperFinchQueue.",
     "I saw a copper finch in the garden.", "I saw a copper finch in the garden."),
    ("different-name", "The service is named SilverOtterCache.",
     "Please restart the Golden Otter cache.", "Please restart the Golden Otter cache."),
    ("separate-noun", "The service is named SilverOtterCache.",
     "Please restart the silver otter cache and flush the cache.",
     "Please restart the SilverOtterCache and flush the cache."),
    ("no-context", "", "Please restart the Silver Otter cache.", "Please restart the Silver Otter cache."),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True,
                        help="explicitly allow synthetic test text to be sent through Claude CLI")
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=2)
    parser.add_argument("--prompt", choices=("cleanup", "structured"), default="cleanup")
    parser.add_argument("--case", choices=[case[0] for case in CASES], help="run one regression case")
    args = parser.parse_args()
    cases = [case for case in CASES if not args.case or case[0] == args.case]
    failures = 0
    with tempfile.TemporaryDirectory(prefix="ramble-spelling-eval-") as tmp:
        env = {k: v for k, v in os.environ.items() if not k.startswith("RAMBLE_")}
        env.update(RAMBLE_GLOSSARY="0", RAMBLE_API_KEY_FILE=str(Path(tmp) / "no-key"), RAMBLE_PROMPT=args.prompt)
        for label, context, raw, expected in cases:
            acceptable = {expected}
            if args.prompt == "structured" and expected.startswith("Please "):
                # Structured mode intentionally permits making requests more direct.
                direct = expected[len("Please "):]
                acceptable.add(direct[:1].upper() + direct[1:])
            path = Path(tmp) / "context.txt"
            path.write_text("Recent text exposed by the active destination:\n" + context if context else "")
            for n in range(args.repeats):
                try:
                    result = subprocess.run([sys.executable, str(ROOT / "cleanup.py"), "run", str(path)],
                                            input=raw, text=True, capture_output=True, timeout=40, env=env)
                    passed = result.returncode == 0 and result.stdout in acceptable
                    print(f'{"PASS" if passed else "FAIL"} {label} {n + 1}: {result.stdout!r}', flush=True)
                except subprocess.TimeoutExpired:
                    passed = False
                    print(f"FAIL {label} {n + 1}: cleanup timed out", flush=True)
                failures += not passed
    print(f"{len(cases) * args.repeats - failures}/{len(cases) * args.repeats} passed")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
