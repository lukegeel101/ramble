#!/bin/bash
# Push-to-talk dictation for AI agents.
# The first press records, the second press stops; the audio is transcribed on this Mac with whisper.cpp,
# cleaned up into a faithful prompt by Claude Haiku, and put on the clipboard.
#
#   dictate.sh toggle | start | stop | status | raw
#
# The cleanup step sends the transcript text, never the audio, to Claude through cleanup.py.
# If cleanup fails or is turned off, the transcript is copied as heard.
# With RAMBLE_COACH=1, labelled suggestions from coach.py go below the text when an agent is the target.
# `raw` copies the transcript of the last dictation as heard.
# The last recording is kept at recordings/last.wav for a re-run; earlier ones are deleted.
#
# Only one command runs at a time: while a stop is still transcribing, toggle, start and stop
# answer BUSY instead of starting a new recording. Each recording has its own file, so a new
# recording can never delete or move the one being transcribed.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$HERE/state"; REC="$HERE/recordings"; LOG="$HERE/dictate.log"
mkdir -p "$STATE" "$REC"
# Everything in config is exported, so cleanup.py and context.py see the same settings.
# shellcheck source=/dev/null
if [ -f "$HERE/config" ]; then set -a; . "$HERE/config"; set +a; fi
MODEL="${RAMBLE_MODEL:-$HERE/models/ggml-small.en.bin}"
DEVICE="${RAMBLE_DEVICE:-default}"                 # ffmpeg recorder only: an avfoundation input name
CLEANUP="${RAMBLE_CLEANUP:-1}"                     # 0 copies the transcript as heard
CLEANUP_SECONDS="${RAMBLE_CLEANUP_SECONDS:-30}"
CLEANUP_MIN_WORDS="${RAMBLE_CLEANUP_MIN_WORDS:-6}" # shorter dictations only get the local filler strip
HINT="${RAMBLE_HINT:-1}"                           # 0: whisper without the glossary's name hint
CONTEXT="${RAMBLE_CONTEXT:-1}"                     # 0: clean up without the conversation's last messages
COACH="${RAMBLE_COACH:-0}"                         # 1: add labelled suggestions below your words; see coach.py
COACH_SECONDS="${RAMBLE_COACH_SECONDS:-20}"
RECORDER="${RAMBLE_RECORDER:-native}"              # native (recorder/mic-record) or ffmpeg
THREADS="${RAMBLE_THREADS:-4}"
PYTHON="${RAMBLE_PYTHON:-/usr/bin/python3}"
PIDFILE="$STATE/recorder.pid"; WAVPATH="$STATE/wav.path"; LOCK="$STATE/lock"
# Appended, not prepended: Hammerspoon starts tasks with a bare PATH, and tests put stand-ins first.
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin"
export RAMBLE_CLEANUP_SECONDS="$CLEANUP_SECONDS"
export RAMBLE_COACH_SECONDS="$COACH_SECONDS"

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$LOG"; }

# The clipboard. RAMBLE_COPY_CMD replaces pbcopy (the tests use it so they never touch your clipboard).
copy() {
  if [ -n "${RAMBLE_COPY_CMD:-}" ]; then sh -c "$RAMBLE_COPY_CMD"; else pbcopy; fi
}

# Keeps dictate.log under about 1 MB: past that only the newest 2,000 lines stay.
trim_log() {
  [ "$(stat -f %z "$LOG" 2>/dev/null || echo 0)" -gt 1048576 ] || return 0
  tail -n 2000 "$LOG" > "$LOG.tmp" && mv -f "$LOG.tmp" "$LOG"
}

recording() { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }

# The lock is a directory holding the owner's pid. A lock whose owner died is taken over;
# one whose pid is not written yet is in use unless it is over a minute old.
locked() {
  [ -d "$LOCK" ] || return 1
  local owner; owner="$(cat "$LOCK/pid" 2>/dev/null)"
  if [ -n "$owner" ]; then kill -0 "$owner" 2>/dev/null; return; fi
  [ -n "$(find "$LOCK" -maxdepth 0 -mmin -1 2>/dev/null)" ]
}

lock() {
  if ! mkdir "$LOCK" 2>/dev/null; then
    locked && return 1
    rm -rf "$LOCK"
    mkdir "$LOCK" 2>/dev/null || return 1
  fi
  echo $$ > "$LOCK/pid"
  trap 'rm -rf "$LOCK"' EXIT
}

