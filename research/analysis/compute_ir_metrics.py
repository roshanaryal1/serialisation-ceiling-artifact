#!/usr/bin/env python3
"""Retrieval quality metrics for RQ1 (RESEARCH_PLAN.md Phases 4 and 8).

Computes nDCG@10, recall@5, recall@10, MRR@10 against `queries/qrels.jsonl`,
plus Spearman rank correlation between two systems' orderings, with bootstrap
confidence intervals over queries.

PROVISIONAL until the qrels are validated: `qrels.jsonl` is currently the
output of the rubric program (`queries/grade_pool.py`), not of validated human
judgement. Until `compute_kappa.py` reports kappa >= 0.7 on the hand-adjudicated
sample, every number this script emits is provisional and is labelled as such in
the output. Do not copy an unvalidated figure into the paper.

Usage:
  # fp32 baseline against the rubric qrels
  python3 compute_ir_metrics.py --run ../baseline/dense_top50_corpus_10000.json

  # compare two systems (adds Spearman rank agreement)
  python3 compute_ir_metrics.py --run A.json --compare B.json
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

KAPPA_REPORT = Path(__file__).parent.parent / "queries" / "kappa_result.json"


def load_qrels(path):
    """{query_id: {doc_id: grade}} plus {query_id: query_category}."""
    rels, cats = {}, {}
    with path.open() as f:
        for line in f:
            row = json.loads(line)
            rels[row["query_id"]] = {j["doc_id"]: j["grade"] for j in row["judgments"]}
            cats[row["query_id"]] = row["query_category"]
    return rels, cats


def load_run(path):
    """{query_id: [doc_id, ...]} ranked best-first.

    Accepts the baseline format ({qid: [[doc_id, score], ...]}) directly.
    """
    with path.open() as f:
        data = json.load(f)
    return {qid: [d for d, _ in ranked] for qid, ranked in data.items()}


def dcg(gains):
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranked, rel, k=10):
    gains = [rel.get(d, 0) for d in ranked[:k]]
    ideal = sorted(rel.values(), reverse=True)[:k]
    idcg = dcg(ideal)
    return dcg(gains) / idcg if idcg > 0 else 0.0


def recall_at_k(ranked, rel, k):
    """Fraction of RELEVANT documents (grade >= 1) retrieved in the top k.

    Note this is recall against the judged pool, not against the whole corpus:
    unjudged documents are treated as non-relevant, the standard pooled-
    evaluation assumption. With a dense+BM25 pool of ~89 candidates per query
    this is reasonable, but it does mean recall is an upper bound relative to
    exhaustive judging -- state that in the paper.
    """
    relevant = {d for d, g in rel.items() if g >= 1}
    if not relevant:
        return None
    hit = sum(1 for d in ranked[:k] if d in relevant)
    return hit / len(relevant)


def mrr_at_k(ranked, rel, k=10):
    for i, d in enumerate(ranked[:k]):
        if rel.get(d, 0) >= 1:
            return 1.0 / (i + 1)
    return 0.0


def bootstrap_ci(values, n_boot=2000, seed=17):
    """Percentile bootstrap over QUERIES (RESEARCH_PLAN.md Phase 8)."""
    vals = np.array([v for v in values if v is not None], dtype=float)
    if len(vals) == 0:
        return None, None, None
    rng = np.random.default_rng(seed)
    means = [rng.choice(vals, size=len(vals), replace=True).mean() for _ in range(n_boot)]
    return float(vals.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def evaluate(run, rels, cats):
    per_query = {"ndcg@10": {}, "recall@5": {}, "recall@10": {}, "mrr@10": {}}
    for qid, ranked in run.items():
        rel = rels.get(qid)
        if rel is None:
            continue
        per_query["ndcg@10"][qid] = ndcg_at_k(ranked, rel, 10)
        per_query["recall@5"][qid] = recall_at_k(ranked, rel, 5)
        per_query["recall@10"][qid] = recall_at_k(ranked, rel, 10)
        per_query["mrr@10"][qid] = mrr_at_k(ranked, rel, 10)
    return per_query


def qrels_are_validated():
    """True only if a kappa result exists AND cleared the 0.7 bar."""
    if not KAPPA_REPORT.exists():
        return False, "no kappa result found (hand adjudication not completed)"
    try:
        data = json.loads(KAPPA_REPORT.read_text())
        k = data.get("kappa")
        if k is None:
            return False, "kappa result file present but has no kappa value"
        if k >= 0.7:
            return True, f"kappa={k:.3f} (n={data.get('n')})"
        return False, f"kappa={k:.3f} is below the 0.7 bar"
    except Exception as e:
        return False, f"could not read kappa result: {e}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--compare", type=Path, default=None,
                         help="Second run; adds Spearman rank agreement against --run.")
    parser.add_argument("--qrels", type=Path,
                         default=Path(__file__).parent.parent / "queries" / "qrels.jsonl")
    parser.add_argument("--out", type=Path, default=None, help="Write JSON results here.")
    args = parser.parse_args()

    validated, why = qrels_are_validated()
    banner = ("VALIDATED" if validated else "PROVISIONAL -- qrels NOT validated")
    print(f"=== {banner} ===")
    print(f"    {why}")
    if not validated:
        print("    Numbers below must not be copied into the paper as final.")
    print()

    rels, cats = load_qrels(args.qrels)
    run = load_run(args.run)
    per_query = evaluate(run, rels, cats)

    print(f"Run: {args.run.name}   queries evaluated: {len(per_query['ndcg@10'])}")
    print(f"{'metric':<12} {'mean':>7}  {'95% CI (bootstrap over queries)':>32}")
    results = {"run": str(args.run), "qrels_validated": validated, "metrics": {}}
    for metric, vals in per_query.items():
        mean, lo, hi = bootstrap_ci(list(vals.values()))
        if mean is None:
            continue
        print(f"{metric:<12} {mean:>7.4f}  [{lo:.4f}, {hi:.4f}]")
        results["metrics"][metric] = {"mean": mean, "ci_low": lo, "ci_high": hi}

    # Structural ceiling on recall@k. The relevant set (grade >= 1) averages
    # 46-71 documents per query in this pool, so recall@5 cannot exceed
    # ~5/46 ~= 0.11 no matter how good the system is. Reporting the raw number
    # without this ceiling invites the reader (and the author) to conclude
    # retrieval is failing when it is arithmetic. See METRICS_NOTES.md.
    ceilings = {}
    for k in (5, 10):
        vals = []
        for qid in per_query[f"recall@{k}"]:
            n_rel = sum(1 for g in rels[qid].values() if g >= 1)
            if n_rel:
                vals.append(min(1.0, k / n_rel))
        if vals:
            ceilings[f"recall@{k}"] = float(np.mean(vals))
    results["recall_ceilings"] = ceilings
    print("\nRecall ceilings (mean of min(1, k/|relevant|)) -- recall@k cannot exceed these:")
    for k, v in ceilings.items():
        achieved = results["metrics"][k]["mean"]
        print(f"  {k:<10} ceiling={v:.4f}   achieved={achieved:.4f}   "
              f"({achieved / v * 100:.1f}% of attainable)")

    # Per query category -- RESEARCH_PLAN.md: "That breakdown is often where the
    # interesting quantisation effect hides."
    print(f"\nnDCG@10 by query category:")
    by_cat = {}
    for qid, v in per_query["ndcg@10"].items():
        by_cat.setdefault(cats.get(qid, "?"), []).append(v)
    results["ndcg_by_category"] = {}
    for cat in sorted(by_cat):
        mean, lo, hi = bootstrap_ci(by_cat[cat])
        n2 = np.mean([sum(1 for g in rels[q].values() if g == 2)
                       for q in per_query["ndcg@10"] if cats.get(q) == cat])
        print(f"  {cat:<11} n={len(by_cat[cat]):<4} {mean:.4f}  [{lo:.4f}, {hi:.4f}]"
              f"   (avg {n2:.0f} grade-2 docs/query)")
        results["ndcg_by_category"][cat] = {"n": len(by_cat[cat]), "mean": mean,
                                             "ci_low": lo, "ci_high": hi,
                                             "avg_grade2_per_query": float(n2)}
    print("  WARNING: do NOT compare nDCG ACROSS these categories. The rubric's"
          "\n  strictness differs by category by design (paraphrase/vague treat a"
          "\n  whole listing category as grade 2; exact demands matching type AND"
          "\n  spec), so cross-category differences measure rubric leniency, not"
          "\n  retrieval difficulty. Compare a category against ITSELF across"
          "\n  systems (int8 vs fp32) -- that is what this breakdown is for.")

    if args.compare:
        run_b = load_run(args.compare)
        per_query_b = evaluate(run_b, rels, cats)
        print(f"\n=== Comparison: {args.run.name} vs {args.compare.name} ===")

        deltas = {}
        for metric in per_query:
            a = per_query[metric]
            b = per_query_b[metric]
            shared = [q for q in a if q in b and a[q] is not None and b[q] is not None]
            d = [b[q] - a[q] for q in shared]
            mean, lo, hi = bootstrap_ci(d)
            print(f"  delta {metric:<10} {mean:+.4f}  [{lo:+.4f}, {hi:+.4f}]")
            deltas[metric] = {"mean": mean, "ci_low": lo, "ci_high": hi}
        results["deltas"] = deltas

        # Per-category nDCG delta. RESEARCH_PLAN.md expects the quantisation
        # effect, if any, to hide in a specific query category rather than in
        # the pooled figure -- and this is the within-category comparison that
        # METRICS_NOTES.md says is the only valid use of the breakdown.
        cat_delta = {}
        for cat in sorted(set(cats.values())):
            qs = [q for q in per_query["ndcg@10"]
                  if cats.get(q) == cat and q in per_query_b["ndcg@10"]]
            if not qs:
                continue
            d = [per_query_b["ndcg@10"][q] - per_query["ndcg@10"][q] for q in qs]
            mean, lo, hi = bootstrap_ci(d)
            cat_delta[cat] = {"n": len(qs), "mean": mean, "ci_low": lo, "ci_high": hi}
        results["ndcg_by_category_delta"] = cat_delta
        print("\n  nDCG@10 delta by query category (within-category only):")
        for cat, v in cat_delta.items():
            print(f"    {cat:<11} n={v['n']:<4} {v['mean']:+.4f}  "
                  f"[{v['ci_low']:+.4f}, {v['ci_high']:+.4f}]")

        # Spearman over the top-10 orderings -- RESEARCH_PLAN.md Phase 8:
        # "Rank agreement is often the more meaningful measure for a UI that
        # shows ten results."
        rhos = []
        for qid in run:
            if qid not in run_b:
                continue
            a10, b10 = run[qid][:10], run_b[qid][:10]
            union = list(dict.fromkeys(a10 + b10))
            # Documents absent from a list are ranked past its end.
            ra = [a10.index(d) if d in a10 else len(a10) for d in union]
            rb = [b10.index(d) if d in b10 else len(b10) for d in union]
            if len(set(ra)) > 1 and len(set(rb)) > 1:
                rho, _ = spearmanr(ra, rb)
                if not math.isnan(rho):
                    rhos.append(rho)
        if rhos:
            mean, lo, hi = bootstrap_ci(rhos)
            print(f"  Spearman rank agreement (top-10): {mean:.4f}  [{lo:.4f}, {hi:.4f}]  "
                  f"(n={len(rhos)} queries)")
            results["spearman_top10"] = {"mean": mean, "ci_low": lo, "ci_high": hi,
                                          "n": len(rhos)}

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=2))
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
