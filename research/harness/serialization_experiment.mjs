// Serialization-intervention experiment (section 6.1/6.6 addendum).
//
// Matches the main protocol's N=20 (bumped from an initial N=10 reduced
// check after review flagged n=10 as the weakest evidentiary spot backing
// the paper's headline 5.19x/7.4-7.5x claim). Compares artifact fetch+parse
// cost across three formats, same corpus, same browser:
//   - json:        the deployed format, float32 embeddings as JSON text
//   - binary:      Float32Array over ArrayBuffer, isolates text-serialisation
//                   overhead alone (same precision as json)
//   - binary-int8: Int8Array over ArrayBuffer, packed post-hoc quantised
//                   vectors (see quantize_vectors_int8.mjs); isolates the
//                   separate question of storage precision, not serialisation
//                   format. Representation fidelity (cosine error against the
//                   float32 original) is reported by quantize_vectors_int8.mjs,
//                   not here -- this script measures fetch+parse cost only.
//
// Requires: harness server already running on PORT (node server.js), and
// convert_to_binary.mjs / quantize_vectors_int8.mjs already run for the sizes
// tested.
//
// Usage: node serialization_experiment.mjs --sizes=1000,10000 --repeats=10

import { chromium } from "playwright";
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
const sizes = (args.sizes || "1000,10000").split(",").map(Number);
const repeats = Number(args.repeats || 20);

function pct(values, p) {
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length));
  return sorted[idx];
}

// Non-parametric bootstrap CI on the median, not a normal-approximation CI:
// n=20 fetch/parse timings are not expected to be normally distributed.
function bootstrapMedianCI(values, iterations = 2000, alpha = 0.05) {
  const medians = [];
  for (let i = 0; i < iterations; i++) {
    const sample = [];
    for (let j = 0; j < values.length; j++) {
      sample.push(values[Math.floor(Math.random() * values.length)]);
    }
    medians.push(pct(sample, 50));
  }
  medians.sort((a, b) => a - b);
  const lo = medians[Math.floor((alpha / 2) * iterations)];
  const hi = medians[Math.floor((1 - alpha / 2) * iterations)];
  return [lo, hi];
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const results = [];

  for (const size of sizes) {
    const binPath = path.join(REPO_ROOT, "research/corpus", `vectors_${size}.bin`);
    if (!fs.existsSync(binPath)) {
      console.log(`SKIP corpus_${size}: run convert_to_binary.mjs first`);
      continue;
    }
    const int8Path = path.join(REPO_ROOT, "research/corpus", `vectors_${size}.int8.bin`);
    const formats = ["json", "binary"];
    if (fs.existsSync(int8Path)) formats.push("binary-int8");
    else console.log(`  (skipping binary-int8 for corpus_${size}: run quantize_vectors_int8.mjs first)`);

    for (const format of formats) {
      const fetchMs = [];
      const parseMs = [];
      for (let r = 0; r < repeats; r++) {
        const context = await browser.newContext();
        const page = await context.newPage();
        await page.goto(`http://localhost:${PORT}/research/harness/bench_page.html`);

        const result = await page.evaluate(
          async ([format, size]) => {
            const t0 = performance.now();
            let t1, t2;
            if (format === "json") {
              const res = await fetch(`/research/corpus/vectors_${size}.json?r=${Math.random()}`, { cache: "no-store" });
              const text = await res.text();
              t1 = performance.now();
              const parsed = JSON.parse(text);
              t2 = performance.now();
              if (parsed.count !== size) throw new Error("bad json payload");
            } else if (format === "binary") {
              const res = await fetch(`/research/corpus/vectors_${size}.bin?r=${Math.random()}`, { cache: "no-store" });
              const buf = await res.arrayBuffer();
              t1 = performance.now();
              const floats = new Float32Array(buf);
              t2 = performance.now();
              if (floats.length !== size * 384) throw new Error("bad binary payload");
            } else {
              const res = await fetch(`/research/corpus/vectors_${size}.int8.bin?r=${Math.random()}`, { cache: "no-store" });
              const buf = await res.arrayBuffer();
              t1 = performance.now();
              const ints = new Int8Array(buf);
              t2 = performance.now();
              if (ints.length !== size * 384) throw new Error("bad int8 payload");
            }
            return { fetch_ms: t1 - t0, parse_ms: t2 - t1 };
          },
          [format, size]
        );
        fetchMs.push(result.fetch_ms);
        parseMs.push(result.parse_ms);
        await context.close();
      }

      const fetchCI = bootstrapMedianCI(fetchMs);
      results.push({
        corpus_size: size,
        format,
        n: repeats,
        fetch_p50_ms: pct(fetchMs, 50),
        fetch_p95_ms: pct(fetchMs, 95),
        fetch_median_ci95: fetchCI,
        fetch_raw_ms: fetchMs,
        parse_p50_ms: pct(parseMs, 50),
        parse_p95_ms: pct(parseMs, 95),
        parse_raw_ms: parseMs,
      });
      console.log(
        `corpus_${size} ${format}: fetch p50=${pct(fetchMs, 50).toFixed(1)}ms ` +
          `[${fetchCI[0].toFixed(1)}, ${fetchCI[1].toFixed(1)}] parse p50=${pct(parseMs, 50).toFixed(1)}ms ` +
          `(total p50=${(pct(fetchMs, 50) + pct(parseMs, 50)).toFixed(1)}ms)`
      );
    }
  }

  await browser.close();

  const outPath = path.join(REPO_ROOT, "research/results/processed/serialization_experiment.json");
  fs.writeFileSync(outPath, JSON.stringify({ generated: new Date().toISOString(), results }, null, 2));
  console.log(`\nWrote ${outPath}`);
}

main();
