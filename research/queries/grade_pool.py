#!/usr/bin/env python3
"""First-pass grading of qrels_pool.jsonl against labelling_protocol.md's
rubric (RESEARCH_PLAN.md Phase 3: "LLM-assisted first pass is acceptable,
but a minimum 20 percent stratified sample must be hand-adjudicated").

IMPORTANT — what this actually is, stated plainly: this is NOT per-item
free-form LLM reasoning over natural-language text. With 250 queries x ~89
candidates = ~22,000 judgments, that isn't practical to do with genuine
reasoning per item in one sitting. Instead, this encodes
labelling_protocol.md's rubric as a deterministic program that reads the
corpus's own structured fields (category, type parsed from name, spec value,
price) -- which the rubric was deliberately written to be checkable against,
since this is a templated synthetic corpus with known structure, not free
text. This is a reasonable proxy for a first pass on THIS corpus specifically
(it wouldn't be for organic listing text), but it is mechanical, not
judgment, and must be labelled as such wherever it's cited.

The category-adjacency judgment calls (grade=1 for "tangentially related"
in paraphrase/vague queries) are the least reliable part of this pass --
ADJACENCY below is a coarse, subjectively-authored mapping, not derived from
anything. This is exactly the kind of thing the required 20% hand
adjudication + Cohen's kappa check should scrutinize most.

Usage: python3 grade_pool.py --corpus ../corpus/corpus_10000.jsonl
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "corpus"))
from generate_corpus import CATEGORIES, SPEC_RANGES  # noqa: E402

# Coarse "plausibly serves the same task" adjacency between categories, for
# the grade=1 case in paraphrase/vague queries. Authored, not derived --
# flagged in the module docstring as the weakest part of this pass.
ADJACENCY = {
    "Construction Equipment": {"Excavation", "Compaction", "Material Handling", "Demolition Tools"},
    "Excavation": {"Construction Equipment", "Compaction"},
    "Compaction": {"Construction Equipment", "Excavation", "Surface Preparation"},
    "Material Handling": {"Construction Equipment", "Cranes"},
    "Cranes": {"Material Handling", "Aerial Equipment"},
    "Aerial Equipment": {"Cranes", "Safety Equipment"},
    "Safety Equipment": {"Aerial Equipment"},
    "Cutting Tools": {"Demolition Tools", "Hand Tools"},
    "Demolition Tools": {"Cutting Tools", "Construction Equipment"},
    "Hand Tools": {"Cutting Tools", "Fastening Tools", "Electrical Tools"},
    "Fastening Tools": {"Hand Tools"},
    "Electrical Tools": {"Hand Tools", "Automotive Tools"},
    "Automotive Tools": {"Electrical Tools"},
    "Landscaping": {"Garden Tools", "Excavation"},
    "Garden Tools": {"Landscaping"},
    "Cleaning Equipment": {"Surface Preparation", "Painting Equipment"},
    "Surface Preparation": {"Cleaning Equipment", "Compaction", "Painting Equipment"},
    "Painting Equipment": {"Cleaning Equipment", "Surface Preparation"},
    "Plumbing Tools": {"Welding Equipment"},
    "Welding Equipment": {"Plumbing Tools", "Cutting Tools"},
    "Pumps": {"Cleaning Equipment"},
    "Power Generation": {"Air Tools", "Electrical Tools"},
    "Air Tools": {"Power Generation"},
    "Survey Equipment": {"Measuring Tools"},
    "Measuring Tools": {"Survey Equipment"},
    "Transportation": {"Construction Equipment", "Material Handling"},
    "Kitchen Equipment": {"Party & Event"},
    "Party & Event": {"Kitchen Equipment", "Sports Equipment"},
    "Sports Equipment": {"Party & Event"},
    "Other": set(),
}


def type_of(name):
    return name.split(" (")[0]


def extract_spec_value(text, last=False):
    matches = re.findall(r"(\d+\.?\d*)", text)
    if not matches:
        return None
    return float(matches[-1] if last else matches[0])


def spec_close(query_text, candidate, listing_category):
    unit, lo, hi, decimals = SPEC_RANGES.get(listing_category, (None, 0, 100, 0))
    # `last=True`: exact-query text is "{type} {spec}", and {spec} itself may
    # start with a numeric-looking style modifier (e.g. "26' Electric, 29.0
    # ft") -- the actual spec value is always the LAST number in the string,
    # matching how generate_corpus.py always appends spec_text last.
    qval = extract_spec_value(query_text, last=True)
    cval = extract_spec_value(candidate["description"].split("Rated ")[-1]) \
        if "Rated " in candidate["description"] else None
    if qval is None or cval is None:
        return False
    tolerance = 0.2 * (hi - lo)
    return abs(qval - cval) <= tolerance


def grade_exact(query, candidate):
    same_category = candidate["category"] == query["listing_category"]
    if not same_category:
        return 0
    cat_types = CATEGORIES[query["listing_category"]]["types"]
    matched_type = next((t for t in cat_types if query["query_text"].startswith(t)), None)
    same_type = matched_type is not None and type_of(candidate["name"]) == matched_type
    if same_type and spec_close(query["query_text"], candidate, query["listing_category"]):
        return 2
    return 1  # same category, but wrong type or spec too far off


def grade_paraphrase_or_vague(query, candidate):
    if candidate["category"] == query["listing_category"]:
        return 2
    if candidate["category"] in ADJACENCY.get(query["listing_category"], set()):
        return 1
    return 0


def grade_attribute(query, candidate):
    if candidate["category"] != query["listing_category"]:
        return 0
    text = query["query_text"]
    if "under $" in text:
        ceiling = extract_spec_value(text.split("under $")[1])
        satisfied = ceiling is not None and candidate["ratePerDay"] <= ceiling
    elif "available in " in text:
        loc = text.split("available in ")[1].strip()
        satisfied = candidate.get("location") == loc
    else:
        satisfied = True  # shouldn't happen given generate_queries.py's templates
    return 2 if satisfied else 1


def grade(query, candidate):
    qtype = query["query_category"]
    if qtype == "exact":
        return grade_exact(query, candidate)
    if qtype == "attribute":
        return grade_attribute(query, candidate)
    return grade_paraphrase_or_vague(query, candidate)  # paraphrase, vague


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("../corpus/corpus_10000.jsonl"))
    parser.add_argument("--pool", type=Path, default=Path("qrels_pool.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("qrels.jsonl"))
    args = parser.parse_args()

    corpus_by_id = {}
    with args.corpus.open() as f:
        for line in f:
            r = json.loads(line)
            corpus_by_id[r["id"]] = r

    with args.pool.open() as f:
        pool_rows = [json.loads(line) for line in f]

    out_rows = []
    grade_counts = {0: 0, 1: 0, 2: 0}
    for row in pool_rows:
        query = {
            "query_text": row["query_text"],
            "query_category": row["query_category"],
            "listing_category": row["listing_category"],
        }
        judgments = []
        for cid in row["candidates"]:
            cand = corpus_by_id[cid]
            g = grade(query, cand)
            grade_counts[g] += 1
            judgments.append({"doc_id": cid, "grade": g})
        out_rows.append({
            "query_id": row["query_id"],
            "query_text": row["query_text"],
            "query_category": row["query_category"],
            "listing_category": row["listing_category"],
            "judgments": judgments,
            "grading_method": "rubric_program_first_pass",  # NOT per-item LLM reasoning -- see module docstring
        })

    with args.out.open("w") as f:
        for row in out_rows:
            f.write(json.dumps(row) + "\n")

    total = sum(grade_counts.values())
    print(f"Wrote {len(out_rows)} query judgment sets ({total} judgments) -> {args.out}")
    print(f"Grade distribution: 0={grade_counts[0]} ({grade_counts[0]/total:.1%})  "
          f"1={grade_counts[1]} ({grade_counts[1]/total:.1%})  "
          f"2={grade_counts[2]} ({grade_counts[2]/total:.1%})")
    print("METHOD NOTE: this is a rubric-program first pass, not per-item LLM "
          "reasoning -- see this script's module docstring. Requires 20% "
          "stratified hand-adjudication + Cohen's kappa before use (plan Phase 3).")


if __name__ == "__main__":
    main()
