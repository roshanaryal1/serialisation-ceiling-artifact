// Streams a vectors_<size>.json artifact and writes the alternative layouts
// used by the serialisation-remedy experiment, without ever holding the whole
// file as one string. That matters: above ~61,000 documents the artifact
// exceeds V8's maximum string length, so convert_to_binary.mjs (which calls
// JSON.parse on the whole file) cannot process it.
//
// Per input size it writes:
//   vectors_<size>.bin / .ids.json            binary float32 + id sidecar
//   vectors_<size>.shard<S>/NNNN.json         JSON shards of S documents, each a
//                                             standalone envelope of the same
//                                             shape as the monolithic file
//   vectors_<size>.shard<S>.manifest.json     ordered list of shard files
//
// The input is split on the "]},{" boundary between chunk objects. That is
// unambiguous for this artifact: an embedding is a flat array of numbers, so
// "]}" can only close a chunk, and the ids contain no braces.
//
// Usage: node shard_vectors.mjs --sizes=1000,10000,100000 --shards=1000,10000

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
const shardSizes = (args.shards || "1000,10000").split(",").map(Number);

const MARK = '"chunks":[';
const SEP = "]},{";

async function* documents(file) {
  let buf = "";
  let header = null;
  const stream = fs.createReadStream(file, { encoding: "latin1", highWaterMark: 1 << 24 });
  for await (const piece of stream) {
    buf += piece;
    if (header === null) {
      const at = buf.indexOf(MARK);
      if (at === -1) continue;
      header = JSON.parse(buf.slice(0, at) + '"chunks":[]}');
      buf = buf.slice(at + MARK.length);
    }
    let start = 0;
    let i;
    while ((i = buf.indexOf(SEP, start)) !== -1) {
      yield { header, doc: buf.slice(start, i + 2) };
      start = i + 3;
    }
    buf = buf.slice(start);
  }
  // Last document is followed by the envelope close "]}".
  if (!buf.endsWith("]}]}")) throw new Error(`${file}: unexpected tail`);
  yield { header, doc: buf.slice(0, -2) };
}

for (const size of sizes) {
  const src = path.join(__dirname, `vectors_${size}.json`);
  if (!fs.existsSync(src)) {
    console.log(`SKIP: ${src} not found`);
    continue;
  }

  const outs = shardSizes.map((s) => {
    const dir = path.join(__dirname, `vectors_${size}.shard${s}`);
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(dir);
    return { s, dir, files: [], docs: [] };
  });

  let floats = null;
  const ids = [];
  let n = 0;
  let header = null;

  const flush = (o, offset) => {
    const name = String(o.files.length).padStart(4, "0") + ".json";
    const head = JSON.stringify({ ...header, count: o.docs.length, offset, chunks: undefined });
    const body = head.slice(0, -1) + ',"chunks":[' + o.docs.join(",") + "]}";
    fs.writeFileSync(path.join(o.dir, name), body, "latin1");
    o.files.push(name);
    o.docs = [];
  };

  for await (const { header: h, doc } of documents(src)) {
    header = h;
    if (floats === null) floats = new Float32Array(h.count * h.dims);
    const parsed = JSON.parse(doc);
    if (parsed.emb.length !== h.dims) throw new Error(`doc ${n}: ${parsed.emb.length} dims`);
    floats.set(parsed.emb, n * h.dims);
    ids.push(parsed.id);
    for (const o of outs) {
      o.docs.push(doc);
      if (o.docs.length === o.s) flush(o, n + 1 - o.s);
    }
    n++;
  }
  for (const o of outs) if (o.docs.length) flush(o, n - o.docs.length);
  if (n !== header.count) throw new Error(`count mismatch: header ${header.count}, read ${n}`);

  fs.writeFileSync(path.join(__dirname, `vectors_${size}.bin`), Buffer.from(floats.buffer));
  // Same sidecar envelope as convert_to_binary.mjs, so sizes are comparable.
  fs.writeFileSync(
    path.join(__dirname, `vectors_${size}.ids.json`),
    JSON.stringify({ model: header.model, dims: header.dims, count: n, generated: header.generated, ids })
  );
  for (const o of outs) {
    fs.writeFileSync(
      path.join(__dirname, `vectors_${size}.shard${o.s}.manifest.json`),
      JSON.stringify({ count: n, dims: header.dims, shard_size: o.s, files: o.files })
    );
  }
  console.log(`corpus_${size}: ${n} docs -> .bin, ${outs.map((o) => `${o.files.length} shards of ${o.s}`).join(", ")}`);
}
