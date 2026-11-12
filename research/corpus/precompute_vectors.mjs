// Precompute corpus vectors for Mode A ("shipped vectors") of the benchmark
// -- see MEASUREMENT_PLAN.md ADDENDUM 1.
//
// Deliberately mirrors the app's own scripts/buildEmbeddings.js as closely as
// the different input shape allows, so Mode A measures what RentMate actually
// ships rather than a research-only artifact:
//   - same library and version (@xenova/transformers from the repo's own
//     node_modules), same model id, same { quantized: true }
//   - same { pooling: "mean", normalize: true } inference options
//   - same batch size (32)
//   - same output envelope: { model, dims, count, generated, chunks: [{id, emb}] }
//   - same JSON (not binary) serialisation -- the JSON.parse memory transient
//     is a hypothesis under test, not an inefficiency to engineer away
// The one intentional difference: text is built from the synthetic listing's
// `name`/`description` (this corpus's fields) rather than `title`/`content`
// (the FAQ chunk fields), matching the "name\n\ndescription" concatenation the
// harness and the fp32 Python baseline both already use, so all three pipelines
// embed byte-identical strings.
//
// Usage (from repo root):
//   node research/corpus/precompute_vectors.mjs --sizes 1000,10000
//   node research/corpus/precompute_vectors.mjs --sizes 100000

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MODEL = "Xenova/all-MiniLM-L6-v2";
const DEFAULT_BATCH_SIZE = 32;

// --batch-size exists because batching is NOT embedding-neutral in
// transformers.js: padding shorter sequences to the batch maximum measurably
// shifts the mean-pooled vector (~0.992 mean cosine vs the unpadded
// batch-of-1 embedding of the same text, min observed 0.986; the effect is
// present at batch 8/32/64 alike, so it is padding presence, not batch size).
// PyTorch/sentence-transformers is padding-invariant here (verified: cosine
// 1.000000 for the same comparison), so batched JS embeddings would inject an
// implementation artifact into RQ1's int8-vs-fp32 quality gap and be
// misattributed to quantisation. Generate BOTH variants and report the
// decomposition -- see research/baseline/BATCH_PADDING_ARTIFACT.md.
//   batch 32 = app-faithful (what scripts/buildEmbeddings.js actually ships)
//   batch 1  = artifact-free, isolates the true quantisation effect

function parseArgs() {
  const args = Object.fromEntries(
    process.argv.slice(2).map((a) => {
      const [k, v] = a.replace(/^--/, "").split("=");
      return [k, v === undefined ? true : v];
    })
  );
  // support both "--sizes 1000,10000" and "--sizes=1000,10000"
  const valueOf = (name, fallback) => {
    let v = args[name];
    if (v === true) v = process.argv[process.argv.indexOf(`--${name}`) + 1];
    return v === undefined ? fallback : v;
  };
  return {
    sizes: String(valueOf("sizes", "1000,10000")).split(",").map(Number),
    batchSize: Number(valueOf("batch-size", DEFAULT_BATCH_SIZE)),
  };
}

