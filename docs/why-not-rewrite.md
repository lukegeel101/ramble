# Why not just ask a model to "make it a clear prompt"?

These are the real outputs behind the image in the README, from 2026-11-03.
Each rewrite ran once through Claude Code on Claude Haiku (`claude -p --model haiku --tools "" --setting-sources project --system-prompt ...`), with no tools and none of my own settings, from an empty folder.

## The ramble (64 words)

> okay so um I want you to look at the the sign up form, like, the one on the pricing page, and um figure out why it's, you know, double submitting, I think it's the button handler but I'm not sure, and don't change the styling, oh and uh also check if the same thing happens on the contact form, if that makes sense

## Ramble's cleanup (48 words)

`cleanup.py run` with the default `prompts/cleanup.md`:

> I want you to look at the sign up form, the one on the pricing page, and figure out why it's double submitting. I think it's the button handler, but I'm not sure. Don't change the styling. Also check if the same thing happens on the contact form.

## A generic rewrite, three runs

The system prompt for all three was: "Rewrite the user's message into a clear, well-structured prompt for an AI coding agent. Reply with only the rewritten prompt."

The only thing I asked for was a diagnosis: figure out why it double submits.
Look for the line in each that decides whether the agent should change the code.

### Run 1 (347 words): "Make no fixes unless I ask."

Run 1 also told the agent that "the working directory is currently an empty scratchpad", which describes the folder the rewrite ran in, not my project.

> **Task: Diagnose double-submission on the pricing page sign-up form, and check whether the contact form has the same issue**
>
> **Goal:** Find out why the pricing page sign-up form submits twice. The user suspects the button's click handler, but this is unconfirmed. Also check whether the contact form has the same bug.
>
> **Steps:**
> 1. Locate the sign-up form on the pricing page and the contact form. Search the codebase for these components if their file paths aren't obvious. The working directory is currently an empty scratchpad and is not a git repository, so first confirm where the project source lives.
> 2. Trace the submit path for the sign-up form, from the button's click handler through form submission to the request it sends. Check for:
>    - Multiple event bindings (for example, a click handler on the button plus a submit handler on the form, or duplicate listeners from re-mounting or re-rendering).
>    - A missing `preventDefault()` or a `type="submit"` button that also has an `onClick` that submits.
>    - Async handlers that don't disable the button or guard against re-entry while a request is in flight.
>    - Effects or lifecycle hooks that re-register listeners or fire the submit more than once.
> 3. Repeat the same analysis for the contact form and note whether it shares the same cause, such as a common component or hook.
> 4. Report findings before changing anything. Explain the root cause with file and line references, and state how confident you are. If you can't reproduce the problem by reading the code, say so and list what would confirm it, such as checking network logs in the browser.
>
> **Constraints:**
> - Do not change any styling: no CSS, class names, inline styles, or markup that affects appearance.
> - Make no fixes unless I ask. Diagnose first.
> - If you do propose a fix, keep the change minimal and limited to the submit logic.
>
> **Expected output:**
> - The root cause for the sign-up form, with evidence.
> - Whether the contact form has the same issue, with evidence.
> - A proposed minimal fix for each, if the cause is confirmed.

### Run 2 (219 words): "Fix the double submission"

> Investigate why the sign-up form on the pricing page submits twice, then check whether the contact form has the same problem.
>
> **Context:**
> - The sign-up form is on the pricing page.
> - The user suspects the button's click handler may be the cause but isn't sure. Verify this rather than assuming it.
>
> **Tasks:**
> 1. Locate the sign-up form on the pricing page and trace its submit flow: the button's click handler, the form's submit handler, and any other listeners or code that triggers a request.
> 2. Identify the root cause of the double submission. Common causes include duplicate event bindings, a click handler and a form submit firing together, missing `preventDefault` or `disabled`-state handling, and re-rendering that re-attaches listeners.
> 3. Check the contact form for the same pattern or a similar bug.
> 4. Fix the double submission with the smallest change that addresses the root cause. Don't modify styling: no CSS, class names, inline styles, or markup changes that affect appearance.
>
> **Constraints:**
> - Don't change any styling.
> - Keep changes minimal and limited to the submit logic.
>
> **Deliverable:**
> - The root cause for each form, with file and line references.
> - A summary of the changes made, if any.
> - Whether the contact form has the same issue, and if so, whether you fixed it or only flagged it.

### Run 3 (166 words): "If the fix is small and clearly correct, apply it."

> Investigate why the sign-up form on the pricing page submits twice.
>
> 1. Find the sign-up form on the pricing page and trace its submit path. The button's click handler is my main suspect, but confirm that rather than assuming it. Check for duplicate event listeners, a submit handler that fires alongside a click handler, missing `preventDefault()`, a form that submits natively and via JavaScript, and any re-renders or retries that re-trigger the request.
> 2. Explain the root cause clearly, pointing to the specific file and lines involved.
> 3. If the fix is small and clearly correct, apply it. Do not change any styling, including CSS, class names, or inline style values. Summarize exactly what you changed.
> 4. Check whether the contact form has the same double-submit problem, using the same method. Report whether it does and why, or why it doesn't.
>
> If the project location is unclear, look for it before concluding anything. Ask me if you can't find the pricing page or the contact form.

## Ramble's own structured prompt, for comparison

`RAMBLE_PROMPT=structured` (`prompts/cleanup-structured.md`) reorders and separates requests but is also told not to add anything.
On this example its three runs stayed faithful; one split the afterthought into its own paragraph.

> Look at the sign-up form on the pricing page and figure out why it double submits. I think the cause is the button handler, but I'm not sure. Don't change the styling.
>
> Then check whether the same thing happens on the contact form.
