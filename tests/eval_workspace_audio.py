#!/usr/bin/env python3
"""Opt-in synthetic speech -> real Whisper -> real cleanup -> file clipboard.

python3 tests/eval_workspace_audio.py --live --model ~/.ramble/models/ggml-small.en.bin
Uses macOS say, a fixture recorder, no microphone and no private directory or conversation.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.helpers import make_install  # noqa: E402
from tests.test_workspace import DIRECTORY  # noqa: E402
from workspace import words  # noqa: E402

SPOKEN = "Read a message in the call center ops channel."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", required=True, action="store_true")
    parser.add_argument("--model", required=True, type=Path)
    args = parser.parse_args()
    if not args.model.is_file():
        parser.error("Whisper model must exist")
    with tempfile.TemporaryDirectory(prefix="ramble-workspace-audio-") as tmp:
        home = Path(tmp) / "install"
        home.mkdir()
        make_install(home, glossary=False)
        (home / "workspace.json").write_text(json.dumps(DIRECTORY))
        aiff, wav, clipboard = [Path(tmp) / name for name in ("speech.aiff", "speech.wav", "clipboard.txt")]
        subprocess.run(["say", "-v", "Samantha", "-o", str(aiff), SPOKEN], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(wav)], check=True)
        (home / "recorder/mic-record").write_text(
            "#!/usr/bin/env python3\nimport os, shutil, signal, sys\n"
            "signal.signal(signal.SIGINT, lambda *_: sys.exit(0))\n"
            "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))\n"
            "shutil.copyfile(os.environ['RAMBLE_TEST_WAV'], sys.argv[1])\n"
            "while True: signal.pause()\n")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("RAMBLE_", "FAKE_"))}
        env.update(RAMBLE_CONTEXT="0", RAMBLE_GLOSSARY="0", RAMBLE_TEST_WAV=str(wav),
                   RAMBLE_WORKSPACE_FILE=str(home / "workspace.json"), RAMBLE_MODEL=str(args.model.resolve()),
                   RAMBLE_PYTHON=sys.executable, RAMBLE_API_KEY_FILE=str(Path(tmp) / "no-key"),
                   RAMBLE_COPY_CMD="cat > " + shlex.quote(str(clipboard)))
        command = ["/bin/bash", str(home / "dictate.sh")]
        try:
            started = subprocess.run([*command, "start"], env=env, text=True, capture_output=True, timeout=10)
            if started.stdout.strip() != "RECORDING":
                raise RuntimeError("fixture recorder failed to start")
            time.sleep(.3)
            result = subprocess.run([*command, "stop"], env=env, text=True, capture_output=True, timeout=90)
            output = clipboard.read_text() if clipboard.exists() else ""
            passed = result.returncode == 0 and words(output) == words(SPOKEN)
            print("Raw:", (home / "state/last-raw.txt").read_text())
            print("Output:", output)
            print("PASS synthetic audio pipeline" if passed else "FAIL synthetic audio pipeline")
            return int(not passed)
        finally:
            pidfile = home / "state/recorder.pid"
            if pidfile.exists():
                try:
                    os.kill(int(pidfile.read_text()), signal.SIGTERM)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    sys.exit(main())
