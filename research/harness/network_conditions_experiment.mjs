// Measured transfer under throttled network conditions.
// Pre-registered in research/results/PREREG_network_conditions.md.
//
// Same loading code as serialization_remedy_experiment.mjs (JSON and binary
// float32 plus id sidecar, identity or brotli), with the network throttled
// through the DevTools protocol so that transfer, not loopback, dominates.
//
// Requires: node server.js running on PORT, compress_artifacts.mjs already run.
// Usage: node network_conditions_experiment.mjs --size=1000 --repeats=5

import { chromium } from "playwright-core";
import path from "node:path";
import fs from "node:fs";
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
const size = Number(args.size || 1000);
const repeats = Number(args.repeats || 5);

// Named by rate only; the paper's existing profile is the first.
const PROFILES = [
  { mbps: 1.6, rtt: 150 },
  { mbps: 4, rtt: 70 },
  { mbps: 10, rtt: 40 },
  { mbps: 25, rtt: 20 },
];
const CELLS = [
  ["json", "identity"],
  ["json", "br"],
  ["binary", "identity"],
  ["binary", "br"],
];

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
  if (arm === "json") {
    const v = parse(await get(`${base}/vectors_${size}.json`, "text"));
    if (v.chunks.length !== size) throw new Error("bad json payload");
  } else {
    const ids = parse(await get(`${base}/vectors_${size}.ids.json`, "text"));
    const buf = await get(`${base}/vectors_${size}.bin`, "binary");
    const floats = new Float32Array(buf);
    if (floats.length !== size * 384 || ids.ids.length !== size) throw new Error("bad binary payload");
  }
  const wall = performance.now() - t0;
  const entries = performance.getEntriesByType("resource").filter((e) => e.name.includes("/research/corpus/"));
  return {
    fetch_ms: fetchMs,
    parse_ms: parseMs,
    wall_ms: wall,
    wire_bytes: entries.reduce((a, e) => a + e.encodedBodySize, 0),
  };
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  for (const prof of PROFILES) {
    for (const [arm, enc] of CELLS) {
      const cell = { profile: prof, corpus_size: size, arm, enc, n: repeats, wire_bytes: [], fetch_raw_ms: [], parse_raw_ms: [], wall_raw_ms: [] };
      for (let r = 0; r < repeats; r++) {
        const context = await browser.newContext();
        const page = await context.newPage();
        await page.goto(`http://localhost:${PORT}/research/harness/bench_page.html`);
        const cdp = await context.newCDPSession(page);
        await cdp.send("Network.enable");
        await cdp.send("Network.emulateNetworkConditions", {
          offline: false,
          latency: prof.rtt,
          downloadThroughput: (prof.mbps * 1e6) / 8,
          uploadThroughput: (prof.mbps * 1e6) / 8,
        });
        const out = await page.evaluate(loadVectors, [arm, size, enc]);
        cell.wire_bytes.push(out.wire_bytes);
        cell.fetch_raw_ms.push(out.fetch_ms);
        cell.parse_raw_ms.push(out.parse_ms);
        cell.wall_raw_ms.push(out.wall_ms);
        await context.close();
      }
      results.push(cell);
      const med = (xs) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)];
      console.log(`${prof.mbps} Mbps ${arm.padEnd(6)} ${enc.padEnd(8)} wall p50 ${(med(cell.wall_raw_ms) / 1000).toFixed(2)} s  wire ${(med(cell.wire_bytes) / 1e6).toFixed(2)} MB`);
      fs.writeFileSync(
        path.join(REPO_ROOT, "research/results/processed/network_conditions_experiment.json"),
        JSON.stringify({ generated: new Date().toISOString(), browser_version: browser.version(), protocol: "PREREG_network_conditions.md", results }, null, 2)
      );
    }
  }
  await browser.close();
}

main();
