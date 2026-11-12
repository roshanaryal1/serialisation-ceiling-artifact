# Runbook — how to actually run the benchmark

For Phase 6 (pilot) and Phase 7 (full matrix). Two execution modes exist,
matched to what each device can support.

| Device | Mode | Why |
|---|---|---|
| Mac (desktop Chrome) | Automated (`runner.js`) | Playwright drives real Chromium directly. |
| Android (Chrome) | Automated if adb set up, else manual | Playwright supports real Android over adb; manual mode is the no-setup fallback. |
| iPhone (Safari) | Manual only | Playwright has no real-Safari automation (WebKit ≠ Mobile Safari). The plan's own protocol says "remote inspection via the Mac" for iPhone, meaning visual/manual by design. |

---

## Prerequisites (once)

```bash
cd ~/Documents/serialisation-ceiling   # repo root, after `npm install`
node_modules/playwright-core/cli.js install chromium   # NOT `npx playwright install` —
  # that can resolve a different, older playwright-core than the one this
  # repo actually imports and silently install the wrong browser revision.
  # Confirmed this the hard way — see PHASE5_STATUS.md.
```

Check both the model mirror and query file exist (harness depends on both):
```bash
ls research/harness/models/Xenova/all-MiniLM-L6-v2/onnx/model_quantized.onnx
ls research/queries/queries.jsonl
```
If the model mirror is missing (it's gitignored), regenerate it:
```bash
mkdir -p research/harness/models/Xenova/all-MiniLM-L6-v2/onnx
cp node_modules/.cache/xenova/Xenova/all-MiniLM-L6-v2/{tokenizer.json,tokenizer_config.json,config.json} \
   research/harness/models/Xenova/all-MiniLM-L6-v2/
cp node_modules/.cache/xenova/Xenova/all-MiniLM-L6-v2/onnx/model_quantized.onnx \
   research/harness/models/Xenova/all-MiniLM-L6-v2/onnx/
```

---

## Mac (automated)

```bash
cd research/harness
node runner.js --sizes=1000,10000,100000 --threads=4,8 --cache=cold,warm
```

This is the **real protocol**: 20 repeats/cell (first discarded), 60s idle between repeats, randomised cell order, fixed network throttle on cold runs, best-effort `vm_stat`/`pmset` sampling per run. **12 cells × 20 repeats × ~60s idle ≈ 4+ hours minimum** — the plan's own Phase 6 pilot budget is 4 hours for a much smaller slice (1k+10k only, 50 queries), so don't run the full matrix as a first attempt. Start with the pilot slice:

```bash
node runner.js --sizes=1000,10000 --threads=4 --cache=cold,warm
```

Optional flags:
- `--repeats=N` (default 20)
- `--idle-seconds=N` (default 60)
- `--powermetrics` — only if you've set up passwordless `sudo` for `powermetrics` specifically (`sudo visudo`, add a NOPASSWD entry). Off by default because a sudo password prompt hangs the "unattended" run indefinitely — confirmed this crashes the browser mid-run, see `PHASE5_STATUS.md`.

Before a real run, per `MEASUREMENT_PLAN.md`'s Mac-specific amendments, check manually (the harness can't verify these for you):
- Mac is on mains power (harness records `on_ac_power` per run — check the raw files after, but plug in beforehand).
- Low Power Mode off.
- Nothing else CPU-heavy running (thermal drift confound).

Output: `research/results/raw/run_*.json`, one file per repeat. Never edit or delete these — superseded runs get new filenames (timestamp suffix), old ones stay.

## Android (automated, if adb is set up)

Not yet wired into `runner.js` — Playwright's Android support (`playwright._android`) needs `adb` on PATH and the device connected with USB debugging enabled. Not implemented here because the Android device spec was still `TBC` at time of writing (`EXECUTION_PLAN.md` Step 2) and Playwright-Android has enough quirks (specific Chrome version requirements, adb reverse port forwarding) that it's worth setting up once the actual device is known, not speculatively. If you want this path, tell me the Android model and I'll wire it in.

## Android / iPhone (manual — works today, no setup)

1. On the Mac, start the server and find its LAN IP:
   ```bash
   cd research/harness && node server.js &
   ipconfig getifaddr en0
   ```
2. On the phone (same WiFi), open: `http://<mac-ip>:8743/research/harness/bench_page.html`
3. Use the on-page form: pick corpus size, cache state, threads, repeats (20), idle (60s). Tap **Run**. Leave the phone alone until it finishes — don't background the tab (mobile browsers throttle/suspend backgrounded tabs, which would corrupt the timing).
4. **iPhone only** — for the metrics that need it (nothing in the current metric set strictly requires DevTools open, but if you want to sanity-check mid-run): connect the iPhone to the Mac by cable, enable Web Inspector (iPhone: Settings → Safari → Advanced → Web Inspector; Mac: Safari → Develop menu → your iPhone → the tab) to watch console output live.
5. Tap **Download results JSON** when done. AirDrop (iPhone) or transfer (Android) the file to the Mac, into `research/results/raw/` — rename to match the automated naming convention (`run_<size>_t<threads>_<cache>_r<repeat>_<timestamp>.json`) or just note in the filename it's manual (`manual_run_*.json` is the default, that's fine, `grading_method`/`run_mode` fields inside distinguish it from automated runs at analysis time).

**Known gap in manual mode**: it can't do the 3-layer cold-cache isolation `runner.js` does (fresh browser context + CDP HTTP-cache-disable) — only Cache API + IndexedDB clearing (in-page, same as the automated path). A phone's regular HTTP cache isn't clearable from a webpage. For a genuinely cold run on mobile, close Safari/Chrome fully (swipe it away, not just background it) before opening the URL again, and consider that a "cold-ish" run — document this limitation in the paper's methodology if manual-mode cold-start numbers get used, don't present them as identical-rigor to the Mac's numbers.

---

## After collecting data

Raw files accumulate in `research/results/raw/`. Nothing consumes them yet — Phase 8's `analysis/analyse.py` and `analysis/make_figures.py` don't exist yet (next build item after Phase 6 data exists). Don't wait for perfect data before checking a few files by hand — `python3 -m json.tool research/results/raw/<file>.json` to sanity-check as you go, the way the harness build itself was validated by manually inspecting output at every step.
