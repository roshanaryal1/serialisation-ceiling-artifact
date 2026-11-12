# Finding: the shipped-vectors deployment has a hard ceiling near 66k documents, imposed by the JavaScript engine

Found 2026-08-10 while generating the 100,000-document Mode A artifact.
This is an envelope boundary of exactly the kind RESEARCH_PLAN.md's RQ2 exists
to locate, and it is not a memory limit.

## What happened

`precompute_vectors.mjs` embedded all 100,000 documents successfully (214
docs/sec, ~8 minutes) and then failed at serialisation:

```
precompute_vectors failed: RangeError: Invalid string length
    at JSON.stringify (<anonymous>)
```

## Root cause, verified

V8 caps the length of a single string. Measured directly on the Node build in
use (v24.4.1):

```
'x'.repeat(2**29 - 24)  ->  536,870,888  OK
'x'.repeat(2**29)       ->  RangeError: Invalid string length
```

So the maximum string is **536,870,888 characters**.

The vectors artifact costs **8,081 bytes per document** (measured:
`vectors_1000.json` is 8,081,293 bytes for 1,000 documents; 384 float32 values
serialised as decimal text plus an id).

```
536,870,888 / 8,081  ~=  66,400 documents
```

## Why this matters, and why it is not just a Node inconvenience

The same limit applies to `JSON.parse` in the browser, because it is a V8 string
limit rather than a Node one. A deployment that ships precomputed vectors as a
single JSON document therefore cannot exceed roughly 66,000 documents **on any
device**, no matter how much memory it has. A 16 GB laptop and a 4 GB phone hit
the identical wall.

This reframes part of RQ2's answer. The expected story was a gradual memory and
latency degradation ending in a device-specific ceiling. For Mode A there is
instead a sharp, device-independent, engine-imposed cliff well below the
100,000-document point the study was designed to probe, and the projected
768 MB at-rest cost of 500k x 384 fp32 vectors is never reached because
serialisation fails long before memory pressure does.

## Consequences for the study

1. **The 100k Mode A cell is expected to fail**, and per RESEARCH_PLAN.md Phase 7
   a failed cell is a first-class result: the failure mode, the corpus size, and
   the error are the finding. The artifact is still generated (via a streaming
   writer that never materialises the whole string) precisely so the
   browser-side failure can be observed and recorded rather than merely
   predicted.
2. **The real Mode A envelope must be located by bisection** between 10,000
   (known good) and 100,000 (expected to fail), not assumed to be exactly 66,400
   -- the arithmetic gives an estimate, and the measured boundary may differ
   because per-document size varies slightly with the decimal expansion of the
   float values.
3. **It is a limitation of the artifact format, not of browser-native retrieval
   as such.** A binary format (raw `Float32Array` over `ArrayBuffer`), chunked
   JSON, or streaming parse would all lift this specific ceiling, and would also
   be roughly 4x smaller since 4 bytes beats ~21 characters per float. The paper
   should say this plainly: the ceiling measured here is the one the deployed
   application would actually hit, and it is straightforwardly avoidable by
   changing the format. That is a useful, actionable result for practitioners
   rather than a defect in the study.
4. Mode B (in-browser index build) is unaffected by this limit, since it never
   materialises a large JSON string. Mode B has a different and much lower
   practical ceiling driven by embedding throughput (~39 docs/sec in-browser).

## Status

- V8 string limit: **measured**, 536,870,888 chars.
- Bytes per document: **measured**, 8,081.
- Derived ceiling: **~66,400 documents** (arithmetic from the two measurements).
- Browser-side failure at 100k: **NOT YET MEASURED** -- artifact generation in
  progress, the cell will be run and its failure mode recorded.
- Exact empirical boundary by bisection: **NOT YET MEASURED**.
