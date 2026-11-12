#!/usr/bin/env python3
"""Author the 250-query set for RQ1 quality evaluation (RESEARCH_PLAN.md
Phase 3), drawn over `research/corpus/corpus_10000.jsonl`.

Four categories, roughly balanced, one per query:
  exact       - exact-term lookup: verbatim or near-verbatim from a real
                corpus record's own name/spec text.
  paraphrase  - describes the target using different vocabulary than the
                corpus text uses (task-oriented, not the equipment noun).
  attribute   - constrained by category, price ceiling, and/or location.
  vague       - intentionally underspecified.

This script authors QUERY TEXT and its category label only. It does NOT
assign qrels (relevance judgments) -- per RESEARCH_PLAN.md Phase 3, qrels
come from pooling top-50 fp32 dense + top-50 BM25 results (Phase 4 baseline,
not yet built) followed by human/LLM-assisted grading. Authoring queries
ahead of the baseline is fine; judging them is not possible yet.

Usage: python3 generate_queries.py --corpus ../corpus/corpus_10000.jsonl
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "corpus"))
from generate_corpus import mulberry32  # noqa: E402

# One generic, non-verbatim task descriptor per category, deliberately
# avoiding the equipment noun so paraphrase queries test semantic match
# rather than keyword overlap. Hand-authored, not mined -- same status as
# CATEGORIES in generate_corpus.py.
PARAPHRASE_PHRASE = {
    "Construction Equipment": "machine to dig and move earth on a building site",
    "Material Handling": "something to lift and move heavy pallets around a warehouse",
    "Aerial Equipment": "way to safely get a worker up high indoors or outdoors",
    "Concrete Equipment": "gear to mix and place concrete for a small pour",
    "Landscaping": "equipment to clear overgrown ground and green waste",
    "Transportation": "vehicle to haul loose materials off a site",
    "Pumps": "something to get standing water off a flooded site",
    "Excavation": "tool to dig a narrow trench for pipework",
    "Compaction": "machine to firm up loose soil before laying a surface",
    "Cutting Tools": "tool that can cut through a concrete slab",
    "Air Tools": "something to run pneumatic tools on-site",
    "Power Generation": "backup power source for tools and site lighting",
    "Cranes": "way to lift something heavy several storeys up",
    "Demolition Tools": "tool for breaking up an old concrete path",
    "Safety Equipment": "way to give workers a safe platform up off the ground",
    "Welding Equipment": "gear to join two steel pieces together",
    "Cleaning Equipment": "something to blast grime off an outdoor surface",
    "Surface Preparation": "way to strip an old floor finish before recoating",
    "Painting Equipment": "fast way to paint a large wall or fence",
    "Plumbing Tools": "tool to cut and thread pipe for a plumbing job",
    "Survey Equipment": "way to check a site is level before building",
    "Hand Tools": "cordless tool for general fixing and assembly jobs",
    "Electrical Tools": "gear to test and prep wiring for an install",
    "Automotive Tools": "way to get a car off the ground for underneath work",
    "Measuring Tools": "device to check exact distances on-site",
    "Fastening Tools": "tool to drive a lot of fasteners quickly",
    "Garden Tools": "gear to tidy up an overgrown backyard",
    "Kitchen Equipment": "gear to cater food for a big event",
    "Party & Event": "cover and sound setup for an outdoor event",
    "Sports Equipment": "gear to set up a casual game in the park",
    "Other": "something flexible for a one-off job that doesn't fit elsewhere",
}

VAGUE_PHRASE = {
    "Construction Equipment": "need something for a big dig",
    "Material Handling": "need help moving stuff around the warehouse",
    "Aerial Equipment": "need to get up high for a bit",
    "Concrete Equipment": "doing a concrete job this weekend",
    "Landscaping": "yard's a mess, need some gear",
    "Transportation": "need to move a load of material",
    "Pumps": "got water where it shouldn't be",
    "Excavation": "need to dig a bit of a trench",
    "Compaction": "ground's too soft, need to sort it",
    "Cutting Tools": "need to cut through something tough",
    "Air Tools": "need something powered by air",
    "Power Generation": "power's out on site, need a fix",
    "Cranes": "need to lift something heavy",
    "Demolition Tools": "need to break some stuff up",
    "Safety Equipment": "need to get workers up safely",
    "Welding Equipment": "need to join some metal",
    "Cleaning Equipment": "surface is filthy, need to clean it",
    "Surface Preparation": "floor needs prepping before we finish it",
    "Painting Equipment": "got a big wall to paint",
    "Plumbing Tools": "pipe job needs doing",
    "Survey Equipment": "need to check the levels on site",
    "Hand Tools": "just need a decent drill or something",
    "Electrical Tools": "sparky work coming up",
    "Automotive Tools": "need to work under a car",
    "Measuring Tools": "need to measure something precisely",
    "Fastening Tools": "lots of screws to put in",
    "Garden Tools": "garden's out of control",
    "Kitchen Equipment": "catering a party, need kitchen gear",
    "Party & Event": "throwing an event outdoors, need setup",
    "Sports Equipment": "want to set up a game with mates",
    "Other": "not sure exactly what I need for this job",
}


def build_queries(corpus_path, seed, target_total=250):
    records = []
    with open(corpus_path) as f:
        for line in f:
            records.append(json.loads(line))

    by_cat = {}
    for r in records:
        by_cat.setdefault(r["category"], []).append(r)

    categories = sorted(by_cat.keys())
    per_cat = target_total // len(categories)  # 8 for 31 categories
    remainder = target_total - per_cat * len(categories)

    rng = mulberry32(seed)
    queries = []
    qid = 0
    for ci, cat in enumerate(categories):
        n_this_cat = per_cat + (1 if ci < remainder else 0)
        cat_records = by_cat[cat]
        # split n_this_cat as evenly as possible across the 4 query types
        counts = [n_this_cat // 4] * 4
        for i in range(n_this_cat - sum(counts)):
            counts[i] += 1
        exact_n, paraphrase_n, attribute_n, vague_n = counts

        for _ in range(exact_n):
            rec = cat_records[int(rng() * len(cat_records))]
            # near-verbatim: the bracketed spec text stripped, matching how a
            # user would actually type a query (not copy-paste the full name).
            base = rec["name"].split(" (")[0]
            spec = rec["name"].split("(", 1)[1].rstrip(")") if "(" in rec["name"] else ""
            text = f"{base} {spec}".strip()
            queries.append({"id": f"q-{qid:04d}", "text": text, "category": "exact",
                             "listing_category": cat})
            qid += 1

        # Mechanical wrap variants so repeated queries for the same category
        # aren't byte-identical (each category typically needs 2 of a type
        # since n_this_cat=8 splits into counts of 2 across 4 types) -- these
        # are still one authored core phrase per category, just phrased as a
        # different sentence, not independently-authored paraphrases.
        paraphrase_wraps = ["{p}", "need {p}", "looking for {p}", "anything for {p}?"]
        vague_wraps = ["{p}", "{p}, any ideas?", "{p} this week", "{p} — what should I get?"]

        base_paraphrase = PARAPHRASE_PHRASE[cat]
        for i in range(paraphrase_n):
            wrap = paraphrase_wraps[i % len(paraphrase_wraps)]
            text = wrap.format(p=base_paraphrase)
            queries.append({"id": f"q-{qid:04d}", "text": text,
                             "category": "paraphrase", "listing_category": cat})
            qid += 1

        for _ in range(attribute_n):
            rec = cat_records[int(rng() * len(cat_records))]
            ceiling = int(rec["ratePerDay"] * (1.0 + rng() * 0.3))
            loc = rec["location"]
            variant = rng()
            if variant < 0.5:
                text = f"{cat.lower()} under ${ceiling} a day"
            else:
                text = f"{cat.lower()} available in {loc}"
            queries.append({"id": f"q-{qid:04d}", "text": text, "category": "attribute",
                             "listing_category": cat})
            qid += 1

        base_vague = VAGUE_PHRASE[cat]
        for i in range(vague_n):
            wrap = vague_wraps[i % len(vague_wraps)]
            text = wrap.format(p=base_vague)
            queries.append({"id": f"q-{qid:04d}", "text": text,
                             "category": "vague", "listing_category": cat})
            qid += 1

    return queries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("../corpus/corpus_10000.jsonl"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path("queries.jsonl"))
    parser.add_argument("--target-total", type=int, default=250)
    args = parser.parse_args()

    queries = build_queries(args.corpus, args.seed, args.target_total)
    with args.out.open("w") as f:
        for q in queries:
            f.write(json.dumps(q) + "\n")

    by_type = {}
    for q in queries:
        by_type[q["category"]] = by_type.get(q["category"], 0) + 1
    print(f"Wrote {len(queries)} queries -> {args.out} (seed={args.seed})")
    print("By type:", by_type)


if __name__ == "__main__":
    main()
