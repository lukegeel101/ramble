#!/usr/bin/env python3
"""Suggest what an experienced agent user would have added to a dictation. Off unless RAMBLE_COACH=1.

    coach.py target                     exit 0 when the app in front is an AI agent worth coaching, 1 when it is not
    coach.py inventory                  print the skills, commands, tools and reference files the model may choose from
    coach.py wanted < transcript        exit 0 when the dictation is worth a model call, 1 when it is a plain reply
    coach.py run [CONTEXT_FILE] < transcript   print the suggestions block, or nothing; never fails the dictation

The speaker's words never pass through this file: dictate.sh cleans them up as usual and appends this block below them,
labelled as added. The model only picks from lists. Code renders the text, and any skill, tool or file that is not in
the inventory is dropped, so a suggestion can never name something the speaker does not have.
"""
from __future__ import annotations

import json
import os
import re
import signal
import sys
from pathlib import Path

import cleanup
import context

HERE = Path(__file__).resolve().parent
PROMPT = HERE / "prompts" / "coach.md"
HEADER = "Suggestions Ramble added (I did not say these, and my words above come first; skip anything that doesn't fit):"
CLAUDE_HOME = Path(os.environ.get("RAMBLE_CLAUDE_HOME", str(Path.home() / ".claude")))
CLAUDE_JSON = Path(os.environ.get("RAMBLE_CLAUDE_JSON", str(Path.home() / ".claude.json")))
AGENT_APPS = {"com.anthropic.claudefordesktop", "com.anthropic.claude"}
AGENT_APPS |= {b.strip() for b in os.environ.get("RAMBLE_COACH_APPS", "").split(",") if b.strip()}
MIN_WORDS = int(os.environ.get("RAMBLE_COACH_MIN_WORDS", "2"))
LIMITS = {"use": 3, "files": 2, "ask": 2, "approach": 2}
MAX_ENTRIES, MAX_DESCRIPTION, MAX_LINE = 120, 200, 240
# Replies an agent is waiting for. They get no model call, so "yes" stays instant.
REPLY = re.compile(r"^(?:yes|yeah|yep|no|nope|ok|okay|sure|thanks|thank you|please|perfect|great|nice|stop|cancel|"
                   r"go ahead|go for it|do it|continue|keep going|sounds good|looks good|that works|"
                   r"(?:the )?(?:first|second|third|last) (?:one|option)|option \w+)(?:[ ,]+(?:please|thanks))?[.!? ]*$", re.I)
DOC_NAMES = re.compile(r"(?:^|[-_ ./])(?:brand(?:ing)?|style[-_ ]?guide|design[-_ ]?system|design|voice|tone)"
                       r"(?:$|[-_ .])", re.I)
UNCHECKED = re.compile(r"`|\b(?:skills?|plugins?|mcp)\b|\b[\w-]+/[\w./-]*\.\w+|\b[\w-]+\.(?:md|mdx|txt|pdf|docx|json|css)\b", re.I)
HUNT = re.compile(r"\b(?:can't|cannot|can not|couldn't|unable to) (?:find|locate)\b|\bif (?:it|one|the \w+ )\s*(?:is|'s) missing\b", re.I)
DOC_DIRS = (".", "docs", "doc", "brand", "branding", "design", "assets", "marketing", ".claude")
DOC_TYPES = {".md", ".mdx", ".txt", ".pdf", ".docx", ".json", ".css"}


def field(frontmatter, name):
    """One value from YAML frontmatter, including a folded or quoted one, without needing a YAML parser."""
    found = re.search(rf"^{name}:[ \t]*(.*(?:\n[ \t]+.*)*)", frontmatter, re.M)
    if not found:
        return ""
    value = " ".join(found.group(1).split())
    return re.sub(r"^[>|][-+]?\s*", "", value).strip("\"' ")


def read_skill(path, prefix=""):
    """(name, description) from a SKILL.md, or None when it is not readable."""
    try:
        with path.open(errors="replace") as handle:
            text = handle.read(8192)
    except OSError:
        return None
    found = re.match(r"---\s*\n(.*?)\n---", text, re.S)
    head = found.group(1) if found else ""
    name = field(head, "name") or path.parent.name
    return prefix + name, field(head, "description")


