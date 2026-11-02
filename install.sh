#!/bin/bash
# Install Ramble on this Mac.
#
#   ./install.sh
#
# Settings (environment variables):
#   RAMBLE_HOME        install folder (default ~/.ramble)
#   RAMBLE_MODEL_NAME  whisper.cpp model to download (default ggml-small.en.bin; ggml-base.en.bin is faster)
#   HAMMERSPOON_DIR    Hammerspoon config folder (default ~/.hammerspoon)
#   RAMBLE_SKIP_CHECKS=1  do not check for Homebrew, whisper-cpp, Hammerspoon and Claude Code
#   RAMBLE_SKIP_MODEL=1   do not download the model
#   RAMBLE_SKIP_BUILD=1   do not build the native recorder
#
# It copies the scripts into RAMBLE_HOME, keeps an existing config and glossary.md, builds recorder/mic-record,
# downloads the model, and installs the Hammerspoon module: ramble.lua next to your init.lua, plus one
# require("ramble") line added to the end of init.lua (backed up first). An existing init.lua is never replaced.
# Running it again updates the scripts and leaves your settings alone.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${RAMBLE_HOME:-$HOME/.ramble}"
HS="${HAMMERSPOON_DIR:-$HOME/.hammerspoon}"
MODEL_NAME="${RAMBLE_MODEL_NAME:-ggml-small.en.bin}"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MODEL_NAME"
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin"

say() { printf '%s\n' "$*"; }
fail() { printf 'install: %s\n' "$*" >&2; exit 1; }

case "$DEST" in *" "*) fail "RAMBLE_HOME must not contain spaces ($DEST)";; esac

if [ "${RAMBLE_SKIP_CHECKS:-0}" != "1" ]; then
  [ "$(uname -s)" = "Darwin" ] || fail "Ramble runs on macOS only."
  missing=()
  command -v brew >/dev/null || missing+=("Homebrew: https://brew.sh")
  command -v whisper-cli >/dev/null || missing+=("whisper.cpp: brew install whisper-cpp")
  [ -d /Applications/Hammerspoon.app ] || [ -d "$HOME/Applications/Hammerspoon.app" ] \
    || missing+=("Hammerspoon: brew install --cask hammerspoon")
  command -v swiftc >/dev/null || missing+=("Xcode Command Line Tools: xcode-select --install")
  if [ ${#missing[@]} -gt 0 ]; then
    say "Install these first, then run ./install.sh again:"
    for m in "${missing[@]}"; do say "  - $m"; done
    exit 1
  fi
  command -v ffmpeg >/dev/null || say "Optional: brew install ffmpeg (fallback recorder and the silent-microphone check)."
  if ! command -v claude >/dev/null && [ ! -f "${RAMBLE_API_KEY_FILE:-$HOME/.config/ramble/anthropic-api-key}" ]; then
    say "Note: no Claude Code (claude) found and no API key file; dictations will be copied as heard until one exists."
    say "      Install Claude Code from https://code.claude.com, or see 'Direct API' in the README."
  fi
fi

say "Installing into $DEST"
mkdir -p "$DEST/prompts" "$DEST/recorder" "$DEST/models" "$DEST/state" "$DEST/recordings"
install -m 755 "$SRC/dictate.sh" "$SRC/cleanup.py" "$SRC/context.py" "$SRC/lab.py" "$DEST/"
install -m 644 "$SRC"/prompts/*.md "$DEST/prompts/"
install -m 644 "$SRC/recorder/mic-record.swift" "$DEST/recorder/"
install -m 644 "$SRC/config.example" "$SRC/glossary.example.md" "$DEST/"
[ -f "$DEST/config" ] || cp "$SRC/config.example" "$DEST/config"
[ -f "$DEST/glossary.md" ] || cp "$SRC/glossary.example.md" "$DEST/glossary.md"

if [ "${RAMBLE_SKIP_BUILD:-0}" != "1" ]; then
  say "Building the native recorder"
  swiftc -O "$DEST/recorder/mic-record.swift" -o "$DEST/recorder/mic-record"
fi

if [ "${RAMBLE_SKIP_MODEL:-0}" != "1" ] && [ ! -s "$DEST/models/$MODEL_NAME" ]; then
  say "Downloading $MODEL_NAME (several hundred MB)"
  curl -fL --progress-bar -o "$DEST/models/$MODEL_NAME.part" "$MODEL_URL"
  mv "$DEST/models/$MODEL_NAME.part" "$DEST/models/$MODEL_NAME"
fi
if [ "$MODEL_NAME" != "ggml-small.en.bin" ] && ! grep -q '^RAMBLE_MODEL=' "$DEST/config"; then
  printf 'RAMBLE_MODEL="%s"\n' "$DEST/models/$MODEL_NAME" >> "$DEST/config"
fi

mkdir -p "$HS"
sed "s|@RAMBLE_HOME@|$DEST|g" "$SRC/hammerspoon/ramble.lua" > "$HS/ramble.lua"
INIT="$HS/init.lua"
if [ -f "$INIT" ] && grep -q 'require("ramble")' "$INIT"; then
  say "Hammerspoon: $INIT already loads ramble"
else
  if [ -f "$INIT" ]; then
    backup="$INIT.bak-$(date +%Y%m%d-%H%M%S)"
    cp "$INIT" "$backup"
    say "Hammerspoon: backed up $INIT to $backup"
  fi
  printf '\n-- Ramble dictation (scripts in %s)\nrequire("ramble")\n' "$DEST" >> "$INIT"
  say "Hammerspoon: added require(\"ramble\") to $INIT"
fi
# shellcheck disable=SC2016 # the backticks are Lua comment text, not a command
grep -q 'require("hs.ipc")' "$INIT" || printf 'require("hs.ipc")  -- lets `hs -c` reach Hammerspoon from a terminal\n' >> "$INIT"

cat <<EOF

Done. Next:
  1. Open Hammerspoon and choose Reload Config (the menu bar shows a microphone).
  2. Press Control+Option+. and allow microphone access for Hammerspoon when macOS asks.
  3. For auto-paste, allow Hammerspoon under System Settings, Privacy & Security, Accessibility.
  4. Put your own names in $DEST/glossary.md and settings in $DEST/config.
EOF
