# Stale: pre-RQ1-withdrawal quality artifacts

Moved here 2026-08-12, not deleted, per PROVENANCE.md (never silently
discard a primary source).

`quality_comparison.json` (generated 2026-08-11 12:25) predates the RQ1
withdrawal (commits e6b3109, 25e7855, both 2026-08-11 15:42+) that dropped
all retrieval-quality claims after the relevance-judgment validation failed
its pre-registered kappa threshold (Section 5.1).

`fig3_quality_delta_by_category.{png,pdf}` was regenerated from this stale
file by `make_figures.py` as late as 2026-08-11 23:20 -- every `run_all.sh`
run since the withdrawal kept silently resurrecting a figure that directly
contradicts the paper's own "no quality result is reported" claim, because
`fig3_quality_delta()` only checks whether the input file exists, not
whether it predates the withdrawal.

With the source file moved out of `results/processed/`, `make_figures.py`
now skips fig3 cleanly (`SKIP fig3: ... not found`) on every future run.
Do not regenerate this comparison unless RQ1 is genuinely reopened per a
repaired relevance-judgment protocol (see the future-work paragraph in
section8_conclusion_and_abstract.md).
