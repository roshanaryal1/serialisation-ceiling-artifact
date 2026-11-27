# Provenance

Values here are either measured facts (with their source) or explicitly marked
`NOT MEASURED` / `TBC`. Never filled in with a plausible guess. Update this file,
never delete a superseded value — strike it through and add the new one with a date.

## Repository state

- Repo: `roshanaryal1/rentmate`
- Tag: `bench-v1`
- Commit SHA: `58fc58b3836ff2e22597de0a11a0076bbe1125d3`
- Tag created (local, not pushed): 2026-08-10
- Every measurement in the paper refers to this tag. Any code change after this point requires a new tag and a note in this file about what changed and why re-measurement was or wasn't needed.

## Retrieval stack versions

- `@xenova/transformers`: `2.17.2` (resolved from `package-lock.json`, package.json declares `^2.17.2`)
- `onnxruntime-web`: `1.14.0` (transitive dep, resolved from `package-lock.json`)
- `onnxruntime-common`: `1.14.0` (transitive dep, resolved from `package-lock.json`)
- Node (this dev machine, used to run `scripts/buildEmbeddings.js`): `v24.4.1`
- npm: `11.4.2`
- **Not yet confirmed**: whether the CI/production build uses the same Node version. `TBC`.

## Model artifact

- Model ID: `Xenova/all-MiniLM-L6-v2`
- Source: Hugging Face Hub, `Xenova/all-MiniLM-L6-v2` repo (mirror of `sentence-transformers/all-MiniLM-L6-v2` in ONNX format). Exact download URL used by `@xenova/transformers` at runtime: `NOT MEASURED` — not captured from a network trace yet, should be recorded from Resource Timing API during Phase 5 harness runs.
- Variant used: `model_quantized.onnx` (int8), selected via `{ quantized: true }` in both `scripts/buildEmbeddings.js:51-53` and `src/services/embeddingService.js:58`.
- File size: 22,972,370 bytes (measured locally from `node_modules/.cache/xenova/Xenova/all-MiniLM-L6-v2/onnx/model_quantized.onnx`, downloaded by a prior run of `npm run embeddings` on this machine).
- SHA-256: `afdb6f1a0e45b715d0bb9b11772f032c399babd23bfc31fed1c170afc848bdb1`
- Embedding dimensionality: 384

## Corpus artifact (current, pre-Phase-2)

- `public/embeddings.json`: model `Xenova/all-MiniLM-L6-v2`, dims 384, count 237, generated `2026-04-05T07:49:19.623Z` (per file's own metadata, not re-verified against current knowledgeChunks.js — may be stale relative to bench-v1's knowledgeChunks.js; check before relying on it for any measurement).

## Synthetic corpus (Phase 2, generated 2026-08-10)

- Generator: `research/corpus/generate_corpus.py`, seed `42`. Deterministic — `corpus_*.jsonl` files are gitignored (regenerable, large) and not committed; these hashes are the citable record.
- Field distributions and vocabulary provenance: `research/corpus/DISTRIBUTIONS.md`. Duplicate/near-duplicate measurement: `research/corpus/CORPUS_REPORT.md`.

| File | Records | Bytes | SHA-256 |
|---|---|---|---|
| corpus_1000.jsonl | 1,000 | 393,499 | `90e4105f3cd3ba890a9d70c5157182ff8d5a76a05642a7ccf03c684171ec8302` |
| corpus_10000.jsonl | 10,000 | 3,939,048 | `4844ec92615eaff3dd8d49c63d929c85247b56812859fe0a04e75f79e93e15a6` |
| corpus_100000.jsonl | 100,000 | 39,399,413 | `a790dab5ecfd4a0775e58908bb4909ff8ff421d269adfd22d2496bd181c37def` |
| corpus_250000.jsonl (reserve) | 250,000 | 98,495,148 | `f77697054312bcd83acb57f0c17ee6c62e94cde22d0a4dcc818d208c95a9cbf6` |
| corpus_500000.jsonl (reserve) | 500,000 | 197,005,761 | `8f02a22c22031d9a4952bf6c4656068fd99b6480c0f86e6c86525a797286a7be` |

Regenerate with: `python3 research/corpus/generate_corpus.py --sizes 1000 10000 100000 250000 500000 --seed 42`

## Query set (Phase 3, authored 2026-08-10 — NOT YET JUDGED)

- Generator: `research/queries/generate_queries.py`, seed `7`, over `corpus_10000.jsonl`.
- 250 queries, 4 categories (exact 64, paraphrase 62, attribute 62, vague 62), all 31 listing categories covered, 0 exact-duplicate query text (verified).
- `research/queries/queries.jsonl`: 250 lines, SHA-256 `572915768dc59460edbc93fcdf6872714c1ec8d1694e4912bc7e089bc39290f7`.
- ~~`qrels.jsonl` (graded) does not exist yet~~ — **superseded 2026-08-10**: `qrels.jsonl` now exists (rubric-program first pass, 250 queries, 22,178 judgments). It is NOT yet validated: hand adjudication is outstanding, so kappa is unknown and every quality figure derived from it is provisional. See the Phase 3 first-pass grading section below.

