# Quarantined: Android warm runs collected before the cache-header fix

Moved 2026-08-13. Batch export id 1786412971170 (2026-08-11 13:49), 20 files.

Commit 161eca3 fixed a harness defect: server.js sent no Cache-Control header,
so the vectors artifact was re-fetched on every nominally warm run. That commit
states plainly: "All warm figures collected before this are invalid."

This batch is from before that fix and was still sitting in results/raw/,
merged into the same cell as the post-fix batch. Effect of the mix: the
10,000/warm p50 read 5,265.8 ms, which is neither the pre-fix figure
(6,628.6 ms) nor the post-fix one (1,437.5 ms) but an artifact of averaging
across a harness change.

Retained rather than deleted, per the append-only rule in PROVENANCE.md. The
pre/post pair is also the evidence for the 4.3x cache-header effect reported
in Section 4.4, so it has documentary value.
