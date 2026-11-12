// Drives the RQ1 quality evaluation: runs the full 250-query set through the
// in-browser int8 system and writes ranked results in the same JSON shape as
// baseline/dense_top50_corpus_*.json, so analysis/compute_ir_metrics.py can
// score it against the fp32 Python baseline with no conversion.
//
// Not a latency measurement: one pass, no repeats, no idle, no throttling.
// Quality is a property of the ranking, so repeating it would only produce
// identical output (the pipeline is deterministic given fixed vectors).
//
// Usage (from research/harness):
//   node quality_run.js --size=10000                 # app-faithful batch-32 vectors
//   node quality_run.js --size=10000 --vectors-suffix=_bs1   # artifact-free batch-1
//   node quality_run.js --size=10000 --browser=firefox

import { chromium, firefox, webkit } from "playwright";
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../..");
const OUT_DIR = path.join(__dirname, "../results/processed");
const PORT = 8744; // deliberately not 8743: lets a quality run coexist with a
                   // latency run's server without a port clash

function parseArgs() {
  const args = Object.fromEntries(
    process.argv.slice(2).map((a) => {
      const [k, v] = a.replace(/^--/, "").split("=");
      return [k, v === undefined ? true : v];
    })
  );
  return {
    size: Number(args.size || 10000),
    vectorsSuffix: args["vectors-suffix"] === undefined || args["vectors-suffix"] === true
      ? ""
      : args["vectors-suffix"],
    threads: Number(args.threads || 4),
    browser: args.browser || "chromium",
    topK: Number(args["top-k"] || 50),
  };
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  const opts = parseArgs();
  const vectorsFile = `vectors_${opts.size}${opts.vectorsSuffix}.json`;
  const vectorsPath = path.join(__dirname, "../corpus", vectorsFile);
  if (!fs.existsSync(vectorsPath)) {
    console.error(`Missing ${vectorsPath}`);
    console.error(`Generate with: node research/corpus/precompute_vectors.mjs --sizes ${opts.size}` +
      (opts.vectorsSuffix === "_bs1" ? " --batch-size 1" : ""));
    process.exit(1);
  }

  const queries = fs
    .readFileSync(path.join(__dirname, "../queries/queries.jsonl"), "utf-8")
    .trim()
    .split("\n")
    .map((l) => {
      const q = JSON.parse(l);
      return { id: q.id, text: q.text };
    });

  console.log(`Quality run: ${vectorsFile}, ${queries.length} queries, ` +
    `${opts.browser}, ${opts.threads} threads, top-${opts.topK}`);

  const serverProc = spawn("node", ["server.js"], {
    cwd: __dirname,
    stdio: "inherit",
    env: { ...process.env, BENCH_PORT: String(PORT) },
  });
  await sleep(600);

  const engines = { chromium, firefox, webkit };
  const browser = await engines[opts.browser].launch();
  const page = await browser.newPage();
  page.on("pageerror", (e) => console.error("PAGE ERROR:", e.message));

  try {
    await page.goto(`http://localhost:${PORT}/research/harness/bench_page.html`);
    await page.waitForFunction(() => window.runQualityEval !== undefined);

    const t0 = Date.now();
    const result = await page.evaluate(
      ([vectorsUrl, qs, threads, topK]) =>
        window.runQualityEval({ vectorsUrl, queries: qs, threads, topK }),
      [`/research/corpus/${vectorsFile}`, queries, opts.threads, opts.topK]
    );
    const elapsed = (Date.now() - t0) / 1000;

    fs.mkdirSync(OUT_DIR, { recursive: true });

    // Two files: the rankings in baseline-compatible shape (what the metric
    // code eats), and the provenance sidecar (what the paper cites).
    const stem = `int8_${opts.browser}_${opts.size}${opts.vectorsSuffix}`;
    const rankPath = path.join(OUT_DIR, `${stem}_top${opts.topK}.json`);
    fs.writeFileSync(rankPath, JSON.stringify(result.results));

    const meta = { ...result, elapsed_seconds: elapsed, browser: opts.browser };
    delete meta.results;
    meta.commit_sha = (() => {
      try {
        return execSync("git rev-parse HEAD", { cwd: REPO_ROOT }).toString().trim();
      } catch {
        return "unknown";
      }
    })();
    meta.generated = new Date().toISOString();
    fs.writeFileSync(path.join(OUT_DIR, `${stem}_meta.json`), JSON.stringify(meta, null, 2));

    console.log(`  ${Object.keys(result.results).length} queries ranked in ${elapsed.toFixed(1)}s`);
    console.log(`  wrote ${rankPath}`);
    console.log(`\nScore it against the fp32 baseline:`);
    console.log(`  research/.venv/bin/python3 research/analysis/compute_ir_metrics.py \\`);
    console.log(`    --run research/baseline/dense_top50_corpus_${opts.size}.json \\`);
    console.log(`    --compare ${path.relative(REPO_ROOT, rankPath)}`);
  } finally {
    await browser.close();
    serverProc.kill();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
