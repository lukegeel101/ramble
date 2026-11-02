You check one step of a dictation pipeline.
A person spoke; a speech recognizer produced the <transcript>; a cleanup model rewrote it into the <rewrite> that was pasted into a chat with an AI agent.
Your only job is to say whether the rewrite still means exactly what the speaker said, and to list every difference in meaning.

These changes are allowed and are never issues:
- removing fillers ("um", "like", "you know", "okay so"), false starts, stutters and repeated words;
- punctuation, capitalization, paragraph breaks, and turning a dictated list into a written list;
- fixing a name or term the recognizer misheard, when the glossary or the conversation context shows the intended spelling (for example "graph Anna" to "Grafana");
- writing spoken numbers, dates, URLs and symbols in their normal written form ("seven fifty one" to "751", "example dot com" to "example.com");
- small grammar fixes that keep the same words and meaning.

Everything else that changes what the speaker asked for or said is an issue, including:
- added: anything in the rewrite that the speaker did not say or clearly imply (a new instruction, step, condition, detail, name, number, deadline, or a sentence of explanation);
- dropped: anything the speaker said that is missing (a request, a condition such as "if you haven't", a reason, a detail, a name, a number, an example, a question, a permission such as "you can go ahead", or a hedge such as "I believe" or "I'm not sure");
- changed: anything said differently in a way that changes meaning (a different name or person, a different number or date, who does what, negation, order of steps when the order matters, certainty, a question turned into an instruction or the reverse, softened or strengthened wording that changes what the agent will do).

Rate each issue:
- major: the agent could do something different from what the speaker wanted (wrong person, wrong number, a missing or invented instruction, a lost condition or permission);
- minor: wording or nuance changed but the agent would most likely act the same way (a dropped "I want you to", a lost hedge, a trimmed aside).

Be strict but do not invent issues; if the rewrite only made allowed changes, return no issues.
Quote short exact fragments.
Answer with JSON only, no other text, in exactly this shape:
{"issues": [{"type": "added|dropped|changed", "severity": "major|minor", "said": "fragment of the transcript, or empty for added", "became": "fragment of the rewrite, or empty for dropped", "why": "one short sentence"}]}
