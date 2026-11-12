"""Summarise the serialisation-remedy experiment and check its pre-registered predictions.

Reads results/processed/serialization_remedy_experiment.json (raw per-repeat
values from harness/serialization_remedy_experiment.mjs). CIs are seeded
bootstraps on the median, so every figure printed here is reproducible.
Predictions are those in results/PREREG_serialisation_remedy.md.
"""
import json
import random
import statistics as st
import sys
from pathlib import Path

RESAMPLES = 2000
SEED = 0
SRC = Path(__file__).resolve().parent.parent / "results/processed" / (
    sys.argv[1] if len(sys.argv) > 1 else "serialization_remedy_experiment.json"
)


def median_ci(values):
    rng = random.Random(SEED)
    meds = sorted(st.median(rng.choices(values, k=len(values))) for _ in range(RESAMPLES))
    return meds[int(0.025 * RESAMPLES) - 1], meds[int(0.975 * RESAMPLES) - 1]


data = json.loads(SRC.read_text())
cells = {(c["corpus_size"], c["arm"], c["enc"]): c for c in data["results"]}
print(f"{SRC.name}  generated {data['generated']}  Chromium {data['browser_version']}")
print(f"{data['platform']}\n")


def med(c, key):
    return st.median(c[key]) if c[key] else None


print(f"{'docs':>7} {'arm':<16} {'enc':<8} {'ok':>5} {'wall p50 ms [95% CI]':>26} {'parse p50':>10} "
      f"{'wire MB':>8} {'x bin wire':>10} {'x bin wall':>10} {'heap MB':>8}")
for (size, arm, enc), c in cells.items():
    ok = f"{c['ok_count']}/{c['n']}"
    if not c["ok_count"]:
        print(f"{size:>7} {arm:<16} {enc:<8} {ok:>5}  FAILED: {c['errors'][0][:60]}")
        continue
    lo, hi = median_ci(c["wall_raw_ms"])
    b = cells.get((size, "binary", enc))
    wire = med(c, "encoded_bytes")
    xw = f"{wire / med(b, 'encoded_bytes'):.2f}" if b and b["ok_count"] else "-"
    xt = f"{med(c, 'wall_raw_ms') / med(b, 'wall_raw_ms'):.2f}" if b and b["ok_count"] else "-"
    heap = [h for h in c["heap_raw_bytes"] if h]
    hm = f"{st.median(heap) / 1e6:.0f}" if heap else "-"
    print(f"{size:>7} {arm:<16} {enc:<8} {ok:>5} {med(c, 'wall_raw_ms'):>9.1f} [{lo:>7.1f}, {hi:>7.1f}] "
          f"{med(c, 'parse_raw_ms'):>10.1f} {wire / 1e6:>8.2f} {xw:>10} {xt:>10} {hm:>8}")


def verdict(name, held, detail):
    print(f"  {'HELD  ' if held else 'FAILED'} {name}: {detail}")


print("\nPre-registered predictions")
sizes = sorted({k[0] for k in cells})
encs = sorted({k[2] for k in cells})
big = max(sizes)
shard_arms = sorted({k[1] for k in cells if k[1].startswith("json-shard")})

mono = [cells[(big, "json", e)] for e in encs if (big, "json", e) in cells]
verdict("1 monolithic JSON fails at largest size", all(c["ok_count"] == 0 for c in mono),
        ", ".join(f"{c['enc']} {c['ok_count']}/{c['n']} ok" for c in mono))

sh = [cells[(big, a, e)] for a in shard_arms for e in encs if (big, a, e) in cells]
verdict("2 sharded JSON succeeds at largest size", all(c["ok_count"] == c["n"] for c in sh),
        ", ".join(f"{c['arm']}/{c['enc']} {c['ok_count']}/{c['n']}" for c in sh))

m10 = cells.get((10000, "json", "identity"))
if m10 and m10["ok_count"]:
    ratios = {a: med(cells[(10000, a, "identity")], "parse_raw_ms") / med(m10, "parse_raw_ms") for a in shard_arms}
    verdict("3 sharded parse within 20% of monolithic at 10k identity",
            all(0.8 <= r <= 1.2 for r in ratios.values()),
            ", ".join(f"{a} {r:.2f}x" for a, r in ratios.items()))

worst = None
for (size, arm, enc), c in cells.items():
    b = cells.get((size, "binary", enc))
    if arm == "binary" or not c["ok_count"] or not (b and b["ok_count"]):
        continue
    r = med(c, "wall_raw_ms") / med(b, "wall_raw_ms")
    if worst is None or r < worst[0]:
        worst = (r, size, arm, enc)
at10 = [med(cells[(10000, a, "identity")], "wall_raw_ms") / med(cells[(10000, "binary", "identity")], "wall_raw_ms")
        for a in ["json"] + shard_arms if (10000, a, "identity") in cells]
verdict("4 binary faster than every JSON arm, >=5x at 10k identity",
        worst is not None and worst[0] > 1 and min(at10) >= 5,
        f"smallest margin {worst[0]:.2f}x ({worst[1]} {worst[2]} {worst[3]}); 10k identity min {min(at10):.2f}x")

slower = []
for (size, arm, enc), c in cells.items():
    ident = cells.get((size, arm, "identity"))
    if enc == "identity" or not c["ok_count"] or not (ident and ident["ok_count"]):
        continue
    slower.append((med(c, "wall_raw_ms") >= med(ident, "wall_raw_ms"), size, arm, enc))
verdict("5 compressed not faster than identity on loopback", all(s[0] for s in slower),
        "exceptions: " + (", ".join(f"{s[1]} {s[2]} {s[3]}" for s in slower if not s[0]) or "none"))
