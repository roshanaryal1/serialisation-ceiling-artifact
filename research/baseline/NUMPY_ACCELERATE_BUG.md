# Correctness bug found and fixed during Phase 4 baseline development

## Summary

`fp32_baseline.py`'s first version computed cosine similarity with plain
numpy (`query_emb @ corpus_emb.T` on arrays produced by
`SentenceTransformer.encode(..., convert_to_numpy=True)`). In the same
Python process as a loaded `sentence-transformers`/`torch` model, this
matmul intermittently returned **silently wrong values** — not a crash, not
a NaN, a plausible-looking wrong number. Caught by manual sanity-checking
top results against known-correct matches, not by any automated check.

## What was observed

For query `"Scissor Lift 26' Electric, 29.0 ft"` against `corpus_10000`:

- `sims[0].max()` (numpy, read once): `0.8804953` (correct — matches an
  independently-verified re-embed of the same texts, see below)
- `sims[0, np.argmax(sims[0])]` (numpy, same array, read moments later in
  the same script run): `-0.8804953` — same magnitude, flipped sign, at a
  **different index** (`np.argmax` returned index 7900 with value 0.0265 in
  one debug run, vs the true max at a different index) — i.e. reading the
  same numpy array twice in quick succession gave two different answers.
  This is only possible if the array's underlying memory buffer was still
  being written by another thread while being read — a data race, not a
  logic bug in the script.

## Root cause (best available explanation, not exhaustively proven)

- `numpy.show_config()` on this machine reports `blas: name: accelerate` —
  numpy is linked against Apple's Accelerate framework BLAS.
- `torch` (loaded by `sentence-transformers`) manages its own CPU threading
  runtime. Known issue class: Apple's Accelerate BLAS thread pool and
  PyTorch's threading runtime can race when both are active in the same
  process on Apple Silicon, corrupting large matmul results
  non-deterministically. This reproduced intermittently (not on every run —
  isolated minimal repros sometimes could not reproduce it), consistent
  with a genuine race condition rather than a deterministic bug.
- Isolated reproduction attempts using only saved `.npy` arrays in a fresh
  process (no torch loaded) were always correct. The bug only appeared when
  numpy's Accelerate-backed matmul ran in a process that also had torch's
  threading runtime active.

## Fix

Compute the similarity matrix and top-k entirely in `torch` (`torch.matmul`
+ `torch.topk`), never dropping to numpy until after the top-k indices and
scores are already resolved to Python lists. `fp32_baseline.py` now does
this. Verified stable across 3 consecutive full runs on `corpus_10000` (250
queries × 10,000 docs): identical top-1 result and score
(`0.8804953098297119`) every time.

## Why this matters for the paper

If this had gone undetected, every RQ1 quality metric (nDCG, recall, MRR)
computed against this baseline would have been silently wrong — not
uniformly biased in a way that might cancel out, but corrupted per-query in
a way tied to a data race, i.e. unreproducible garbage that would have
looked like a real number. This is exactly the class of error Phase 4's own
tokenization-parity hard-stop rule is designed to catch for a *different*
failure mode (tokenizer divergence); this one was a general lesson from the
plan's own Rule 1 ("Never fabricate a number") extended to "never trust a
number until it's been sanity-checked against a manually-verified case" —
applied here by spot-checking that the top retrieval results for
exact-match queries were plausible (correct equipment type, correct spec
range) before trusting the similarity scores, which is what surfaced the
sign anomaly.

## Action item for later phases

Phase 5's browser harness computes similarity in JavaScript (plain
`Float32Array` dot products, see `AUDIT.md` — no BLAS library, no torch, no
threading of this kind), so this specific bug class doesn't apply there. But
any future Python-side numpy matmul in this research/ codebase that runs
after a torch model has been loaded should either (a) use torch tensors
throughout, matching the fix here, or (b) be independently sanity-checked
the way this one was, not assumed correct because it "ran without error."
