// Module script for bench_page.html. Served over http(s) by server.js (must
// be http, not file://, for fetch()/WASM/module resolution to work).
import { pipeline, env } from "/node_modules/@xenova/transformers/dist/transformers.js";
import {
  now,
  peakJsHeapBytes,
  getWasmHeapBytes,
  transferBytesForUrlPattern,
  clearAllStorage,
} from "./instrument.js";

const MODEL = "Xenova/all-MiniLM-L6-v2";

// Force same-origin, local-only model loading instead of the library's
// default (fetch from huggingface.co / jsdelivr CDN). Two reasons, both
// found empirically while building this harness, not assumed upfront:
//   1. Resource Timing zeroes out encodedBodySize/transferSize for
//      cross-origin resources without a Timing-Allow-Origin header, which
//      huggingface.co's CDN doesn't send -- "model_transfer_bytes" was
//      silently measuring an unrelated jsdelivr WASM runtime file instead
//      of the actual model weights (see PHASE5_STATUS.md item 3). Same-
//      origin resources always report full Resource Timing detail.
//   2. RESEARCH_PLAN.md's own protocol wants network throttled to a fixed,
//      comparable profile across devices -- trivial to do for a same-origin
//      local server (Playwright/CDP network conditions), effectively
//      impossible to guarantee for a live third-party CDN whose actual
//      served bytes and routing vary run to run.
// Model files are mirrored at research/harness/models/ (copied once from
// the already-downloaded node_modules/.cache/xenova/ cache -- see
// PHASE5_STATUS.md for provenance).
env.allowRemoteModels = false;
env.localModelPath = "/research/harness/models/";

function normalise(arr) {
  let norm = 0;
  for (let i = 0; i < arr.length; i++) norm += arr[i] * arr[i];
  norm = Math.sqrt(norm);
  if (norm < 1e-9) return arr;
  for (let i = 0; i < arr.length; i++) arr[i] /= norm;
  return arr;
}

function dot(a, b) {
  let d = 0;
  for (let i = 0; i < a.length; i++) d += a[i] * b[i];
  return d;
}

/**
 * Runs one full benchmark cell: load model, embed corpus (index build),
 * embed+search N queries. Returns the full metric set (MEASUREMENT_PLAN.md).
 *
 * @param {Object} opts
 * @param {string} opts.corpusUrl - e.g. "/research/corpus/corpus_1000.jsonl"
 * @param {string[]} opts.queries - query texts to run
 * @param {number} opts.threads - ONNX Runtime Web thread count (4 or 8, per
 *   MEASUREMENT_PLAN.md's amendment: set explicitly, never left to default)
 * @param {boolean} opts.clearStorageFirst - true for cold-cache runs
 * @param {"shipped"|"build"} [opts.mode="build"] - deployment mode under test,
 *   per MEASUREMENT_PLAN.md ADDENDUM 1:
 *     "shipped" (Mode A) - fetch precomputed vectors, parse, build index.
 *        What RentMate actually does. Cheap, so full N=20 protocol applies.
 *     "build"   (Mode B) - embed the whole corpus in-browser. ~43 docs/sec,
 *        so run at reduced N and always report N alongside the figure.
 * @param {string} [opts.vectorsUrl] - Mode A only, e.g.
 *   "/research/corpus/vectors_1000.json"
 */
