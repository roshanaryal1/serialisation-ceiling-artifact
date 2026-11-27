# Changelog

## Unreleased

- Security: dependency pins moved past every open advisory. Python lock:
  sentence-transformers 3.4.1 to 5.6.0, transformers 4.57.6 to 5.10.4,
  huggingface-hub 0.36.2 to 1.33.0, certifi to 2026.11.20, filelock to
  4.3.1, setuptools to 84.2.1. Pillow, requests and urllib3 are no longer
  in the baseline lock. The figure scripts still need Pillow through
  Matplotlib, so the README's figure step now installs `pillow>=13.0.0`.
  npm: scoped overrides move sharp to 0.35.5 under @xenova/transformers
  and protobufjs to 7.6.6 under onnx-proto; the measured library
  (@xenova/transformers 2.17.2) is unchanged.
- Reproducibility checked after the change, old lock against new on
  Python 3.11, with Matplotlib 3.11.2 for the figures:
  - CI's headline medians, bootstrap intervals and the five HELD
    predictions match.
  - `run_all.sh` plus `make_design_figure.py`, run from the same path:
    `processed/cells.csv`, `processed/queries.csv`,
    `processed/quality_fp32_10k.json` and the four PNG figures are
    byte-identical. The four PDF figures differ only in Matplotlib's
    `/CreationDate` timestamp, and are byte-identical when both runs set
    `SOURCE_DATE_EPOCH`.
  - `all-MiniLM-L6-v2` embeddings of the 250 queries and of the
    regenerated `corpus_1000.jsonl` are bit-identical (max abs difference
    0.0), and the top-50 lists match the committed
    `baseline/dense_top50_corpus_1000.json`.
  - Python token ids are unchanged on the 250 queries and on the
    100-document tokenisation parity sample, so the Python and JS parity
    in `research/baseline/TOKENIZATION_PARITY.md` still holds.
- Tag `v1.0.0` preserves the original artifact and its lockfiles, but not
  the browser builds: the pinned Playwright 1.64.1 now downloads Chromium
  156.0.8078.4, while the paper measured Playwright's Chromium
  141.0.7390.37 (build 1194). `research/PROVENANCE.md` records the browser
  versions behind every result.

## 1.0.0 (2026-11-14)

- First tagged release, matching the camera-ready paper submitted on
  10 November 2026.
- README with study design and cold-start figures, headline results and a
  reproduce section.
- CI that recomputes the Section 5.2 medians and bootstrap intervals and
  re-checks the five pre-registered remedy predictions from committed data.
- CITATION.cff, a CC BY 4.0 data licence and Zenodo metadata.