async function main() {
  const { sizes, batchSize } = parseArgs();
  const { pipeline, env } = await import("@xenova/transformers");

  // Use the harness's already-mirrored local model copy -- same file, same
  // SHA-256 as PROVENANCE.md records. Avoids a network fetch and guarantees
  // the precompute and the in-browser run use bit-identical weights.
  env.allowRemoteModels = false;
  env.localModelPath = path.join(__dirname, "../harness/models/");

  console.log(`Loading model ${MODEL} (local, quantized)...`);
  const embedder = await pipeline("feature-extraction", MODEL, { quantized: true });
  console.log("Model ready.");

  for (const size of sizes) {
    const corpusPath = path.join(__dirname, `corpus_${size}.jsonl`);
    if (!fs.existsSync(corpusPath)) {
      console.error(`SKIP ${size}: ${corpusPath} not found (regenerate with generate_corpus.py)`);
      continue;
    }

    const records = fs
      .readFileSync(corpusPath, "utf-8")
      .trim()
      .split("\n")
      .map((l) => JSON.parse(l));

    console.log(`\ncorpus_${size}: embedding ${records.length} documents (batch=${batchSize})...`);
    const t0 = Date.now();
    const result = [];

    for (let i = 0; i < records.length; i += batchSize) {
      const batch = records.slice(i, i + batchSize);
      const texts = batch.map((r) => `${r.name}\n\n${r.description}`);
      // batch of 1 is passed as a bare string, not a 1-element array: the
      // array form still goes through the padding code path in
      // transformers.js, which is the thing being avoided.
      const output =
        batchSize === 1
          ? await embedder(texts[0], { pooling: "mean", normalize: true })
          : await embedder(texts, { pooling: "mean", normalize: true });
      const dims = output.dims[output.dims.length - 1];
      for (let j = 0; j < batch.length; j++) {
        result.push({
          id: batch[j].id,
          emb: Array.from(output.data.slice(j * dims, (j + 1) * dims)),
        });
      }
      if (i % (batchSize * 50) === 0) {
        const pct = ((i / records.length) * 100).toFixed(1);
        const rate = i > 0 ? (i / ((Date.now() - t0) / 1000)).toFixed(0) : "-";
        process.stdout.write(`  ${pct}% (${rate} docs/sec)\r`);
      }
    }

    const elapsed = (Date.now() - t0) / 1000;
    const payload = {
      model: MODEL,
      dims: result[0]?.emb.length ?? 384,
      count: result.length,
      generated: new Date().toISOString(),
      batch_size: batchSize,
      chunks: result,
    };

    // batch=32 keeps the plain name (it is the app-faithful default that Mode
    // A runs against); other batch sizes get suffixed so the artifact-free
    // batch=1 variant can coexist rather than silently overwrite it.
    const outPath = path.join(
      __dirname,
      batchSize === DEFAULT_BATCH_SIZE ? `vectors_${size}.json` : `vectors_${size}_bs${batchSize}.json`
    );

    // Streamed rather than JSON.stringify'd in one shot. A single
    // stringify of the 100k artifact throws
    //   RangeError: Invalid string length
    // because the result exceeds V8's maximum string length
    // (536,870,888 chars, verified empirically). At ~8,081 bytes/document
    // that caps a single-JSON-string vectors artifact at roughly 66,400
    // documents.
    //
    // This is kept as a deliberate finding, not engineered around: the same
    // V8 limit applies to JSON.parse in the browser, so a shipped-vectors
    // deployment using one JSON document has a hard ceiling near 66k
    // regardless of how much memory the device has. Streaming here lets the
    // artifact be produced anyway so the BROWSER-side failure can be
    // observed and recorded as a failed cell (which RESEARCH_PLAN.md Phase 7
    // treats as a first-class result), instead of the study simply being
    // unable to generate the input.
    const out = fs.createWriteStream(outPath);
    const write = (s) => new Promise((res, rej) => (out.write(s) ? res() : out.once("drain", res)));
    await write(`{"model":${JSON.stringify(payload.model)},`
      + `"dims":${payload.dims},"count":${payload.count},`
      + `"generated":${JSON.stringify(payload.generated)},`
      + `"batch_size":${payload.batch_size},"chunks":[`);
    for (let i = 0; i < result.length; i++) {
      await write((i ? "," : "") + JSON.stringify(result[i]));
    }
    await write("]}");
    await new Promise((res) => out.end(res));
    const mb = (fs.statSync(outPath).size / 1024 / 1024).toFixed(1);
    console.log(
      `  done: ${result.length} vectors, ${payload.dims} dims, ${mb} MB, ` +
        `${elapsed.toFixed(1)}s (${(result.length / elapsed).toFixed(0)} docs/sec) -> ${outPath}`
    );
  }
}

main().catch((err) => {
  console.error("precompute_vectors failed:", err);
  process.exit(1);
});
