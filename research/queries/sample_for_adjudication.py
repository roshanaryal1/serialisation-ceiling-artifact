#!/usr/bin/env python3
"""Select the stratified 20% sample for hand-adjudication (RESEARCH_PLAN.md
Phase 3) and emit a plain CSV to grade by hand.

Stratified across the 4 query categories (exact/paraphrase/attribute/vague),
not drawn uniformly, per the plan's own instruction ("so category-specific
quantisation effects aren't hidden by an unrepresentative sample").

Output CSV columns: query_id, query_text, query_category, doc_id, doc_name,
doc_category, first_pass_grade, your_grade (blank, fill in 0/1/2).

After filling in `your_grade` for every row, run compute_kappa.py to compare
against the rubric-program first pass and get Cohen's kappa.

Usage: python3 sample_for_adjudication.py --corpus ../corpus/corpus_10000.jsonl
"""

import argparse
import csv
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "corpus"))
from generate_corpus import mulberry32  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("../corpus/corpus_10000.jsonl"))
    parser.add_argument("--qrels", type=Path, default=Path("qrels.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("adjudication_sample.csv"))
    parser.add_argument("--fraction", type=float, default=0.2,
                         help="Fraction of QUERIES to sample (stratified by query type).")
    parser.add_argument("--max-rows", type=int, default=300,
                         help="Cap on individual judgment rows to hand-grade, "
                              "stratified across query types. 0 = no cap (all "
                              "~4,455 rows). See the note in main() about why "
                              "this deviates from a literal reading of the plan.")
    parser.add_argument("--seed", type=int, default=99)
    parser.add_argument("--exclude", type=Path, default=None,
                         help="A previous sample CSV. Its (query_id, doc_id) pairs are "
                              "excluded, so a re-grade draws rows the grader has not "
                              "already seen and cannot be answering from memory.")
    args = parser.parse_args()

    corpus_by_id = {}
    with args.corpus.open() as f:
        for line in f:
            r = json.loads(line)
            corpus_by_id[r["id"]] = r

    with args.qrels.open() as f:
        qrels = [json.loads(line) for line in f]

    by_type = {}
    for row in qrels:
        by_type.setdefault(row["query_category"], []).append(row)

    rng = mulberry32(args.seed)
    selected = []
    for qtype, rows in sorted(by_type.items()):
        n_sample = max(1, round(len(rows) * args.fraction))
        pool = list(rows)
        # deterministic shuffle-and-take via the seeded PRNG
        for i in range(len(pool) - 1, 0, -1):
            j = int(rng() * (i + 1))
            pool[i], pool[j] = pool[j], pool[i]
        selected.extend(pool[:n_sample])

    # Flatten to individual judgment rows, then optionally subsample.
    #
    # Why subsample: every candidate of 20% of queries is 4,455 individual
    # judgments, which is not a realistic amount of careful human attention to
    # ask for -- and a rushed 4,455 is worse evidence than a careful 300.
    # Kappa on n=300 still has a tight enough CI to answer the only question
    # being asked of it (is the rubric pass above or below 0.7).
    #
    # This IS a deviation from RESEARCH_PLAN.md Phase 3's "minimum 20 percent
    # stratified sample", under the reading that the 20% applies to queries
    # (49/250, preserved exactly here) rather than to judgments. The deviation
    # and the achieved n must both be reported in the paper -- see
    # labelling_protocol.md. Do not quietly describe this as "20%".
    # location and ratePerDay are REQUIRED, not decorative: attribute queries
    # constrain on "available in <location>" or "under $<price> a day", and the
    # rubric's 2-vs-1 boundary is exactly whether that constraint is satisfied.
    # Without these fields on the card the grader cannot apply the rule at all.
    excluded = set()
    if args.exclude and args.exclude.exists():
        with args.exclude.open() as f:
            excluded = {(r["query_id"], r["doc_id"]) for r in csv.DictReader(f)}

    all_rows = []
    for row in selected:
        for j in row["judgments"]:
            if (row["query_id"], j["doc_id"]) in excluded:
                continue
            cand = corpus_by_id[j["doc_id"]]
            all_rows.append([row["query_id"], row["query_text"], row["query_category"],
                              j["doc_id"], cand["name"], cand["category"],
                              cand.get("location", ""), cand.get("ratePerDay", ""),
                              j["grade"], ""])

    total_available = len(all_rows)
    if args.max_rows and total_available > args.max_rows:
        # Stratify the subsample by query type too, so no query category is
        # squeezed out by the ones that happen to have bigger pools.
        by_qtype = {}
        for r in all_rows:
            by_qtype.setdefault(r[2], []).append(r)
        picked = []
        qtypes = sorted(by_qtype)
        per_type = args.max_rows // len(qtypes)
        for qi, qt in enumerate(qtypes):
            bucket = by_qtype[qt]
            for i in range(len(bucket) - 1, 0, -1):
                j = int(rng() * (i + 1))
                bucket[i], bucket[j] = bucket[j], bucket[i]
            take = per_type + (1 if qi < args.max_rows - per_type * len(qtypes) else 0)
            picked.extend(bucket[:take])
        all_rows = picked

    with args.out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["query_id", "query_text", "query_category", "doc_id",
                          "doc_name", "doc_category", "doc_location", "doc_price_per_day",
                          "first_pass_grade", "your_grade"])
        writer.writerows(all_rows)

    print(f"Selected {len(selected)}/{len(qrels)} queries "
          f"({args.fraction:.0%} target, stratified across "
          f"{sorted(by_type.keys())})")
    print(f"{total_available} judgment rows available; wrote {len(all_rows)} "
          f"(--max-rows={args.max_rows}) -> {args.out}")
    counts = {}
    for r in all_rows:
        counts[r[2]] = counts.get(r[2], 0) + 1
    print("Rows by query type:", counts)
    print("Grade in the browser UI (recommended): research/queries/grading_ui.html")
    print("Or fill the 'your_grade' column by hand, then run compute_kappa.py")


if __name__ == "__main__":
    main()
