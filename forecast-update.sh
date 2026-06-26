#!/usr/bin/env bash
# Daily auto-update for the World Cup "Forecast" piece.
#
# Re-grades the frozen pre-tournament forecast against the latest openfootball results
# and writes forecast.json straight into the live Portfolio site, then commits + pushes
# so williamcatt.dev/explorations refreshes. The model itself is frozen (ASOF) — only
# the scorecard / results move. Driven by launchd (dev.williamcatt.wcforecast).
#
# Manual run:  ./forecast-update.sh    (safe; no-ops when nothing changed)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/.venv/bin/python"
PORTFOLIO="$HOME/Documents/Projects/Portfolio"
TARGET="$PORTFOLIO/explorations/data/forecast.json"
REL="explorations/data/forecast.json"
LOG="$ROOT/data/logs/forecast-update.log"

mkdir -p "$(dirname "$LOG")"
ts() { date "+%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(ts)] $*" | tee -a "$LOG"; }

log "── run start ──"
[ -x "$PY" ] || { log "no venv python at $PY — aborting"; exit 1; }

# Regenerate forecast.json directly into the live site.
export PYTHONPATH="$ROOT"
played=$("$PY" -c "from pathlib import Path; from mlfootball import forecast; \
  print(forecast.export(Path('$TARGET'))['scorecard']['n_played'])" 2>>"$LOG") \
  || { log "export failed — aborting"; exit 1; }
log "regenerated forecast.json ($played group games graded)"

cd "$PORTFOLIO" || { log "no Portfolio repo at $PORTFOLIO — aborting"; exit 1; }
if git diff --quiet -- "$REL"; then
  log "no change in forecast.json — nothing to publish"
  log "── run done ──"
  exit 0
fi

git add "$REL"
git commit -q -m "explorations: auto-update World Cup forecast scorecard ($(date +%Y-%m-%d), $played graded)" 2>>"$LOG"
if git push -q 2>>"$LOG"; then
  log "published update — live"
else
  log "commit OK but PUSH FAILED (launchd may lack SSH-key access; see notes)"
  exit 1
fi
log "── run done ──"
