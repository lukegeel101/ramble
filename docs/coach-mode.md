# Coach mode

Coach mode is for people who are new to working with AI agents.
It is off by default; add `RAMBLE_COACH=1` to `config` to turn it on.

## The problem

When an agent's work falls short, someone new says "make them better".
Someone experienced says "use the design and social media skills I have, work from the brand guide with our fonts, colors, spacing and logos, and tell me what falls short before redoing it".
The difference is not effort.
It is knowing what can be asked for, and which skills and files exist.

## Why it does not rewrite your words

Ramble exists because a model told to improve a prompt changes what you meant; [why-not-rewrite.md](why-not-rewrite.md) has three rewrites that each decided differently whether the agent should fix a bug.
So coach mode leaves the cleanup alone.
It is a separate model call, and its output goes below your words, labelled as added:

```text
Make them better

Suggestions Ramble added (I did not say these, and my words above come first; skip anything that doesn't fit):
- Use if it fits: the `social-media-content` skill, the `ui-ux-pro-max` skill.
- Reference: `docs/brand-guide.md`.
- Ask me first: What specifically fell short in these posts or graphics?
- Before redoing the work, say specifically what falls short of a professional LinkedIn standard, both in the copy and in the graphics.
```

The text is pasted, not sent, so you read it first and can delete what you do not want.
The agent can also tell which part you said, and that part always wins.
`state/last-clean.txt` holds only your cleaned-up words, so `lab.py last` still judges only the cleanup, and `state/last-coach.txt` holds the suggestions.

## The rules it runs under

Each of these is enforced by code, not left to the model's judgment:

- **It can only name what you have.** It scans your skills, commands, MCP servers and any brand or style documents in the project. The model picks names from that list and code writes the sentence, so a name that is not on the list is dropped. A free-text suggestion that names a skill or a file is dropped too, because nothing could check it.
- **It only goes where an agent will read it.** The Claude app counts. A terminal, VS Code or Cursor counts only with a live Claude Code session, because otherwise it could be a shell. Slack, Mail and everything else get your words alone. `RAMBLE_COACH_APPS` adds apps.
- **It never costs you your dictation.** A slow, failed or unreadable coach call just means no suggestions. Your text is never held past `RAMBLE_COACH_SECONDS`.
- **Plain replies stay instant.** "Yes", "go ahead" and "the second one" get no model call.
- **Short requests still count.** Cleanup skips the model under six words, but "do better" is exactly the message that needs help, so the coach has its own limit of two words.

These are asked of the model in `prompts/coach.md`, and measured by `lab.py coach` rather than guaranteed:

- Stay silent unless the message needs help, which most do not.
- Never change the job: no new tasks or requirements, no turning a diagnosis into a fix, nothing with outside effects like publishing or deploying.

## What gets sent

With coach mode on, one more call goes to the same model as the cleanup, holding the transcript, the conversation context when there is one, and the names and first 200 characters of the descriptions of your skills, commands and tools.
It reads only server names from `~/.claude.json` and `.mcp.json`, never their settings, because those can hold tokens.
It lists brand documents by path and does not read what is in them.

## Cost and speed

Measured on Haiku through Claude Code, with a small inventory and context:

| Call | Tokens in | Cost |
|---|---|---|
| Cleanup | about 2,400 | about $0.0002 |
| Coach | about 3,500 | about $0.0004 |

The calls run in parallel, so coach mode adds little wait.
Through the real pipeline, three dictations that made the coach call took 10.7 to 11.8 s and two that did not took 9.8 and 11.0 s, on a busy machine where `claude` itself took most of that to start.
A hedged second attempt can double a call's cost.

## How well it works

`lab.py coach` runs the real model over the cases in `evals/coach.json`, with a made-up list of skills in `evals/coach-inventory.txt`, or none at all for the cases that test someone with nothing installed.
Each case says whether the coach should stay silent or suggest something, and what it must never say.

The last full run passed 90 of 90 (18 cases, 5 runs each) on Haiku.
An earlier run of the same cases passed 53 of 54; its one failure told the agent to check "mobile layout" on a bakery landing page, a small requirement nobody had asked for.
Since Haiku is not deterministic, expect an occasional line like that, which is one reason the block says to skip what does not fit.

On the example from [why-not-rewrite.md](why-not-rewrite.md), the coach stayed silent in every run and so did not decide whether the bug gets fixed.

These evals check that the suggestions are safe and relevant, not that an agent does better work with them; that is still to be measured.
