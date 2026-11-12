# Finding: cross-engine latency comparison is invalid below ~1ms

Found 2026-08-11 while inspecting the first Firefox and WebKit results. Would
have produced a confidently stated, backwards conclusion.

## What the summary table appeared to say

Search latency, 1,000-document corpus, warm cache, p50:

| engine | search p50 |
|---|---|
| Chromium | 1.8 ms |
| Firefox | 1.0 ms |
| WebKit | 1.0 ms |

Read naively: Firefox and WebKit search nearly twice as fast as Chromium.

## What is actually happening

The distribution of individual `search_ms` readings gives it away:

| engine | corpus | n | distinct values | most common |
|---|---|---|---|---|
| Chromium | 1k | 190 | **21** | 1.8 x47, 1.9 x37, 1.9 x26, 2.0 x21 |
| Firefox | 1k | 190 | **3** | 1.0 x107, **0.0 x75**, 2.0 x8 |
| WebKit | 1k | 190 | **9** | 1.0 x75, **0.0 x75**, 2.0 x29 |
| Chromium | 10k | 190 | 71 | 6.4, 6.5, 6.4, 6.6 |
| Firefox | 10k | 190 | 9 | 6.0, 7.0, 5.0, 8.0 |

Firefox produced **three** distinct values across 190 measurements, and **39%
of them were literally 0.0 ms**. Every Firefox and WebKit reading lands on a
whole millisecond; Chromium's land on roughly 0.1 ms steps.

So the 1.0 ms figure is not a measurement of anything. It is the effective
resolution floor of the clock in these engines. A coarser clock reads as a
faster operation, which inverts the comparison.

**On the mechanism, and a correction.** The obvious explanation is
timing-attack/fingerprinting mitigation, and `performance.now()` is indeed
deliberately coarsened for that reason. But the documented figures do not match
what was observed here: MDN states the coarsening as "Resolution in isolated
contexts: 5 microseconds" and "Resolution in non-isolated contexts: 100
microseconds", and notes that unlike `Date.now`, `performance.now()` timestamps
"are not limited to one-millisecond resolution".

The observed behaviour is whole-millisecond quantisation, three to four orders
of magnitude coarser than the documented 100 microseconds. Something beyond the
specified coarsening is in play, plausibly a Firefox/WebKit privacy setting more
aggressive than the spec baseline, but that has **not been verified** and is not
asserted.

What is asserted is only what was measured: in these engine builds, under this
harness, search timings were quantised to whole milliseconds with a large
fraction reading exactly zero, and are therefore unusable for sub-millisecond
cross-engine comparison. The practical rule below does not depend on knowing
which mechanism produced it.

## Rule adopted

`analyse.py` now flags any cell whose search timings are at or below the timer
floor, using two signals: more than 5% of readings exactly 0.0, or more than 95%
landing on whole milliseconds. Flagged cells:

- firefox / 1k / warm — p50 1.0 ms, 39% zeros, 3 distinct values
- webkit / 1k / warm — p50 1.0 ms, 39% zeros, 9 distinct values
- firefox / 10k / warm — p50 6.0 ms, 0% zeros, 9 distinct values (quantised to
  whole ms but comfortably above the floor; usable with the quantisation stated)

**Cross-engine search-latency comparisons are reported only where the value is
comfortably above 1 ms**, which in practice means the 10,000-document corpus and
above. The 1,000-document search figures are reported for Chromium only, and the
Firefox/WebKit equivalents are marked as resolution-limited rather than quietly
included in a table that invites the wrong reading.

## What is NOT affected

Query **embedding** latency is 8-9 ms on Chromium and WebKit and 78-79 ms on
Firefox, all far above the 1 ms floor, so the embedding comparison stands. That
matters, because the largest cross-engine effect in the data is on embedding,
not search (see `FINDING_firefox_wasm_slowdown.md`). Cold-start totals are
hundreds of milliseconds to minutes and are likewise unaffected.

## Generalisation worth stating in the paper

Any browser-native performance study that reports sub-millisecond operations
across engines faces this. It is not specific to retrieval. The mitigation is
cheap: check the number of distinct values and the fraction of exact zeros
before believing a cross-engine latency difference, or batch the operation until
it is comfortably above the coarsest clock in the comparison.
