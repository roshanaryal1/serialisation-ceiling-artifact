#!/usr/bin/env python3
"""Compute Cohen's kappa between the rubric-program first pass and the
hand-adjudicated sample (RESEARCH_PLAN.md Phase 3: "Report the agreement
rate between the LLM pass and my adjudication in the paper. If agreement is
below about 0.7 Cohen's kappa, the LLM pass is not usable and the full set
must be hand-labelled.").

Usage: python3 compute_kappa.py --sample adjudication_sample.csv
"""

import argparse
import csv
import json
from pathlib import Path

from sklearn.metrics import cohen_kappa_score


def load_from_csv(path):
    """Hand grades filled into the CSV's `your_grade` column directly."""
    first_pass, hand, qtypes = [], [], []
    incomplete = 0
    with path.open() as f:
        for row in csv.DictReader(f):
            if row["your_grade"].strip() == "":
                incomplete += 1
                continue
            first_pass.append(int(row["first_pass_grade"]))
            hand.append(int(row["your_grade"]))
            qtypes.append(row["query_category"])
    return first_pass, hand, qtypes, incomplete


def load_from_ui_json(path, csv_path):
    """Hand grades exported by grading_ui.js.

    The UI never sees `first_pass_grade` (by design -- it would anchor the
    grader), so the rubric's grades are joined back in here from the CSV on
    (query_id, doc_id).
    """
    with path.open() as f:
        export = json.load(f)

    rubric = {}
    qtype = {}
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            key = (row["query_id"], row["doc_id"])
            rubric[key] = int(row["first_pass_grade"])
            qtype[key] = row["query_category"]

    first_pass, hand, qtypes = [], [], []
    missing = 0
    for j in export["judgments"]:
        key = (j["query_id"], j["doc_id"])
        if key not in rubric:
            missing += 1
            continue
        first_pass.append(rubric[key])
        hand.append(int(j["hand_grade"]))
        qtypes.append(qtype[key])

    if missing:
        print(f"WARNING: {missing} exported judgments had no matching row in "
              f"{csv_path} -- the sample was probably regenerated after grading "
              f"started. Those rows are excluded; re-grade against the current "
              f"sample if this number is large.")

    incomplete = export.get("n_total", len(hand)) - len(hand)
    return first_pass, hand, qtypes, incomplete


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=Path("adjudication_sample.csv"),
                         help="The CSV. Also the join source for first_pass_grade "
                              "when --ui-export is used.")
    parser.add_argument("--ui-export", type=Path, default=None,
                         help="JSON exported by grading_ui.js. If given, hand "
                              "grades come from here instead of the CSV column.")
    args = parser.parse_args()

    if args.ui_export:
        first_pass, hand, qtypes, incomplete = load_from_ui_json(args.ui_export, args.sample)
    else:
        first_pass, hand, qtypes, incomplete = load_from_csv(args.sample)

    if incomplete > 0:
        print(f"WARNING: {incomplete} rows are ungraded and excluded. Kappa on a "
              f"partial sample is not the number to report; finish grading first.")

    if not hand:
        print("No graded rows found.")
        return

    kappa = cohen_kappa_score(first_pass, hand, weights="linear")
    exact_agree = sum(1 for a, b in zip(first_pass, hand) if a == b) / len(hand)

    print(f"n = {len(hand)} judgments compared")
    print(f"Exact agreement: {exact_agree:.1%}")
    print(f"Cohen's kappa (linear-weighted, appropriate for an ordinal 0/1/2 "
          f"scale): {kappa:.3f}")

    # Per-query-type breakdown. The rubric's weakest component (the hand-authored
    # ADJACENCY map in grade_pool.py) is used ONLY for paraphrase and vague
    # queries, so a low kappa concentrated in those two is diagnostic of that
    # specific weakness rather than of the rubric as a whole. A single pooled
    # number would hide exactly that.
    by_type = {}
    for fp, h, qt in zip(first_pass, hand, qtypes):
        by_type.setdefault(qt, ([], []))
        by_type[qt][0].append(fp)
        by_type[qt][1].append(h)

    print("\nPer query type:")
    for qt in sorted(by_type):
        fps, hs = by_type[qt]
        if len(set(fps)) < 2 and len(set(hs)) < 2:
            # kappa is undefined when both raters used a single label
            print(f"  {qt:<11} n={len(hs):<4} kappa=undefined (no label variance)")
            continue
        k = cohen_kappa_score(fps, hs, weights="linear")
        agree = sum(1 for a, b in zip(fps, hs) if a == b) / len(hs)
        print(f"  {qt:<11} n={len(hs):<4} kappa={k:.3f}  exact agreement={agree:.1%}")

    print()
    if kappa >= 0.7:
        print("kappa >= 0.7: rubric-program first pass is usable as qrels.jsonl, "
              "per RESEARCH_PLAN.md Phase 3.")
    else:
        print("kappa < 0.7: rubric-program first pass is NOT usable. Per "
              "RESEARCH_PLAN.md Phase 3, the full 250-query set must be "
              "hand-labelled instead.")
    print("\nReport in the paper: kappa, n, AND that n is a capped subsample of "
          "the 20%-of-queries pool (see labelling_protocol.md).")


if __name__ == "__main__":
    main()