start() {
  if recording; then echo "RECORDING"; exit 0; fi
  local wav how="ffmpeg"
  wav="$REC/rec-$(date +%Y%m%d-%H%M%S)-$$.wav"
  printf '%s' "$wav" > "$WAVPATH"
  # The native recorder by default: ffmpeg's avfoundation input drops audio buffers (see docs/gotchas.md).
  # A recorder that fails to start falls back to ffmpeg. A native recording that came back as pure silence
  # leaves state/native-silent, and ffmpeg is used until that file is removed.
  if [ "$RECORDER" = "native" ] && [ -x "$HERE/recorder/mic-record" ] && [ ! -e "$STATE/native-silent" ]; then
    nohup "$HERE/recorder/mic-record" "$wav" </dev/null >>"$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    sleep 0.4
    if recording; then how="native"; else rm -f "$PIDFILE"; log "mic-record did not start; using ffmpeg"; fi
  fi
  if [ "$how" = "ffmpeg" ]; then
    nohup ffmpeg -nostdin -hide_banner -loglevel error -y -f avfoundation -i ":$DEVICE" -ar 16000 -ac 1 -c:a pcm_s16le "$wav" </dev/null >>"$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    sleep 0.4
  fi
  if ! recording; then
    rm -f "$PIDFILE" "$WAVPATH"
    log "ffmpeg failed to start (device '$DEVICE')"
    echo "ERROR: microphone '$DEVICE' did not open; see dictate.log"
    exit 1
  fi
  printf '%s' "$how" > "$STATE/recorder"
  log "recording started ($how)"
  echo "RECORDING"
}

stop() {
  if ! recording; then echo "IDLE"; exit 0; fi
  local pid wav text words
  pid="$(cat "$PIDFILE")"
  wav="$(cat "$WAVPATH" 2>/dev/null)"; [ -n "$wav" ] || wav="$REC/current.wav"
  rm -f "$PIDFILE" "$WAVPATH"
  kill -INT "$pid" 2>/dev/null
  for _ in $(seq 1 40); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
  kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
  if [ ! -s "$wav" ]; then log "no audio captured ($wav)"; echo "ERROR: no audio captured"; exit 1; fi
  # Pure digital silence from the native recorder means macOS gave it no microphone; use ffmpeg next time.
  if [ "$(cat "$STATE/recorder" 2>/dev/null)" = "native" ] && command -v ffmpeg >/dev/null; then
    local peak
    peak="$(ffmpeg -nostdin -hide_banner -i "$wav" -af volumedetect -f null - 2>&1 | sed -n 's/.*max_volume: \(-*[0-9.]*\) dB.*/\1/p')"
    if [ -n "$peak" ] && [ "${peak%.*}" -le -85 ]; then
      touch "$STATE/native-silent"; mv -f "$wav" "$REC/last.wav"
      log "native recorder captured only silence (max ${peak} dB; microphone permission?); next dictations use ffmpeg"
      echo "ERROR: the recorder heard nothing (microphone permission?). The next dictation uses ffmpeg; please say it again."
      exit 1
    fi
  fi
  log "recording stopped ($(( $(stat -f %z "$wav") / 32000 ))s)"
  # The conversation being dictated into (the app in front now), read while whisper runs; see context.py.
  local ctx="$STATE/context.txt" ctxpid=""
  : > "$ctx"
  if [ "$CONTEXT" = "1" ]; then "$PYTHON" "$HERE/context.py" > "$ctx" 2>>"$LOG" & ctxpid=$!; fi
  # Coaching only goes where an agent will read it, judged by the app in front now, not after whisper has run.
  local coachtarget="$STATE/coach-target" targetpid=""
  rm -f "$coachtarget"
  if [ "$COACH" = "1" ]; then ( "$PYTHON" "$HERE/coach.py" target 2>>"$LOG" && : > "$coachtarget" ) & targetpid=$!; fi
  # whisper-cli prints about eight lines of start-up per run; they reach the log only when a run fails.
  local werr="$STATE/whisper.err" hint=()
  [ "$HINT" = "1" ] && hint=(--prompt "$("$PYTHON" "$HERE/cleanup.py" hint 2>/dev/null)")
  [ "${#hint[@]}" -eq 2 ] && [ -z "${hint[1]}" ] && hint=()
  text="$(whisper-cli -m "$MODEL" -f "$wav" -nt -np -t "$THREADS" ${hint[@]+"${hint[@]}"} 2>"$werr" | tr '\n' ' ' \
    | sed -E 's/\[BLANK_AUDIO\]//g; s/^[[:space:]]+//; s/[[:space:]]+$//; s/[[:space:]]{2,}/ /g')"
  mv -f "$wav" "$REC/last.wav"
  find "$REC" -name 'rec-*.wav' -mmin +1440 -delete 2>/dev/null
  trim_log
  if [ -z "$text" ]; then cat "$werr" >> "$LOG"; log "empty transcript"; echo "ERROR: nothing heard"; exit 1; fi
  printf '%s' "$text" > "$STATE/last-raw.txt"
  words="$(printf '%s' "$text" | wc -w | tr -d ' ')"
  [ -n "$ctxpid" ] && wait "$ctxpid"
  cp "$ctx" "$STATE/last-context.txt" 2>/dev/null
  [ -n "$targetpid" ] && wait "$targetpid"
  rm -f "$STATE/last-coach.txt"
  coach_start "$text" "$ctx"
  if [ "$CLEANUP" = "1" ] && [ "$words" -ge "$CLEANUP_MIN_WORDS" ]; then
    local clean
    if clean="$(cleanup "$text" "$ctx")"; then
      printf '%s' "$clean" > "$STATE/last-clean.txt"
      coach_add "$clean"
      printf '%s' "$COACHED" | copy
      log "cleaned ${#text} -> ${#clean} chars and copied (context $(wc -c < "$ctx" | tr -d ' ') chars)"
      echo "COPIED: $COACHED"
      return
    fi
    coach_add "$text"
    printf '%s' "$COACHED" | copy
    log "cleanup failed; copied raw ${#text} chars"
    echo "RAW: $COACHED"
    return
  fi
  # Too short for the model (or cleanup off): still take out "um", "okay so" and the like, locally.
  [ "$CLEANUP" = "1" ] && text="$(printf '%s' "$text" | "$PYTHON" "$HERE/cleanup.py" strip)"
  coach_add "$text"
  printf '%s' "$COACHED" | copy
  log "copied ${#text} chars"
  echo "COPIED: $COACHED"
}

