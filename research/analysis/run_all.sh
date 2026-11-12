#!/usr/bin/env bash
# Regenerate every table and figure from raw data, in one command.
# RESEARCH_PLAN.md Phase 8 gate: "One script regenerates every table and figure
# from results/raw/. No manual steps, no spreadsheet."
#
# Usage:
#   bash research/analysis/run_all.sh
#   FAILURE_THRESHOLD_N=5 bash research/analysis/run_all.sh
#
# FAILURE_THRESHOLD_N is the desktop failure rule (p50 query latency > N x the
# 10k baseline). It is a PRE-COMMITMENT that must be chosen before looking at
# results -- see MEASUREMENT_PLAN.md. Left unset, cells stay unclassified
# rather than being classified against a threshold picked to suit the data.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESEARCH="$(dirname "$HERE")"
PY="$RESEARCH/.venv/bin/python3"

if [ ! -x "$PY" ]; then
  echo "No venv at $PY"
  echo "Create it with:  python3 -m venv research/.venv && research/.venv/bin/pip install -r research/requirements.txt"
  exit 1
fi

echo "=== 1/3  Reducing raw runs to per-cell statistics ==="
if [ -n "${FAILURE_THRESHOLD_N:-}" ]; then
  "$PY" "$HERE/analyse.py" --failure-threshold-n "$FAILURE_THRESHOLD_N"
else
  "$PY" "$HERE/analyse.py"
fi

echo
echo "=== 2/3  Retrieval quality metrics ==="
# fp32 reference baseline. Additional runs (int8 in-browser) are added here as
# they are produced; each writes its own JSON under results/processed/.
BASELINE="$RESEARCH/baseline/dense_top50_corpus_10000.json"
if [ -f "$BASELINE" ]; then
  "$PY" "$HERE/compute_ir_metrics.py" \
    --run "$BASELINE" \
    --out "$RESEARCH/results/processed/quality_fp32_10k.json"
else
  echo "SKIP: $BASELINE not found (run baseline/fp32_baseline.py)"
fi

echo
echo "=== 3/3  Figures ==="
"$PY" "$HERE/make_figures.py"

echo
echo "Done. Tables: research/results/processed/  Figures: research/results/figures/"