## Phase 4 fp32 baseline (run 2026-08-10)

- `research/baseline/fp32_baseline.py`, model `sentence-transformers/all-MiniLM-L6-v2` (fp32, **forced CPU device** — see correctness note below), exact brute-force cosine (torch, not numpy — see below), top-50 per query.
- Ran on `corpus_1000.jsonl`, `corpus_10000.jsonl`, and `corpus_100000.jsonl` (the last added 2026-08-10: 741.7 docs/sec, 134.8s for 100,000 documents). No baseline for the 250k/500k reserve corpora — those arms are not in scope for the CITRENZ short paper.
- Corpus embed throughput (this machine, MacBook Air M2, CPU-only, fp32): ~700-725 docs/sec at 10k scale, ~640 docs/sec at 1k scale (small-batch overhead). Full figures in `research/baseline/baseline_meta_corpus_*.json`.
- **Correctness bug found and fixed during this run**: numpy's Accelerate-BLAS matmul intermittently returned sign-flipped similarity scores when run in the same process as a loaded torch model (a data race, not a logic bug) — caught by manually sanity-checking that top results were plausible before trusting scores. Fixed by computing similarity entirely in torch instead of numpy. Full writeup: `research/baseline/NUMPY_ACCELERATE_BUG.md`. Verified stable across 3 consecutive re-runs (identical top-1 result and score every time) before trusting any further output.
- Tokenization parity (Python vs the app's own JS pipeline): **PASS, 0/100 mismatches** — `research/baseline/TOKENIZATION_PARITY.md`. RQ1's hard-stop gate cleared.

## Phase 3 candidate pool (built 2026-08-10, UNGRADED)

- `research/queries/build_candidate_pool.py`: union of fp32 dense top-50 (`dense_top50_corpus_10000.json`) and BM25 top-50 (`rank_bm25==0.2.2`, `BM25Okapi`, whitespace-lowercase tokenization over `name + description + features`).
- Output: `research/queries/qrels_pool.jsonl`, 250 rows (one per query), SHA-256 `7fe6572f02a1f6578035eb27dde8fdf0566a5f0a0f68107217ba729b9510b0d6`.
- Avg pool size 88.7 candidates/query (of max 100), avg dense/BM25 overlap only 11.3/50 (22%) — dense and BM25 surface substantially different candidates, confirming the plan's rationale for pooling both rather than judging dense results alone.
- **Contains candidate IDs only, no relevance grades.** Grading is the next step, needs a human (per `labelling_protocol.md`'s 20% hand-adjudication requirement) — not something this session can complete alone.

## Phase 3 first-pass grading (built 2026-08-10, method: rubric program, NOT free-form LLM reasoning)

- `research/queries/grade_pool.py`: encodes `labelling_protocol.md`'s rubric as a deterministic program over the corpus's own structured fields (category, type, spec value, price) — chosen because per-item free-form judgment over ~22,178 candidate pairs isn't practical in one sitting, and this synthetic corpus's structure makes a faithful mechanical proxy possible. **This is explicitly not the same thing as an LLM reading and judging each candidate**, and must be described that way in the paper's methodology, not glossed as "LLM-assisted."
- Output: `research/queries/qrels.jsonl`, 250 queries, 22,178 total judgments, SHA-256 `a5484d5e9c75c5be0649e6b31737fc7b45197fecfbf40face7f739694a256e5d`. Grade distribution: 0=32.9%, 1=26.3%, 2=40.8%.
- One real bug found and fixed in this script during development: initial numeric-spec extraction from query text grabbed the first number in the string, which for style+spec name constructions (e.g. "Scissor Lift 26' Electric, 29.0 ft") is the style modifier's number, not the actual spec — fixed to take the last number, matching how `generate_corpus.py` always appends the spec value last.
- **Weakest part, flagged for scrutiny**: the `ADJACENCY` dict used for grade=1 "tangentially related category" judgments in paraphrase/vague queries is authored by hand, not derived from anything — exactly the kind of judgment call the required hand-adjudication should check hardest.
- `research/queries/sample_for_adjudication.py` selected the required 20% stratified sample: 49/250 queries, 4,455 judgment rows, written to `research/queries/adjudication_sample.csv` (524KB, small enough to commit as-is). **Not yet hand-graded — waiting on you.**
- `research/queries/compute_kappa.py` is ready to run once `adjudication_sample.csv`'s `your_grade` column is filled in. Per the plan: kappa ≥ 0.7 → `qrels.jsonl` as generated is usable; below that → the rubric-program pass is discarded and all 250 queries need real hand-labelling instead.

## Phase 5 harness (built 2026-08-10)

- `research/harness/`: `server.js` (static file server), `bench_page.html`+`bench_page.js` (isolated benchmark surface, loads the app's real `@xenova/transformers@2.17.2`), `instrument.js` (timing/heap/transfer hooks), `runner.js` (Playwright driver). Named `.js` not `.ts` per RESEARCH_PLAN.md's directory sketch — no TypeScript toolchain in this repo, documented deviation, not silent.
- **Gate met**: `node runner.js --smoke-test` ran unattended, produced valid structured JSON raw files. Full account: `research/harness/PHASE5_STATUS.md`.
- Model files mirrored same-origin at `research/harness/models/` (gitignored, regenerable from `node_modules/.cache/xenova/`) — `model_quantized.onnx` there hashes to `afdb6f1a0e45b715d0bb9b11772f032c399babd23bfc31fed1c170afc848bdb1`, identical to the model artifact hash already recorded above under "Model artifact." Loading same-origin instead of from `huggingface.co`/`jsdelivr.net` (the library's default) was necessary for `model_transfer_bytes` to be measurable at all — see below.
- **Two correctness bugs found and fixed during harness development** (both in `PHASE5_STATUS.md` in full):
  1. Cold-cache clearing only emptied Cache API + IndexedDB in-page; the browser's regular HTTP disk cache persisted across repeats in the same `BrowserContext`, silently making "cold" runs partially warm. Fixed: fresh isolated context + CDP `Network.setCacheDisabled` per cold repeat.
  2. `model_transfer_bytes` was silently measuring the wrong resource — Resource Timing zeroes out size fields for cross-origin responses lacking a `Timing-Allow-Origin` header (HF's CDN doesn't send one), so the metric was accidentally capturing an unrelated jsdelivr WASM runtime file instead of the actual model weights. Fixed by serving the model same-origin; verified the fix by confirming the measured size exactly matches the independently-hashed model file.
- **Known unresolved limitation**: WASM heap (`WebAssembly.Memory.buffer.byteLength`) is not obtainable through a stable public API in this `onnxruntime-web` version — returns `null`. Chromium JS heap is used as the practical proxy. If the 8GB-Mac memory-ceiling finding (`MEASUREMENT_PLAN.md` amendment 2) needs true WASM heap specifically, this needs revisiting.
- **Extended 2026-08-10**: `runner.js` now also does network throttling (fixed "Fast 3G" CDP profile on cold runs — Chrome DevTools' own preset numbers, independently reproducible) and best-effort macOS system-state sampling (`vm_stat` swap counters — cumulative since boot, must be differenced before/after at analysis time, not read raw; `pmset` battery%/AC/Low-Power-Mode; `powermetrics` CPU frequency, off by default — a `sudo` prompt with no cached credential hung the harness past its own timeout and crashed the browser mid-run, confirmed by reproducing it, fixed by defaulting off and switching to `sudo -n` which fails fast instead of prompting).
- **Manual-run mode added** (`research/harness/manual_ui.js`, on-page controls in `bench_page.html`) for devices `runner.js` can't automate: iPhone Safari (Playwright has no real-Safari automation) and Android without adb configured. Runs the same N-repeats/idle/warmup-discard protocol, driven by tapping a button instead of Playwright. Cannot do the 3-layer cold-cache isolation the automated path does (no CDP access from a normal page) — documented limitation, not silently equivalent.
- Full run instructions: `research/harness/RUNBOOK.md`.

## Device matrix

| Tier | Device | OS | Browser(s) | Status |
|---|---|---|---|---|
| Desktop | MacBook Air 15", M2, base config, 8GB unified memory, 256GB SSD, 8-core (4P+4E), fanless | macOS **26.5.1** (build 25F80) | Harness drives **Playwright Chromium 141.0.7390.37** (rev 1194). Also installed on the machine: Google Chrome 151.0.7922.108, Safari 26.5. Firefox not installed system-wide. | **IN USE** — all measurements come from this device |
| iOS | iPhone 16 | iOS — exact build `NOT MEASURED` | Safari, manual runs (Playwright cannot drive real Safari) | Pending |
| Android | **Xiaomi Redmi Note 11**, Snapdragon 680 octa-core @ 2.40 GHz max, **4 GB physical RAM + 1 GB extended** | **Android 13**, build `TKQ1.221114.001`, HyperOS `1.0.3.0 TGCMIXM` | Chrome 151.0.0.0, `navigator.hardwareConcurrency` = 8 | **IN USE** |

**The Android user-agent string cannot be used for provenance.** Chrome 151 on
this device reports `Mozilla/5.0 (Linux; Android 10; K) ... Chrome/151.0.0.0
Mobile Safari/537.36`: the OS version is frozen at "10" and the device model is
replaced by the literal `K`, as fingerprinting-reduction measures. The device is
actually Android 13. Specs above were read from the device's own Settings, not
inferred from the UA. Anyone reproducing this work from the raw files'
`device_user_agent` field alone would attribute the results to the wrong OS
version and an unidentifiable device.

The 4 GB physical RAM matters for RQ2: it is the first device in this study where
the memory ceiling anticipated in the original design could plausibly bind before
the V8 string-length ceiling does.

**Important distinction for the paper**: the harness drives Playwright's *bundled* browser builds, not the browsers installed on the machine. Cited browser versions must be the Playwright build versions (Chromium 141.0.7390.37, Firefox 142.0.1, WebKit 26.0), because those are what actually executed the code. Playwright's WebKit is also **not** Safari — it is the upstream WebKit engine, and any WebKit result must be described that way rather than as "Safari".

## Research-side dependency pinning

- Python (Phase 4 baseline): `research/requirements.txt` (loose bounds) + `research/requirements.lock.txt` (exact, via `pip freeze`), installed into `research/.venv` (gitignored, not committed — lockfile is the citable record). Installed 2026-08-10.
  - Key exact versions: `sentence-transformers==3.4.1`, `torch==2.13.0`, `transformers==4.57.6`, `numpy==1.26.4`, `scikit-learn==1.9.0`, `rank-bm25==0.2.2`, `scipy==1.17.1`.
  - These are the versions the published baseline was built with, and they stay
    reproducible from tag `v1.0.0`. In PR #6 (2026-11-28) the lock moved to
    `sentence-transformers==5.6.0` and `transformers==5.10.4` (security advisories);
    torch, tokenizers, numpy, scikit-learn, rank-bm25 and scipy are unchanged.
    Checked then, old lock against new on Python 3.11: `all-MiniLM-L6-v2`
    embeddings of the 250 queries and of the regenerated `corpus_1000.jsonl`
    (hash as above) are bit-identical (max abs difference 0.0), the top-50 lists
    match `baseline/dense_top50_corpus_1000.json`, and token ids match on the
    queries and on the 100-document parity sample. The 10,000 and 100,000
    baselines were not re-run.
  - Python (venv): whatever `python3 -m venv` resolved to on this machine — `NOT MEASURED` exact patch version, record via `research/.venv/bin/python3 --version` before Phase 4 baseline runs.
- ~~JS harness (Phase 5): not yet created~~ — **superseded 2026-08-10**: `research/harness/` is built and its unattended-run gate is met. Dependencies are the repo's own `node_modules` (`@xenova/transformers` 2.17.2, `onnxruntime-web` 1.14.0, both pinned in the root `package-lock.json`) plus Playwright, driving Chromium 141.0.7390.37 (Playwright build v1194). See `harness/PHASE5_STATUS.md`.

## Amendments to the measurement protocol (recorded 2026-08-10, before any measurement taken)

Decided when confirming the device matrix, applies to `research/MEASUREMENT_PLAN.md` and Phase 5/6/7 execution:

1. **Thermal protocol extends to the Mac, not just mobile.** M2 Air is fanless and throttles under sustained load. 60s idle between cells on macOS, same as mobile. Log CPU package temperature/clock where obtainable (`powermetrics`, requires sudo); if unavailable, log wall-clock run index per cell and check for monotonic drift. Randomise cell execution order rather than ascending corpus size, so thermal drift doesn't get mistaken for a scaling effect. Mains power connected and Low Power Mode off for every run, recorded per run.
2. **Memory ceiling is a primary result on the desktop tier, not an edge case.** 8GB unified memory shared with GPU. Projected 500k × 384 fp32 ≈ 768MB at rest, with `JSON.parse` peak transient plausibly 2-3× that. Measure and report as a finding, don't treat as a broken cell.
3. **Desktop failure is redefined.** macOS compresses/swaps rather than killing the tab — failure on this tier is a latency cliff, not a crash. Desktop-tier failure := p50 query latency exceeding N× the 10k baseline (N to be fixed before Phase 6, not after seeing data), OR sustained swap activity during the run. Swap sampled via `vm_stat` around each run. A swapping cell is never recorded as passed.
4. **ONNX Runtime Web thread count set explicitly, not left to default.** `navigator.hardwareConcurrency` reports 8 on M2, but 4 are efficiency cores. Test the threads arm at both 4 and 8, report which was actually used per run — don't let the runtime pick silently.

These are protocol decisions, not measurements — they constrain how Phase 5's harness and Phase 6/7's runs must be built, and must be pre-committed in `MEASUREMENT_PLAN.md` per the plan's own rule against adjusting metric definitions after seeing data.
