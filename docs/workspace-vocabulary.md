# Workspace vocabulary

Ramble can recognize Slack channel names, people's names and aliases, and the professional context explicitly supplied in their profiles.
This works alongside active-window context in terminals and desktop apps; Slack does not need to be open.
It is a spelling aid, not a searchable copy of Slack message history.

## What happens during dictation

1. A bounded selection of directory names joins the personal glossary in Whisper's local transcription hint.
2. After transcription, local matching selects up to 12 relevant directory entries, capped at 6,000 characters, for the existing cleanup model.
3. Entries supply canonical spelling, aliases, channel purpose and available job title or explicitly supplied professional background.
4. A local guard rejects cleanup that removes or substitutes an exactly recognized channel/person phrase, falling back to the original words with fillers removed.

For example, `call center ops` can be spelled `call-center-ops`, but cannot become `call systems` when the first phrase is in the directory.
Near spellings such as `Myra Bellamy` can nominate `Mira Bellamy` as a candidate; they are not automatically replaced by local fuzzy matching.
Ambiguous audio can still be misrecognized, and the directory cannot reconstruct words that neither Whisper nor the cleanup model recognized.
The prompt instructs cleanup to preserve first names as spoken and not add job titles, background facts or Slack mention syntax.

The microphone tooltip has a separate `Workspace vocabulary` line with directory counts and how many candidates were used in the last cleanup.
The `Context` line continues to describe active-window Accessibility/OCR capture.
`python3 ~/.ramble/workspace.py status` shows counts, workspace and last import time without printing names or message content.

## Private storage and controls

The directory is `~/.ramble/workspace.json`, written atomically with mode `0600` and ignored by Git.
Install/reinstall preserves it and the handwritten `glossary.md`.
No Slack credentials are needed by Ramble, and Ramble makes no Slack API requests during dictation.
Names in the Whisper hint remain local; selected name/profile entries accompany the dictated text to the same Claude cleanup backend already configured for Ramble.
A cached directory is available offline, although model cleanup still requires its normal connection.
Missing, disabled or malformed directories do not prevent dictation.

Set `RAMBLE_WORKSPACE=0` in `~/.ramble/config` to disable both its Whisper hint and cleanup reference.
Set `RAMBLE_WORKSPACE_FILE` to use a different private directory file.
`RAMBLE_CONTEXT=0` controls active-window capture separately; it does not disable workspace vocabulary.
`RAMBLE_HINT=0` disables all Whisper hints, while `RAMBLE_GLOSSARY=0` disables only the handwritten glossary.

## Refresh through the connected Slack account

Refresh is an explicit import, not automatic background synchronization.
Ask the assistant with the Slack connector to refresh Ramble's workspace vocabulary when channels or people change.
The initial directory covers active joined public/private channels and their active human members; it is not guaranteed to include every person or unjoined channel in the workspace.

The refresh procedure is:

1. Verify the connected user's profile and workspace ID with `slack_read_user_profile` and `slack_list_workspaces`.
2. List active joined channels using `slack_list_user_channels`, scoped to that workspace, excluding archived channels and DMs; follow every pagination cursor.
3. List each channel's members using `slack_list_channel_members`, excluding bots and deactivated people; follow every pagination cursor and deduplicate by user ID.
4. Export only the schema below to a private temporary file, preserving names, display-name/handle aliases and profile titles.
   Do not copy email addresses, phone numbers, messages, credentials, or infer roles from channel membership.
   If professional background is explicitly provided later, it can be included in the optional `background` field.
5. Import the complete verified snapshot, specifying the expected workspace ID, and delete the temporary export afterward.

```sh
python3 ~/.ramble/workspace.py import /private/tmp/ramble-directory.json --workspace-id TWORKSPACE
python3 ~/.ramble/workspace.py status
```

The importer validates before replacing anything, removes unsupported fields, and refuses a workspace-ID mismatch.
A refresh replaces the snapshot, so removed or renamed channels do not linger; explicitly maintained aliases/background must be carried into the refreshed export.
Changes apply on the next dictation without reloading Hammerspoon.

```json
{
  "version": 1,
  "workspace": {"id": "TWORKSPACE", "name": "Example"},
  "source": "Verified Slack directory export",
  "channels": [
    {"id": "C1", "name": "call-center-ops", "purpose": "Call center operations"}
  ],
  "people": [
    {"id": "U1", "name": "Mira Bellamy", "aliases": ["Mira"], "title": "Support engineer"}
  ]
}
```

## Verification

Risk is medium: directory handling changes dictated text and the reference data sent to cleanup.
Offline tests cover faithful name preservation, relevant retrieval, bounds, escaped reference data, disabled/missing/malformed directories, identity mismatches, private writes, installation preservation, and the full dictation pipeline with a file clipboard.
The following live checks use fictional directory data, with no saved conversation or personal glossary:

```sh
python3 -m unittest discover -s tests -t . -v
python3 tests/eval_workspace.py --live
python3 tests/eval_workspace.py --live --prompt structured
python3 tests/eval_workspace_audio.py --live --model ~/.ramble/models/ggml-small.en.bin
```

The audio check uses macOS-generated speech, the installed local Whisper model, real model cleanup, and a temporary file clipboard.
It exercises recording start/stop via a fixture recorder, not the physical microphone or destination app's paste UI.
