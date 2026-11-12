#!/usr/bin/env python3
"""Server-side fp32 baseline (RESEARCH_PLAN.md Phase 4) — the fixed reference
point for RQ1, and the dense half of Phase 3's candidate pool.

Steps:
  1. Embed a corpus (`sentence-transformers/all-MiniLM-L6-v2`, fp32) and
     save vectors as .npy.
  2. Embed the 250 queries the same way.
  3. Exact brute-force cosine retrieval, top-50 per query.
  4. Record wall-clock embedding throughput + this machine's identity, for
     the cost-of-compute comparison later (RESEARCH_PLAN.md Phase 4).

Does NOT compute nDCG/recall/MRR yet — those need qrels, which need this
script's top-50 output unioned with BM25's top-50 (build_candidate_pool.py)
and then graded (labelling_protocol.md), neither done yet.

CORRECTNESS NOTE (see research/baseline/NUMPY_ACCELERATE_BUG.md): on this
machine, `numpy` is linked against Apple's Accelerate BLAS. Running a large
numpy matmul (query_emb @ corpus_emb.T, ~250x384 @ 384x10000) in the SAME
process as a loaded PyTorch/sentence-transformers model intermittently
produced silently WRONG results — same-magnitude but sign-flipped, and in
one observed case `array.max()` and `array[argmax(array)]` disagreed within
the same array read moments apart, which is only possible if the underlying
buffer was still being written by a stale thread. This is a known class of
bug (torch's threading runtime and Accelerate's BLAS thread pool interfering
in-process on Apple Silicon), not something specific to this script's logic
-- verified by reproducing it, then reproducing its ABSENCE when the same
matmul is done via torch.matmul on torch tensors instead of numpy on
numpy arrays. The similarity computation below therefore stays in torch the
entire time and only converts to numpy/Python floats after the argsort/topk
is already resolved.

Usage: python3 fp32_baseline.py --corpus ../corpus/corpus_10000.jsonl
"""

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 50


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("../corpus/corpus_10000.jsonl"))
    parser.add_argument("--queries", type=Path, default=Path("../queries/queries.jsonl"))
    parser.add_argument("--out-dir", type=Path, default=Path("."))
    args = parser.parse_args()

    corpus = load_jsonl(args.corpus)
    queries = load_jsonl(args.queries)
    corpus_texts = [f"{r['name']}\n\n{r['description']}" for r in corpus]
    corpus_ids = [r["id"] for r in corpus]
    query_texts = [q["text"] for q in queries]
    query_ids = [q["id"] for q in queries]

    print(f"Loading {MODEL} (fp32)...")
    # Forced to CPU rather than the default MPS device on Apple Silicon, for
    # a citable/reproducible reference baseline -- MPS numerics on this
    # torch version are less battle-tested than CPU for exact reproduction
    # across machines. NOTE: forcing CPU alone did NOT fix the sign-flip bug
    # found during development of this script -- that was a separate numpy
    # Accelerate BLAS thread-race issue, fixed by staying in torch through
    # the similarity computation instead of dropping to numpy. Full account:
    # research/baseline/NUMPY_ACCELERATE_BUG.md.
    model = SentenceTransformer(MODEL, device="cpu")

    print(f"Embedding {len(corpus_texts)} corpus documents...")
    t0 = time.perf_counter()
    corpus_emb = model.encode(corpus_texts, batch_size=64, show_progress_bar=True,
                               convert_to_tensor=True, normalize_embeddings=True)
    corpus_elapsed = time.perf_counter() - t0
    throughput = len(corpus_texts) / corpus_elapsed

    print(f"Embedding {len(query_texts)} queries...")
    t1 = time.perf_counter()
    query_emb = model.encode(query_texts, batch_size=64, show_progress_bar=False,
                              convert_to_tensor=True, normalize_embeddings=True)
    query_elapsed = time.perf_counter() - t1

    emb_path = args.out_dir / f"baseline_embeddings_{args.corpus.stem}.npy"
    np.save(emb_path, corpus_emb.numpy())

    # Exact brute-force cosine (vectors are already L2-normalised, so dot
    # product == cosine similarity). No ANN index -- matches the plan's
    # instruction for an exact reference, and matches the in-browser system's
    # own brute-force approach (AUDIT.md), so both sides use the same
    # retrieval algorithm and only differ in model precision.
    #
    # Stays in torch (not numpy) through argsort/topk -- see the module
    # docstring's CORRECTNESS NOTE. torch.topk also avoids a full O(n log n)
    # sort when we only need the top 50 of 10k+.
    sims = torch.matmul(query_emb, corpus_emb.T)  # (n_queries, n_corpus)
    top_scores, top_idx = torch.topk(sims, k=min(TOP_K, sims.shape[1]), dim=1)
    top_scores = top_scores.tolist()
    top_idx = top_idx.tolist()

    dense_results = {}
    for qi, qid in enumerate(query_ids):
        ranked = [(corpus_ids[ci], top_scores[qi][k]) for k, ci in enumerate(top_idx[qi])]
        dense_results[qid] = ranked

    results_path = args.out_dir / f"dense_top{TOP_K}_{args.corpus.stem}.json"
    with results_path.open("w") as f:
        json.dump(dense_results, f)

    meta = {
        "model": MODEL,
        "precision": "fp32",
        "corpus_file": str(args.corpus),
        "corpus_size": len(corpus_texts),
        "query_count": len(query_texts),
        "corpus_embed_seconds": corpus_elapsed,
        "corpus_embed_throughput_docs_per_sec": throughput,
        "query_embed_seconds": query_elapsed,
        "embedding_dims": int(corpus_emb.shape[1]),
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "top_k": TOP_K,
    }
    meta_path = args.out_dir / f"baseline_meta_{args.corpus.stem}.json"
    with meta_path.open("w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nWrote {emb_path} ({corpus_emb.shape})")
    print(f"Wrote {results_path} (top-{TOP_K} per query)")
    print(f"Wrote {meta_path}")
    print(f"Corpus embed throughput: {throughput:.1f} docs/sec "
          f"({corpus_elapsed:.2f}s for {len(corpus_texts)} docs)")


if __name__ == "__main__":
    main()
