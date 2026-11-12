// Locate the exact corpus size at which the Mode A ("shipped vectors")
// deployment stops working in the browser.
//
// FINDING_json_string_ceiling.md derives an estimate of ~66,400 documents from
// two measurements (V8's 536,870,888-character string limit, and 8,081 bytes
// per document). This script finds the ACTUAL boundary by bisection, because
// the derived figure is an estimate: per-document serialised size varies with
// the decimal expansion of the float values, so the true ceiling will not land
// exactly on the arithmetic.
//
// Method: binary search over corpus size. At each probe, generate the vectors
// artifact if absent, then attempt a real browser fetch + JSON.parse. Success
// and failure are both recorded with the exact error text.
//
// Usage (from research/harness):
//   node find_ceiling.js --lo=10000 --hi=100000
//   node find_ceiling.js --lo=60000 --hi=70000 --tolerance=1000

import { chromium, firefox, webkit } from "playwright";
import { spawn, execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../..");
const CORPUS_DIR = path.join(__dirname, "../corpus");
const PORT = 8745;
const ENGINES = { chromium, firefox, webkit };

function parseArgs() {
  const a = Object.fromEntries(
    process.argv.slice(2).map((x) => {
      const [k, v] = x.replace(/^--/, "").split("=");
      return [k, v === undefined ? true : v];
    })
  );
  return {
    lo: Number(a.lo || 10000),
    hi: Number(a.hi || 100000),
    tolerance: Number(a.tolerance || 5000),
    browser: String(a.browser || "chromium"),
    singleProbe: a["single-probe"] !== undefined ? Number(a["single-probe"]) : null,
  };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function ensureCorpus(size) {
  const corpus = path.join(CORPUS_DIR, `corpus_${size}.jsonl`);
  if (!fs.existsSync(corpus)) {
    console.log(`  generating corpus_${size}.jsonl ...`);
    execFileSync("python3", [path.join(CORPUS_DIR, "generate_corpus.py"),
                              "--sizes", String(size), "--seed", "42"],
                  { stdio: "inherit" });
  }
  const vectors = path.join(CORPUS_DIR, `vectors_${size}.json`);
  if (!fs.existsSync(vectors)) {
    // Vectors cost ~8,081 bytes/document. Refuse rather than fill the disk
    // part-way through an unattended run and leave a half-written artifact
    // that would look like a genuine parse failure.
    const needBytes = size * 8081 * 1.15; // 15% headroom
    const free = Number(
      execFileSync("df", ["-k", CORPUS_DIR]).toString().trim().split("\n")[1].split(/\s+/)[3]
    ) * 1024;
    if (free < needBytes) {
      throw new Error(
        `Refusing to generate vectors_${size}.json: needs ~${(needBytes / 1e9).toFixed(1)}GB, ` +
        `only ${(free / 1e9).toFixed(1)}GB free. Free space or narrow the bisection range.`
      );
    }
    console.log(`  generating vectors_${size}.json (this takes a few minutes) ...`);
    execFileSync("node", [path.join(CORPUS_DIR, "precompute_vectors.mjs"),
                           "--sizes", String(size)],
                  { stdio: "inherit" });
  }
  return fs.statSync(vectors).size;
}

// Intermediate probe artifacts are deleted after use. Each vectors file at
// these sizes is 400-800MB and the machine has under 10GB free, so keeping
// every probe would risk filling the disk part-way through an unattended
// overnight run. They are regenerable from a recorded seed and their sizes are
// captured in the probe record before deletion, so nothing measured is lost.
const KEEP_SIZES = new Set([1000, 10000, 100000]);

function cleanupProbeArtifacts(size) {
  if (KEEP_SIZES.has(size)) return;
  for (const f of [`vectors_${size}.json`, `corpus_${size}.jsonl`]) {
    const p = path.join(CORPUS_DIR, f);
    if (fs.existsSync(p)) {
      fs.unlinkSync(p);
    }
  }
}

async function probe(browser, size) {
  const bytes = ensureCorpus(size);
  const page = await browser.newPage();
  try {
    await page.goto(`http://localhost:${PORT}/research/harness/bench_page.html`);
    await page.waitForFunction(() => window.runQualityEval !== undefined);
    // Only the fetch + parse + index construction is under test here, not
    // retrieval quality -- this is the step that throws at the ceiling.
    const result = await page.evaluate(async (url) => {
      try {
        const res = await fetch(url);
        const text = await res.text();
        const parsed = JSON.parse(text);
        return { ok: true, count: parsed.count, chars: text.length };
      } catch (e) {
        return { ok: false, error: `${e.name}: ${e.message}` };
      }
    }, `/research/corpus/vectors_${size}.json`);
    return { size, bytes, ...result };
  } catch (e) {
    // A crashed tab / OOM kill also counts as a failure at this size.
    return { size, bytes, ok: false, error: `harness: ${e.message}` };
  } finally {
    await page.close().catch(() => {});
    cleanupProbeArtifacts(size);
  }
}

async function main() {
  const { lo: loArg, hi: hiArg, tolerance, browser: engineName, singleProbe } = parseArgs();
  const launcher = ENGINES[engineName];
  if (!launcher) throw new Error(`unknown --browser=${engineName}, expected one of ${Object.keys(ENGINES).join(", ")}`);
  const OUT = path.join(__dirname, `../results/ceiling_probe_${engineName}.json`);

  const serverProc = spawn("node", ["server.js"], {
    cwd: __dirname,
    stdio: "ignore",
    env: { ...process.env, BENCH_PORT: String(PORT) },
  });
  await sleep(600);
  const browser = await launcher.launch();

  // Single-probe mode: confirm one size still works, without bisecting to an
  // exact boundary. Used when the predicted ceiling is too large to bisect
  // within available disk (Section 5.1's WebKit result): one probe near the
  // predicted floor is enough to show the ceiling is at least that high,
  // honestly reported as a floor rather than a located boundary.
  if (singleProbe !== null) {
    try {
      console.log(`Single-probe mode (${engineName}): checking ${singleProbe} ...`);
      const r = await probe(browser, singleProbe);
      console.log(`  ${singleProbe}: ${r.ok ? "OK" : "FAILED -- " + r.error}`);
      fs.mkdirSync(path.dirname(OUT), { recursive: true });
      fs.writeFileSync(
        OUT,
        JSON.stringify({ generated: new Date().toISOString(), engine: engineName, mode: "single-probe", probe: r }, null, 2)
      );
      console.log(`Wrote ${path.relative(REPO_ROOT, OUT)}`);
    } finally {
      await browser.close();
      serverProc.kill();
    }
    return;
  }

  const probes = [];
  let lo = loArg; // known-good (or assumed good, verified below)
  let hi = hiArg; // known-bad (or assumed bad, verified below)

  try {
    console.log(`Verifying bounds (${engineName}): ${lo} should succeed, ${hi} should fail`);
    const loRes = await probe(browser, lo);
    probes.push(loRes);
    console.log(`  ${lo}: ${loRes.ok ? "OK" : "FAILED -- " + loRes.error}`);
    if (!loRes.ok) {
      console.error(`Lower bound ${lo} already fails; rerun with a smaller --lo.`);
      return;
    }

    const hiRes = await probe(browser, hi);
    probes.push(hiRes);
    console.log(`  ${hi}: ${hiRes.ok ? "OK" : "FAILED -- " + hiRes.error}`);
    if (hiRes.ok) {
      console.log(`Upper bound ${hi} succeeds -- no ceiling in [${lo}, ${hi}].`);
      fs.writeFileSync(OUT, JSON.stringify({ engine: engineName, probes, ceiling: null }, null, 2));
      return;
    }

    while (hi - lo > tolerance) {
      const mid = Math.round((lo + hi) / 2 / 1000) * 1000; // probe on 1k boundaries
      if (mid === lo || mid === hi) break;
      console.log(`Probing ${mid} (bracket ${lo}-${hi}) ...`);
      const r = await probe(browser, mid);
      probes.push(r);
      console.log(`  ${mid}: ${r.ok ? "OK" : "FAILED -- " + r.error}`);
      if (r.ok) lo = mid;
      else hi = mid;
    }

    const summary = {
      generated: new Date().toISOString(),
      engine: engineName,
      largest_working: lo,
      smallest_failing: hi,
      tolerance,
      note: "Ceiling lies between largest_working and smallest_failing.",
      probes,
    };
    fs.mkdirSync(path.dirname(OUT), { recursive: true });
    fs.writeFileSync(OUT, JSON.stringify(summary, null, 2));
    console.log(`\nCeiling is between ${lo} (works) and ${hi} (fails).`);
    console.log(`Wrote ${path.relative(REPO_ROOT, OUT)}`);
  } finally {
    await browser.close();
    serverProc.kill();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
