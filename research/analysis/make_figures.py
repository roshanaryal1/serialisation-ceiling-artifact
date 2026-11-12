#!/usr/bin/env python3
"""Regenerate every figure from processed results (RESEARCH_PLAN.md Phase 8).

Figures (per the plan's own list):
  1. Latency vs corpus size, per device tier, p50 with p95 band, log x-axis.
  2. Cold start decomposed into stacked components, per device tier.
  3. Quality delta int8 vs fp32, by query category, with confidence intervals.
  4. Peak memory vs corpus size, with the failure boundary marked per device.

Every figure is written at 300 dpi and also as PDF (vector) where the venue
allows it. A figure whose input data does not exist yet is SKIPPED with a
printed reason -- it is never drawn from placeholder or invented numbers.

Usage: python3 make_figures.py
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PROCESSED = Path(__file__).parent.parent / "results" / "processed"
FIGDIR = Path(__file__).parent.parent / "results" / "figures"

plt.rcParams.update({
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def save(fig, name):
    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGDIR / f"{name}.png")
    fig.savefig(FIGDIR / f"{name}.pdf")
    plt.close(fig)
    print(f"  wrote {name}.png / .pdf")


def load_cells():
    path = PROCESSED / "cells.csv"
    if not path.exists():
        return []
    with path.open() as f:
        rows = list(csv.DictReader(f))
    # Coerce numerics, leave everything else as text. Listing the text columns
    # explicitly was fragile -- adding `browser` to analyse.py silently broke
    # this. Try/except is the robust direction: anything that does not parse as
    # a number stays a string.
    for r in rows:
        for k, v in list(r.items()):
            if v in ("", "None", None):
                r[k] = None
                continue
            try:
                r[k] = float(v)
            except ValueError:
                pass  # genuine text column (browser, mode, cache_state, ...)
    return rows


# The paper's scope is one desktop machine (Section 7). cells.csv also holds
# phone runs, which must not enter its figures; with matching labels they
# would also be drawn over the desktop bars.
DESKTOP = {"chromium", "firefox", "webkit"}


def series_label(r):
    return f"{r['browser']} / {r['mode']} / {r['cache_state']}"


def fig1_latency_vs_corpus(cells):
    """Query latency vs corpus size. p50 line, p50-p95 band, log x."""
    groups = defaultdict(list)
    for r in cells:
        if r["browser"] in DESKTOP:
            groups[series_label(r)].append(r)
    groups = {k: sorted(v, key=lambda r: r["corpus_size"]) for k, v in groups.items()}
    groups = {k: v for k, v in groups.items() if len(v) >= 2}
    if not groups:
        print("  SKIP fig1: need >=2 corpus sizes in at least one series")
        return

    # Drawn at the printed LNCS width (4.8 in) so labels need no scaling.
    fig, axes = plt.subplots(1, 2, figsize=(4.8, 2.25))
    for label, rows in sorted(groups.items()):
        x = [r["corpus_size"] for r in rows]
        for ax, p50k, p95k, title in (
            (axes[0], "query_embed_p50_ms", "query_embed_p95_ms", "(a) query embedding"),
            (axes[1], "search_p50_ms", "search_p95_ms", "(b) search"),
        ):
            p50 = [r[p50k] for r in rows]
            p95 = [r[p95k] for r in rows]
            (line,) = ax.plot(x, p50, marker="o", markersize=3.5, label=label)
            ax.fill_between(x, p50, p95, alpha=0.15, color=line.get_color())
            ax.set_title(title, fontsize=7.5)
            ax.set_xscale("log")
            ax.set_xlabel("corpus size (documents)", fontsize=7)
            ax.set_ylabel("latency (ms)", fontsize=7)
            ax.tick_params(labelsize=6.5)
    axes[0].legend(fontsize=5.5, frameon=False, handlelength=1.2)
    save(fig, "fig1_latency_vs_corpus")


def fig2_cold_start_decomposition(cells):
    """Stacked cold-start components per cell."""
    # Only Chromium has cold cells (Section 7), so the decomposition is Chromium's.
    rows = sorted((r for r in cells if r["browser"] == "chromium"),
                  key=lambda r: (str(r["mode"]), r["corpus_size"], r["cache_state"]))
    if not rows:
        print("  SKIP fig2: no cells")
        return

    labels = [f"{r['mode']}\n{int(r['corpus_size']):,}\n{r['cache_state']}" for r in rows]
    # Seconds: the cold-start components run to hundreds of seconds.
    model = [(r["model_load_p50_ms"] or 0) / 1000 for r in rows]
    fetch = [(r["vectors_fetch_p50_ms"] or 0) / 1000 for r in rows]
    parse = [(r["vectors_parse_p50_ms"] or 0) / 1000 for r in rows]
    # In Mode B index_build IS the embedding work; in Mode A it also contains
    # fetch+parse, so subtract them to avoid double counting.
    rest = [
        max(0, (r["index_build_p50_ms"] or 0) - (r["vectors_fetch_p50_ms"] or 0)
             - (r["vectors_parse_p50_ms"] or 0)) / 1000
        for r in rows
    ]

    fig, ax = plt.subplots(figsize=(4.8, 2.25))
    bottom = [0] * len(rows)
    for vals, name in ((model, "model load"), (fetch, "vectors fetch"),
                        (parse, "vectors parse"), (rest, "index construction")):
        if not any(vals):
            continue
        ax.bar(labels, vals, bottom=bottom, label=name)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_ylabel("time to first query (s, p50)", fontsize=7)
    ax.legend(fontsize=6, frameon=False)
    ax.tick_params(axis="x", labelsize=6.5)
    ax.tick_params(axis="y", labelsize=6.5)
    save(fig, "fig2_cold_start_decomposition")


def fig3_quality_delta():
    """int8 vs fp32 nDCG delta by query category, with bootstrap CIs.

    Input is the JSON written by compute_ir_metrics.py --compare --out.
    """
    path = PROCESSED / "quality_comparison.json"
    if not path.exists():
        print(f"  SKIP fig3: {path.name} not found -- run compute_ir_metrics.py "
              f"--compare ... --out {path}")
        return
    data = json.loads(path.read_text())
    by_cat = data.get("ndcg_by_category_delta")
    if not by_cat:
        print("  SKIP fig3: no per-category delta in quality_comparison.json")
        return

    cats = sorted(by_cat)
    means = [by_cat[c]["mean"] for c in cats]
    lo = [by_cat[c]["mean"] - by_cat[c]["ci_low"] for c in cats]
    hi = [by_cat[c]["ci_high"] - by_cat[c]["mean"] for c in cats]

    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    ax.axhline(0, color="black", linewidth=0.8)
    ax.errorbar(cats, means, yerr=[lo, hi], fmt="o", capsize=4, markersize=5)
    ax.set_ylabel("nDCG@10 delta (int8 - fp32)")
    ax.set_title("Retrieval quality cost of int8, by query category")
    ax.text(0.5, -0.28, "Compare each category against itself only; rubric strictness "
                         "differs by category (see METRICS_NOTES.md).",
            transform=ax.transAxes, ha="center", fontsize=6, style="italic")
    save(fig, "fig3_quality_delta_by_category")


def fig4_memory_vs_corpus(cells):
    """Peak JS heap vs corpus size, failure boundary marked."""
    groups = defaultdict(list)
    for r in cells:
        if r["peak_js_heap_p50_bytes"]:
            groups[series_label(r)].append(r)
    groups = {k: sorted(v, key=lambda r: r["corpus_size"]) for k, v in groups.items()}
    groups = {k: v for k, v in groups.items() if len(v) >= 2}
    if not groups:
        print("  SKIP fig4: need >=2 corpus sizes with heap data "
              "(performance.memory is Chromium-only)")
        return

    fig, ax = plt.subplots(figsize=(6, 3.8))
    for label, rows in sorted(groups.items()):
        x = [r["corpus_size"] for r in rows]
        y = [r["peak_js_heap_p50_bytes"] / 1e6 for r in rows]
        (line,) = ax.plot(x, y, marker="o", markersize=4, label=label)
        for r in rows:
            if r.get("cell_status", "").startswith("FAILED"):
                ax.scatter([r["corpus_size"]], [r["peak_js_heap_p50_bytes"] / 1e6],
                            marker="x", s=90, color="red", zorder=5)
    ax.set_xscale("log")
    ax.set_xlabel("corpus size (documents, log scale)")
    ax.set_ylabel("peak JS heap (MB, p50)")
    ax.set_title("Peak memory vs corpus size (red x = failed cell)")
    ax.legend(fontsize=6.5, frameon=False)
    ax.text(0.5, -0.3, "JS heap is Chromium-only (performance.memory); WASM heap was "
                        "not obtainable in this onnxruntime-web version.",
            transform=ax.transAxes, ha="center", fontsize=6, style="italic")
    save(fig, "fig4_memory_vs_corpus")


def main():
    cells = load_cells()
    if not cells:
        print(f"No processed cells found in {PROCESSED}. Run analyse.py first.")
        return
    print(f"Generating figures from {len(cells)} cells...")
    fig1_latency_vs_corpus(cells)
    fig2_cold_start_decomposition(cells)
    fig3_quality_delta()
    fig4_memory_vs_corpus(cells)
    print(f"Figures in {FIGDIR}")


if __name__ == "__main__":
    main()
