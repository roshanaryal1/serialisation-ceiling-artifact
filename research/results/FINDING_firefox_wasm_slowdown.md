# Finding: Firefox executes the same int8 WASM model ~9.4x slower than Chromium and WebKit

Measured 2026-08-11 on one machine (MacBook Air M2), same model artifact, same
library version, same thread setting, warm cache, N=20 repeats per cell with the
first discarded.

## The measurement

Query embedding latency (ms), warm cache, p50 across 190 measured queries:

| engine | 1k corpus | 10k corpus | min | max |
|---|---|---|---|---|
| Chromium 141.0.7390.37 | 8.1 | 8.3 | 6.5 | 34.0 |
| **Firefox 142.0.1** | **79.0** | **78.0** | **65.0** | 130.0 |
| WebKit 26.0 | 9.0 | 8.0 | 6.0 | 99.0 |

Ratios against Chromium at 10k: **Firefox 9.4x slower, WebKit 1.0x (identical)**.

Query embedding does not touch the corpus, which is why the figure is flat
across corpus sizes: it is one forward pass through the int8 model.

## This is not a measurement artifact

Three checks, because a 9x cross-engine difference is exactly the kind of claim
that is usually an instrumentation bug:

1. **Not the timer floor.** Firefox's 78 ms sits far above the 1 ms
   `performance.now()` clamp that invalidates the sub-millisecond *search*
   comparisons (`FINDING_timer_resolution.md`). The embedding comparison is
   unaffected.
2. **Not a different model or a scalar WASM fallback.** The obvious explanation
   would be Firefox falling back to a non-SIMD build. It does not: all three
   engines fetch the identical `ort-wasm-simd.wasm`, 2,359,124 bytes, confirmed
   by inspecting Resource Timing entries in each engine directly.
3. **Not an outlier or a warmup effect.** The whole distribution is shifted, not
   the tail: Firefox's *fastest* observed embedding (65 ms) is still 10x
   Chromium's fastest (6.5 ms). The warmup repeat is discarded and per-query CV
   is low in every engine (Firefox 0.026-0.032).

## What it means

For a browser-native retrieval deployment, the engine is a first-order
performance variable, larger in this workload than corpus size across the range
measured. A query that returns in 8 ms on Chromium and WebKit takes about 78 ms
on Firefox on the same hardware. That is still interactive, but it is an order of
magnitude, and it is invisible to any study that measures one engine and
generalises.

The cause is not established here. Same SIMD binary, same machine, same model
rules out the cheap explanations, but attributing it to a specific difference in
WASM compilation, SIMD lowering, or threading would require profiling inside the
engine, which was not done. **State the measurement, not a mechanism.**

## Secondary caveat found alongside it

WebKit reports `encodedBodySize: 0` for the ONNX Runtime WASM binary, because
that file is served cross-origin from a CDN and WebKit does not expose sizes for
cross-origin responses lacking `Timing-Allow-Origin`. WebKit's
`model_transfer_bytes` is therefore **undercounted by ~2.36 MB** relative to
Chromium and Firefox (23,685,093 vs 26,044,171). The model files themselves are
served same-origin and are counted correctly in all three engines. Any
cross-engine transfer-bytes comparison must either add the known WASM size back
for WebKit or exclude the runtime binary from all three.

This is the same class of problem as the earlier transfer-bytes bug: the model
files were made same-origin to fix it, but the ONNX Runtime WASM binary still
loads from jsdelivr. Serving it locally too would close the gap.
