// Serialisation-remedy experiment: sharded JSON and compressed transfer.
// Pre-registered in research/results/PREREG_serialisation_remedy.md.
//
// Extends serialization_experiment.mjs (left unchanged, it produced the
// submitted Section 5.2 data) with:
//   - json-shard<S>: the same vectors split into standalone JSON files of S
//     documents (corpus/shard_vectors.mjs), fetched and parsed one after
//     another, plus their manifest
//   - enc: identity, gzip or br, served precompressed by server.js (?enc=)
//   - corpus sizes past the JSON string ceiling, where failure is an outcome
//     to record, not an error to abort on
// Every arm fetches every file a client needs, so binary includes its id
// sidecar. Raw per-repeat values are written; CIs are computed afterwards by
// analysis/serialization_remedy_summary.py with a fixed seed.
//
// Requires: node server.js running on PORT, shard_vectors.mjs and
// compress_artifacts.mjs already run for the sizes tested.
//
// Usage: node serialization_remedy_experiment.mjs --sizes=1000,10000,100000 \
//          --arms=json,json-shard1000,json-shard10000,binary --encs=identity,gzip,br --repeats=20

// playwright-core, not playwright: the repo root depends on the former only
// (see RUNBOOK.md on browser revisions).
import { chromium } from "playwright-core";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../..");
const PORT = 8743;

const args = Object.fromEntries(
  process.argv.slice(2).map((a) => {
    const [k, v] = a.replace(/^--/, "").split("=");
    return [k, v === undefined ? true : v];
  })
);
const sizes = (args.sizes || "1000,10000").split(",").map(Number);
const arms = (args.arms || "json,json-shard1000,json-shard10000,binary").split(",");
const encs = (args.encs || "identity,gzip,br").split(",");
const repeats = Number(args.repeats || 20);
const outPath = path.join(
  REPO_ROOT,
  "research/results/processed",
  args.out || "serialization_remedy_experiment.json"
);

// Runs inside the page. Returns timings for one complete load of the vectors,
// or ok:false with the error text when the load fails.
async function loadVectors([arm, size, enc]) {
  const base = "/research/corpus";
  const q = enc === "identity" ? "" : `&enc=${enc}`;
  let fetchMs = 0;
  let parseMs = 0;
  const get = async (url, kind) => {
    const t = performance.now();
    const res = await fetch(`${url}?r=${Math.random()}${q}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
    const body = kind === "text" ? await res.text() : await res.arrayBuffer();
    fetchMs += performance.now() - t;
    return body;
  };
  const parse = (text) => {
    const t = performance.now();
    const v = JSON.parse(text);
    parseMs += performance.now() - t;
    return v;
  };

  performance.clearResourceTimings();
  const t0 = performance.now();
  try {
    let kept;
    if (arm === "json") {
      kept = parse(await get(`${base}/vectors_${size}.json`, "text"));
      if (kept.count !== size || kept.chunks.length !== size) throw new Error("bad json payload");
    } else if (arm.startsWith("json-shard")) {
      const s = arm.slice("json-shard".length);
      const manifest = parse(await get(`${base}/vectors_${size}.shard${s}.manifest.json`, "text"));
      kept = [];
      let count = 0;
      for (const f of manifest.files) {
        const shard = parse(await get(`${base}/vectors_${size}.shard${s}/${f}`, "text"));
        count += shard.chunks.length;
        kept.push(shard);
      }
      if (count !== size) throw new Error(`bad sharded payload: ${count} docs`);
    } else if (arm === "binary") {
      const ids = parse(await get(`${base}/vectors_${size}.ids.json`, "text"));
      const buf = await get(`${base}/vectors_${size}.bin`, "binary");
      const t = performance.now();
      const floats = new Float32Array(buf);
      parseMs += performance.now() - t;
      if (floats.length !== size * 384 || ids.ids.length !== size) throw new Error("bad binary payload");
      kept = { ids, floats };
    } else {
      throw new Error(`unknown arm ${arm}`);
    }
    // Keep the result reachable so the heap reading includes it.
    window.__kept = kept;
    const wall = performance.now() - t0;
    const entries = performance.getEntriesByType("resource").filter((e) => e.name.includes("/research/corpus/"));
    return {
      ok: true,
      fetch_ms: fetchMs,
      parse_ms: parseMs,
      wall_ms: wall,
      encoded_bytes: entries.reduce((a, e) => a + e.encodedBodySize, 0),
      decoded_bytes: entries.reduce((a, e) => a + e.decodedBodySize, 0),
      requests: entries.length,
      heap_bytes: performance.memory ? performance.memory.usedJSHeapSize : null,
    };
  } catch (e) {
    return { ok: false, error: String(e && e.message ? e.message : e), wall_ms: performance.now() - t0 };
  }
}

async function main() {
  const browser = await chromium.launch({ headless: true, args: ["--enable-precise-memory-info"] });
  const results = [];

  for (const size of sizes) {
    for (const arm of arms) {
      for (const enc of encs) {
        const cell = { corpus_size: size, arm, enc, n: repeats, ok_count: 0, errors: [], fetch_raw_ms: [], parse_raw_ms: [], wall_raw_ms: [], encoded_bytes: [], decoded_bytes: [], requests: [], heap_raw_bytes: [] };
        for (let r = 0; r < repeats; r++) {
          const context = await browser.newContext();
          const page = await context.newPage();
          await page.goto(`http://localhost:${PORT}/research/harness/bench_page.html`);
          let out;
          try {
            out = await page.evaluate(loadVectors, [arm, size, enc]);
          } catch (e) {
            // A crashed renderer (out of memory) is also an outcome.
            out = { ok: false, error: `page: ${String(e.message || e).split("\n")[0]}` };
          }
          if (out.ok) {
            cell.ok_count++;
            cell.fetch_raw_ms.push(out.fetch_ms);
            cell.parse_raw_ms.push(out.parse_ms);
            cell.wall_raw_ms.push(out.wall_ms);
            cell.encoded_bytes.push(out.encoded_bytes);
            cell.decoded_bytes.push(out.decoded_bytes);
            cell.requests.push(out.requests);
            cell.heap_raw_bytes.push(out.heap_bytes);
          } else {
            cell.errors.push(out.error);
          }
          await context.close();
        }
        results.push(cell);
        const med = (xs) => (xs.length ? [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)] : NaN);
        console.log(
          `corpus_${size} ${arm.padEnd(16)} ${enc.padEnd(8)} ok ${cell.ok_count}/${repeats}` +
            (cell.ok_count
              ? `  wall p50 ${med(cell.wall_raw_ms).toFixed(1)}ms  parse p50 ${med(cell.parse_raw_ms).toFixed(1)}ms  wire ${(med(cell.encoded_bytes) / 1e6).toFixed(2)}MB`
              : `  ${cell.errors[0]}`)
        );
        // Write after every cell so a crash late in the run loses nothing.
        fs.writeFileSync(
          outPath,
          JSON.stringify(
            {
              generated: new Date().toISOString(),
              browser_version: browser.version(),
              platform: `${os.platform()} ${os.release()} ${os.arch()}, ${os.cpus()[0].model}, ${Math.round(os.totalmem() / 2 ** 30)} GiB`,
              protocol: "PREREG_serialisation_remedy.md",
              results,
            },
            null,
            2
          )
        );
      }
    }
  }

  await browser.close();
  console.log(`\nWrote ${outPath}`);
}

main();
