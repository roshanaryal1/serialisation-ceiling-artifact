# Batch-padding artifact in transformers.js — a second threat to RQ1

Found 2026-08-10 while verifying Mode A's precomputed vectors (`precompute_vectors.mjs`).
Same class of problem as the Phase 4 tokenisation-parity gate, one layer further
down the pipeline: it would contaminate RQ1's int8-vs-fp32 quality gap with an
implementation artifact that has nothing to do with quantisation.

`RESEARCH_PLAN.md` Phase 4 states the principle for tokenisation: "A tokenisation
divergence would mean any measured quality gap is an implementation artifact, not
a quantisation effect, and it would invalidate RQ1 entirely." That reasoning
applies verbatim here. Tokenisation parity passed (`TOKENIZATION_PARITY.md`,
0/100 mismatches) — that check does not cover pooling, so this slipped past it.

## The finding

Embedding the *same text* through `@xenova/transformers` gives a different vector
depending on whether it was embedded alone or inside a batch of mixed-length texts:

| Comparison | Cosine |
|---|---|
| JS batch-of-1 vs JS single (bare string) | **1.000001** (identical) |
| JS batch-of-32 vs JS single, same text | **0.994763** |
| JS batch-of-32 vs JS batch-of-1, 1,000 docs | mean **0.99238**, min **0.98382**, p05 0.98924 |
| **Python (sentence-transformers) batch-of-32 vs single** | **1.000000** (identical) |

Measured at batch 8, 32, and 64 — all ~0.992 mean. The effect is driven by the
*presence* of padding, not its amount.

## Interpretation

`sentence-transformers` performs attention-mask-aware mean pooling, so padded
positions contribute nothing and batching is embedding-neutral. `@xenova/transformers`
at version 2.17.2, with `{ pooling: "mean", normalize: true }`, does not reproduce
that invariance — shorter sequences padded up to the batch maximum come out with
measurably shifted vectors.

This is stated as an observed behavioural difference between the two libraries,
verified by direct measurement in both. It is **not** a claim about the internals
of either implementation; no source-level root-cause analysis was performed, and
none should be asserted in the paper without one.

## Why it matters

1. **RQ1 contamination.** The fp32 Python baseline is padding-invariant; the int8
   in-browser system is not. A naive comparison would attribute the whole gap to
   int8 quantisation, when part of it is a JS pooling artifact. The two effects
   must be separated or the RQ1 number is not what it claims to be.
2. **It affects the real application, not just the benchmark.** `scripts/buildEmbeddings.js`
   batches at 32 (`BATCH_SIZE = 32`, line 15) with the same library and options, so
   the vectors RentMate actually ships in `public/embeddings.json` carry this
   artifact. That is a genuine finding about the deployed system, and worth a line
   in the paper rather than a silent correction.
3. **Queries are unaffected.** Query embedding is done one string at a time, both
   in the app (`embeddingService.js`) and in the harness — no padding, no artifact.
   Only the document side is affected.

## How it is handled

`precompute_vectors.mjs` takes `--batch-size`, and both variants are generated:

- `vectors_<size>.json` — batch 32, **app-faithful**, what Mode A measures by
  default because it is what production actually ships.
- `vectors_<size>_bs1.json` — batch 1, **artifact-free**, isolates the true
  quantisation effect.

The quality analysis reports the decomposition rather than a single blended number:

- fp32 Python vs int8 JS **batch-1** → the true quantisation cost (RQ1 as intended).
- fp32 Python vs int8 JS **batch-32** → the cost actually paid in deployment.
- The difference between those two → the batch-padding artifact, quantified.

Whether this ~0.008 mean cosine shift materially moves nDCG@10 is an empirical
question and is **NOT YET MEASURED** — it will be answered by
`analysis/compute_ir_metrics.py` once run against both variants. Do not assume it
is negligible because the cosine looks close; ranking metrics can be sensitive to
small perturbations when candidate scores are tightly clustered, which they are
in this templated corpus (see `CORPUS_REPORT.md`).

## Reproduce

```bash
# JS: single vs batched, same text
node -e "…"   # see git history of this investigation, or:
node research/corpus/precompute_vectors.mjs --sizes 1000 --batch-size 1
node research/corpus/precompute_vectors.mjs --sizes 1000
# then cosine-compare vectors_1000.json against vectors_1000_bs1.json
```

Python side verified with `sentence-transformers==3.4.1`, `torch==2.13.0` (see
`PROVENANCE.md`), CPU device.
