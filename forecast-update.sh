#!/usr/bin/env bash
# Daily auto-update for the World Cup "Forecast" + "Bracket" pieces.
#
# Re-grades the frozen pre-tournament forecast against the latest openfootball results,
# and re-reads + re-simulates the knockout bracket from the same frozen model, writing
# forecast.json and bracket.json straight into the live Portfolio site, then commits +
# pushes so williamcatt.dev/explorations refreshes. The model itself is frozen (ASOF) —
# only the results, the scorecard, and which knockout slots are filled move. Driven by
# launchd (dev.williamcatt.wcforecast).
#
# Manual run:  ./forecast-update.sh    (safe; no-ops when nothing changed)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/.venv/bin/python"
PORTFOLIO="$HOME/Documents/Projects/Portfolio"
TARGET="$PORTFOLIO/explorations/data/forecast.json"
REL="explorations/data/forecast.json"
TARGET_BR="$PORTFOLIO/explorations/data/bracket.json"
REL_BR="explorations/data/bracket.json"
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

# Regenerate bracket.json (knockout odds + title-race simulation) into the live site.
# The group stage may still be running, in which case there are no knockout ties yet —
# treat that as a soft skip, not a failure.
ko=$("$PY" -c "from pathlib import Path; from mlfootball import bracket; \
  print(bracket.export(Path('$TARGET_BR'))['meta']['n_played'])" 2>>"$LOG") \
  && log "regenerated bracket.json ($ko knockout ties played)" \
  || log "bracket export skipped/failed (see log) — continuing with forecast only"

cd "$PORTFOLIO" || { log "no Portfolio repo at $PORTFOLIO — aborting"; exit 1; }
if git diff --quiet -- "$REL" "$REL_BR"; then
  log "no change in forecast.json / bracket.json — nothing to publish"
  log "── run done ──"
  exit 0
fi

git add "$REL" "$REL_BR"
git commit -q -m "explorations: auto-update World Cup forecast + bracket ($(date +%Y-%m-%d), $played graded, $ko KO ties)" 2>>"$LOG"
if git push -q 2>>"$LOG"; then
  log "published update — live"
else
  log "commit OK but PUSH FAILED (launchd may lack SSH-key access; see notes)"
  exit 1
fi
log "── run done ──"
