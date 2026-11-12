#!/usr/bin/env python3
"""Rank agreement between fp32 and int8 retrieval orderings.

WHY THIS IS COMPUTABLE AND THE QUALITY METRICS ARE NOT
------------------------------------------------------
RQ1 (retrieval quality) was withdrawn because the relevance judgments failed
their pre-registered validation (Section 5.1). Every quality metric -- nDCG,
recall, MRR -- requires those judgments, because "quality" means "agreement
with ground truth about what is relevant".

Rank AGREEMENT requires no ground truth at all. It asks a strictly different
question: do two systems order the same corpus the same way? That comparison
is between the two systems, not between a system and a human label. The
original method section dropped Spearman alongside the quality metrics; that
was a logical error, since Spearman over two systems' orderings never touched
the judgments.

WHAT THIS CAN AND CANNOT SUPPORT
--------------------------------
CAN: "int8 reproduces the fp32 reference's ordering to degree X."
CANNOT: "int8 retrieval is good", or "int8 costs nothing in quality".
Two systems can agree perfectly and both be wrong. Agreement with a reference
is fidelity, not quality. Every number here is fidelity.

DECOMPOSITION
-------------
Two int8 variants are compared against the same fp32 reference:
  - batch 32: what the application actually ships
  - batch 1:  free of the transformers.js batch-padding artifact (Section 4.4)
The batch-1 comparison isolates quantisation. The gap between the two isolates
the padding artifact's contribution to ranking, which Section 4.4 states would
otherwise be indistinguishable from a quantisation effect.

METRICS, and why more than one
------------------------------
Top-k lists from two systems need not contain the same documents, so a plain
Spearman over "the top 10" is ill-defined. Three complementary measures:

  overlap@k     set agreement: |top-k(A) intersect top-k(B)| / k. Interpretable,
                ignores order entirely.
  spearman@k    computed over A's top-k documents, correlating each system's
                rank of those same documents. Requires B to rank them, so it is
                computed over the documents B also retrieved within its top-50,
                and the count is reported (an unreported denominator here would
                hide how often B lost a document entirely).
  RBO           rank-biased overlap, the standard measure for top-weighted
                comparison of indefinite rankings with differing item sets.
                p=0.9 weights roughly the first ten ranks.

Usage:
  python3 rank_agreement.py
"""

import json
from pathlib import Path

import numpy as np

RESEARCH = Path(__file__).parent.parent
BASELINE = RESEARCH / "baseline"
PROCESSED = RESEARCH / "results" / "processed"


def load_ranking(path):
    """{query_id: [doc_id, ...]} ordered best-first."""
    raw = json.loads(Path(path).read_text())
    return {q: [doc for doc, _score in hits] for q, hits in raw.items()}


def overlap_at_k(a, b, k):
    return len(set(a[:k]) & set(b[:k])) / k


def spearman_at_k(a, b, k):
    """Spearman over A's top-k, using both systems' ranks of those documents.

    Returns (rho, n_common). Documents A ranked but B did not retrieve at all
    cannot be assigned a B-rank without inventing one, so they are excluded and
    n_common reports how many survived.
    """
    b_rank = {doc: i for i, doc in enumerate(b)}
    pairs = [(i, b_rank[doc]) for i, doc in enumerate(a[:k]) if doc in b_rank]
    if len(pairs) < 3:
        return None, len(pairs)
    x = np.array([p[0] for p in pairs], dtype=float)
    y = np.array([p[1] for p in pairs], dtype=float)
    # Spearman = Pearson on ranks; these are already ranks, no ties possible
    # within a single system's ordering.
    if np.std(x) == 0 or np.std(y) == 0:
        return None, len(pairs)
    rho = float(np.corrcoef(x, y)[0, 1])
    return rho, len(pairs)


def rbo(a, b, p=0.9):
    """Rank-biased overlap. Webber et al. (2010), the standard top-weighted
    measure for rankings that need not contain the same items."""
    depth = min(len(a), len(b))
    if depth == 0:
        return None
    total = 0.0
    seen_a, seen_b = set(), set()
    for d in range(1, depth + 1):
        seen_a.add(a[d - 1])
        seen_b.add(b[d - 1])
        total += (len(seen_a & seen_b) / d) * (p ** (d - 1))
    return (1 - p) * total


def bootstrap_ci(values, n_boot=5000, seed=0):
    rng = np.random.default_rng(seed)
    arr = np.array([v for v in values if v is not None], dtype=float)
    if len(arr) == 0:
        return None, None, None
    means = [rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n_boot)]
    return float(arr.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def compare(fp32, int8, label):
    qs = sorted(set(fp32) & set(int8))
    ov10 = [overlap_at_k(fp32[q], int8[q], 10) for q in qs]
    ov1 = [1.0 if fp32[q][:1] == int8[q][:1] else 0.0 for q in qs]
    sp, ncom = zip(*[spearman_at_k(fp32[q], int8[q], 10) for q in qs])
    rb = [rbo(fp32[q], int8[q], p=0.9) for q in qs]

    print(f"\n=== {label} ===")
    print(f"queries compared: {len(qs)}")
    for name, vals in (("overlap@10", ov10), ("top-1 agreement", ov1),
                       ("spearman@10", sp), ("RBO(p=0.9)", rb)):
        m, lo, hi = bootstrap_ci(vals)
        n_valid = len([v for v in vals if v is not None])
        note = "" if n_valid == len(qs) else f"  [{n_valid}/{len(qs)} queries computable]"
        print(f"  {name:<18} {m:.4f}  95% CI [{lo:.4f}, {hi:.4f}]{note}")
    lost = [10 - n for n in ncom]
    print(f"  documents from fp32 top-10 absent from int8 top-50: "
          f"mean {np.mean(lost):.2f} of 10, max {max(lost)}")
    return {
        "label": label,
        "n_queries": len(qs),
        "overlap_at_10": bootstrap_ci(ov10),
        "top1_agreement": bootstrap_ci(ov1),
        "spearman_at_10": bootstrap_ci(sp),
        "rbo_p090": bootstrap_ci(rb),
        "mean_fp32_top10_docs_missing_from_int8_top50": float(np.mean(lost)),
    }


def main():
    fp32_path = BASELINE / "dense_top50_corpus_10000.json"
    if not fp32_path.exists():
        raise SystemExit(f"missing {fp32_path}")
    fp32 = load_ranking(fp32_path)

    print("Rank agreement against the fp32 reference, corpus 10,000.")
    print("FIDELITY TO A REFERENCE, NOT QUALITY. No relevance judgments are")
    print("involved; these numbers say nothing about whether either system")
    print("retrieves well, only about whether they agree with each other.")

    results = []
    for fname, label in (
        ("int8_chromium_10000_top50.json", "fp32 vs int8 batch-32 (as shipped: quantisation + padding)"),
        ("int8_chromium_10000_bs1_top50.json", "fp32 vs int8 batch-1 (quantisation alone)"),
    ):
        path = PROCESSED / fname
        if not path.exists():
            print(f"\nSKIP {label}: {path.name} not found")
            continue
        results.append(compare(fp32, load_ranking(path), label))

    out = PROCESSED / "rank_agreement.json"
    out.write_text(json.dumps({
        "note": ("Fidelity to the fp32 reference, not retrieval quality. "
                 "Computed without relevance judgments, which is why these "
                 "survive the RQ1 withdrawal (Section 5.1)."),
        "results": results,
    }, indent=2, default=list))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
