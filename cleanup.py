#!/usr/bin/env python3
"""Rewrite a dictation transcript into a clean, faithful prompt for an AI agent.

    cleanup.py run [CONTEXT_FILE] < transcript   print the rewrite; exit 1 if every attempt failed
    cleanup.py strip < transcript                 print the transcript with spoken fillers removed (no model)
    cleanup.py hint                               print glossary.md's "Transcriber hint" line for whisper --prompt
    cleanup.py prompt                             print the full system prompt that `run` sends

The model's instructions are prompts/cleanup.md (or RAMBLE_PROMPT) followed by glossary.md, when that file exists.

Backends, in order:
  - The Anthropic API directly, when the key file exists (RAMBLE_API_KEY_FILE, default
    ~/.config/ramble/anthropic-api-key, one line). About 1 s, billed to that key. Without the file it is never used.
  - Claude Code: `claude -p` with no tools, hooks, MCP servers or saved session, the instructions as its system prompt.
An attempt that has not answered within RAMBLE_CLEANUP_HEDGE seconds gets a second, parallel attempt (and a third
after the same wait again); the first answer wins and the rest are killed. The whole call gives up after
RAMBLE_CLEANUP_SECONDS so the caller can copy the raw transcript.
"""
from __future__ import annotations

import json
import difflib
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
import workspace

HERE = Path(__file__).resolve().parent
GLOSSARY = HERE / "glossary.md"
HINT_CHARS = 800  # whisper takes at most 224 prompt tokens
MODEL = os.environ.get("RAMBLE_CLEANUP_MODEL", "haiku")
API_MODEL = os.environ.get("RAMBLE_API_MODEL", "claude-haiku-4-5")
TOTAL = float(os.environ.get("RAMBLE_CLEANUP_SECONDS", "30"))
HEDGE = float(os.environ.get("RAMBLE_CLEANUP_HEDGE", "8"))

FILLERS = re.compile(r"\b(?:um+|uh+|erm+|er|hmm+|mm+|ah)\b[,.]?\s*", re.I)
LEAD = re.compile(r"^(?:(?:okay|ok|so|alright|all right|well|yeah)[,.]?\s+)+", re.I)
PHRASES = re.compile(r",?\s*\b(?:you know|i mean|kind of like|so yeah|if that makes sense)\b,?", re.I)


def log(msg):
    print(f"cleanup: {msg}", file=sys.stderr, flush=True)


def prompt_file():
    """RAMBLE_PROMPT picks the instructions: a name in prompts/ ("structured" or "cleanup-structured.md") or a path."""
    name = os.environ.get("RAMBLE_PROMPT", "cleanup.md")
    for candidate in (Path(name), HERE / "prompts" / name, HERE / "prompts" / f"{name}.md",
                      HERE / "prompts" / f"cleanup-{name}.md"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"no cleanup instructions called {name!r}")


def api_key_file():
    return Path(os.environ.get("RAMBLE_API_KEY_FILE", str(Path.home() / ".config/ramble/anthropic-api-key")))


def strip(text):
    """The local, model-free cleanup: spoken fillers, a leading "okay so", and repeated words."""
    out = PHRASES.sub("", FILLERS.sub("", text))
    out = LEAD.sub("", out.strip())
    out = re.sub(r"\b(\w+)( \1\b)+", r"\1", out, flags=re.I)  # "the the" -> "the"
    out = re.sub(r"\s+([,.?!])", r"\1", re.sub(r"\s{2,}", " ", out)).strip(" ,")
    return out[:1].upper() + out[1:] if out else text


def system_prompt():
    out = prompt_file().read_text()
    # RAMBLE_GLOSSARY=0 leaves the glossary out (lab.py compares with and without it).
    if GLOSSARY.is_file() and os.environ.get("RAMBLE_GLOSSARY", "1") != "0":
        out += "\n<glossary>\n" + GLOSSARY.read_text(errors="replace").strip() + "\n</glossary>\n"
    return out


