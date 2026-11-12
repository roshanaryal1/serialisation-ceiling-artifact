// Minimal static file server for the benchmark harness. Serves the repo
// root so bench_page.html can load /node_modules/@xenova/transformers and
// /research/corpus/*.jsonl by absolute path. Must be http(s), not file://
// -- fetch() of the corpus and WASM instantiation both require it.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const PORT = process.env.BENCH_PORT || 8743;

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".json": "application/json",
  ".jsonl": "application/json",
  ".wasm": "application/wasm",
  ".onnx": "application/octet-stream",
};

const server = http.createServer((req, res) => {
  const urlPath = decodeURIComponent(req.url.split("?")[0]);
  const filePath = path.join(REPO_ROOT, urlPath);

  // Prevent path traversal outside the repo root.
  if (!filePath.startsWith(REPO_ROOT)) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }

  // ?enc=gzip|br serves the precompressed copy written by
  // corpus/compress_artifacts.mjs, the way a CDN serves a static encoding.
  // A missing copy is a 404, never a silent fallback to identity, or an
  // "encoded" measurement could quietly be an uncompressed one.
  const enc = new URLSearchParams(req.url.split("?")[1] || "").get("enc");
  const SUFFIX = { gzip: ".gz", br: ".br" };
  if (enc && !SUFFIX[enc]) {
    res.writeHead(400);
    res.end("Unknown enc: " + enc);
    return;
  }

  fs.readFile(enc ? filePath + SUFFIX[enc] : filePath, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end("Not found: " + urlPath + (enc ? ` (${enc})` : ""));
      return;
    }
    const ext = path.extname(filePath);
    const headers = { "Content-Type": MIME[ext] || "application/octet-stream" };
    if (enc) headers["Content-Encoding"] = enc;

    // Cache the immutable measurement inputs: model weights, tokenizer, and
    // the precomputed vectors artifact. Without this the browser re-fetches
    // the vectors on every "warm" run, which is not a state any real
    // deployment is in -- a static content-addressed asset would be cached.
    // Measured consequence of omitting it: on the Redmi Note 11 over WiFi the
    // 77MB artifact was re-transferred every repeat, 4.1s of a 6.6s "warm"
    // start, making warm figures overstate real return-visit cost. Loopback
    // hid this on desktop (157ms), which is why it was not caught earlier.
    if (/\/(models|corpus)\//.test(urlPath) || ext === ".wasm") {
      headers["Cache-Control"] = "public, max-age=31536000, immutable";
    } else {
      // Harness code itself must never be cached, or an edited bench_page.js
      // would silently keep measuring the previous version.
      headers["Cache-Control"] = "no-store";
    }

    res.writeHead(200, headers);
    res.end(data);
  });
});

server.listen(PORT, () => {
  console.log(`Benchmark harness server: http://localhost:${PORT}/research/harness/bench_page.html`);
});
