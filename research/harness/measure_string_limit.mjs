// Measures each browser engine's maximum JS string length directly, by
// binary search on 'x'.repeat(N) inside a real page context, rather than
// relying on documentation or a single hardcoded constant. This is the first
// link in the mechanism -> prediction -> observation chain reported in
// Section 5.1: raw string limit -> (L_max / B_doc) -> predicted ceiling ->
// observed bisection ceiling, repeated per engine.
//
// Usage: node measure_string_limit.mjs --browser=chromium
//        node measure_string_limit.mjs --browser=firefox
//        node measure_string_limit.mjs --browser=webkit
//        node measure_string_limit.mjs --browser=all

import { chromium, firefox, webkit } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildEnvelope, expectedBrowser, launchRecord, finish } from "./p7/provenance.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.join(__dirname, "../results/p7");
const ENGINES = { chromium, firefox, webkit };

// Binary search for the largest N such that 'x'.repeat(N) succeeds. Starts
// from a range comfortably either side of V8's known 536,870,888, but is not
// seeded with that value, so the result for each engine is independent.
async function measureLimit(page) {
  const probe = async (n) =>
    page.evaluate((n) => {
      try {
        const s = "x".repeat(n);
        return { ok: true, len: s.length };
      } catch (e) {
        return { ok: false, error: `${e.name}: ${e.message}` };
      }
    }, n);

  let lo = 1_000_000; // known-good starting point for every engine tested
  let hi = 2 ** 31 - 1; // initial upper bound: the 32-bit signed index range
  const loRes = await probe(lo);
  if (!loRes.ok) throw new Error(`lower bound ${lo} unexpectedly failed: ${loRes.error}`);
  let hiRes = await probe(hi);
  if (hiRes.ok) {
    // Some engines (observed: WebKit) exceed the 32-bit signed range. A
    // multi-gigabyte UTF-16 string risks OOMing the harness machine for a
    // number that is already many orders of magnitude past any corpus size
    // relevant to this study (Section 5.1's ceiling is tens of thousands of
    // documents), so report a floor rather than construct it. `lo` is
    // reported as this floor; `max_length` stays a lower bound in that case.
    return { max_length: hi, first_failing: null, lower_bound_only: true };
  }

  while (hi - lo > 1) {
    const mid = lo + Math.floor((hi - lo) / 2);
    const r = await probe(mid);
    if (r.ok) lo = mid;
    else hi = mid;
  }
  return { max_length: lo, first_failing: hi };
}

export async function main({
  engines = ENGINES,
  argv = process.argv.slice(2),
  outputDir = OUT_DIR,
} = {}) {
  const envelope = buildEnvelope({ command: [...process.argv.slice(0, 2), ...argv] });
  const args = Object.fromEntries(argv.map((arg) => {
    const [key, value] = arg.replace(/^--/, "").split("=");
    return [key, value === undefined ? true : value];
  }));
  const requested = (args.browser || "all") === "all" ? Object.keys(engines) : [args.browser];
  const results = {};
  for (const name of requested) {
    const launcher = Object.hasOwn(engines, name) ? engines[name] : null;
    const launchOptions = {};
    const record = {
      expected: expectedBrowser(name),
      actual: launchRecord(null, name, launchOptions, { browserType: launcher }),
      status: "ok",
      error: null,
      measurement: null,
    };
    results[name] = record;
    let browser;
    try {
      if (!launcher) throw new Error(`unknown engine: ${name}`);
      console.log(`Measuring ${name}...`);
      browser = await launcher.launch(launchOptions);
      record.actual = launchRecord(browser, name, launchOptions);
      const page = await browser.newPage();
      record.measurement = await measureLimit(page);
      const r = record.measurement;
      console.log(`  ${name}: max string length = ${r.max_length} (${r.first_failing} first fails)`);
    } catch (error) {
      record.status = "failed";
      record.error = String(error);
      record.measurement_reason = String(error);
    } finally {
      try {
        await browser?.close();
      } catch (error) {
        record.status = "failed";
        record.error = [record.error, String(error)].filter(Boolean).join("; ");
      }
    }
  }

  const failures = Object.entries(results).filter(([, record]) => record.status === "failed");
  const result = finish(envelope, { engines: results }, {
    status: failures.length ? "failed" : "ok",
    error: failures.length ? failures.map(([name, record]) => `${name}: ${record.error}`).join("; ") : null,
  });
  const out = path.join(outputDir, `string_limit_${envelope.run_id}.json`);
  fs.mkdirSync(outputDir, { recursive: true });
  // Exclusive creation keeps even an unexpected ID collision from replacing a run.
  fs.writeFileSync(out, `${JSON.stringify(result, null, 2)}\n`, { flag: "wx" });
  console.log(`\nWrote ${out}`);
  return result;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().then((result) => {
    if (result.status !== "ok") {
      console.error(result.error);
      process.exitCode = 1;
    }
  }).catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