window.runBenchCell = async function runBenchCell(opts) {
  const { corpusUrl, vectorsUrl, queries, threads, clearStorageFirst } = opts;
  const mode = opts.mode || "build";
  const t_navStart = now();
  const storageCleared = clearStorageFirst ? await clearAllStorage() : null;

  // Explicit thread count -- MEASUREMENT_PLAN.md amendment 4: don't let the
  // runtime pick silently. Must be set before the pipeline is created.
  env.backends.onnx.wasm.numThreads = threads;

  const t_pipelineStart = now();
  const embedder = await pipeline("feature-extraction", MODEL, { quantized: true });
  const t_pipelineReady = now();
  // WASM instantiation + tokeniser init + model transfer are bundled inside
  // this single await (transformers.js doesn't expose finer-grained hooks
  // publicly) -- reported as one combined "model_load_ms" span, not
  // fabricated sub-splits. Transfer bytes recovered separately below via
  // Resource Timing, which IS independently measurable.

  const index = [];
  let corpusCount = 0;
  // Mode A sub-spans, null in Mode B so a missing value is never mistaken for
  // a measured zero.
  let vectorsFetchMs = null;
  let vectorsParseMs = null;

  const t_indexBuildStart = now();

  if (mode === "shipped") {
    // Fetch and parse are timed separately: JSON.parse of a large vectors
    // artifact is the hypothesised 2-3x transient memory spike
    // (MEASUREMENT_PLAN.md device amendment 2), so it must be visible on its
    // own rather than buried inside a single "load" number.
    const t_fetchStart = now();
    const res = await fetch(vectorsUrl);
    const text = await res.text();
    const t_fetchEnd = now();

    const parsed = JSON.parse(text);
    const t_parseEnd = now();

    vectorsFetchMs = t_fetchEnd - t_fetchStart;
    vectorsParseMs = t_parseEnd - t_fetchEnd;

    const dims = parsed.dims;
    for (const chunk of parsed.chunks) {
      const emb = new Float32Array(dims);
      for (let d = 0; d < dims; d++) emb[d] = chunk.emb[d];
      // Vectors are already normalised at precompute time; normalise() again
      // is idempotent and cheap, and keeps both modes on an identical code
      // path from here on so the search comparison stays apples-to-apples.
      index.push({ id: chunk.id, emb: normalise(emb) });
    }
    corpusCount = parsed.count;
  } else {
    const corpusRes = await fetch(corpusUrl);
    const corpusText = await corpusRes.text();
    const corpusLines = corpusText.trim().split("\n");
    const corpus = corpusLines.map((l) => JSON.parse(l));
    corpusCount = corpus.length;

    // BATCH = 32 matches scripts/buildEmbeddings.js. Note this incurs the
    // batch-padding artifact documented in
    // research/baseline/BATCH_PADDING_ARTIFACT.md -- deliberately kept,
    // because it is what the real build pipeline does.
    const BATCH = 32;
    for (let i = 0; i < corpus.length; i += BATCH) {
      const batch = corpus.slice(i, i + BATCH);
      const texts = batch.map((r) => `${r.name}\n\n${r.description}`);
      const output = await embedder(texts, { pooling: "mean", normalize: true });
      for (let j = 0; j < batch.length; j++) {
        const dims = output.dims[1];
        const emb = new Float32Array(dims);
        for (let d = 0; d < dims; d++) emb[d] = output.data[j * dims + d];
        index.push({ id: batch[j].id, emb: normalise(emb) });
      }
    }
  }
  const t_indexBuildEnd = now();

  const queryResults = [];
  for (const q of queries) {
    const t_qStart = now();
    const out = await embedder(q, { pooling: "mean", normalize: true });
    const qVec = normalise(new Float32Array(out.data));
    const t_qEmbedded = now();

    const scored = index
      .map(({ id, emb }) => ({ id, score: dot(qVec, emb) }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 10);
    const t_searchDone = now();

    queryResults.push({
      query: q,
      embed_ms: t_qEmbedded - t_qStart,
      search_ms: t_searchDone - t_qEmbedded,
      top1_id: scored[0] ? scored[0].id : null,
      top1_score: scored[0] ? scored[0].score : null,
    });
  }

  // Everything needed before first inference: model weights, tokenizer
  // files, and the ONNX Runtime Web WASM binary itself -- all now
  // same-origin (see the env.allowRemoteModels/localModelPath note above),
  // so Resource Timing reports real sizes for all of them, not just the
  // two that happened to end in .onnx/.wasm.
  const modelTransfer = transferBytesForUrlPattern(/\/models\/|ort-wasm/);

  return {
    timestamp: new Date().toISOString(),
    mode,
    corpus_url: mode === "shipped" ? vectorsUrl : corpusUrl,
    corpus_size: corpusCount,
    threads_configured: threads,
    threads_actual_reported: env.backends.onnx.wasm.numThreads,
    cache_state: clearStorageFirst ? "cold" : "warm",
    storage_cleared: storageCleared,
    timings_ms: {
      nav_to_pipeline_start: t_pipelineStart - t_navStart,
      model_load: t_pipelineReady - t_pipelineStart,
      // Mode A: fetch + parse + Float32Array construction.
      // Mode B: in-browser embedding of the whole corpus.
      // Same wall-clock span in both, but they measure different work --
      // never pool these across modes in analysis.
      index_build: t_indexBuildEnd - t_indexBuildStart,
      vectors_fetch: vectorsFetchMs,
      vectors_parse: vectorsParseMs,
      cold_start_total: t_indexBuildEnd - t_navStart,
    },
    query_results: queryResults,
    peak_js_heap_bytes: peakJsHeapBytes(),
    wasm_heap_bytes: getWasmHeapBytes(),
    model_transfer_bytes: modelTransfer.totalBytes,
    model_transfer_resource_count: modelTransfer.matchedResources,
    user_agent: navigator.userAgent,
    hardware_concurrency: navigator.hardwareConcurrency,
  };
};

/**
 * RQ1 quality evaluation: run the FULL query set through the in-browser int8
 * system and return complete ranked lists, so the result can be scored against
 * the fp32 Python baseline with the same metric code.
 *
 * Separate from runBenchCell on purpose. runBenchCell measures LATENCY, so it
 * uses a small query sample and repeats it many times; keeping full 250-query
 * top-50 rankings on every one of those repeats would bloat the raw files
 * enormously for no benefit. Quality is a property of the ranking, not of the
 * clock, so it needs one careful pass and no repeats.
 *
 * Output shape deliberately matches baseline/dense_top50_corpus_*.json
 * ({query_id: [[doc_id, score], ...]}) so analysis/compute_ir_metrics.py can
 * consume it with no conversion step.
 *
 * @param {Object} opts
 * @param {string} opts.vectorsUrl - precomputed vectors artifact to score against
 * @param {{id: string, text: string}[]} opts.queries - the full query set
 * @param {number} opts.threads
 * @param {number} [opts.topK=50]
 */
window.runQualityEval = async function runQualityEval(opts) {
  const { vectorsUrl, queries, threads } = opts;
  const topK = opts.topK || 50;

  env.backends.onnx.wasm.numThreads = threads;
  const embedder = await pipeline("feature-extraction", MODEL, { quantized: true });

  const res = await fetch(vectorsUrl);
  const parsed = JSON.parse(await res.text());
  const dims = parsed.dims;
  const index = parsed.chunks.map((c) => {
    const emb = new Float32Array(dims);
    for (let d = 0; d < dims; d++) emb[d] = c.emb[d];
    return { id: c.id, emb: normalise(emb) };
  });

  const results = {};
  for (let i = 0; i < queries.length; i++) {
    const q = queries[i];
    const out = await embedder(q.text, { pooling: "mean", normalize: true });
    const qVec = normalise(new Float32Array(out.data));
    const scored = index
      .map(({ id, emb }) => ({ id, score: dot(qVec, emb) }))
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);
    results[q.id] = scored.map((s) => [s.id, s.score]);
    if (i % 25 === 0) {
      document.getElementById("status").textContent =
        `quality eval: ${i}/${queries.length}`;
    }
  }

  return {
    vectors_url: vectorsUrl,
    vectors_batch_size: parsed.batch_size ?? null,
    corpus_size: parsed.count,
    dims,
    threads,
    top_k: topK,
    query_count: queries.length,
    user_agent: navigator.userAgent,
    results,
  };
};

document.getElementById("status").textContent = "ready";
