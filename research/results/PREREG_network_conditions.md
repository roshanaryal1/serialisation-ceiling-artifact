# Pre-registration: measured transfer under throttled network conditions

Written 2026-10-21 before any timing run, and committed before the runner is
executed. Responds to the SSD 2026 decision (major revision, 2026-10-20),
which asked for more network conditions.

## Design

- Chromium (Playwright, headless shell 153), the same desktop as Section 5.2.
- Network emulated through the DevTools protocol
  (`Network.emulateNetworkConditions`), applied per page before the fetch.
- Profiles, named by rate only: 1.6 Mbps / 150 ms RTT (the paper's existing
  profile), 4 Mbps / 70 ms, 10 Mbps / 40 ms, 25 Mbps / 20 ms.
- Corpus: 1,000 documents (8.08 MB JSON). Larger corpora would take minutes
  per repeat at the slowest profile.
- Arms: JSON and binary float32 plus id sidecar, each served uncompressed and
  as brotli (quality 9, precompressed). Every arm fetches every file it needs.
- N=5 per cell, fresh browser context per repeat, `cache: "no-store"`.

## Predictions

1. Measured fetch time is within 15% of the byte-count model
   `wire bytes x 8 / rate` in every cell, so the derived figures in Sections
   5.3 and 6.3 are measured rather than only modelled.
2. Under every profile, binary is faster than brotli-compressed JSON end to
   end, by at least 2x.
3. Brotli makes JSON faster than uncompressed JSON under every profile here
   (unlike on loopback), because transfer dominates decompression.

A prediction that fails is reported as failed.
