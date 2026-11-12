"""Study design figure for the SSD 2026 camera-ready (reviewer request).

Draws the measured pipeline, the variables manipulated at each stage, and
where each research question is answered. Written at the LNCS text width
(4.8 in) so it is embedded without scaling and the 6.5 pt labels stay legible.
No data is read: every label restates the design in Section 4.

Usage: research/.venv/bin/python3 analysis/make_design_figure.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

FIGDIR = Path(__file__).parent.parent / "results" / "figures"
FS = 6.5
W, H = 0.20, 0.16
BOX = dict(boxstyle="round,pad=0.01,rounding_size=0.015", linewidth=0.7)


def box(ax, x, y, text, fill="#ffffff"):
    ax.add_patch(FancyBboxPatch((x - W / 2, y - H / 2), W, H, facecolor=fill, edgecolor="#333333", **BOX))
    ax.text(x, y, text, ha="center", va="center", fontsize=FS, linespacing=1.15)


def arrow(ax, a, b):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=6, linewidth=0.7, color="#333333",
                                 shrinkA=0, shrinkB=0))


def rq(ax, x, y, text, ha="center"):
    ax.text(x, y, text, ha=ha, va="center", fontsize=FS - 0.5, color="#8a1c1c", style="italic")


def main():
    fig, ax = plt.subplots(figsize=(4.8, 2.3))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    xs = [0.11, 0.35, 0.60, 0.86]
    top, mid, low = 0.80, 0.48, 0.13
    grey = "#eeeeee"

    ax.text(0.005, 0.975, "Build time (Node.js)", fontsize=FS, weight="bold", va="center")
    box(ax, xs[0], top, "Synthetic corpus\n1k, 10k, 100k docs\n(5k held out)", grey)
    box(ax, xs[1], top, "Embed\nMiniLM-L6, 384-d\nfloat32 output", grey)
    box(ax, xs[2], top, "Serialise\nJSON | JSON shards\nbinary f32 | int8", grey)
    box(ax, xs[3], top, "Encode\nnone | gzip\nbrotli", grey)
    for a, b in zip(xs, xs[1:]):
        arrow(ax, (a + W / 2, top), (b - W / 2, top))

    ax.text(0.005, 0.645, "In the browser: Mode A, ship vectors", fontsize=FS, weight="bold", va="center")
    box(ax, xs[3], mid, "Serve vectors or text\nloopback, or\n1.6 Mbps, 150 ms")
    box(ax, xs[2], mid, "Fetch\n(wire bytes,\ntime)")
    box(ax, xs[1], mid, "Parse\nJSON.parse or\ntyped-array view")
    box(ax, xs[0], mid, "Search\nbrute-force\ncosine")
    arrow(ax, (xs[3], top - H / 2), (xs[3], mid + H / 2))
    for a, b in [(xs[3], xs[2]), (xs[2], xs[1]), (xs[1], xs[0])]:
        arrow(ax, (a - W / 2, mid), (b + W / 2, mid))

    ax.text(0.005, 0.30, "Mode B, build in the browser", fontsize=FS, weight="bold", va="center")
    box(ax, xs[2], low, "Fetch corpus\ntext")
    box(ax, xs[1], low, "Embed in\nbrowser\n(39 docs/s)")
    box(ax, xs[0], low, "Search\nbrute-force\ncosine")
    arrow(ax, (xs[3], mid - H / 2), (xs[2] + W / 2, low))
    for a, b in [(xs[2], xs[1]), (xs[1], xs[0])]:
        arrow(ax, (a - W / 2, low), (b + W / 2, low))

    rq(ax, xs[1], mid - H / 2 - 0.045, "RQ1-2: does parse succeed? (bisection; 3 engines)")
    rq(ax, xs[2], 0.645, "RQ3: wire bytes, fetch + parse time")
    rq(ax, xs[3], low, "RQ4: cold start,\nMode A vs Mode B")

    FIGDIR.mkdir(parents=True, exist_ok=True)
    fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)
    fig.savefig(FIGDIR / "fig0_study_design.png", dpi=300)
    fig.savefig(FIGDIR / "fig0_study_design.pdf")
    plt.close(fig)
    print(f"wrote {FIGDIR / 'fig0_study_design.png'}")


if __name__ == "__main__":
    main()
