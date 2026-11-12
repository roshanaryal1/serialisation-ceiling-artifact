// Playwright driver for the benchmark harness (RESEARCH_PLAN.md Phase 5).
// Not runner.ts, matching instrument.js's deviation note -- no TypeScript
// toolchain in this repo.
//
// Protocol implemented (MEASUREMENT_PLAN.md, don't edit without a dated
// addendum there first):
//   - N repeats per cell (default 20), discard first as warmup, report p50/p95.
//   - Idle between runs (default 60s) -- extended to all tiers per the
//     2026-08-10 amendment, not just mobile.
//   - Cell execution order randomised, not ascending by corpus size.
//   - Cold-cache runs clear storage at 3 layers (Cache API, IndexedDB, HTTP
//     disk cache) and get a fresh isolated browser context per repeat.
//   - Fixed network throttle profile (NETWORK_PROFILE below) on cold runs.
//   - macOS-only best-effort system state sampled before/after every run:
//     vm_stat (swap activity), pmset (battery %, AC power, Low Power Mode),
//     powermetrics (CPU frequency, only if passwordless sudo is set up --
//     silently null otherwise, never blocks the run on a password prompt).
//     Runs below 30% battery and not on AC should be treated as discarded
//     per protocol -- this script records the state but does NOT auto-skip
//     the run, so you can decide at analysis time; check
//     system_state_before.power in each raw file before trusting a run.
//   - Every run writes one JSON file to results/raw/.
//
// NOT YET WIRED UP: the desktop failure threshold N (p50 vs 10k baseline,
// MEASUREMENT_PLAN.md's "Open before Phase 5 harness build" item) -- this
// script only collects raw timing data, it doesn't classify cells as
// pass/fail. N is applied at analysis time (Phase 8), once decided (Phase 6
// gate, EXECUTION_PLAN.md Step 2).
//
// Usage (real measurement run, default protocol):
//   node runner.js --sizes 1000,10000,100000 --threads 4,8 --cache cold,warm
//
// Usage (fast smoke test, NOT a measurement run -- see --smoke-test):
//   node runner.js --smoke-test