def scan(root, prefix=""):
    """Skills and commands under one .claude-style folder: [(kind, name, description)]."""
    out = []
    for path in sorted((root / "skills").glob("*/SKILL.md")):
        skill = read_skill(path, prefix)
        if skill:
            out.append(("skill", *skill))
    for path in sorted((root / "commands").glob("*.md")):
        out.append(("command", prefix + path.stem, ""))
    return out


def enabled_plugins():
    """The install folders of plugins that are turned on. A plugin missing from enabledPlugins is treated as off."""
    try:
        installed = json.loads((CLAUDE_HOME / "plugins" / "installed_plugins.json").read_text())["plugins"]
        enabled = json.loads((CLAUDE_HOME / "settings.json").read_text()).get("enabledPlugins") or {}
    except (OSError, ValueError, KeyError, TypeError):
        return []
    out = []
    for key, installs in installed.items():
        if enabled.get(key) and installs and installs[0].get("installPath"):
            out.append((key.split("@")[0], Path(installs[0]["installPath"])))
    return out


def mcp_servers(project):
    """MCP server names only. These files can hold tokens in server settings, so nothing else is ever read from them."""
    names = set()
    try:
        data = json.loads(CLAUDE_JSON.read_text())
        names |= set(data.get("mcpServers") or {})
        if project:
            names |= set(((data.get("projects") or {}).get(str(project)) or {}).get("mcpServers") or {})
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    if project:
        try:
            names |= set(json.loads((project / ".mcp.json").read_text()).get("mcpServers") or {})
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    return sorted(names)


def reference_files(project):
    """Brand and style documents near the top of the project, as paths relative to it."""
    out = []
    for folder in DOC_DIRS:
        try:
            names = sorted(os.listdir(project / folder))
        except OSError:
            continue
        for name in names:
            path = project / folder / name
            if path.suffix.lower() in DOC_TYPES and DOC_NAMES.search(name) and path.is_file():
                out.append(os.path.normpath(os.path.join(folder, name)))
    return out[:20]


def project_dir():
    """The folder of the Claude Code session being dictated into, when there is one."""
    try:
        cwd = context.newest_session_cwd()
    except Exception:  # noqa: BLE001
        return None
    return Path(cwd) if cwd and Path(cwd).is_dir() else None


def inventory():
    """[(kind, name, description)] of what this person can really use. kind: skill, command, tool or file."""
    project = project_dir()
    items = scan(CLAUDE_HOME)
    for plugin, root in enabled_plugins():
        items += scan(root, f"{plugin}:")
    if project:
        items += scan(project / ".claude")
    for extra in os.environ.get("RAMBLE_SKILL_DIRS", "").split(":"):
        if extra:
            for path in sorted(Path(extra).expanduser().glob("*/SKILL.md")):
                skill = read_skill(path)
                if skill:
                    items.append(("skill", *skill))
    if project:
        items += [("tool", name, "") for name in mcp_servers(project)]
        items += [("file", name, "") for name in reference_files(project)]
    else:
        items += [("tool", name, "") for name in mcp_servers(None)]
    seen, unique = set(), []
    for item in items:
        if item[:2] not in seen:
            seen.add(item[:2])
            unique.append(item)
    return unique[:MAX_ENTRIES]


def render_inventory(items):
    lines = []
    for kind, name, description in items:
        lines.append(f"{kind}: {name}" + (f" - {description[:MAX_DESCRIPTION]}" if description else ""))
    return "\n".join(lines) or "(nothing found)"


def load_inventory():
    """RAMBLE_COACH_INVENTORY replaces the scan with a file of `kind: name - description` lines (lab.py's evals).
    An empty file is someone with nothing installed."""
    fixed = os.environ.get("RAMBLE_COACH_INVENTORY")
    if not fixed:
        return inventory()
    out = []
    for line in Path(fixed).read_text().splitlines():
        found = re.match(r"(skill|command|tool|file): (\S+)(?: - (.*))?$", line)
        if found:
            out.append((found.group(1), found.group(2), found.group(3) or ""))
    return out


