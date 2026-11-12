# Two ways these metrics will mislead you

Both found by running the plan's own Phase 4 sanity check ("exact-match queries
should score far higher nDCG than vague ones; if they don't, the metric code or
the qrels are wrong") and having it **fail**. The check was right to fire; the
cause turned out to be neither broken metric code nor broken qrels, but two
structural properties of the evaluation design that must be stated in the paper
rather than silently worked around.

## 1. nDCG is not comparable across query categories

Observed (fp32 baseline, corpus_10000, rubric qrels):

| query type | nDCG@10 | avg grade-2 docs per query | avg pool |
|---|---|---|---|
| attribute | 0.6051 | 17.9 | 96.0 |
| exact | 0.8021 | 27.6 | 73.0 |
| paraphrase | 0.8737 | 56.0 | 90.8 |
| vague | 0.7999 | 43.4 | 95.5 |

The ordering looks backwards — vague queries appear to do as well as exact ones,
and paraphrase best of all. The cause is the rubric in `labelling_protocol.md`,
which applies **deliberately different strictness per query category**:

- `paraphrase` / `vague`: grade 2 = *any* listing in the intended category.
  With ~56 of ~91 pooled candidates qualifying, almost any sensible top-10 is
  all-grade-2, so nDCG saturates near 1.
- `exact`: grade 2 requires matching equipment **type** and a nearby **spec**
  value — only ~28 of ~73 candidates qualify.
- `attribute`: grade 2 requires correct category **and** a satisfied
  price/location constraint — strictest of all, ~18 of ~96.

So a cross-category nDCG difference measures how lenient the rubric is for that
category, **not** how hard the queries are or how well retrieval works. The
per-category breakdown exists to compare **one category against itself across
systems** (int8 vs fp32) — which is precisely what RQ1 needs and where the plan
expects the quantisation effect to hide. `compute_ir_metrics.py` prints this
warning on every run.

**Do not write** "browser-native retrieval handles vague queries as well as exact
ones." That sentence is not supported by these numbers.

## 2. recall@k has a structural ceiling far below 1.0

Raw recall@5 = 0.0743 looks like a broken system. It isn't. Recall here is
computed against the judged pool, where the relevant set (grade >= 1) averages
46-71 documents per query. Retrieving 5 documents therefore cannot exceed
~5/46 ≈ 0.11 by arithmetic alone.

Reported alongside every run:

| metric | ceiling | achieved | % of attainable |
|---|---|---|---|
| recall@5 | 0.1137 | 0.0743 | 65.3% |
| recall@10 | 0.2022 | 0.1502 | 74.3% |

The "% of attainable" column is the interpretable one. Quote the raw recall
number only next to its ceiling, or the reader will conclude retrieval is
failing when it is performing reasonably.

Root cause is pooled evaluation with a broad relevance definition: the dense+BM25
pool surfaces ~89 candidates per query and the rubric marks a large fraction of
them relevant. This is a property of the study design, not a bug, but it does
mean **recall@k is a weak metric for this setup**. nDCG@10 (rank-aware,
normalised by the ideal ranking) and MRR@10 are the more informative headline
numbers here, and Spearman rank agreement is the more meaningful int8-vs-fp32
comparison per the plan's own Phase 8 note.

## Also: unjudged documents count as non-relevant

Standard pooled-evaluation assumption. With ~89 judged candidates out of a
10,000-document corpus, a system could retrieve a genuinely relevant unjudged
document and be scored as if it were wrong. The dense+BM25 union pooling exists
to keep this bias small and symmetric between the systems under comparison, but
it is a real limitation and belongs in the limitations section.
