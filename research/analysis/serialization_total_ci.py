"""Bootstrap 95% CI on the median of per-run fetch+parse totals (paper Section 5.2).

Reads results/processed/serialization_experiment.json. Seeded so the interval in
the table is reproducible. Binary parse time is zero, so the total equals fetch.
"""
import json
import random
import statistics as st
from pathlib import Path

RESAMPLES = 2000
SEED = 0
SRC = Path(__file__).resolve().parent.parent / "results/processed/serialization_experiment.json"


def median_ci(values):
    meds = sorted(st.median(random.choices(values, k=len(values))) for _ in range(RESAMPLES))
    return meds[int(0.025 * RESAMPLES) - 1], meds[int(0.975 * RESAMPLES) - 1]


random.seed(SEED)
for r in json.loads(SRC.read_text())["results"]:
    totals = [f + p for f, p in zip(r["fetch_raw_ms"], r["parse_raw_ms"])]
    lo, hi = median_ci(totals)
    print(f"{r['corpus_size']:>6} {r['format']:<12} stage-sum p50 {r['fetch_p50_ms'] + r['parse_p50_ms']:6.1f} ms  CI [{lo:.1f}, {hi:.1f}]")
