# Relevance labelling protocol

Defines the grade boundaries *before* any judging starts (RESEARCH_PLAN.md
Phase 3). Written against `queries.jsonl` (250 queries, 4 categories) and the
candidate pool that `build_candidate_pool.py` produces over `corpus_10000.jsonl`
as the union of fp32 dense top-50 and BM25 top-50. Pooling has since been run
(`qrels_pool.jsonl`, 250 queries, avg 88.7 candidates each). This document is
the rubric that grading follows; it does not itself contain judgments.

## Scale

- **0 — Not relevant.** The listing would not satisfy the query's underlying need at all. Wrong category, wrong function, or answers a different question entirely.
- **1 — Partially relevant.** The listing is in the right category or serves an adjacent function, but isn't the best match — wrong capacity/spec for the stated need, a related-but-different tool, or satisfies only part of an attribute-constrained query (right category, wrong price band; right price, wrong category).
- **2 — Highly relevant.** The listing is a strong, direct match for what the query is asking for — right category, right function, and (where the query specifies one) right constraint.

## Boundary rules, with worked examples

Examples below use the query set's own categories and the synthetic corpus's
own vocabulary (`research/corpus/generate_corpus.py`), so a labeller can
apply them without needing outside equipment knowledge.

### Exact-term queries
Query text is a near-verbatim equipment name+spec (e.g. `"Scissor Lift 26' Electric, 29.0 ft"`).

- **2**: A listing whose type matches (`Scissor Lift`) and whose spec value is at or very close to the queried figure (e.g. 27-31 ft).
- **1**: Same type, but spec far off (e.g. a 60 ft boom lift when 29 ft was asked for), or a different type in the same category (e.g. a Boom Lift when a Scissor Lift was asked for) that could plausibly serve the same task.
- **0**: Different category entirely, or same category but a fundamentally different function (e.g. a Cherry Picker query matched against a Scaffolding System listing — both "Aerial"-adjacent by task, but not remotely the same equipment).

### Paraphrase queries
Query text avoids the equipment noun (e.g. `"need machine to dig and move earth on a building site"` for Construction Equipment).

- **2**: Any listing whose type is a standard tool for that task, regardless of exact type (an Excavator *and* a Bulldozer *and* a Backhoe Loader all satisfy "dig and move earth" — this is the point of the paraphrase category, testing whether semantic retrieval beats keyword match).
- **1**: A listing that's tangentially related — e.g. a Skid Steer Loader (compaction/landscaping-adjacent) surfacing for a "dig and move earth" query. Plausible but not the direct answer.
- **0**: A listing from an unrelated category (e.g. a Paint Sprayer surfacing for "dig and move earth").

### Attribute-constrained queries
Query text is `"{category} under ${price} a day"` or `"{category} available in {location}"`.

- **2**: Correct category **and** the stated constraint is satisfied (price at or under the ceiling; matching location).
- **1**: Correct category, constraint **not** satisfied (e.g. a $650/day listing for a "under $432" query) — still useful information, still graded down for not answering what was asked.
- **0**: Wrong category, regardless of whether the constraint happens to be satisfied.

### Vague queries
Query text is deliberately underspecified (e.g. `"need to get up high for a bit"`).

- **2**: Any listing from the category the vague query maps to in `queries.jsonl`'s `listing_category` field, since that field encodes the intended category even though the query text itself doesn't name it. This is the one category where the grader should consult `listing_category` before grading, precisely because the query text alone is ambiguous by design.
- **1**: A listing from an adjacent category that could plausibly resolve the same vague need (e.g. a Ladder-adjacent Safety Equipment listing for "need to get up high").
- **0**: Unrelated category.

## What agreement rate means here

Per RESEARCH_PLAN.md Phase 3: first-pass grading may be assisted, but a
minimum 20% stratified sample (stratified across the 4 query categories, not
just drawn uniformly — so category-specific effects aren't hidden by an
unrepresentative sample) must be hand-adjudicated and Cohen's kappa reported.
Below ~0.7 kappa, the assisted pass is discarded and the full 250 are
hand-labelled.

### Declared deviation — read this before citing the kappa figure

The plan's "20 percent" is ambiguous between 20% of *queries* and 20% of
*judgments*. Every candidate of 20% of queries is 49 × ~91 = **4,455
individual judgments**, which is not a realistic amount of careful human
attention to ask for in one sitting — and a rushed 4,455 is weaker evidence
than a careful 300.

What is actually done:

- **Query-level stratification preserved exactly**: 49 of 250 queries (19.6%),
  stratified across the four query categories.
- **Judgment rows then capped at 300**, themselves stratified so each query
  category contributes 75 (`sample_for_adjudication.py --max-rows`).

The adjudicated sample is therefore 20% of queries but ~6.7% of judgments.
Kappa at n=300 is precise enough to resolve the only question asked of it —
whether agreement clears 0.7 — but **the paper must report n=300 and describe
this cap, never present it as "20% adjudicated"**. `compute_kappa.py` prints a
reminder to that effect on every run.

Kappa is also reported **per query category**, not only pooled. The rubric
program's weakest component (the hand-authored `ADJACENCY` map in
`grade_pool.py`) is consulted only for `paraphrase` and `vague` queries, so
weak agreement concentrated there would indict that specific component rather
than the rubric as a whole — a distinction a single pooled number erases.

### Anchoring control

Grading is done in `grading_ui.html`, which never loads the rubric's own
`first_pass_grade`: the column is dropped at parse time, not merely hidden, so
it cannot be recovered from the DOM either. Showing the grader the answer being
audited would inflate agreement and make the kappa figure meaningless.

## Explicitly out of scope for this document

- Actual pooled candidates and their grades (`qrels.jsonl`) — depends on Phase 4.
- The stratified 20% sample selection and kappa computation — depends on qrels existing first.
