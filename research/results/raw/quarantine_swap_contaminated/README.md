# Quarantined: warm-cell raw runs, swap telemetry unattributable

Moved here 2026-08-11, not deleted, per PROVENANCE.md (never fabricate,
never silently discard a primary source).

## Why

`swap_out_bytes_*` (from `vm_stat`'s `Swapouts` counter, `runner.js`'s
`parseVmStat()`) is a system-wide, all-process, cumulative-since-boot counter.
It is not scoped to the harness's own process tree.

A live diagnostic control (2026-08-11, same machine, same session) proved the
counter reads a clean near-zero delta for a genuinely idle window (3x20s,
delta=0 every time) and for a real warm/1k/chromium workload run cleanly
(10 of 12 reps delta=0, remainder 3.8MB/65.6MB -- nothing like the historical
readings).

The historical warm-cell files quarantined here were captured during a long
unattended run (`for b in chromium firefox webkit; do runner.js ...; done`,
~2hr wall clock) with substantial other concurrent activity on the machine.
Their swap_out_bytes readings (up to ~605MB for webkit/1000/warm) are not
attributable to the cells being measured and must not be used for the
pre-registered swapping-failure classification.

Cold cells are NOT affected and were not moved: cold cells spin up a fresh
browser context per repeat (20x full ONNX/WASM pipeline cold-boot per cell),
a real, plausible mechanism for genuine swap pressure on 8GB RAM, and were not
implicated by the control.

## What's in here

- All `run_{chromium,firefox,webkit}_shipped_{1000,10000}_t{4,8}_warm_*.json`
  from the original unattended batch.
- 12 files from the diagnostic control itself (`chromium/1000/warm`,
  threads=4 and 8, repeats=6, idle=5s) -- clean, but not protocol-compliant
  (N=20, idle=60s per MEASUREMENT_PLAN.md) and superseded by the real re-run.

## What happens next

Warm cells are being re-measured under the same protocol (N=20, 60s idle)
in a fresh batch, tracked separately. Once that batch lands and passes the
same swap sanity check, cells.csv is regenerated from the clean set only.
This directory is excluded from `analyse.py`'s raw-file glob by construction
(it globs `results/raw/run_*.json`, not subdirectories).
