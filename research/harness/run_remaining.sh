#!/usr/bin/env bash
# Everything still to measure, in one unattended sequence.
#
# Runs strictly SERIALLY and never alongside another measurement: concurrent
# CPU work perturbs the very timings being measured, and MEASUREMENT_PLAN.md's
# thermal protocol assumes an otherwise-idle machine. Do not run this while
# runner.js is already going.
#
# Ordered cheapest-and-most-diagnostic first, so a broken step surfaces in
# seconds rather than after hours of long runs:
#   1. quality runs (~1 min each)   - RQ1, and validates the newest code path
#   2. Mode A ceiling probe          - expected to FAIL at 100k; failure is the result
#   3. Mode B reduced (N=3)          - RQ2 second deployment mode
#   4. Firefox / WebKit              - cross-engine
#
# Each step is allowed to fail without killing the run: a failed cell is a
# first-class result (RESEARCH_PLAN.md Phase 7), not a reason to stop.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
LOG="/tmp/run_remaining.log"
: > "$LOG"

step() {
  echo "" | tee -a "$LOG"
  echo "=== $* ===" | tee -a "$LOG"
  echo "    started $(date '+%H:%M:%S')" | tee -a "$LOG"
}

run() {
  if "$@" >> "$LOG" 2>&1; then
    echo "    OK  $(date '+%H:%M:%S')" | tee -a "$LOG"
  else
    echo "    FAILED (exit $?) -- recorded, continuing" | tee -a "$LOG"
  fi
}

step "1/6  RQ1 quality: int8 batch-32 vectors (app-faithful), 10k"
run node quality_run.js --size=10000

step "2/6  RQ1 quality: int8 batch-1 vectors (padding-artifact-free), 10k"
run node quality_run.js --size=10000 --vectors-suffix=_bs1

step "3/6  Mode A at 100k -- EXPECTED TO FAIL (V8 max string length)"
echo "    A RangeError here is the finding, not a bug: see" | tee -a "$LOG"
echo "    research/results/FINDING_json_string_ceiling.md" | tee -a "$LOG"
run node runner.js --mode=shipped --sizes=100000 --threads=4 --cache=cold \
    --repeats=2 --idle-seconds=10 --no-throttle

step "3b/6  Bisect the exact Mode A ceiling between 10k and 100k"
echo "    Generates intermediate corpora/vectors as needed; slowest step." | tee -a "$LOG"
run node find_ceiling.js --lo=10000 --hi=100000 --tolerance=10000

step "4/6  Mode B (in-browser index build), reduced N=3 per ADDENDUM 1"
run node runner.js --mode=build --sizes=1000,10000 --threads=4 --cache=cold \
    --repeats=3 --idle-seconds=60

step "5/6  Firefox, Mode A, warm only (no CDP: cold isolation is weaker there)"
run node runner.js --browser=firefox --mode=shipped --sizes=1000,10000 \
    --threads=4 --cache=warm --repeats=20 --idle-seconds=60

step "6/6  WebKit, Mode A, warm only (upstream WebKit engine, NOT Safari)"
run node runner.js --browser=webkit --mode=shipped --sizes=1000,10000 \
    --threads=4 --cache=warm --repeats=20 --idle-seconds=60

echo "" | tee -a "$LOG"
echo "=== all steps attempted, finished $(date '+%H:%M:%S') ===" | tee -a "$LOG"
echo "Next: bash research/analysis/run_all.sh" | tee -a "$LOG"
