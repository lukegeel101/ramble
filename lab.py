#!/usr/bin/env python3
"""Ramble's test bench: find which step changed what you said, transcription or cleanup.

    lab.py compare TRANSCRIPT_FILE [--context F] [--ref TEXT] [--json]   run every cleanup variant on a transcript
    lab.py audio WAV [--context F] [--ref TEXT] [--json]                 transcribe with and without the name hint,
                                                                          then compare the cleanups
    lab.py check TRANSCRIPT_FILE REWRITE_FILE [--context F] [--json]     meaning check of one rewrite
    lab.py last [--json]                                                  meaning check of the last dictation
    lab.py sentences                                                      test sentences to read aloud

Cleanup variants: the live instructions, the same again (Haiku is not deterministic), the structured instructions,
without the glossary, without the conversation context (when there is one), and the local filler strip (no model).
With --ref (what you actually said) each output gets a word error rate and a list of glossary names it lost.

The meaning check has a second, stronger model (RAMBLE_MEANING_MODEL, default sonnet) compare the transcript with a
rewrite, using prompts/meaning.md plus the glossary, and list anything added, dropped or changed, rated major or minor.
A rewrite with the same words as the transcript (or the transcript minus fillers) passes without a model call.
Everything here runs through cleanup.py and `claude -p`; nothing touches dictate.sh's recording or the clipboard.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "state"
JUDGE_MODEL = os.environ.get("RAMBLE_MEANING_MODEL", "sonnet")
MODEL = os.environ.get("RAMBLE_MODEL") or str(HERE / "models/ggml-small.en.bin")
ENV = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
ENV["PATH"] = f"{os.environ.get('PATH', '')}:/opt/homebrew/bin:/usr/local/bin:{Path.home()}/.local/bin"

SENTENCES = [
    "Please read the latest messages in the release channel and draft a reply for me to review.",
    "Tell Sonny that Priya will take the Grafana alerts this week, and ask him to confirm by Friday.",
    "Check whether the Postgres migration for Project Lighthouse ran on staging, and if it did, list the tables it changed.",
    "Open example dot com slash docs and tell me what changed since PR seven fifty one.",
    "Before you start building, give me three options and tell me which one you recommend and why.",
]


def ms_since(t0):
    return int((time.time() - t0) * 1000)


def read(p):
    p = Path(p)
    return p.read_text(errors="replace") if p.is_file() else ""


# ---- pipeline steps ------------------------------------------------------------------------------------------------

def hint():
    p = subprocess.run([sys.executable, str(HERE / "cleanup.py"), "hint"], capture_output=True, text=True, env=ENV)
    return p.stdout.strip()


def transcribe(wav, with_hint):
    args = ["whisper-cli", "-m", MODEL, "-f", str(wav), "-nt", "-np", "-t", "4"]
    h = hint() if with_hint else ""
    if h:
        args += ["--prompt", h]
    t0 = time.time()
    try:
        p = subprocess.run(args, capture_output=True, text=True, env=ENV, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"text": "", "ms": ms_since(t0), "error": str(error)}
    text = re.sub(r"\s+", " ", p.stdout.replace("[BLANK_AUDIO]", "")).strip()
    return {"text": text, "ms": ms_since(t0), "error": "" if p.returncode == 0 else p.stderr[-400:]}


def cleanup(text, context_file=None, glossary=True, prompt=None):
    args = [sys.executable, str(HERE / "cleanup.py"), "run"] + ([str(context_file)] if context_file else [])
    env = {**ENV, "RAMBLE_GLOSSARY": "1" if glossary else "0"}
    if prompt:
        env["RAMBLE_PROMPT"] = prompt
    t0 = time.time()
    p = subprocess.run(args, input=text, capture_output=True, text=True, timeout=90, env=env)
    return {"text": p.stdout.strip(), "ms": ms_since(t0),
            "error": "" if p.returncode == 0 else (p.stderr.strip()[-400:] or "cleanup failed")}


def strip(text):
    p = subprocess.run([sys.executable, str(HERE / "cleanup.py"), "strip"], input=text, capture_output=True, text=True, env=ENV)
    return {"text": p.stdout.strip(), "ms": 0, "error": ""}


# ---- scoring -------------------------------------------------------------------------------------------------------

NUMS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                                    "fifteen sixteen seventeen eighteen nineteen".split())}
NUMS.update({w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())})


def words(text):
    """Comparable words: lower case, "dot"/"slash" dropped (said aloud for "." and "/"), number words as digits, and
    letters split from digits ("PR751" = "pr 751"), so "example.com/docs" or "PR751" is not counted as wrong against
    "example dot com slash docs" or "PR seven fifty one"."""
    raw = re.findall(r"[a-z]+(?:'[a-z]+)?|[0-9]+", text.lower())
    out, i = [], 0
    while i < len(raw):
        w = raw[i]
        if w in ("dot", "slash"):
            i += 1
            continue
        if w in NUMS:  # a run of number words: "seven fifty one" -> 751, "twenty one" -> 21
            digits, j = "", i
            while j < len(raw) and raw[j] in NUMS:
                n = NUMS[raw[j]]
                if n >= 20 and j + 1 < len(raw) and raw[j + 1] in NUMS and NUMS[raw[j + 1]] < 10:
                    n, j = n + NUMS[raw[j + 1]], j + 1
                digits += str(n)
                j += 1
            out.append(digits)
            i = j
            continue
        out.append(w)
        i += 1
    return out


def wer(ref, hyp):
    """Word error rate of hyp against ref: (substitutions + deletions + insertions) / words in ref."""
    r, h = words(ref), words(hyp)
    if not r:
        return None
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hw in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw))
        prev = cur
    return round(prev[-1] / len(r), 3)


def glossary_names():
    """Proper names worth checking: the transcriber hint plus the names that start glossary bullets."""
    text = read(HERE / "glossary.md")
    names = set()
    m = re.search(r"^## Transcriber hint\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if m:
        names |= {n.strip().rstrip(".") for n in m.group(1).replace("\n", " ").split(",") if n.strip()}
    names |= set(re.findall(r"^- ([A-Z][A-Za-z0-9]+(?: [A-Z][A-Za-z0-9]+)?)[ :,(]", text, re.M))
    return sorted(n for n in names if len(n) > 2)


def score(ref, text):
    if not ref:
        return None
    present = [n for n in glossary_names() if re.search(rf"\b{re.escape(n)}\b", ref, re.I)]
    missing = [n for n in present if not re.search(rf"\b{re.escape(n)}\b", text, re.I)]
    return {"wer": wer(ref, text), "names": len(present), "namesMissing": missing}


# ---- meaning check ------------------------------------------------------------------------------------------------

def meaning(raw, out, context_file=None):
    """{"issues": [{type, severity, said, became, why}], "ms", "error", "model"} for the rewrite `out` of `raw`."""
    raw, out = raw.strip(), out.strip()
    if not raw or not out:
        return {"issues": [], "ms": 0, "error": "nothing to compare", "model": ""}
    if words(out) in (words(raw), words(strip(raw)["text"])):
        return {"issues": [], "ms": 0, "error": "", "model": "same words"}
    system = read(HERE / "prompts/meaning.md")
    if (HERE / "glossary.md").is_file():
        system += "\n<glossary>\n" + read(HERE / "glossary.md").strip() + "\n</glossary>\n"
    ctx = read(context_file) if context_file else ""
    body = (f"<context>\n{ctx}\n</context>\n\n" if ctx.strip() else "") + \
        f"<transcript>\n{raw}\n</transcript>\n\n<rewrite>\n{out}\n</rewrite>\n"
    t0 = time.time()
    try:
        p = subprocess.run(["claude", "-p", "--model", JUDGE_MODEL, "--tools", "", "--no-session-persistence",
                            "--setting-sources", "project", "--strict-mcp-config", "--system-prompt", system,
                            "--output-format", "text"],
                           input=body, capture_output=True, text=True, timeout=120, cwd=HERE, env=ENV)
    except subprocess.TimeoutExpired:
        return {"issues": [], "ms": ms_since(t0), "error": "the meaning check took longer than 120 s", "model": JUDGE_MODEL}
    except OSError as error:
        return {"issues": [], "ms": ms_since(t0), "error": str(error), "model": JUDGE_MODEL}
    found = re.search(r"\{.*\}", p.stdout, re.S)
    try:
        issues = json.loads(found.group(0))["issues"] if found else None
    except (ValueError, KeyError, TypeError):
        issues = None
    if not isinstance(issues, list):
        return {"issues": [], "ms": ms_since(t0), "error": (p.stderr.strip() or p.stdout.strip() or "no answer")[-300:],
                "model": JUDGE_MODEL}
    keep = [{k: str(i.get(k) or "")[:400] for k in ("type", "severity", "said", "became", "why")}
            for i in issues if isinstance(i, dict)]
    return {"issues": keep, "ms": ms_since(t0), "error": "", "model": JUDGE_MODEL}


# ---- runs ----------------------------------------------------------------------------------------------------------

def cleanup_variants(raw, context_file, ref):
    ctx = context_file if context_file and Path(context_file).is_file() and Path(context_file).stat().st_size else None
    jobs = {
        "live": ("Cleanup as live", lambda: cleanup(raw, ctx)),
        "again": ("Cleanup as live, second try", lambda: cleanup(raw, ctx)),
        "structured": ("Structured cleanup (reorders and numbers)", lambda: cleanup(raw, ctx, prompt="structured")),
        "noglossary": ("Cleanup without the glossary", lambda: cleanup(raw, ctx, glossary=False)),
        "strip": ("Fillers removed only (no model)", lambda: strip(raw)),
    }
    if ctx:
        jobs["nocontext"] = ("Cleanup without the conversation context", lambda: cleanup(raw))
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {key: pool.submit(fn) for key, (_, fn) in jobs.items()}
        out = []
        for key, (label, _) in jobs.items():
            try:
                res = futures[key].result()
            except Exception as error:  # noqa: BLE001
                res = {"text": "", "ms": 0, "error": str(error)}
            out.append({"key": key, "label": label, **res, "score": score(ref, res["text"])})
        checked = {v["key"]: pool.submit(meaning, raw, v["text"], ctx)
                   for v in out if v["key"] in ("live", "structured") and v["text"]}
        for v in out:
            if v["key"] in checked:
                v["meaning"] = checked[v["key"]].result()
    return out


def run_audio(wav, context_file=None, ref=""):
    live, plain = transcribe(wav, True), transcribe(wav, False)
    transcripts = [{"key": "hint", "label": "Transcription with the name hint", **live, "score": score(ref, live["text"])},
                   {"key": "nohint", "label": "Transcription without the name hint", **plain, "score": score(ref, plain["text"])}]
    return {"transcripts": transcripts, "cleanups": cleanup_variants(live["text"], context_file, ref) if live["text"] else [],
            "ref": ref}


def run_text(raw, context_file=None, ref=""):
    return {"transcripts": [{"key": "given", "label": "Transcript given", "text": raw, "ms": 0, "error": "",
                             "score": score(ref, raw)}],
            "cleanups": cleanup_variants(raw, context_file, ref), "ref": ref}


# ---- output --------------------------------------------------------------------------------------------------------

def show_meaning(m, indent="  "):
    lines = []
    if m.get("error"):
        lines.append(f"{indent}meaning check failed: {m['error']}")
    elif not m.get("issues"):
        lines.append(f"{indent}meaning: unchanged ({m.get('model') or 'no model'})")
    for i in m.get("issues", []):
        lines.append(f"{indent}{i['severity']} {i['type']}: \"{i['said']}\" -> \"{i['became']}\" ({i['why']})")
    return lines


def show(result):
    lines = []
    for section in ("transcripts", "cleanups"):
        for v in result.get(section, []):
            head = f"## {v['label']}" + (f" ({v['ms']} ms)" if v.get("ms") else "")
            lines += [head, v["text"] or f"(nothing: {v.get('error') or 'empty'})"]
            if v.get("score"):
                s = v["score"]
                lines.append(f"  word error rate {s['wer']}; names lost: {', '.join(s['namesMissing']) or 'none'}")
            if "meaning" in v:
                lines += show_meaning(v["meaning"])
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def option(argv, name):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    as_json = "--json" in argv
    ctx, ref = option(argv, "--context"), option(argv, "--ref") or ""
    if cmd == "sentences":
        print("\n".join(SENTENCES))
        return 0
    if cmd in ("compare", "audio") and len(argv) > 2:
        result = run_audio(Path(argv[2]), ctx, ref) if cmd == "audio" else run_text(read(argv[2]).strip(), ctx, ref)
        sys.stdout.write(json.dumps(result) + "\n" if as_json else show(result))
        return 0
    if cmd in ("check", "last"):
        if cmd == "check" and len(argv) > 3:
            raw, out = read(argv[2]), read(argv[3])
        else:
            raw, out, ctx = read(STATE / "last-raw.txt"), read(STATE / "last-clean.txt"), ctx or STATE / "last-context.txt"
        if not raw.strip() or not out.strip():
            print("nothing to check: need a transcript and a rewrite", file=sys.stderr)
            return 1
        m = meaning(raw, out, ctx)
        sys.stdout.write(json.dumps(m) + "\n" if as_json else "\n".join(show_meaning(m, "")) + "\n")
        return 0 if not m.get("error") else 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