def wanted(text):
    """Worth a model call? One-word dictations and plain replies are not. "do better" is, which is why this is not
    the cleanup's six-word minimum: the shortest messages are often the ones that most need help."""
    text = text.strip()
    return len(text.split()) >= MIN_WORDS and not REPLY.match(text)


def parse(answer):
    """The model's JSON as a dict of lists of strings, or None."""
    found = re.search(r"\{.*\}", answer or "", re.S)
    try:
        data = json.loads(found.group(0)) if found else None
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    return {key: [str(v) for v in data.get(key) or [] if isinstance(v, str)] if isinstance(data.get(key) or [], list) else []
            for key in LIMITS}


def line(text):
    """One suggestion as a single, bounded line. Reply text is pasted to an agent, so it never spans lines."""
    return " ".join(text.replace("\u2014", "-").split())[:MAX_LINE].strip()


def named_for_the_agent(kind, name):
    return {"skill": f"the `{name}` skill", "command": f"the `/{name}` command", "tool": f"the `{name}` tool"}[kind]


def render(answer, items):
    """The block to paste, or "". Code writes it: anything not in the inventory is dropped, however it was asked for."""
    if not answer:
        return ""
    names = {name: kind for kind, name, _ in reversed(items) if kind != "file"}
    files = {name for kind, name, _ in items if kind == "file"}
    use = [named_for_the_agent(names[n.strip().lstrip("/")], n.strip().lstrip("/"))
           for n in answer["use"] if n.strip().lstrip("/") in names][:LIMITS["use"]]
    paths = [f"`{p.strip()}`" for p in answer["files"] if p.strip() in files][:LIMITS["files"]]
    # Skills, tools and files are only ever named through "use" and "files", where they are checked.
    # A free-text sentence that names one is dropped, because nothing could check it.
    asks = [line(q) for q in answer["ask"] if line(q) and not UNCHECKED.search(q)][:LIMITS["ask"]]
    ways = [line(a) for a in answer["approach"] if line(a) and not UNCHECKED.search(a)
            and not (paths and HUNT.search(a))][:LIMITS["approach"]]
    bullets = []
    if use:
        bullets.append("Use if it fits: " + ", ".join(use) + ".")
    if paths:
        bullets.append("Reference: " + ", ".join(paths) + ".")
    bullets += [f"Ask me first: {q}" for q in asks]
    bullets += ways
    return "\n".join([HEADER] + [f"- {b}" for b in bullets]) if bullets else ""


def target():
    """Only coach where an agent will read it. In a terminal that needs a live Claude Code session: it could be a shell."""
    app = context.front_app()
    if app in AGENT_APPS:
        return True
    return app in context.TERMINALS and bool(context.from_terminal()[1])


def run(context_file):
    text = sys.stdin.read().strip()
    if not text or not wanted(text):
        return 0
    os.environ["RAMBLE_PROMPT"] = str(PROMPT)
    cleanup.MODEL = os.environ.get("RAMBLE_COACH_MODEL", cleanup.MODEL)
    cleanup.TOTAL = float(os.environ.get("RAMBLE_COACH_SECONDS", "20"))
    items = load_inventory()
    body = f"<inventory>\n{render_inventory(items)}\n</inventory>\n\n" + cleanup.message(text, context_file)
    answer = cleanup.race(body)
    block = render(parse(answer), items)
    if block:
        sys.stdout.write(block)
    return 0


def main(argv):
    signal.signal(signal.SIGTERM, cleanup.on_term)
    mode = argv[1] if len(argv) > 1 else ""
    if mode == "target":
        try:
            return 0 if target() else 1
        except Exception:  # noqa: BLE001
            return 1
    if mode == "inventory":
        sys.stdout.write(render_inventory(load_inventory()) + "\n")
        return 0
    if mode == "wanted":
        return 0 if wanted(sys.stdin.read()) else 1
    if mode == "run":
        return run(argv[2] if len(argv) > 2 else "")
    print("usage: coach.py target | inventory | wanted | run [CONTEXT_FILE]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
