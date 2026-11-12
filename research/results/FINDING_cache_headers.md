# Correction: a missing cache header inflated every warm-start figure

Found 2026-08-11 while adding the Android tier. This is a harness bug of mine,
not a property of the system under test, and it invalidated a headline number
before it reached the paper.

## What was wrong

`research/harness/server.js` sent no `Cache-Control` header on any response. The
precomputed vectors artifact is fetched with a plain `fetch()`, so without a
caching directive the browser re-requested it on every run. "Warm cache" in the
harness therefore meant *model cached, vectors not* -- a state no real
deployment is in, since a static content-addressed asset would carry cache
headers.

Loopback hid it on desktop. Serving 77 MB over the loopback interface took
157 ms, small enough next to a 531 ms warm start that nothing looked wrong. The
Android device exposed it immediately: over WiFi the same fetch took a rock
steady 4,104 ms on **every** repeat (CV 0.077, 19.7 MB/s), which is a full
transfer each time, not a cache hit.

## The fix and its measured effect

Added `Cache-Control: public, max-age=31536000, immutable` for model and corpus
artifacts, and `no-store` for the harness's own JavaScript (so an edited
`bench_page.js` can never be silently measured in its previous version).

Redmi Note 11, 10,000 documents, warm, Mode A:

| | cold_start_total p50 |
|---|---|
| before (no cache header) | 6,629 ms (n=19) |
| after | **~1,556 ms** (n=4) |
| first fetch in the new run (uncached, expected) | 6,853 ms |

A 4.3x reduction. The warmup repeat still pays full transfer, which is correct:
that repeat *is* the uncached case, and it is discarded by protocol.

## Why the Playwright check was misleading

Before asking for the device re-run, the same question was tested under
Playwright: fetch the artifact three times in one context and inspect
`transferSize`. It reported the full byte count every time, for both an 8 MB and
an 80 MB artifact, even with valid headers. That suggested the artifact was
uncacheable at any size.

It was not. Real Chrome on the phone cached it. Playwright's browser context does
not reproduce a normal profile's HTTP caching behaviour closely enough to answer
this question, and the artificial environment was about to produce a confidently
wrong finding: "large vector artifacts cannot be cached, so every visit pays full
transfer." That would have been a dramatic claim and a false one.

The lesson generalises and belongs in the methodology: **cache behaviour must be
verified on a real browser profile over a real network.** Loopback plus an
automation context defeats both halves of the test.

## Consequences for the study

1. **All warm-cache figures collected before this fix are invalid**, on every
   device and engine, because they include an unnecessary artifact transfer.
   The desktop cells are being re-run with the corrected server; the Android
   cell has been re-measured.
2. **The corrected picture is more favourable to browser-native retrieval**, not
   less. Mobile warm start is roughly 1.6 s rather than 6.6 s, which is
   interactive rather than sluggish, and it materially softens the equity
   conclusion drawn from the earlier numbers.
3. **Cold-start figures are unaffected.** Cold runs clear storage and disable the
   HTTP cache deliberately, so they were always measuring a genuine first visit.
   The 535.7 s throttled 10k cold start stands.
4. Any device-to-device ratio computed from the old warm numbers must be
   recomputed. The previously noted "phone is 12x the Mac" is an artifact of the
   phone paying a real network transfer while the Mac paid a loopback one.

## Status

- Android re-measured: done, n=4 diagnostic. A full n=20 run at the corrected
  settings is still worth taking before the figure is final.
- Desktop re-run across Chromium, Firefox and WebKit at 1k and 10k warm: running.
- Superseded raw files are retained rather than deleted, per the append-only
  rule, and are distinguishable by commit SHA and timestamp.