import { chromium, firefox, webkit } from "playwright";
import { spawn, execSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import crypto from "node:crypto";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../..");
const RAW_DIR = path.join(__dirname, "../results/raw");
const PORT = 8743;

// Fixed network profile for cold-start runs, applied via CDP
// Network.emulateNetworkConditions. Chosen to approximate a mid-tier mobile
// connection (the plan's device matrix includes a mid-tier Android and
// iPhone alongside desktop) -- roughly a "Fast 3G/slow 4G" profile, same
// numbers Chrome DevTools ships as a built-in throttling preset, chosen for
// exactly that reason: independently reproducible, not invented here.
const NETWORK_PROFILE = {
  name: "Fast 3G (Chrome DevTools preset numbers)",
  downloadMbps: 1.6,
  uploadMbps: 0.75,
  latencyMs: 150,
};

const QUERY_SAMPLE = fs
  .readFileSync(path.join(__dirname, "../queries/queries.jsonl"), "utf-8")
  .trim()
  .split("\n")
  .slice(0, 10)
  .map((line) => JSON.parse(line).text);

function parseArgs() {
  const args = Object.fromEntries(
    process.argv.slice(2).map((a) => {
      const [k, v] = a.replace(/^--/, "").split("=");
      return [k, v === undefined ? true : v];
    })
  );
  const smoke = !!args["smoke-test"];
  return {
    sizes: (args.sizes || (smoke ? "1000" : "1000,10000,100000")).split(",").map(Number),
    threads: (args.threads || (smoke ? "4" : "4,8")).split(",").map(Number),
    cacheStates: (args.cache || (smoke ? "cold" : "cold,warm")).split(","),
    repeats: Number(args.repeats || (smoke ? 2 : 20)),
    idleSeconds: Number(args["idle-seconds"] ?? (smoke ? 0 : 60)),
    powermetrics: !!args.powermetrics,
    noThrottle: !!args["no-throttle"],
    // Playwright's bundled builds, NOT the machine's installed browsers.
    // Note webkit is the upstream WebKit engine, not Safari -- results from it
    // must never be labelled "Safari" (PROVENANCE.md).
    browser: args.browser || "chromium",
    // MEASUREMENT_PLAN.md ADDENDUM 1. Default "shipped" (Mode A): it is the
    // app-faithful path and the one the full N=20 protocol applies to.
    // Mode B ("build") must be run with reduced repeats -- see the addendum.
    modes: (args.mode || "shipped").split(","),
    smoke,
  };
}

function shuffle(arr, seed) {
  // Same mulberry32 PRNG used across the rest of research/ for consistency.
  let state = seed >>> 0;
  const rng = () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t = (t + Math.imul(t ^ (t >>> 7), t | 61)) | 0;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const out = [...arr];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function commitSha() {
  try {
    return execSync("git rev-parse HEAD", { cwd: REPO_ROOT }).toString().trim();
  } catch {
    return "unknown";
  }
}

// macOS-only, best-effort system state -- MEASUREMENT_PLAN.md amendments
// for the desktop tier: "Log swap via vm_stat sampled around each run,"
// "mains power connected, Low Power Mode off, for every run. Record it,"
// "log CPU package temperature and clock where obtainable (powermetrics
// requires sudo; if unavailable, log wall-clock run index and check for
// monotonic drift)." Every field here is either a real parsed value or
// `null` -- never a guess -- so a run on non-macOS or without sudo still
// produces valid (if partially null) provenance rather than crashing.
function parseVmStat() {
  // NOTE: vm_stat's counters are cumulative since boot, not per-run deltas.
  // A raw file's system_state_before/system_state_after.vm_stat values are
  // both large cumulative totals -- swap activity DURING this specific run
  // is (after.swapouts_bytes - before.swapouts_bytes), computed at analysis
  // time, never the raw number itself. Documented here so it isn't misread
  // as "this run swapped out 2TB."
  try {
    const out = execSync("vm_stat").toString();
    const pageSizeMatch = out.match(/page size of (\d+) bytes/);
    const pageSize = pageSizeMatch ? Number(pageSizeMatch[1]) : 4096;
    const grab = (label) => {
      const m = out.match(new RegExp(label + ":\\s+(\\d+)"));
      return m ? Number(m[1]) * pageSize : null;
    };
    return {
      pageouts_bytes: grab("Pageouts"),
      swapins_bytes: grab("Swapins"),
      swapouts_bytes: grab("Swapouts"),
      pages_free_bytes: grab("Pages free"),
    };
  } catch {
    return null; // not macOS, or vm_stat unavailable
  }
}

function parsePmset() {
  try {
    const out = execSync("pmset -g batt").toString();
    const percentMatch = out.match(/(\d+)%/);
    const onACPower = /'AC Power'/.test(out);
    const lowPowerMatch = execSync("pmset -g | grep lowpowermode").toString();
    const lowPowerMode = /lowpowermode\s+1/.test(lowPowerMatch);
    return {
      battery_percent: percentMatch ? Number(percentMatch[1]) : null,
      on_ac_power: onACPower,
      low_power_mode: lowPowerMode,
    };
  } catch {
    return null; // not macOS, or pmset unavailable (e.g. desktop w/o battery)
  }
}

function tryPowermetrics(enabled) {
  // Off by default -- a `sudo` invocation with no cached credential can pop
  // a macOS GUI auth prompt that blocks indefinitely, which execSync's
  // `timeout` does NOT reliably kill (confirmed: it hung the harness past
  // the smoke test's own 60s outer timeout and crashed the browser). Only
  // call this if the operator has set up passwordless sudo for exactly this
  // command (`sudo visudo` entry for `powermetrics`) AND passes
  // --powermetrics explicitly. Falls back to null on any failure either way.
  if (!enabled) return null;
  try {
    const out = execSync("sudo -n powermetrics -n 1 -i 200 --samplers cpu_power 2>/dev/null", {
      timeout: 3000,
    }).toString();
    const freqMatch = out.match(/CPU die frequency\s*:\s*([\d.]+)/);
    return freqMatch ? { cpu_die_frequency_mhz: Number(freqMatch[1]) } : null;
  } catch {
    return null; // sudo -n fails immediately (no prompt) if no cached/passwordless credential
  }
}

function sampleSystemState(opts) {
  return {
    hostname: os.hostname(),
    platform: os.platform(),
    release: os.release(),
    arch: os.arch(),
    vm_stat: parseVmStat(),
    power: parsePmset(),
    powermetrics: tryPowermetrics(opts && opts.powermetrics),
    sampled_at: new Date().toISOString(),
  };
}

async function runCell(browser, warmContext, cell, repeatIndex, isWarmup, opts) {
  // Cold vs warm needs different browser-context handling, not just the
  // in-page Cache API/IndexedDB clear in instrument.js:
  //   - COLD: a brand-new isolated context per repeat (so Cache
  //     API/IndexedDB genuinely start empty, not just cleared-but-with-a-
  //     warm HTTP disk cache left over from a previous page load in the
  //     same context) PLUS the regular browser HTTP cache disabled via CDP.
  //     Found by inspecting the smoke test's suspiciously low
  //     model_transfer_bytes on a nominally "cold" run -- see
  //     PHASE5_STATUS.md item 3. HTTP cache is a THIRD cache layer beyond
  //     Cache API and IndexedDB, and MEASUREMENT_PLAN.md's protocol
  //     explicitly requires clearing it too, which instrument.js alone
  //     cannot do from inside the page.
  //   - WARM: one shared, long-lived context reused across every warm-cell
  //     repeat, so Cache API/model weights genuinely persist between
  //     visits, matching what "warm" is supposed to represent.
  let context;
  let ownContext = false;
  if (cell.cacheState === "cold") {
    context = await browser.newContext();
    ownContext = true;
  } else {
    context = warmContext;
  }

  const page = await context.newPage();

  // CDP is Chromium-only. On Firefox/WebKit the HTTP-disk-cache disable and
  // the network throttle are simply unavailable -- Playwright exposes no
  // cross-browser equivalent. Rather than silently producing weaker cold-cache
  // isolation and calling it the same thing, record what was actually applied
  // in every raw file (`cache_isolation` / `network_profile`) so analysis can
  // tell the two apart, and note the limitation in the paper.
  const isChromium = opts.browser === "chromium";
  let cdp = null;
  if (isChromium) {
    cdp = await context.newCDPSession(page);
    if (cell.cacheState === "cold") {
      await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
    }
  }

  // Fixed network throttle profile for cold-start runs, so model-transfer
  // time is comparable across devices/runs (MEASUREMENT_PLAN.md protocol:
  // "Network throttled to a fixed profile for cold-start runs... Record the
  // profile."). Warm runs are unthrottled -- the point of "warm" is to
  // measure with the model already local, not to re-measure network cost.
  // Skipped during --smoke-test (at Fast-3G the ~24MB model download alone
  // takes ~2 min, defeating a quick functional check) and under
  // --no-throttle.
  //
  // Why --no-throttle exists: throttled cold-start time is dominated by, and
  // very nearly linear in, transfer bytes -- measured 1k cold at 172s for
  // ~32MB, consistent with the 1.6 Mbps profile. Extrapolating, a 100k Mode A
  // cold cell moves ~794MB, i.e. ~66 min per repeat and ~22 hr for the cell,
  // which buys nothing: transfer time at a fixed bandwidth is derivable from
  // the transfer bytes this harness already records exactly. The parts of
  // cold start that are NOT network-bound and NOT analytically predictable --
  // JSON parse, index construction, peak heap -- are what large corpus sizes
  // are actually being run to measure. So: throttle at small sizes where it
  // is cheap and real, run large sizes unthrottled, and derive their transfer
  // time from bytes. The deviation and the derivation are recorded in
  // MEASUREMENT_PLAN.md ADDENDUM 2.
  const networkProfile =
    cell.cacheState === "cold" && !opts.smoke && !opts.noThrottle && isChromium
      ? NETWORK_PROFILE
      : null;
  if (networkProfile) {
    await cdp.send("Network.emulateNetworkConditions", {
      offline: false,
      downloadThroughput: (networkProfile.downloadMbps * 1_000_000) / 8,
      uploadThroughput: (networkProfile.uploadMbps * 1_000_000) / 8,
      latency: networkProfile.latencyMs,
    });
  }

  const systemStateBefore = sampleSystemState(opts);

  await page.goto(`http://localhost:${PORT}/research/harness/bench_page.html`);
  await page.waitForFunction(() => window.runBenchCell !== undefined);

  const corpusUrl = `/research/corpus/corpus_${cell.size}.jsonl`;
  const vectorsUrl = `/research/corpus/vectors_${cell.size}.json`;
  const result = await page.evaluate(
    ([corpusUrl, vectorsUrl, queries, threads, clearFirst, mode]) =>
      window.runBenchCell({
        corpusUrl,
        vectorsUrl,
        queries,
        threads,
        clearStorageFirst: clearFirst,
        mode,
      }),
    [corpusUrl, vectorsUrl, QUERY_SAMPLE, cell.threads, cell.cacheState === "cold", cell.mode]
  );

  const systemStateAfter = sampleSystemState(opts);

  await page.close();
  if (ownContext) await context.close();

  return {
    ...result,
    cell: {
      corpus_size: cell.size,
      threads: cell.threads,
      cache_state: cell.cacheState,
      mode: cell.mode,
    },
    repeat_index: repeatIndex,
    is_warmup: isWarmup,
    commit_sha: commitSha(),
    run_id: crypto.randomUUID(),
    browser: opts.browser,
    // Cold-cache isolation is genuinely weaker outside Chromium; record which
    // layers were actually cleared rather than implying parity.
    cache_isolation:
      cell.cacheState === "cold"
        ? (isChromium
            ? "cacheAPI+indexedDB+httpDiskCache+freshContext"
            : "cacheAPI+indexedDB+freshContext (no CDP: HTTP disk cache NOT disabled)")
        : "warm (shared context, caches retained)",
    network_profile: networkProfile,
    system_state_before: systemStateBefore,
    system_state_after: systemStateAfter,
  };
}

async function main() {
  const opts = parseArgs();
  fs.mkdirSync(RAW_DIR, { recursive: true });

  console.log(`Config: sizes=${opts.sizes} threads=${opts.threads} cache=${opts.cacheStates} ` +
    `repeats=${opts.repeats} idle=${opts.idleSeconds}s ${opts.smoke ? "(SMOKE TEST, not a measurement run)" : ""}`);

  const serverProc = spawn("node", ["server.js"], { cwd: __dirname, stdio: "inherit" });
  await sleep(500);

  let cells = [];
  for (const mode of opts.modes) {
    for (const size of opts.sizes) {
      for (const threads of opts.threads) {
        for (const cacheState of opts.cacheStates) {
          cells.push({ size, threads, cacheState, mode });
        }
      }
    }
  }
  // Preflight: Mode A cannot run without its precomputed vectors artifact.
  // Fail loudly here rather than letting the page 404 and record a run whose
  // numbers look plausible but measure nothing.
  const missing = cells
    .filter((c) => c.mode === "shipped")
    .map((c) => path.join(__dirname, `../corpus/vectors_${c.size}.json`))
    .filter((p, i, arr) => arr.indexOf(p) === i && !fs.existsSync(p));
  if (missing.length) {
    console.error("Missing Mode A vectors:\n  " + missing.join("\n  "));
    console.error("Generate with: node research/corpus/precompute_vectors.mjs --sizes <sizes>");
    serverProc.kill();
    process.exit(1);
  }

  // Randomised cell order -- MEASUREMENT_PLAN.md amendment: ascending order
  // by corpus size confounds thermal drift with a scaling effect.
  cells = shuffle(cells, 42);

  const engines = { chromium, firefox, webkit };
  const engine = engines[opts.browser];
  if (!engine) {
    console.error(`Unknown --browser=${opts.browser}. Use chromium, firefox, or webkit.`);
    serverProc.kill();
    process.exit(1);
  }
  const browser = await engine.launch();
  console.log(`Browser: ${opts.browser} ${browser.version()}`);
  // One shared context for ALL warm-cache cells/repeats, so Cache API /
  // IndexedDB genuinely accumulate across visits -- see runCell's comment.
  const warmContext = await browser.newContext();
  let written = 0;

  try {
    for (const cell of cells) {
      console.log(`Cell: mode=${cell.mode} corpus=${cell.size} threads=${cell.threads} cache=${cell.cacheState}`);
      for (let r = 0; r < opts.repeats; r++) {
        const isWarmup = r === 0;
        const result = await runCell(browser, warmContext, cell, r, isWarmup, opts);
        const fname = `run_${opts.browser}_${cell.mode}_${cell.size}_t${cell.threads}_${cell.cacheState}_r${r}_${Date.now()}.json`;
        fs.writeFileSync(path.join(RAW_DIR, fname), JSON.stringify(result, null, 2));
        written++;
        console.log(`  repeat ${r}${isWarmup ? " (warmup, discarded from p50/p95)" : ""}: ` +
          `cold_start_total=${result.timings_ms.cold_start_total.toFixed(1)}ms`);
        if (opts.idleSeconds > 0) await sleep(opts.idleSeconds * 1000);
      }
    }
  } finally {
    await warmContext.close();
    await browser.close();
    serverProc.kill();
  }

  console.log(`\nWrote ${written} raw run files to ${RAW_DIR}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
