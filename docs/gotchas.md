# Gotchas

Problems hit while building Ramble, and their verified fixes.

## Hammerspoon reload invalidates the CLI message port

- **Symptom:** `hs -c 'hs.reload()'` returned exit 69 with a message-port invalidation error.
- **Root cause:** Reloading Hammerspoon tears down the IPC connection that requested the reload.
- **Fix:** Verify the newly loaded module in a fresh CLI call rather than treating the old connection closing as a load failure.
- **Verified:** 2026-11-14: the subsequent call reported `package.loaded.ramble` present, Accessibility and Screen Recording enabled, and the installed dictation script idle.

## Spoken workspace names become unrelated phrases

- **Symptom:** A spoken channel such as `call center ops` could become `call systems`, and people outside the visible conversation had no directory context.
- **Root cause:** Active-window context and the handwritten glossary supplied no maintained channel/person directory; the compound-identifier guard covered CamelCase identifiers only.
- **Fix:** Add a private validated workspace import, bounded local vocabulary retrieval, a shared Whisper hint budget, short-dictation routing, and a local guard preserving recognized channel/person phrases.
  Refresh via the verified Slack connector's joined-channel directory and member profiles; never read messages to construct this vocabulary.
- **Verified:** 2026-11-14: the full fixture dictation path rejects an injected `call systems` rewrite, and generated speech passed through real Whisper and Claude with `call-center-ops` preserved in the file clipboard.
  Live fictional cases passed in both cleanup modes; import identity, permissions, malformed data and negative matching paths are covered offline.

## Structured cleanup expands a spoken first name

- **Symptom:** A live synthetic test changed `Ask Mira about the build` into `Ask Mira Bellamy about the build` after receiving a directory entry.
- **Root cause:** The first directory guard checked only that the spoken first name survived; a surname could be added while satisfying that check.
- **Fix:** Reject an introduced longer person-name form when only its shorter alias was spoken, while allowing a near-spelled surname actually present in the transcript to be corrected.
- **Verified:** 2026-11-14: focused tests cover both rejected expansion and permitted surname correction; all six live structured-mode cases passed after the fix.

## Slack user search cannot enumerate the directory

- **Symptom:** An empty keyword search returned `INVALID_ARGUMENT`; a wildcard search returned no users.
- **Root cause:** The connected Slack user-search tool is a search interface, not a workspace user-list endpoint.
- **Fix:** Enumerate active joined channels, paginate their human member lists, and deduplicate profiles by user ID.
  Document the resulting coverage instead of claiming to have every workspace user.
- **Verified:** 2026-11-14: all 20 returned channels reported completed member pagination, yielding 18 unique active people.

## Captured identifier spellings are ignored or acquire a duplicated suffix

- **Symptom:** A user-initiated desktop OCR test captured `SilverOtterCache` correctly, but cleanup returned "Silver Otter cache".
  Another test produced "CopperFinchQueue queue" even though queue was spoken once.
- **Root cause:** Context capture succeeded, but the cleanup model applied the short-transcript and valid-name preservation rules inconsistently to compound identifiers.
  Synthetic replay reproduced the duplicated suffix and exposed unsupported replacement of a different name with the contextual name.
  Prompt-only revisions still sometimes added a category such as service or completed an ordinary description into an identifier.
- **Fix:** Both cleanup prompts explicitly consume the complete spoken identifier once, preserve its exact contextual spelling, and prohibit importing category labels or substituting different constituent words.
  A local output check independently rejects emitted contextual compound names without a complete matching word sequence in the original, ambiguous spellings, excess name occurrences, and inserted words beside a corrected name.
  A rejected rewrite falls back to local cleanup of the original while retaining only fully supported identifier spellings.
  This check is conservative and does not guess phonetic matches for compound names.
- **Verified:** 2026-11-14: 66 offline tests passed, including source-preservation regressions, and synthetic speech passed through real Whisper, cleanup, the local check, and a file clipboard as "Please restart the SilverOtterCache."
  The default prompt passed all 12 repeated live synthetic cases.
  Structured mode passed all five contextual cases; its no-context control intentionally shortened "Please restart" to "Restart", so the evaluator accepts that documented direct style only in structured mode.
  The opt-in `tests/eval_context_spelling.py` suite tests the real cleanup pipeline with fictional examples without reading saved dictations.
  The user-initiated native test also confirmed `window-ocr` capture; capture success alone was insufficient evidence of correct cleanup.

## Debug replay can retransmit private captured context

- **Symptom:** Automatic approval review rejected a proposed replay of the saved dictation and captured conversation to the cleanup provider.
- **Root cause:** Debugging retransmission of that private payload was not specifically authorized by the original feature request.
- **Fix:** Inspect the relevant saved evidence locally, then reproduce with newly constructed fictional context and test sentences.
  The live regression runner disables the personal glossary, uses no saved dictation state, and requires `--live` to send its synthetic cases.