def hint():
    """The text under "## Transcriber hint" in glossary.md, on one line, or nothing."""
    glossary = ""
    if GLOSSARY.is_file() and os.environ.get("RAMBLE_GLOSSARY", "1") != "0":
        section = re.search(r"^## Transcriber hint\s*\n(.*?)(?=^## |\Z)", GLOSSARY.read_text(errors="replace"), re.M | re.S)
        if section:
            glossary = " ".join(section.group(1).split())
    directory, state = workspace.load()
    workspace.record_status(directory, state, 0)
    vocabulary = workspace.hint(directory, HINT_CHARS // 2 if glossary else HINT_CHARS)
    if not vocabulary:
        return glossary[:HINT_CHARS]
    return (vocabulary + ". " + glossary[:HINT_CHARS - len(vocabulary) - 2]).rstrip(". ")


def read_context(context_file):
    if context_file and os.path.isfile(context_file):
        return Path(context_file).read_text(errors="replace")
    return ""


def message(text, context_file, context_text=None):
    context_text = read_context(context_file) if context_text is None else context_text
    ctx = "<context>\n" + context_text + "</context>\n\n" if context_text else ""
    return f"{ctx}<transcript>\n{text}\n</transcript>\n"


IDENTIFIER = re.compile(r"(?<![\w-])[A-Za-z][A-Za-z0-9]*(?![\w-])")
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def name_parts(name):
    return CAMEL_BOUNDARY.split(name)


def lexical_words(text):
    # CamelCase changes spelling, not the number of words the person spoke.
    return [part.casefold() for word in re.findall(r"\w+", text) for part in name_parts(word)]


def guard_context_names(raw, rewrite, context):
    """Reject unsupported compound-name substitutions and words added next to them.

    This is deliberately an exact-word check, not phonetic name guessing.
    On rejection use local cleanup of the original, retaining only full-name spellings
    the model chose AND whose complete word sequence is present in the original.
    Ordinary single-word spelling corrections remain the model's responsibility.
    """
    names = {m.group() for m in IDENTIFIER.finditer(context) if len(name_parts(m.group())) > 1}
    if not names:
        return rewrite
    canonical = {}
    for name in names:
        canonical.setdefault(tuple(p.casefold() for p in name_parts(name)), set()).add(name)
    valid, spans = {}, []
    unsupported = False
    for name in sorted(names):
        # Only guard names actually introduced in their contextual spelling.
        emitted = list(re.finditer(r"(?<!\w)" + re.escape(name) + r"(?!\w)", rewrite))
        if not emitted:
            continue
        parts = name_parts(name)
        pattern = re.compile(r"(?<!\w)" + r"\s*".join(re.escape(p) for p in parts) + r"(?!\w)", re.I)
        heard = list(pattern.finditer(raw))
        ambiguous = len(canonical[tuple(p.casefold() for p in parts)]) > 1
        if len(heard) < len(emitted) or (ambiguous and not all(m.group() == name for m in heard)):
            unsupported = True
            continue
        valid[name] = pattern
        for occurrence in emitted:
            start = len(lexical_words(rewrite[:occurrence.start()]))
            spans.append((start, start + len(parts)))
    before, after = lexical_words(strip(raw)), lexical_words(rewrite)
    # A new category label or duplicated suffix immediately before/after an identifier
    # is not part of its spelling. Do not erase an independently spoken use elsewhere.
    added_near_name = any(
        tag in ("insert", "replace") and any(j1 <= end and j2 >= start for start, end in spans)
        for tag, _, _, j1, j2 in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes()
    )
    if not unsupported and not added_near_name:
        return rewrite
    safe = strip(raw)
    # Longest first avoids replacing a prefix of a longer compound name.
    for name, pattern in sorted(valid.items(), key=lambda item: len(item[0]), reverse=True):
        safe = pattern.sub(name, safe)
    log("rejected unsupported contextual name or adjacent addition; used faithful local cleanup")
    return safe


def claude_cmd():
    return ["claude", "-p", "--model", MODEL, "--tools", "", "--no-session-persistence", "--setting-sources", "project",
            "--strict-mcp-config", "--system-prompt", system_prompt(), "--input-format", "stream-json",
            "--output-format", "stream-json", "--verbose"]


def child_env():
    """`claude` refuses to start inside another Claude Code session, which matters when this runs from one."""
    return {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}


LIVE = []  # every Attempt started, so a SIGTERM from the caller's timeout can kill their process groups


def on_term(*_):
    for a in LIVE:
        a.kill()
    sys.exit(1)


class Attempt:
    """One rewrite in flight. `result` is set (text or None) when it ends."""

    def __init__(self, label):
        self.label, self.start, self.result, self.done = label, time.time(), None, threading.Event()
        self.proc = None
        LIVE.append(self)

    def finish(self, result):
        if not self.done.is_set():
            self.result = result
            self.done.set()

    def kill(self):
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except OSError:
                pass


def spawn_claude():
    return subprocess.Popen(claude_cmd(), cwd=HERE, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, start_new_session=True, env=child_env())


def feed(attempt, proc, body):
    """Send body to a stream-json Claude Code process and wait for its result in a thread."""
    attempt.proc = proc

    def go():
        try:
            proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": body}}) + "\n")
            proc.stdin.close()
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "result":
                    text = (event.get("result") or "").strip()
                    attempt.finish(text if text and not event.get("is_error") else None)
                    break
        except (OSError, ValueError):
            pass
        attempt.finish(None)
        attempt.kill()
    threading.Thread(target=go, daemon=True).start()
    return attempt


def via_api(attempt, body):
    def go():
        try:
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", method="POST",
                                         headers={"x-api-key": api_key_file().read_text().strip(),
                                                  "anthropic-version": "2023-06-01", "content-type": "application/json"},
                                         data=json.dumps({"model": API_MODEL, "max_tokens": 2048, "system": system_prompt(),
                                                          "messages": [{"role": "user", "content": body}]}).encode())
            with urllib.request.urlopen(req, timeout=TOTAL) as response:
                data = json.loads(response.read())
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
            attempt.finish(text or None)
        except Exception as error:  # noqa: BLE001
            log(f"{attempt.label} API error: {error}")
            attempt.finish(None)
    threading.Thread(target=go, daemon=True).start()
    return attempt


