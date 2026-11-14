# RQ1: what int8 quantisation costs in retrieval quality

> **Superseded.** The relevance judgments behind this note later failed their
> pre-registered validation (kappa 0.512 against 0.70), so RQ1 was dropped and
> no quality result is reported. See `research/queries/ADJUDICATION_OUTCOME.md`.

**PROVISIONAL.** These numbers are scored against `qrels.jsonl`, which is the
rubric-program first pass. Hand adjudication has not been done, so Cohen's kappa
is unknown and the judgments are not validated. Do not present any figure here
as final until kappa clears 0.7.

Corpus: 10,000 synthetic listings. Queries: all 250. Reference: fp32
`sentence-transformers/all-MiniLM-L6-v2` in Python, CPU. System under test: int8
ONNX via transformers.js in Chromium. Bootstrap CIs over queries.

## Headline: no detectable quality cost

Delta = int8 minus fp32. Negative means int8 is worse.

| variant | nDCG@10 | recall@5 | recall@10 | MRR@10 |
|---|---|---|---|---|
| int8, batch-1 vectors (artifact-free) | -0.0063 [-0.0165, +0.0023] | -0.0002 | -0.0019 | -0.0027 |
| int8, batch-32 vectors (app-faithful) | -0.0013 [-0.0116, +0.0076] | +0.0010 | +0.0031 | +0.0051 |

**Every confidence interval includes zero.** On this corpus and query set, int8
quantisation has no measurable effect on retrieval quality by any of the four
metrics. The point estimates are all under 0.007 nDCG, well inside noise.

This is a null result and is reported as one. It is also the practically useful
answer: the 4x model-size reduction that makes browser-native retrieval feasible
is, here, free in quality terms.

## The batch-padding artifact also has no measurable effect

`BATCH_PADDING_ARTIFACT.md` established that transformers.js batching shifts
document vectors (mean cosine 0.992 against unpadded) while PyTorch is
padding-invariant, and flagged it as a threat to this comparison. Measured, it
is not one: the two variants' deltas overlap heavily and both include zero. The
batch-32 variant is nominally *closer* to fp32 than batch-1, which is not
meaningful given the interval widths.

Worth keeping in the paper anyway, as a methodological point: the artifact was
real and measurable at the vector level, and could easily have been mistaken for
a quantisation effect had it not been isolated. It happens not to matter here.
That it did not matter is a finding, not a reason to have skipped the check.

## Rank agreement is much lower than the quality metrics suggest

Spearman correlation between int8 and fp32 top-10 orderings:

| variant | Spearman | 95% CI |
|---|---|---|
| int8 batch-1 | 0.375 | [0.328, 0.422] |
| int8 batch-32 | 0.362 | [0.315, 0.408] |

So the two systems return substantially **different orderings** while scoring
essentially **identical quality**. Both statements are true and they are not in
tension: in this corpus a large fraction of pooled candidates are graded equally
relevant (see `METRICS_NOTES.md` -- paraphrase and vague queries average 56 and
43 grade-2 documents respectively), so reshuffling among equally-relevant
documents moves the ranking without moving nDCG.

The practitioner reading: if the interface shows ten results and the user does
not care which equally-good item is first, int8 is free. If anything depends on
*stable* ordering between a server-side fp32 index and a client-side int8 one --
pagination, caching a "first result", A/B consistency, deduplicating against a
server ranking -- those systems will visibly disagree.

RESEARCH_PLAN.md's expectation that rank agreement is "often the more meaningful
measure for a UI that shows ten results" is borne out: it is the only metric here
that distinguishes the two systems at all.

## Caveat on interpreting the low Spearman

The Spearman figure is computed over the union of the two top-10 lists, ranking
absent documents past the end of their list. It therefore mixes two effects:
genuine reordering of shared documents, and documents appearing in one list but
not the other. It should be read as "how differently do these two systems present
ten results", not as a pure rank correlation over a fixed item set.

## Provenance

- fp32 reference: `baseline/dense_top50_corpus_10000.json`
- int8 batch-32: `results/processed/int8_chromium_10000_top50.json`
- int8 batch-1: `results/processed/int8_chromium_10000_bs1_top50.json`
- Metric code: `analysis/compute_ir_metrics.py`
- Judgments: `queries/qrels.jsonl` (**unvalidated**)
