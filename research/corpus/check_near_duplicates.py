#!/usr/bin/env python3
"""Pairwise near-duplicate check for a generated corpus (RESEARCH_PLAN.md
Phase 2: "Guarantee no near-duplicates at a level that would inflate recall:
check pairwise similarity on a sample and report the distribution.").

Jaccard similarity over bag-of-words(name + description), computed on a
random sample of pairs (all-pairs is O(n^2) and unnecessary for a
distribution estimate). Deterministic given --seed.
"""

import argparse
import json
import re
from pathlib import Path

from generate_corpus import mulberry32


def tokenize(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def jaccard(a, b):
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus_file", type=Path)
    parser.add_argument("--pairs", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=1234)
    args = parser.parse_args()

    records = []
    with args.corpus_file.open() as f:
        for line in f:
            r = json.loads(line)
            records.append(tokenize(r["name"] + " " + r["description"]))

    n = len(records)
    rng = mulberry32(args.seed)
    scores = []
    exact_dup = 0
    for _ in range(args.pairs):
        i = int(rng() * n)
        j = int(rng() * n)
        if i == j:
            continue
        s = jaccard(records[i], records[j])
        scores.append(s)
        if s == 1.0:
            exact_dup += 1

    scores.sort()
    m = len(scores)

    def pct(p):
        return scores[min(int(p * m), m - 1)]

    print(f"corpus: {args.corpus_file.name}  n={n}  sampled_pairs={m}")
    print(f"Jaccard similarity distribution: "
          f"p50={pct(0.50):.3f} p90={pct(0.90):.3f} p95={pct(0.95):.3f} "
          f"p99={pct(0.99):.3f} max={scores[-1]:.3f}")
    print(f"exact-match pairs in sample (Jaccard=1.0): {exact_dup}/{m} "
          f"({exact_dup / m:.4f})")
    print(f"pairs with Jaccard >= 0.8 (near-duplicate threshold): "
          f"{sum(1 for s in scores if s >= 0.8)}/{m}")


if __name__ == "__main__":
    main()
