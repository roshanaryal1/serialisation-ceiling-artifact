#!/usr/bin/env python3
"""Reduce raw harness runs to per-cell statistics (RESEARCH_PLAN.md Phase 8).

Reads every `results/raw/run_*.json`, applies the protocol in
MEASUREMENT_PLAN.md (+ ADDENDUM 1), and writes `results/processed/cells.csv`
plus `results/processed/queries.csv`.

Protocol applied here, not at collection time:
  - Discard the warmup repeat (repeat_index == 0) from all statistics.
  - Report p50 and p95. Never the mean (the plan forbids it for latency).
  - Difference the cumulative vm_stat swap counters before/after each run to
    get per-run swap activity.
  - Verify threads_configured == threads_actual_reported; flag mismatches.
  - Flag runs not on AC power or below 30% battery for exclusion.
  - Refuse to classify cells pass/fail unless --failure-threshold-n is given
    (that value is a pre-commitment and is still open -- see MEASUREMENT_PLAN.md).

Usage:
  python3 analyse.py
  python3 analyse.py --failure-threshold-n 5
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

RAW_DIR = Path(__file__).parent.parent / "results" / "raw"
OUT_DIR = Path(__file__).parent.parent / "results" / "processed"


def pct(values, p):
    return float(np.percentile(values, p)) if values else None


def swap_delta(run):
    """Bytes swapped out during this run.

    vm_stat counters are cumulative since boot, so only the difference across
    the run is meaningful -- see the note in runner.js's parseVmStat().
    """
    before = (run.get("system_state_before") or {}).get("vm_stat")
    after = (run.get("system_state_after") or {}).get("vm_stat")
    if not before or not after:
        return None
    b, a = before.get("swapouts_bytes"), after.get("swapouts_bytes")
    if b is None or a is None:
        return None
    return max(0, a - b)


def load_runs():
    runs = []
    for path in sorted(RAW_DIR.glob("run_*.json")):
        with path.open() as f:
            run = json.load(f)
        run["_file"] = path.name
        runs.append(run)
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failure-threshold-n", type=float, default=None,
                         help="Desktop failure rule: p50 query latency > N x the "
                              "10k-corpus baseline counts as a failed cell. This is "
                              "a PRE-COMMITMENT and must be chosen before seeing "
                              "data; if omitted, cells are left unclassified.")
    args = parser.parse_args()

    runs = load_runs()
    if not runs:
        print(f"No raw runs found in {RAW_DIR}. Nothing to do.")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- per-query rows (query latency is measured per query, not per run) ----
    query_rows = []
    for run in runs:
        if run.get("is_warmup"):
            continue
        cell = run["cell"]
        for q in run["query_results"]:
            query_rows.append({
                "browser": run.get("browser", "chromium"),
                "mode": cell.get("mode"),
                "corpus_size": cell["corpus_size"],
                "threads": cell["threads"],
                "cache_state": cell["cache_state"],
                "repeat_index": run["repeat_index"],
                "query": q["query"],
                "embed_ms": q["embed_ms"],
                "search_ms": q["search_ms"],
            })

    with (OUT_DIR / "queries.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(query_rows[0].keys()))
        w.writeheader()
        w.writerows(query_rows)

    # ---- per-cell aggregation ----
    cells = defaultdict(list)
    for run in runs:
        c = run["cell"]
        # `browser` was added to the raw schema partway through data collection.
        # Runs written before that were all Chromium (it was the only engine
        # wired up), so defaulting is a statement of fact here, not a guess.
        browser = run.get("browser", "chromium")
        key = (browser, c.get("mode"), c["corpus_size"], c["threads"], c["cache_state"])
        cells[key].append(run)

    warnings = []
    rows = []
    for key, cell_runs in sorted(cells.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]), kv[0][2])):
        browser, mode, size, threads, cache = key
        measured = [r for r in cell_runs if not r.get("is_warmup")]
        n_warmup = len(cell_runs) - len(measured)
        if not measured:
            warnings.append(f"{key}: only warmup runs present, no measured repeats")
            continue

        # protocol integrity checks
        for r in measured:
            if r.get("threads_configured") != r.get("threads_actual_reported"):
                warnings.append(
                    f"{r['_file']}: thread count not honoured "
                    f"(configured {r.get('threads_configured')}, "
                    f"reported {r.get('threads_actual_reported')})")
            power = (r.get("system_state_before") or {}).get("power") or {}
            if power.get("on_ac_power") is False:
                warnings.append(f"{r['_file']}: NOT on AC power -- exclude per protocol")
            batt = power.get("battery_percent")
            if batt is not None and batt < 30:
                warnings.append(f"{r['_file']}: battery {batt}% (<30) -- exclude per protocol")
            if power.get("low_power_mode"):
                warnings.append(f"{r['_file']}: Low Power Mode ON -- exclude per protocol")

        cold_totals = [r["timings_ms"]["cold_start_total"] for r in measured]
        model_loads = [r["timings_ms"]["model_load"] for r in measured]
        index_builds = [r["timings_ms"]["index_build"] for r in measured]
        embeds = [q["embed_ms"] for r in measured for q in r["query_results"]]
        searches = [q["search_ms"] for r in measured for q in r["query_results"]]
        heaps = [r["peak_js_heap_bytes"] for r in measured if r.get("peak_js_heap_bytes")]
        swaps = [s for s in (swap_delta(r) for r in measured) if s is not None]
        fetches = [r["timings_ms"].get("vectors_fetch") for r in measured
                    if r["timings_ms"].get("vectors_fetch") is not None]
        parses = [r["timings_ms"].get("vectors_parse") for r in measured
                   if r["timings_ms"].get("vectors_parse") is not None]

        # Coefficient of variation -- RESEARCH_PLAN.md Phase 6 abandons the study
        # if CV exceeds ~20% on p50 latency after warmup, so it must be visible.
        #
        # Reported for BOTH cold start and per-query embedding, because they
        # behave differently and only one of them is the "query latency" the
        # abandon rule is really about. Cold start on a warm cache is a
        # sub-second measurement where tens of ms of GC/scheduler jitter is
        # enough to push CV past 0.20 without any instrumentation problem;
        # query-embedding CV is the more meaningful stability signal. Judge the
        # abandon criterion on query CV, and treat a high cold-start CV on a
        # fast warm cell as expected rather than disqualifying.
        # CRITICAL: query CV must be computed PER QUERY across repeats, then
        # aggregated. Pooling all queries together conflates repeat-to-repeat
        # instrumentation noise (what the abandon rule is about) with genuine
        # between-query differences -- the 10 sample queries have different
        # token lengths and legitimately embed at different speeds. Pooling
        # gave CV ~1.5 and would have spuriously tripped the abandon criterion.
        def per_query_cv(field):
            by_q = defaultdict(list)
            for r in measured:
                for q in r["query_results"]:
                    by_q[q["query"]].append(q[field])
            cvs = [float(np.std(v) / np.mean(v))
                   for v in by_q.values() if len(v) > 1 and np.mean(v) > 0]
            return float(np.median(cvs)) if cvs else None

        cv = float(np.std(cold_totals) / np.mean(cold_totals)) if len(cold_totals) > 1 else None
        cv_embed = per_query_cv("embed_ms")
        cv_search = per_query_cv("search_ms")

        # Timer-resolution guard. Firefox and WebKit clamp performance.now() to
        # 1ms as a timing-attack mitigation; Chromium resolves ~0.1ms. A cell
        # whose timings are quantised to whole milliseconds, or contain literal
        # 0.0 readings, is at or below the clock's floor and its value is not a
        # measurement -- comparing it across engines produces exactly the wrong
        # conclusion (Firefox 1k search reads 1.0ms vs Chromium 1.8ms, which
        # would look like Firefox being faster when it is only coarser).
        def resolution_limited(values):
            if not values:
                return None
            zeros = sum(1 for v in values if v == 0.0)
            whole = sum(1 for v in values if float(v).is_integer())
            return {
                "zero_fraction": zeros / len(values),
                "whole_ms_fraction": whole / len(values),
                "distinct_values": len(set(values)),
                # Below the floor if a meaningful share read exactly zero, or
                # everything landed on whole milliseconds.
                "below_timer_floor": (zeros / len(values) > 0.05) or (whole / len(values) > 0.95),
            }

        search_res = resolution_limited(searches)
        embed_res = resolution_limited(embeds)

        rows.append({
            "browser": browser,
            "mode": mode,
            "corpus_size": size,
            "threads": threads,
            "cache_state": cache,
            "n_measured": len(measured),
            "n_warmup_discarded": n_warmup,
            "cold_start_p50_ms": pct(cold_totals, 50),
            "cold_start_p95_ms": pct(cold_totals, 95),
            "cold_start_min_ms": min(cold_totals),
            "cold_start_max_ms": max(cold_totals),
            "cold_start_cv": cv,
            "query_embed_cv": cv_embed,
            "search_cv": cv_search,
            "search_below_timer_floor": search_res["below_timer_floor"] if search_res else None,
            "search_zero_fraction": search_res["zero_fraction"] if search_res else None,
            "search_distinct_values": search_res["distinct_values"] if search_res else None,
            "embed_below_timer_floor": embed_res["below_timer_floor"] if embed_res else None,
            "model_load_p50_ms": pct(model_loads, 50),
            "index_build_p50_ms": pct(index_builds, 50),
            "vectors_fetch_p50_ms": pct(fetches, 50),
            "vectors_parse_p50_ms": pct(parses, 50),
            "query_embed_p50_ms": pct(embeds, 50),
            "query_embed_p95_ms": pct(embeds, 95),
            "search_p50_ms": pct(searches, 50),
            "search_p95_ms": pct(searches, 95),
            "peak_js_heap_p50_bytes": pct(heaps, 50) if heaps else None,
            "peak_js_heap_max_bytes": max(heaps) if heaps else None,
            "swap_out_bytes_p50": pct(swaps, 50) if swaps else None,
            "swap_out_bytes_max": max(swaps) if swaps else None,
            "transfer_bytes_p50": pct([r["model_transfer_bytes"] for r in measured], 50),
        })

    # ---- failure classification (only if the threshold was pre-committed) ----
    # Baseline is per (browser, mode, threads, cache): comparing a Firefox cell
    # against a Chromium baseline would measure the engine difference, not a
    # scaling cliff.
    #
    # Metric is search_p50_ms, not query_embed_p50_ms. Query embedding times
    # the query text and is corpus-size-invariant by construction (confirmed
    # empirically: ~8.1ms @ 1k vs ~8.3ms @ 10k, chromium/shipped/warm); it
    # cannot answer a corpus-scaling question. Search is the component that
    # scales with corpus size (brute-force cosine over the stored vectors) and
    # is what MEASUREMENT_PLAN.md's "corpus-scaling cliff" concept refers to.
    # MEASUREMENT_PLAN.md line 13 requires embed/search be reported separately
    # and never blended; line 30's "query latency" was underspecified against
    # that rule -- resolved here in favour of search, corrected 2026-08-11
    # before any intermediate (>10k) corpus size was measured.
    baselines = {}
    for r in rows:
        if r["corpus_size"] == 10000:
            baselines[(r["browser"], r["mode"], r["threads"], r["cache_state"])] = \
                r["search_p50_ms"]

    for r in rows:
        swapped = (r["swap_out_bytes_max"] or 0) > 0
        if args.failure_threshold_n is None:
            r["cell_status"] = "unclassified (no --failure-threshold-n given)"
            continue
        base = baselines.get((r["browser"], r["mode"], r["threads"], r["cache_state"]))
        # A cell that crashed before producing a search measurement (e.g. the
        # V8 string-length RangeError near the shipped-vectors ceiling) has no
        # search_p50_ms to compare -- it is a hard execution failure, not a
        # latency-cliff verdict, and must not silently read as "passed".
        if r["search_p50_ms"] is None:
            r["cell_status"] = "unclassified (no search measurement -- execution failure?)"
            continue
        latency_fail = (
            base is not None
            and r["search_p50_ms"] > args.failure_threshold_n * base
        )
        if latency_fail and swapped:
            r["cell_status"] = "FAILED (latency cliff + swapping)"
        elif latency_fail:
            r["cell_status"] = "FAILED (latency cliff)"
        elif swapped:
            r["cell_status"] = "FAILED (swapping)"
        else:
            r["cell_status"] = "passed"

    with (OUT_DIR / "cells.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- console summary ----
    print(f"Read {len(runs)} raw runs -> {len(rows)} cells")
    print(f"Wrote {OUT_DIR / 'cells.csv'} and {OUT_DIR / 'queries.csv'}\n")
    hdr = f"{'browser':<9} {'mode':<8} {'corpus':>7} {'thr':>3} {'cache':<5} {'n':>3} " \
          f"{'cold p50':>9} {'cold p95':>9} {'emb p50':>8} {'srch p50':>9} {'CV':>6}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        cv = f"{r['cold_start_cv']:.3f}" if r["cold_start_cv"] is not None else "  -  "
        flag = " !!" if r["cold_start_cv"] and r["cold_start_cv"] > 0.20 else ""
        print(f"{str(r['browser']):<9} {str(r['mode']):<8} {r['corpus_size']:>7} {r['threads']:>3} "
              f"{r['cache_state']:<5} {r['n_measured']:>3} "
              f"{r['cold_start_p50_ms']:>9.1f} {r['cold_start_p95_ms']:>9.1f} "
              f"{r['query_embed_p50_ms']:>8.2f} {r['search_p50_ms']:>9.2f} {cv:>6}{flag}")

    # Swap is a protocol failure regardless of whether the latency threshold was
    # supplied. MEASUREMENT_PLAN.md: "A swapping cell is a failed cell, never a
    # passed one with an asterisk." Surfacing this only during classification
    # would let a compromised run look clean whenever the threshold is omitted.
    swapping = [r for r in rows if (r["swap_out_bytes_max"] or 0) > 0]
    if swapping:
        print(f"\n!! SWAP DURING MEASUREMENT in {len(swapping)} of {len(rows)} cells. "
              "\n   The protocol treats a swapping cell as FAILED, not as a passed cell "
              "\n   with a caveat. Close other applications and re-run these cells.")
        for r in swapping:
            print(f"     {r['browser']:<13} {r['mode']:<8} corpus={int(r['corpus_size']):<7} "
                  f"{r['cache_state']:<5} swap_out max={(r['swap_out_bytes_max'] or 0)/1e6:.0f}MB")

    floored = [r for r in rows if r.get("search_below_timer_floor")]
    if floored:
        print(f"\n!! TIMER FLOOR: search timings unusable in {len(floored)} cell(s) -- the "
              "\n   value is at or below the browser's performance.now() resolution "
              "\n   (Firefox/WebKit clamp to 1ms; Chromium resolves ~0.1ms). Do NOT compare "
              "\n   these across engines: a coarser clock reads as a faster search.")
        for r in floored:
            print(f"     {r['browser']:<9} {r['mode']:<8} corpus={int(r['corpus_size']):<7} "
                  f"{r['cache_state']:<5} p50={r['search_p50_ms']:.1f}ms "
                  f"zeros={r['search_zero_fraction']:.0%} distinct={r['search_distinct_values']}")

    noisy_query = [r for r in rows if r["query_embed_cv"] and r["query_embed_cv"] > 0.20]
    noisy_cold = [r for r in rows if r["cold_start_cv"] and r["cold_start_cv"] > 0.20]
    if noisy_query:
        print(f"\n!! QUERY-latency CV > 0.20 on {len(noisy_query)} cell(s). This is the "
              "\n   measurement RESEARCH_PLAN.md Phase 6's abandon criterion is about. "
              "\n   Investigate before trusting any downstream comparison.")
    if noisy_cold and not noisy_query:
        print(f"\n   Note: cold-start CV > 0.20 on {len(noisy_cold)} cell(s), but query "
              "\n   latency is stable. On fast warm cells a sub-second cold start makes "
              "\n   CV sensitive to ordinary GC/scheduler jitter; this is expected and is "
              "\n   NOT the Phase 6 abandon condition. Query CV is the one that matters.")

    if args.failure_threshold_n is None:
        print("\nCells left UNCLASSIFIED: --failure-threshold-n was not supplied. "
              "\nThat value is a pre-commitment (MEASUREMENT_PLAN.md) and must be "
              "\nchosen before looking at these numbers, not after.")

    if warnings:
        print(f"\n{len(warnings)} protocol warning(s):")
        for w in warnings[:20]:
            print(f"  - {w}")
        if len(warnings) > 20:
            print(f"  ... and {len(warnings) - 20} more")


if __name__ == "__main__":
    main()
