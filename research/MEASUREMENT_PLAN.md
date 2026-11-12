# Measurement Plan

Pre-committed before any measurement is taken. Do not edit metric definitions,
protocol, or decision thresholds after seeing data — amend by dated addendum only,
never by silent edit.

## Metric definitions

| Metric | Definition |
|---|---|
| Cold start | Navigation start to first query embedding returned, with all browser storage cleared. Decomposed into: model transfer, WASM instantiation, tokeniser init, index load or build, first inference. |
| Warm start | Same, with model and vectors already in IndexedDB / Cache API. |
| Query latency | Split and reported separately: query embedding time, and search time. Never as a single blended number. |
| Index build | Time to construct the searchable structure from stored vectors. |
| Peak JS heap | `performance.memory.usedJSHeapSize`, Chromium only. Report as Chromium-only and say so. |
| WASM heap | `WebAssembly.Memory.buffer.byteLength` at peak. Cross-browser. |
| Transfer bytes | Total bytes over the wire on cold start, from the Resource Timing API. |

## Protocol

- N = 20 repeats per cell. Discard the first run of each cell as warmup. Report p50 and p95. Never report mean latency.
- Cold-cache runs clear IndexedDB, Cache API, and HTTP cache programmatically, verified before each run.
- Network throttled to a fixed profile for cold-start runs so model transfer time is comparable across devices. Record the profile.
- Every run writes one JSON file to `results/raw/` containing the full metric set plus device fingerprint, timestamp, commit SHA, corpus size, and run index.

## Device-specific amendments (dated 2026-08-10, pre-measurement — see PROVENANCE.md for full rationale)

- **All tiers, not just mobile**: 60s idle between cells. Battery floor 30% and thermal-state logging apply to mobile (iPhone 16); the Mac uses the powermetrics/wall-clock-drift substitute since it has no battery-floor equivalent as a fanless mains-connected device, but mains power + Low Power Mode off is still recorded per run.
- **Desktop (M2 Air)**: cell execution order is randomised, not ascending by corpus size, across ALL device tiers where thermal drift is plausible — ascending order confounds throttling with a scaling effect.
- **Desktop failure definition**: p50 query latency exceeding N× the 10k-corpus baseline (N fixed before Phase 6 pilot, not after), OR sustained swap activity (`vm_stat` sampled around each run). A swapping cell is a failed cell, never a passed one with an asterisk.
- **Memory ceiling on desktop is a primary reported result**, not a discarded edge case — 8GB unified memory shared with GPU, projected ~768MB at rest for 500k×384 fp32 with 2-3× transient parse spikes plausible.
- **ONNX Runtime Web thread count**: set explicitly, tested at both 4 and 8 threads on the M2 (4P+4E cores; `navigator.hardwareConcurrency` reports 8 but only 4 are performance cores). Record which thread count was configured and confirm via runtime inspection that it was honoured, for every run.

## Open before Phase 5 harness build

- N for the desktop latency-cliff failure threshold: not yet fixed. Must be set before Phase 6 pilot begins, from no source other than a deliberate pre-commitment (not derived from pilot data).
- Android device (Realme) model/spec: `TBC`, blocks Phase 6 pilot until resolved.

---

# ADDENDUM 1 — 2026-08-10: two-mode split, forced by a measured feasibility failure

Appended, not edited in place, per this file's own rule. Nothing above this line
has been changed. This addendum is justified by a measurement, not by
convenience — the original design cannot physically be executed, and the
justification is reproducible from committed artifacts.

## The measurement that forced this

From `research/harness/smoke_test_output/` (two independent cold runs, corpus_1000,
4 threads, desktop Chromium on the M2 Air): in-browser index build took 23,281 ms
and 23,599 ms for 1,000 documents — **~43 documents/second**, dominating a
~24 s cold start of which model load was only ~0.6 s.

Projected against the protocol frozen above (N=20 repeats, 60 s idle between repeats):

| Corpus | One cold run | One cell (N=20 + idle) |
|---|---|---|
| 1k | 23 s | ~28 min |
| 10k | 3.9 min | ~1.6 hr |
| 100k | 39 min | **~13 hr** |
| 250k | 97 min | ~33 hr |
| 500k | 3.2 hr | ~65 hr |

The Phase 7 desktop matrix alone (3 sizes × 2 thread settings × 2 cache states =
12 cells) projects to **~62 hours of continuous running**, before any mobile tier.
On a mid-tier Android it would be several times slower again, and would additionally
hit thermal throttling and background-tab suspension long before completion. The
matrix as specified is not executable. Discovering this at Phase 7 rather than now
would have cost the schedule far more.

