#!/usr/bin/env bash
# Robust final attempt at the warm-cell re-measurement. Learns from three
# failed attempts on 2026-08-12: system sleep, a mid-cell browser crash, and
# silent battery-power measurement. Fixes, in order:
#   1. Wrapped in `caffeinate -i -s -d` by the caller (see launch command) --
#      prevents system/display sleep for the whole run.
#   2. Waits for AC power before starting or resuming any cell, rather than
#      measuring on battery and finding out afterward.
#   3. Per-cell, per-(engine,size) invocation with automatic retry up to 4
#      attempts if a cell doesn't reach 20 files (covers crashes like the
#      WebKit "TypeError: Load failed" from earlier tonight).
#   4. Regenerates cells.csv at the end so the morning check is just "read
#      the log," not "re-run the pipeline."
set -uo pipefail
cd "$(dirname "$0")"
RAW_DIR="../results/raw"
LOG="_final_run.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S'): $*" >> "$LOG"; }

wait_for_ac_power() {
  while true; do
    if pmset -g batt | grep -q "AC Power"; then
      return 0
    fi
    log "WAITING: not on AC power -- pausing until charger is connected"
    sleep 60
  done
}

TARGET_EPOCH=1786545000  # 2026-08-13 02:30:00 NZST
now=$(date +%s)
sleep_secs=$(( TARGET_EPOCH - now ))
if [ "$sleep_secs" -gt 0 ]; then
  log "sleeping ${sleep_secs}s until 2026-08-13 02:30 NZST"
  sleep "$sleep_secs"
fi

log "=== starting final warm re-run ==="
wait_for_ac_power

for eng in chromium firefox webkit; do
  for size in 1000 10000; do
    attempt=0
    max_attempts=4
    while [ "$attempt" -lt "$max_attempts" ]; do
      wait_for_ac_power
      count=$(ls "$RAW_DIR"/run_${eng}_shipped_${size}_t4_warm_r*.json 2>/dev/null | wc -l | tr -d ' ')
      if [ "$count" -ge 20 ]; then
        log "$eng/$size/warm: already has $count files, done"
        break
      fi
      attempt=$((attempt + 1))
      log "$eng/$size/warm: attempt $attempt/$max_attempts, currently $count files"
      node runner.js --browser=$eng --mode=shipped --sizes=$size --threads=4 --cache=warm --repeats=20 --idle-seconds=60 >> "$LOG" 2>&1
      count=$(ls "$RAW_DIR"/run_${eng}_shipped_${size}_t4_warm_r*.json 2>/dev/null | wc -l | tr -d ' ')
      log "$eng/$size/warm: after attempt $attempt, $count files"
    done
    if [ "$count" -lt 20 ]; then
      log "$eng/$size/warm: FAILED after $max_attempts attempts, only $count files -- needs manual attention"
    fi
  done
done

log "=== all cells attempted, final tally ==="
for eng in chromium firefox webkit; do
  for size in 1000 10000; do
    count=$(ls "$RAW_DIR"/run_${eng}_shipped_${size}_t4_warm_r*.json 2>/dev/null | wc -l | tr -d ' ')
    log "FINAL: $eng/$size/warm = $count files"
  done
done

log "regenerating cells.csv"
(cd .. && .venv/bin/python3 analysis/analyse.py --failure-threshold-n 2 >> harness/_final_run.log 2>&1)

log "=== final warm re-run complete ==="