# Asks coach.py for suggestions alongside the cleanup, so the two calls take no longer than the slower one.
# Runs only when RAMBLE_COACH=1 chose an agent as the target. A plain reply never gets here, so it stays instant.
COACHPID=""; COACHOUT=""; COACH_BEGAN=0
coach_start() {
  COACHPID=""
  [ -e "$STATE/coach-target" ] || return 0
  printf '%s' "$1" | "$PYTHON" "$HERE/coach.py" wanted || return 0
  COACHOUT="$STATE/coach.txt"
  : > "$COACHOUT"
  COACH_BEGAN=$SECONDS
  ( printf '%s' "$1" | "$PYTHON" "$HERE/coach.py" run "$2" > "$COACHOUT" 2>>"$LOG" ) &
  COACHPID=$!
}

# Sets COACHED to the text followed by any suggestions. The text is never changed and never waits past the limit:
# a slow or failed coach call only means no suggestions. It sets a variable instead of printing because a $(...)
# subshell could not `wait` for COACHPID.
coach_add() {
  COACHED="$1"
  [ -n "$COACHPID" ] || return 0
  while kill -0 "$COACHPID" 2>/dev/null && [ $((SECONDS - COACH_BEGAN)) -lt $((COACH_SECONDS + 2)) ]; do sleep 0.1; done
  if kill -0 "$COACHPID" 2>/dev/null; then
    pkill -P "$COACHPID" 2>/dev/null; kill "$COACHPID" 2>/dev/null
    log "coach timed out after ${COACH_SECONDS}s; copied without suggestions"
    COACHPID=""
    return 0
  fi
  wait "$COACHPID" 2>/dev/null
  COACHPID=""
  [ -s "$COACHOUT" ] || { log "coach had no suggestions"; return 0; }
  cp "$COACHOUT" "$STATE/last-coach.txt"
  COACHED="$1"$'\n\n'"$(cat "$COACHOUT")"
  log "coach added $(($(wc -l < "$COACHOUT") )) suggestions"
}

# Rewrites a transcript with cleanup.py. $2 is an optional file with the last messages of the
# conversation being dictated into (context.py), sent ahead of the transcript as reference.
# Prints the result and succeeds, or fails within CLEANUP_SECONDS (plus a few seconds of grace)
# so the caller can fall back to the raw text.
cleanup() {
  local out pid clean
  out="$(mktemp "$STATE/cleanup.XXXXXX")"
  ( printf '%s' "$1" | "$PYTHON" "$HERE/cleanup.py" run "${2:-}" > "$out" 2>>"$LOG" ) &
  pid=$!
  for _ in $(seq 1 $(((CLEANUP_SECONDS + 5) * 10))); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
  if kill -0 "$pid" 2>/dev/null; then
    pkill -P "$pid" 2>/dev/null; kill "$pid" 2>/dev/null
    log "cleanup timed out after ${CLEANUP_SECONDS}s"
    rm -f "$out"; return 1
  fi
  wait "$pid" || { log "cleanup exited with an error"; rm -f "$out"; return 1; }
  clean="$(sed -E 's/[[:space:]]+$//' "$out")"
  rm -f "$out"
  [ -n "$clean" ] || { log "cleanup returned nothing"; return 1; }
  printf '%s' "$clean"
}

raw() {
  if [ ! -s "$STATE/last-raw.txt" ]; then echo "ERROR: no dictation yet"; exit 1; fi
  copy < "$STATE/last-raw.txt"
  log "copied last raw transcript"
  echo "RAW: $(cat "$STATE/last-raw.txt")"
}

busy() { log "pressed while busy; ignored"; echo "BUSY"; exit 0; }

case "${1:-toggle}" in
  start) lock || busy; start ;;
  stop) lock || busy; stop ;;
  status) if locked; then echo "BUSY"; elif recording; then echo "RECORDING"; else echo "IDLE"; fi ;;
  toggle) lock || busy; if recording; then stop; else start; fi ;;
  raw) raw ;;
  *) echo "usage: dictate.sh toggle|start|stop|status|raw"; exit 2 ;;
esac