## Root cause

Not a bug. It follows from a deliberate design decision recorded in
`bench_page.html`'s own header comment: the harness re-embeds the entire corpus
in-browser on every repeat, to expose "index build" as a first-class metric (it is
in the metric table above). The real application does not do this — it ships
precomputed vectors as a static build artifact (`public/embeddings.json`, see
`AUDIT.md`) and embeds only the query at runtime.

## The amendment

The study is split into two deployment modes, measured as separate arms rather than
cutting scope. They answer genuinely different questions and have different
envelopes, which strengthens rather than weakens RQ2.

**Mode A — "shipped vectors"** (what RentMate actually does, deployment-realistic):
fetch a precomputed vectors artifact, `JSON.parse` it, build the in-memory index,
embed the query, search. Cheap per run, so **N=20 stands unchanged** and the full
protocol above applies without exception. This is also where the 8 GB memory-ceiling
question lives — the JSON parse transient is exactly the 2-3× spike hypothesised in
the device-specific amendments above, and keeping the artifact as JSON rather than a
binary format is a deliberate choice so that hypothesis remains testable.

**Mode B — "in-browser index build"** (answers "what if you cannot precompute"):
the existing behaviour, unchanged. Reduced to **N=3, cold-cache only, single thread
setting**, sizes 1k/10k/100k (~2.4 hr total). **Every Mode B figure must state N=3
next to it.** Mode B numbers are never to be presented as though they carry the
N=20 protocol's repeat count, and p95 is not meaningful at N=3 — report the observed
range instead, and say so.

## What is NOT changed by this addendum

- All metric definitions in the table above.
- N=20, warmup discard, p50/p95, and "never report mean latency" — for Mode A.
- 60 s idle, randomised cell order, cold-cache clearing, network throttle profile,
  battery/AC/thermal logging: all apply to both modes.
- The desktop failure threshold N and the Android device spec remain open above;
  this addendum does not resolve either and must not be read as doing so.

---

# ADDENDUM 2 — 2026-08-10: network throttling limited to small corpus sizes

Also measurement-forced, also appended rather than edited in place.

## Measurement

First real protocol runs: the Mode A **1k cold** cell took **~172 s per repeat**
(consistent across repeats 4-7: 172.2, 171.9, 171.9, 172.1 s), moving ~32 MB
(24 MB model + tokenizer, 7.7 MB vectors) under the frozen Fast-3G profile
(1.6 Mbps down). That is 160 s of pure transfer at the profile bandwidth — the
number is essentially all network.

## Projection

Throttled cold-start time is dominated by, and near-linear in, transfer bytes:

| Corpus | Mode A cold bytes | Per repeat @1.6 Mbps | Cell (N=20 + idle) |
|---|---|---|---|
| 1k | ~32 MB | ~172 s (measured) | ~1.3 hr |
| 10k | ~101 MB | ~505 s | ~3.1 hr |
| 100k | ~794 MB | ~66 min | **~22 hr** |

## The amendment

Cold-cache runs are throttled at **1k and 10k**, and run **unthrottled at 100k
and above** (`runner.js --no-throttle`). For unthrottled cells, transfer time at
the profile bandwidth is **derived** from the exactly-recorded
`model_transfer_bytes` rather than measured.

Justification, not convenience:

1. Transfer time at a fixed emulated bandwidth is a deterministic function of
   bytes. Measuring it 20 times at 100k adds no information the byte count does
   not already carry exactly, and costs 22 hours.
2. The components of cold start that are *not* network-bound and *not*
   analytically predictable — `JSON.parse` cost, index construction, peak heap,
   and any swap behaviour — are precisely what the large corpus sizes are being
   run to measure. Throttling does not improve those measurements; it only
   delays them.
3. The original rationale for throttling was cross-device comparability. With
   the device matrix scoped to the desktop tier (see below), there is currently
   no second device to be comparable with.

**Any derived transfer time must be labelled as derived, never presented as
measured.** Raw files record `network_profile: null` for unthrottled runs, so
the two cases remain distinguishable in the data rather than by memory.

## Related scope change (recorded here for traceability, decided 2026-08-10)

CITRENZ 2026's full/short paper deadline was verified from the organisation's
own site as **17 August 2026** — seven days out. The submission is therefore
scoped to a short paper/poster covering the **desktop tier only** (MacBook Air
M2, Chrome/Firefox/WebKit). The Android tier (device spec still `TBC`) and the
iOS tier become stated future work rather than silently-missing cells. This is a
scope reduction, not a change to any metric definition or protocol above.
