// Converts an existing vectors_<size>.json artifact (the shipped-vectors
// format measured throughout this study) into a binary equivalent, for the
// serialization-intervention experiment referenced in section 6.1/6.6.
//
// Format: vectors_<size>.bin = raw Float32Array, doc-major, dims-minor
// (count * dims * 4 bytes, no framing). vectors_<size>.ids.json = the id
// list in the same order, tiny relative to the vector payload, kept
// separate so the .bin file is a pure typed-array fetch with zero parsing
// beyond `new Float32Array(await res.arrayBuffer())`.
//
// Usage: node convert_to_binary.mjs --sizes=1000,10000

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

  const floats = new Float32Array(count * dims);
  const ids = new Array(count);
  for (let i = 0; i < count; i++) {
    ids[i] = chunks[i].id;
    const emb = chunks[i].emb;
    if (emb.length !== dims) throw new Error(`doc ${i} (${chunks[i].id}): expected ${dims} dims, got ${emb.length}`);
    floats.set(emb, i * dims);
  }

  const binPath = path.join(__dirname, `vectors_${size}.bin`);
  const idsPath = path.join(__dirname, `vectors_${size}.ids.json`);
  fs.writeFileSync(binPath, Buffer.from(floats.buffer, floats.byteOffset, floats.byteLength));
  fs.writeFileSync(idsPath, JSON.stringify({ model: payload.model, dims, count, generated: payload.generated, ids }));

  const jsonBytes = fs.statSync(inPath).size;
  const binBytes = fs.statSync(binPath).size;
  const idsBytes = fs.statSync(idsPath).size;
  console.log(
    `corpus_${size}: JSON ${(jsonBytes / 1e6).toFixed(2)} MB -> ` +
      `binary ${(binBytes / 1e6).toFixed(2)} MB + ids ${(idsBytes / 1e3).toFixed(1)} KB ` +
      `(total ${((binBytes + idsBytes) / 1e6).toFixed(2)} MB, ${(jsonBytes / (binBytes + idsBytes)).toFixed(2)}x smaller)`
  );
}
