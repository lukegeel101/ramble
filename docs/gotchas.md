# Gotchas

Problems hit while building Ramble, and their verified fixes.

## ffmpeg's avfoundation input drops audio buffers

Recording with `ffmpeg -f avfoundation` dropped about one 11 ms audio buffer in seven on a MacBook Air: 122 holes, 1.3 s of a 9.55 s recording, closed up in the file rather than left as silence, and worse under load.
It also started about 0.5 s late.
Whisper then heard clipped words, and over 159 real dictations the saved audio was a median 4 s shorter than the time spent recording.
Fix: `recorder/mic-record.swift` records through AVAudioRecorder instead, and a 20 s recording now keeps 19.9 s.
ffmpeg stays as the fallback when the native recorder fails to start.

## The native recorder can record pure silence

When macOS gives the recorder no microphone (no permission, or a session without one), AVAudioRecorder still writes a valid file of digital silence instead of failing.
Fix: `dictate.sh` measures the peak with ffmpeg; at -85 dB or lower it reports "the recorder heard nothing", writes `state/native-silent`, and uses ffmpeg until that file is removed.
Testing over SSH always gives silence for the same reason, so test recording from the hotkey.

## `claude` cannot sign in over SSH

On a Mac, Claude Code keeps its login in the keychain, which is locked to the desktop session, so `claude -p` fails when started over SSH.
Fix: test cleanup from Terminal on the machine itself, or through Hammerspoon (`hs -c`), not over SSH.

## Testing the pipeline overwrites your clipboard

`dictate.sh stop` ends with a copy, so a test run, even of a copied folder, replaces whatever is on the clipboard, including a dictation you have not pasted yet.
Fix: `RAMBLE_COPY_CMD` replaces `pbcopy`; the tests set it to write a file, and `tests/bin/pbcopy` catches anything that still reaches `pbcopy`, so a test that forgets the setting fails instead of touching the clipboard.

## The first whisper run after a reboot is slow

whisper.cpp compiles its Metal kernels on the first run, which takes about 20 s; later runs take 1 to 2 s for a typical sentence.
This is expected, not a hang; the cleanup timeout does not cover transcription.

## A cleanup that "improves" the prompt changes what you meant

The first cleanup instructions (now `prompts/cleanup-structured.md`) asked the model to put requests in a logical order, number them, and say preferences directly.
The same transcript came back differently from run to run: two of three runs turned a sentence into a numbered list, and one run of a 305-character dictation came back addressed to the speaker, with a closing sentence that was never said.
A glossary also tempted it to swap one real name for a similar name it listed.
Fix: the default `prompts/cleanup.md` keeps the speaker's sentences, order and wording and only removes fillers and false starts, fixes misheard words and adds punctuation; in six runs on the same cases it changed nothing that was said.
Both prompts now say never to replace one real name with a different one, and `lab.py check` flags rewrites that add, drop or change meaning.

## One `claude -p` call in a few can stall

On a machine whose upload link was saturated, about one call in three stalled mid-stream for 20 s or more.
Fix: `cleanup.py` starts a parallel second attempt after `RAMBLE_CLEANUP_HEDGE` seconds (default 8) and a third after the same wait again; the first answer wins and the rest are killed.

## Hammerspoon starts tasks with a bare PATH

Tasks started by `hs.task` do not see the PATH from your shell profile, so `whisper-cli` and `claude` are not found.
Fix: `dictate.sh` appends `/opt/homebrew/bin`, `/usr/local/bin` and `~/.local/bin` to PATH.
They are appended rather than prepended so the stand-ins the tests put first on PATH still win over a real `claude` or `whisper-cli`.

## The prompt text mentions its own glossary tag

A test that checked `RAMBLE_GLOSSARY=0` by looking for `<glossary>` in the system prompt failed, because the instructions themselves refer to "the <glossary> at the end".
Fix: the tests look for the appended block, `\n<glossary>\n`, instead.

## The first push to a brand-new GitHub repository is refused by the guardrail hook

The pre-push hook refuses any push to `main`, and a new, empty repository has no `main` yet to open a pull request into.
Fix: push the first commit once with `ALLOW_PROTECTED_PUSH=1 git push -u origin main`, then make every later change on a branch through a pull request.

## A `claude -p` experiment picks up your own CLAUDE.md

Running a comparison prompt through plain `claude -p` loads your user-level CLAUDE.md and settings, which leaked my own working rules into a "generic" rewrite.
Fix: pass `--setting-sources project --strict-mcp-config --tools ""` and a `--system-prompt`, run it from an empty folder, as `cleanup.py` does, so the result reflects the prompt alone.
