// In-page timing/memory/transfer instrumentation, loaded by bench_page.html.
// Plain JS ESM, not instrument.ts as RESEARCH_PLAN.md's directory sketch
// names it -- this repo has no TypeScript toolchain (CRA app, no tsconfig),
// and adding one just for the harness risked derailing Phase 5 on tooling
// rather than measurement. Documented deviation, not a silent one.
//
// MEASUREMENT_PLAN.md's metric definitions, implemented here:
//   - Peak JS heap: performance.memory.usedJSHeapSize (Chromium only)
//   - WASM heap: WebAssembly.Memory.buffer.byteLength (best-effort -- see
//     getWasmHeapBytes; onnxruntime-web doesn't always expose its Memory
//     object, in which case this returns null, not a fabricated number)
//   - Transfer bytes: Resource Timing API, encodedBodySize

export function now() {
  return performance.now();
}

export function peakJsHeapBytes() {
  // Chromium-only, per MEASUREMENT_PLAN.md -- returns null elsewhere so the
  // caller can record "not applicable on this browser", not a wrong zero.
  return performance.memory ? performance.memory.usedJSHeapSize : null;
}

// onnxruntime-web (used internally by @xenova/transformers) does not
// consistently expose its WebAssembly.Memory instance through a public API
// across versions. This best-effort hook checks the two places it has been
// observed to live; if neither is present, returns null rather than
// guessing. This gap must be stated in the paper's limitations if it
// persists, not silently worked around.
export function getWasmHeapBytes() {
  try {
    // eslint-disable-next-line no-undef
    if (typeof ort !== "undefined" && ort.env && ort.env.wasm && ort.env.wasm.wasmMemory) {
      return ort.env.wasm.wasmMemory.buffer.byteLength;
    }
  } catch (e) {
    // fall through
  }
  return null;
}

export function transferBytesForUrlPattern(pattern) {
  const entries = performance.getEntriesByType("resource");
  let total = 0;
  let matched = 0;
  for (const e of entries) {
    if (pattern.test(e.name)) {
      total += e.encodedBodySize || 0;
      matched += 1;
    }
  }
  return { totalBytes: total, matchedResources: matched };
}

export async function clearAllStorage() {
  // Cold-cache runs: clear IndexedDB, Cache API, and confirm empty before
  // the run starts (MEASUREMENT_PLAN.md protocol: "verified before each run").
  const results = { caches: null, indexedDB: null };

  if (window.caches) {
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
    results.caches = (await caches.keys()).length; // should be 0
  }

  if (window.indexedDB && indexedDB.databases) {
    const dbs = await indexedDB.databases();
    await Promise.all(
      dbs.map(
        (db) =>
          new Promise((resolve) => {
            const req = indexedDB.deleteDatabase(db.name);
            req.onsuccess = req.onerror = req.onblocked = () => resolve();
          })
      )
    );
    results.indexedDB = (await indexedDB.databases()).length; // should be 0
  }

  return results;
}
