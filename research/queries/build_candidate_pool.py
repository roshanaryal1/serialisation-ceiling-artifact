#!/usr/bin/env python3
"""Build the Phase 3 candidate pool: union of top-50 fp32 dense retrieval
(research/baseline/fp32_baseline.py output) and top-50 BM25, per query.

RESEARCH_PLAN.md Phase 3: "Build a candidate pool per query by union of the
top 50 from fp32 dense retrieval and top 50 from BM25. Judging only dense
results biases the pool toward the systems under test."

Output (`qrels_pool.jsonl`) has candidate IDs and provenance (which
system(s) surfaced each one) but NO relevance grades -- grading is a
separate, human/LLM-assisted step per `labelling_protocol.md`, not done by
this script.

Usage: python3 build_candidate_pool.py --corpus ../corpus/corpus_10000.jsonl \
         --dense ../baseline/dense_top50_corpus_10000.json
"""

import argparse
import json
from pathlib import Path

from rank_bm25 import BM25Okapi


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


def tokenize(text):
    return text.lower().split()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("../corpus/corpus_10000.jsonl"))
    parser.add_argument("--queries", type=Path, default=Path("queries.jsonl"))
    parser.add_argument("--dense", type=Path, default=Path("../baseline/dense_top50_corpus_10000.json"))
    parser.add_argument("--out", type=Path, default=Path("qrels_pool.jsonl"))
    parser.add_argument("--top-k", type=int, default=50)
    args = parser.parse_args()

    corpus = load_jsonl(args.corpus)
    queries = load_jsonl(args.queries)
    corpus_ids = [r["id"] for r in corpus]
    corpus_texts = [f"{r['name']} {r['description']} {' '.join(r.get('features', []))}" for r in corpus]

    print(f"Building BM25 index over {len(corpus)} documents...")
    tokenized_corpus = [tokenize(t) for t in corpus_texts]
    bm25 = BM25Okapi(tokenized_corpus)

    with args.dense.open() as f:
        dense_results = json.load(f)

    pool_rows = []
    for q in queries:
        qid = q["id"]
        dense_ids = {cid for cid, _ in dense_results.get(qid, [])[:args.top_k]}

        scores = bm25.get_scores(tokenize(q["text"]))
        bm25_top_idx = sorted(range(len(scores)), key=lambda i: -scores[i])[:args.top_k]
        bm25_ids = {corpus_ids[i] for i in bm25_top_idx}

        union_ids = dense_ids | bm25_ids
        pool_rows.append({
            "query_id": qid,
            "query_text": q["text"],
            "query_category": q["category"],
            "listing_category": q["listing_category"],
            "candidates": sorted(union_ids),
            "n_dense_only": len(dense_ids - bm25_ids),
            "n_bm25_only": len(bm25_ids - dense_ids),
            "n_both": len(dense_ids & bm25_ids),
        })

    with args.out.open("w") as f:
        for row in pool_rows:
            f.write(json.dumps(row) + "\n")

    total_candidates = sum(len(r["candidates"]) for r in pool_rows)
    avg_pool_size = total_candidates / len(pool_rows)
    avg_overlap = sum(r["n_both"] for r in pool_rows) / len(pool_rows)
    print(f"Wrote {len(pool_rows)} query pools -> {args.out}")
    print(f"Avg pool size: {avg_pool_size:.1f} (max possible {args.top_k * 2})")
    print(f"Avg dense/BM25 overlap: {avg_overlap:.1f} of {args.top_k}")
    print("NOTE: candidates are UNGRADED. Next step is human/LLM-assisted "
          "grading per labelling_protocol.md, not done by this script.")


if __name__ == "__main__":
    main()
