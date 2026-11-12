# A Serialisation Ceiling in Browser-Native Semantic Retrieval

Harness, corpus generator, raw run records and analysis for
"A Serialisation Ceiling in Browser-Native Semantic Retrieval: Mechanism,
Prediction, and Remedy", accepted for the Proceedings of SSD 2026 (4th
International Conference on Smart Sustainable Development, Atlantis Press).

The manuscript itself is not included here; cite the proceedings version once
it is published.

## Layout

| Path | What |
|---|---|
| `research/harness/` | Browser harness, static server, experiment runners |
| `research/corpus/` | Corpus generator and vector conversion scripts |
| `research/queries/` | Query sets |
| `research/baseline/` | FP32 reference baseline |
| `research/analysis/` | Summaries, confidence intervals, figures |
| `research/results/` | Raw run records, processed results, pre-registrations |
| `research/MEASUREMENT_PLAN.md` | Measurement plan |
| `research/PROVENANCE.md` | Hashes of every regenerable artifact |

Some notes refer to planning documents that are not part of this public copy.

## Setup

```sh
npm install                                  # transformers.js and Playwright, pinned
python3 -m venv research/.venv && research/.venv/bin/pip install -r research/requirements.lock.txt
```

Large artifacts (corpora, vectors, model mirror) are not committed; regenerate
them as described in `research/harness/RUNBOOK.md` and check them against
`research/PROVENANCE.md`.
