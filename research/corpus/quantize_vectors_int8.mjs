// Post-hoc scalar quantisation of an existing vectors_<size>.json artifact
// (float32 embeddings, as emitted by precompute_vectors.mjs) to packed int8,
// for the binary-int8 arm of the serialisation-intervention experiment
// (section 5.2 addendum). This is a storage-representation experiment, not a
// retrieval-quality one: it measures artifact size and fetch+parse cost, plus
// a representation-fidelity check (cosine error against the float32
// original), and reports neither top-k retrieval overlap as a quality claim
// nor touches the withdrawn RQ1 protocol.
//
// Quantisation: per-vector scalar, symmetric around zero (embeddings from a
// normalized mean-pooled encoder are not zero-centred per-dimension in a way
// that would benefit from a learned zero-point, and a fixed zero-point keeps
// dequantisation to one multiply). scale = max(abs(v)) / 127, q_i =
// round(v_i / scale), clamped to [-127, 127]. Dequantisation: v_i ~= q_i * scale.
//
// Format: vectors_<size>.int8.bin = raw Int8Array, doc-major, dims-minor
// (count * dims bytes). vectors_<size>.int8.meta.json = { model, dims, count,
// generated, ids: [...], scales: [...] } -- one float32 scale per vector,
// kept separate so the .bin file is a pure typed-array fetch with zero
// parsing beyond `new Int8Array(await res.arrayBuffer())`.
//
// Usage: node quantize_vectors_int8.mjs --sizes=1000,10000

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const args = Object.fromEntries(
  process.argv.slice(2).map((a) => {
    const [k, v] = a.replace(/^--/, "").split("=");
    return [k, v];
  })
);
const sizes = (args.sizes || "1000,10000").split(",").map(Number);

function quantizeVector(emb) {
  let maxAbs = 0;
  for (let i = 0; i < emb.length; i++) {
    const a = Math.abs(emb[i]);
    if (a > maxAbs) maxAbs = a;
  }
  // A zero vector has no meaningful scale; scale=1 keeps q all-zero without
  // a divide-by-zero. Not expected in practice for normalized embeddings.
  const scale = maxAbs > 0 ? maxAbs / 127 : 1;
  const q = new Int8Array(emb.length);
  let sumSqErr = 0;
  let sumSqNorm = 0;
  for (let i = 0; i < emb.length; i++) {
    const qi = Math.max(-127, Math.min(127, Math.round(emb[i] / scale)));
    q[i] = qi;
    const dequant = qi * scale;
    const err = emb[i] - dequant;
    sumSqErr += err * err;
    sumSqNorm += emb[i] * emb[i];
  }
  return { q, scale, sumSqErr, sumSqNorm };
}

function cosineFidelity(emb, q, scale) {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < emb.length; i++) {
    const dequant = q[i] * scale;
    dot += emb[i] * dequant;
    normA += emb[i] * emb[i];
    normB += dequant * dequant;
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom > 0 ? dot / denom : 1;
}

for (const size of sizes) {
  const inPath = path.join(__dirname, `vectors_${size}.json`);
  if (!fs.existsSync(inPath)) {
    console.log(`SKIP: ${inPath} not found`);
    continue;
  }
  const payload = JSON.parse(fs.readFileSync(inPath, "utf-8"));
  const { dims, count, chunks } = payload;
  if (chunks.length !== count) {
    throw new Error(`count mismatch: header says ${count}, chunks.length is ${chunks.length}`);
  }

  const packed = new Int8Array(count * dims);
  const ids = new Array(count);
  const scales = new Array(count);
  const cosErrors = new Array(count);

  for (let i = 0; i < count; i++) {
    ids[i] = chunks[i].id;
    const emb = chunks[i].emb;
    if (emb.length !== dims) throw new Error(`doc ${i} (${chunks[i].id}): expected ${dims} dims, got ${emb.length}`);
    const { q, scale } = quantizeVector(emb);
    packed.set(q, i * dims);
    scales[i] = scale;
    cosErrors[i] = 1 - cosineFidelity(emb, q, scale);
  }

  const binPath = path.join(__dirname, `vectors_${size}.int8.bin`);
  const metaPath = path.join(__dirname, `vectors_${size}.int8.meta.json`);
  fs.writeFileSync(binPath, Buffer.from(packed.buffer, packed.byteOffset, packed.byteLength));
  fs.writeFileSync(
    metaPath,
    JSON.stringify({ model: payload.model, dims, count, generated: payload.generated, ids, scales })
  );

  cosErrors.sort((a, b) => a - b);
  const p50 = cosErrors[Math.floor(cosErrors.length * 0.5)];
  const p95 = cosErrors[Math.floor(cosErrors.length * 0.95)];
  const mean = cosErrors.reduce((a, b) => a + b, 0) / cosErrors.length;
  const max = cosErrors[cosErrors.length - 1];

  const jsonBytes = fs.statSync(inPath).size;
  const binBytes = fs.statSync(binPath).size;
  const metaBytes = fs.statSync(metaPath).size;
  console.log(
    `corpus_${size}: JSON ${(jsonBytes / 1e6).toFixed(2)} MB -> ` +
      `int8 binary ${(binBytes / 1e6).toFixed(2)} MB + meta ${(metaBytes / 1e3).toFixed(1)} KB ` +
      `(total ${((binBytes + metaBytes) / 1e6).toFixed(2)} MB, ${(jsonBytes / (binBytes + metaBytes)).toFixed(2)}x smaller than JSON)`
  );
  console.log(
    `  cosine error (1-cos) vs float32 original: mean=${mean.toExponential(3)} ` +
      `p50=${p50.toExponential(3)} p95=${p95.toExponential(3)} max=${max.toExponential(3)}`
  );
}
