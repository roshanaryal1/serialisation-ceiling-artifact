// On-page controls for devices runner.js can't automate directly (iOS
// Safari, or Android without adb set up). Runs the same protocol as
// runner.js (N repeats, discard first as warmup, idle between repeats) but
// driven by a human tapping a button on the device itself, since there's no
// Playwright/CDP session available on a phone's own Safari/Chrome.
//
// NOT covered here (device-side scripting can't reach these): the 3-layer
// cold-cache isolation runner.js does via fresh BrowserContext + CDP
// Network.setCacheDisabled, and CDP-based network throttling. This mode
// clears Cache API + IndexedDB in-page (same as instrument.js does for the
// automated path) but cannot disable the browser's own HTTP disk cache from
// inside a normal page. State this limitation in the paper's methodology if
// manual-mode data is used for any cold-start figure.

import { clearAllStorage } from "./instrument.js";

const QUERY_SAMPLE_URL = "/research/queries/queries.jsonl";

async function loadQuerySample() {
  const res = await fetch(QUERY_SAMPLE_URL);
  const text = await res.text();
  return text.trim().split("\n").slice(0, 10).map((l) => JSON.parse(l).text);
}

function log(msg) {
  const el = document.getElementById("m-log");
  el.textContent += msg + "\n";
  el.scrollTop = el.scrollHeight;
}

function percentile(arr, p) {
  const sorted = [...arr].sort((a, b) => a - b);
  const idx = Math.min(Math.floor(p * sorted.length), sorted.length - 1);
  return sorted[idx];
}

let lastRunResults = null;

async function runManual() {
  const deviceLabel = document.getElementById("m-device").value.trim();
  if (!deviceLabel) {
    alert("Enter a device label first (e.g. redmi-note-11).\n\n" +
          "Without it this run would be pooled with the desktop results in " +
          "analysis, averaging a phone and a laptop into one cell.");
    return;
  }
  const mode = document.getElementById("m-mode").value;
  const size = document.getElementById("m-size").value;
  const cacheState = document.getElementById("m-cache").value;
  const threads = Number(document.getElementById("m-threads").value);
  const repeats = Number(document.getElementById("m-repeats").value);
  const idleSeconds = Number(document.getElementById("m-idle").value);

  document.getElementById("m-run").disabled = true;
  document.getElementById("m-log").textContent = "";
  log(`Starting: mode=${mode} corpus=${size} cache=${cacheState} threads=${threads} repeats=${repeats} idle=${idleSeconds}s`);
  log(`device: ${navigator.userAgent}`);
  log(`hardwareConcurrency: ${navigator.hardwareConcurrency}`);
  if (mode === "build") {
    log(`WARNING: Mode B embeds the whole corpus in-browser. On a phone this`);
    log(`can take many minutes PER REPEAT at 10k. Use 1000 or few repeats.`);
  }

  const queries = await loadQuerySample();
  const corpusUrl = `/research/corpus/corpus_${size}.jsonl`;
  const vectorsUrl = `/research/corpus/vectors_${size}.json`;
  const runs = [];

  for (let r = 0; r < repeats; r++) {
    const isWarmup = r === 0;
    const t0 = performance.now();
    const result = await window.runBenchCell({
      mode,
      corpusUrl,
      vectorsUrl,
      queries,
      threads,
      clearStorageFirst: cacheState === "cold",
    });
    const elapsed = performance.now() - t0;
    result.repeat_index = r;
    result.is_warmup = isWarmup;
    result.run_mode = "manual";
    result.device_user_agent = navigator.userAgent;
    result.device_hardware_concurrency = navigator.hardwareConcurrency;
    // navigator.deviceMemory is Chromium-only and coarsely rounded, but on a
    // phone it is the only in-page signal of RAM available; null elsewhere
    // rather than guessed.
    result.device_memory_gb = navigator.deviceMemory ?? null;
    // `browser` is the dimension analyse.py groups cells by. Without it,
    // manual on-device runs default to "chromium" and get pooled with the
    // Mac's desktop numbers, which would silently average a phone and a
    // laptop into one cell. The device label is required for that reason.
    result.browser = deviceLabel;
    result.device_label = deviceLabel;
    result.cell = {
      corpus_size: result.corpus_size,
      threads,
      cache_state: cacheState,
      mode,
    };
    // Manual runs cannot disable the HTTP disk cache (no CDP from a page), so
    // record the weaker isolation honestly rather than letting analysis treat
    // it as equivalent to an automated cold run.
    result.cache_isolation =
      cacheState === "cold"
        ? "cacheAPI+indexedDB only (manual: HTTP disk cache NOT disabled)"
        : "warm";
    result.network_profile = null; // no CDP throttling available on-device
    result.timestamp = new Date().toISOString();
    runs.push(result);
    log(`repeat ${r}${isWarmup ? " (warmup)" : ""}: cold_start_total=${result.timings_ms.cold_start_total.toFixed(1)}ms (wall ${elapsed.toFixed(0)}ms)`);
    if (idleSeconds > 0 && r < repeats - 1) {
      log(`  idling ${idleSeconds}s...`);
      await new Promise((resolve) => setTimeout(resolve, idleSeconds * 1000));
    }
  }

  const measured = runs.filter((r) => !r.is_warmup);
  const totals = measured.map((r) => r.timings_ms.cold_start_total);
  log(`\nDone. p50=${percentile(totals, 0.5).toFixed(1)}ms p95=${percentile(totals, 0.95).toFixed(1)}ms (n=${measured.length}, warmup discarded)`);

  lastRunResults = runs;
  document.getElementById("m-download").disabled = false;
  document.getElementById("m-run").disabled = false;
}

function downloadResults() {
  if (!lastRunResults) return;
  const blob = new Blob([JSON.stringify(lastRunResults, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `manual_run_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

document.getElementById("m-run").addEventListener("click", () => {
  runManual().catch((err) => log("ERROR: " + err.message));
});
document.getElementById("m-download").addEventListener("click", downloadResults);
