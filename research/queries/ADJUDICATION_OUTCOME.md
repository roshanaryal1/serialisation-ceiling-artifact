# Adjudication outcome: RQ1 is dropped

**Decision: the programmatic relevance judgments failed their pre-registered
validation, so no retrieval-quality results are reported.**

Three adjudication passes were run. The first two are void because of a defect
in the grading interface. The third is the valid measurement, and it fails.

## The valid measurement

| | value |
|---|---|
| Cohen's kappa (linear-weighted) | **0.512** |
| 95% CI (bootstrap, 5000 resamples) | **[0.302, 0.691]** |
| n | 60 judgments, 15 per query category |
| Pre-registered threshold | **0.70** |
| Bootstrap P(kappa >= 0.70) | **2.0%** |

Per category: paraphrase 0.697, attribute 0.455, vague 0.366, exact 0.262.

The upper bound of the interval does not reach the threshold. This is a clear
fail, not a borderline one.

**The threshold was not moved.** 0.512 is close enough to 0.7 to be tempting,
which is exactly why the bar was fixed in `labelling_protocol.md` before any
grading happened. Relaxing it after seeing the number would make the
pre-registration meaningless.

## Why the first two passes are void

| pass | n | kappa | status |
|---|---|---|---|
| 1 (fast) | 300 | +0.259 | void, interface defect |
| 2 (careful) | 60 | -0.102 | void, interface defect |
| 3 (redesigned) | 60 | **+0.512** | **valid** |

Passes 1 and 2 produced grades essentially uncorrelated with the rubric, and
internally inconsistent in ways no coherent standard explains: for the query
"way to safely get a worker up high", a Boom Lift was graded not-relevant while
a Jackhammer was graded partially-relevant.

Before attributing this to the grader, three checks were run:

1. **Join integrity** — 300/300 and 60/60 rows matched on (query_id, doc_id).
2. **Click mapping** — programmatically clicking a known row's button stored the
   grade under that row's key. Correct.
3. **Alignment shift** — kappa recomputed at offsets -2..+2 in display order. No
   offset improved on the recorded alignment, ruling out an off-by-one.
4. **Scale inversion** — kappa recomputed with grades flipped (2-g). Also near
   zero, ruling out a reversed scale.

The grader then identified the cause directly: the interface presented a
*different* meaning for the same three buttons depending on query category
(exact / paraphrase / attribute / vague), and required holding the correct one
in mind per row. Applying the wrong category's standard produces exactly the
observed pattern.

**This was an instrument defect, not grader error.** A measurement instrument
that requires the operator to mentally switch between four scales while working
at speed is badly designed, and the two void passes are the instrument's fault.

## The fix, and what it demonstrates

Pass 3 removed the numeric scale from the interface entirely. One question,
phrased identically for every query type:

> Someone searched for "<query>". Would this person be pleased to see this listing?
> *Yes, that's what I wanted* / *Close, but not quite* / *No, wrong thing*

The mapping to 0/1/2 happens invisibly, so the underlying scale and the
comparison to the rubric are unchanged. The auto-advance was also removed, since
it fired 180ms after a query's last candidate was rated and could catch a click
already in flight.

Effect: kappa moved from **-0.102 to +0.512** on a fresh, non-overlapping
sample, and the grade distribution moved from implausible (40/19/1, i.e. 67%
"not relevant" among top-50 retrieved candidates) to plausible (14/18/28).

That is a large effect from an interface change alone, and it is worth reporting
in its own right: **in a human-adjudication study, the framing of the grading
instrument can dominate the signal being measured.** Anyone running a similar
validation should ask one concrete question rather than a category-dependent
rubric.

## Consequences

1. **All RQ1 retrieval-quality claims are withdrawn.** nDCG, recall, MRR and
   Spearman figures computed against `qrels.jsonl` are not reported as results.
   The judgments underlying them did not pass validation.
2. The pre-registered remedy is to hand-label the full 250-query set. That is
   22,178 judgments and is not feasible here, so the axis is dropped rather than
   rescued.
3. **The paper is unaffected in substance.** Every headline finding is
   independent of relevance labels: the 61k-67k ceiling, the 2.52 Mbps mode
   crossover, the 9.4x Firefox gap, the cache-header correction, the timer
   resolution trap, and the Android tier.
4. What *is* reported from this exercise: the validation was attempted, what it
   cost, why it failed, and the interface effect above. A failed validation
   honestly reported is a result. An unvalidated quality number presented as one
   would not be.

## Artifacts

- `hand_grades.json` (pass 1, void), `hand_grades_careful.json` (pass 2, void),
  `hand_grades_v3.json` (pass 3, valid)
- `adjudication_sample_v1_fast.csv`, `_v2.csv`, `_v3.csv` — mutually
  non-overlapping, so no pass could be answered from memory of another
- All retained rather than deleted, per the append-only rule.
