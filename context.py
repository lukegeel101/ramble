#!/usr/bin/env python3
"""Print the last few messages of the conversation you are dictating into, for the cleanup step.

    context.py            uses the app in front now
    context.py <bundle>   uses that app's bundle ID (tests)

It lets the cleanup step resolve "that previous message" or "the second option", and spell names and numbers the way
the conversation does. Where the text will be pasted is guessed from the app in front when the recording stops:
  - A terminal, VS Code, Cursor or the Claude app: the newest interactive Claude Code session on this Mac
    (entrypoint "cli" or "claude-desktop") written in the last 2 hours. Headless `claude -p` runs ("sdk-cli") are
    skipped, so background jobs never count as the conversation.
  - Anything else: nothing.
It prints nothing on any doubt or error, so cleanup simply runs without context. It never prints more than
RAMBLE_CONTEXT_CHARS characters, newest messages kept first.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PROJECTS = Path(os.environ.get("RAMBLE_CLAUDE_PROJECTS", str(Path.home() / ".claude/projects")))
MESSAGES = int(os.environ.get("RAMBLE_CONTEXT_MESSAGES", "6"))
TOTAL = int(os.environ.get("RAMBLE_CONTEXT_CHARS", "8000"))
EACH = 3000
FRESH_SECONDS = 2 * 3600
TAIL_BYTES = 2_000_000
TERMINALS = {"com.apple.Terminal", "com.googlecode.iterm2", "com.mitchellh.ghostty", "dev.warp.Warp-Stable",
             "net.kovidgoyal.kitty", "com.microsoft.VSCode", "com.todesktop.230313mzl4w4u92",
             "com.anthropic.claudefordesktop", "com.anthropic.claude"}
TERMINALS |= {b.strip() for b in os.environ.get("RAMBLE_CONTEXT_APPS", "").split(",") if b.strip()}
NOISE = re.compile(r"^\s*<(system-reminder|command-|local-command|bash-|task-notification|user-prompt-submit-hook)", re.I)


def front_app():
    asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True, timeout=2).stdout.strip()
    out = subprocess.run(["lsappinfo", "info", "-only", "bundleid", asn], capture_output=True, text=True, timeout=2).stdout
    found = re.search(r'"?(?:CFBundleIdentifier|bundleID)"?\s*=\s*"([^"]+)"', out)
    return found.group(1) if found else ""


def clip(text, limit=EACH):
    text = text.strip()
    if len(text) <= limit:
        return text
    head = limit // 4
    return f"{text[:head]}\n[... {len(text) - limit} characters left out ...]\n{text[-(limit - head):]}"


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def session_messages(path):
    """(interactive, [(who, text)]) from the end of one Claude Code transcript; assistant pieces of a turn joined."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, size - TAIL_BYTES))
        lines = handle.read().decode("utf-8", "replace").splitlines()[1 if size > TAIL_BYTES else 0:]
    messages, interactive = [], None
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        kind = entry.get("type")
        if kind == "user" and entry.get("entrypoint"):
            interactive = entry["entrypoint"] in ("cli", "claude-desktop")
        if kind not in ("user", "assistant") or entry.get("isMeta") or entry.get("isSidechain"):
            continue
        text = text_of((entry.get("message") or {}).get("content")).strip()
        if not text or NOISE.match(text):
            continue
        who = "user" if kind == "user" else "assistant"
        if messages and messages[-1][0] == who == "assistant":
            messages[-1] = (who, messages[-1][1] + "\n\n" + text)
        else:
            messages.append((who, text))
    return bool(interactive), messages


def from_terminal(now=None):
    now = time.time() if now is None else now
    files = sorted((p for p in PROJECTS.glob("*/*.jsonl") if now - p.stat().st_mtime < FRESH_SECONDS),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:6]:
        interactive, messages = session_messages(path)
        if interactive and messages:
            return "Claude Code session", messages
    return "", []


def render(where, messages):
    if not messages:
        return ""
    parts, used = [], 0
    for who, text in reversed(messages[-MESSAGES:]):
        body = clip(text)
        if used + len(body) > TOTAL:
            break
        used += len(body)
        parts.append(f'<message from="{who}">\n{body}\n</message>')
    return f"Recent messages in the {where}, oldest first:\n" + "\n".join(reversed(parts))


def main(argv):
    if os.environ.get("RAMBLE_CONTEXT", "1") == "0":
        return 0
    try:
        app = argv[1] if len(argv) > 1 else front_app()
        where, messages = from_terminal() if app in TERMINALS else ("", [])
        out = render(where, messages)
    except Exception:  # noqa: BLE001
        return 0
    if out:
        sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
