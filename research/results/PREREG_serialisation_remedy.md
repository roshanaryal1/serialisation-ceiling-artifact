# Pre-registration: sharded JSON and compressed transfer

Written 2026-10-21, before any timing run of this experiment. Committed before
the runner is executed, so the predictions can be checked against git history.

## Why

SSD 2026 review (2026-10-02) said the size and deployment claims rest on
uncompressed transfer, and suggested chunked JSON as an alternative remedy.
This experiment adds both arms to the Section 5.2 comparison.

## Design

- Engine: Chromium (Playwright), loopback, same desktop as Section 5.2.
- Corpus sizes: 1,000, 10,000, 100,000 documents. 100,000 uses real
  embeddings from `precompute_vectors.mjs` (same model, batch 32).
- Arms: monolithic JSON; JSON sharded at 1,000 docs per file; JSON sharded at
  10,000 docs per file; binary float32 plus its id sidecar.
- Encodings: identity, gzip (level 9), brotli (quality 9), served
  precompressed with `Content-Encoding`.
- N=20 per cell, fresh browser context per repeat, `cache: "no-store"`.
- Shards are fetched and parsed sequentially, which is conservative: it gives
  sharding no credit for request parallelism.
- Every arm fetches every file a client needs: binary includes its id
  sidecar, sharded JSON includes its manifest.

## Already known before this file was written (not predictions)

Byte sizes at 1k and 10k were measured while building the compressed copies:
JSON compresses 2.29x (gzip) and 2.40-2.42x (brotli), float32 binary 1.08x.
So the compressed size ratio of JSON to binary-plus-sidecar is about 2.4x,
not 5.19x. This is reported, not predicted.

## Predictions

1. Monolithic JSON fails at 100,000 documents in 20/20 repeats under every
   encoding. Compression changes the wire size, not the decoded string.
2. Both sharded arms succeed at 100,000 in 20/20 repeats.
3. At 10,000 documents, identity encoding, sharded JSON parse time (summed
   over shards) is within 20% of monolithic parse time, because the same bytes
   of text are parsed. Sharding removes the failure, not the cost.
4. Binary remains faster end to end than every JSON arm at every size and
   encoding, by at least 5x at 10,000 documents with identity encoding.
5. On loopback, gzip and brotli arms are not faster than identity for any
   arm: decompression is added and no bandwidth is saved. Their benefit is
   wire size, which loopback cannot show.

A prediction that fails is reported as failed.