def start_attempt(n, body):
    if api_key_file().is_file():
        return via_api(Attempt(f"attempt {n} (api)"), body)
    try:
        proc = spawn_claude()
    except OSError as error:
        log(f"could not start claude: {error}")
        attempt = Attempt(f"attempt {n} (claude)")
        attempt.finish(None)
        return attempt
    return feed(Attempt(f"attempt {n} (claude)"), proc, body)


def race(body):
    """Run attempts with hedging until one answers or TOTAL passes."""
    began = time.time()
    attempts = [start_attempt(1, body)]
    try:
        while time.time() - began < TOTAL:
            for a in attempts:
                if a.done.is_set() and a.result:
                    log(f"{a.label} answered in {time.time() - a.start:.1f}s ({len(attempts)} started)")
                    return a.result
            running = [a for a in attempts if not a.done.is_set()]
            since = time.time() - max(a.start for a in attempts)
            if (not running or since >= HEDGE) and len(attempts) < 3:
                log(f"{'no answer' if running else 'failed'} after {time.time() - began:.1f}s; starting attempt {len(attempts) + 1}")
                attempts.append(start_attempt(len(attempts) + 1, body))
            elif not running:
                break
            time.sleep(0.05)
        log(f"gave up after {time.time() - began:.1f}s ({len(attempts)} attempts)")
        return None
    finally:
        for a in attempts:
            a.kill()


def run(context_file):
    text = sys.stdin.read().strip()
    if not text:
        return 1
    context = read_context(context_file)
    directory, state = workspace.load()
    vocabulary, count = workspace.reference(directory, text)
    workspace.record_status(directory, state, count)
    result = race(vocabulary + message(text, context_file, context))
    if not result:
        return 1
    result = guard_context_names(text, result, context)
    if not workspace.preserves_names(directory, text, result):
        log("rejected cleanup that changed a recognized workspace name")
        result = strip(text)
    sys.stdout.write(result)
    return 0


def main(argv):
    signal.signal(signal.SIGTERM, on_term)
    mode = argv[1] if len(argv) > 1 else ""
    if mode == "run":
        return run(argv[2] if len(argv) > 2 else "")
    if mode == "strip":
        sys.stdout.write(strip(sys.stdin.read()))
        return 0
    if mode == "hint":
        sys.stdout.write(hint())
        return 0
    if mode == "prompt":
        sys.stdout.write(system_prompt())
        return 0
    print("usage: cleanup.py run [CONTEXT_FILE] | strip | hint | prompt", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