- **Verified:** 2026-11-14: the rejected replay was not executed; the synthetic baseline reproduced the duplication and wrong-name errors, and the audio smoke test used synthetic speech and a file clipboard.

## Context can come from a different Claude conversation

- **Symptom:** Dictating into one terminal or the GPT desktop app could use another Claude session, or no context at all.
- **Root cause:** The old reader selected the most recently modified interactive Claude transcript rather than matching the destination.
- **Fix:** Capture the active app/window, read only its focused terminal pane or conversation Accessibility subtree, and use on-device window OCR for supported desktop apps without exposed text.
  Remove the session-recency fallback entirely and report capture status without logging message text.
- **Verified:** 2026-11-14: AX tree fixtures cover destination changes, sidebar exclusion, secure fields, unsupported apps, and missing permissions; Python regressions prove a newer unrelated Claude transcript is never selected.
  A synthetic spoken recording passed through real Whisper and signed-in Claude cleanup, correcting "marzipan queue" to "MarzipanQueue" from supplied context.

## Short dictations bypassed contextual correction

- **Symptom:** A short request with a context-specific term only received local filler removal.
- **Root cause:** The word-count threshold bypassed the cleanup model even when conversation context existed.
- **Fix:** Use model cleanup for short dictations when context is available, retaining the local path when it is absent.
- **Verified:** 2026-11-14: the full shell pipeline test confirms a three-word dictation reaches cleanup with the captured context and is copied to the safe test clipboard.

## The installed dictation tool can predate the Ramble install folder

- **Symptom:** `~/.ramble` was absent although the menu button and dictation shortcut worked.
- **Root cause:** Hammerspoon's inline module still invoked `~/Claude/Dictation/dictate.sh`, which has separate scripts and older context behavior.
- **Fix:** Inspect the actual Hammerspoon entry point before diagnosing a missing installation.
  For the verified mac16 migration, back up the legacy-only `init.lua`, install Ramble, preserve the personal glossary and existing Whisper model, and replace the old inline bindings with one `require("ramble")`.
  Do not append a second dictation module alongside the legacy bindings.
- **Verified:** 2026-11-14: the new `~/.ramble` reports IDLE; Hammerspoon reports exactly the Control+Option+., Command+Option+., and raw-recovery bindings.
  The original installation and `init.lua.before-ramble-context-20261114` remain available for rollback.

## Native desktop messages can be absent from Accessibility

- **Symptom:** The GPT desktop app exposed only empty nested groups, with no focused message element.
- **Root cause:** The installed `com.openai.codex` app did not expose its conversation text through the tested Accessibility attributes, even after requesting manual Accessibility exposure.
- **Fix:** Use local Apple Vision OCR of that active desktop window when text is unavailable.
  Screen Recording permission for Hammerspoon is required in addition to Accessibility.
  Report `screen-recording-denied` instead of substituting a different conversation.
- **Verified:** 2026-11-14: a native rendered-image fixture recovered `MarzipanQueue` and `retryBudget` exactly; after Luke enabled permission, Hammerspoon reported both permission checks true.
  Computer Use denied direct Terminal and GPT desktop control, so no successful automated desktop conversation test is claimed.

## Local verification has machine-specific constraints

- **Symptom:** Swift's first build could not write its module cache, ShellCheck was missing, and the other machine's coordination mailbox was unreachable.
- **Root cause:** The execution sandbox excluded the default Swift cache; the lint tool was not installed; the air8 SSH connection timed out even after an approved retry.
- **Fix:** Compile with approved cache access and install ShellCheck through Homebrew.
  Continue repository coordination through the verified GitHub branch claim without treating the unreachable mailbox as evidence that the other machine is idle.
- **Verified:** 2026-11-14: both native helpers compiled, ShellCheck passed, and `agent-branch` created an isolated mac16 claim.
  The mailbox remained unreachable; no cross-machine state was modified.

## A native UI test can outlive its command timeout

- **Symptom:** A Hammerspoon AppleScript fixture timed out at the IPC client while the underlying request was still completing.
- **Root cause:** A synchronous automation request blocked Hammerspoon; the later capture could observe a changed front window.
- **Fix:** Do not count that fixture as a controlled end-to-end success or retry it through another UI interface after a safety denial.
  Production capture receives the stop-press app/window identity and fails closed on a mismatch.
- **Verified:** 2026-11-14: destination mismatch regressions pass; the test console was closed and Hammerspoon was reloaded for the installed build.
  The successful audio-to-cleanup smoke test used only synthetic input and a file clipboard.

## A shell fixture embedded in Python can break test discovery

- **Symptom:** The first new pipeline regression failed to import because of nested quote escaping in its fake Hammerspoon script.
- **Root cause:** Shell quote syntax was embedded incorrectly inside a Python string.
- **Fix:** Use a small Python stand-in that emits JSON instead of nested shell quoting.
- **Verified:** 2026-11-14: all 53 unit and pipeline regression tests pass after the fixture correction.

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
