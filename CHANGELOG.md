# Changelog

## Unreleased

- Security: dependency pins moved past every open advisory. Python lock:
  sentence-transformers 3.4.1 to 5.6.0, transformers 4.57.6 to 5.10.0,
  huggingface-hub 0.36.2 to 1.33.0, certifi to 2026.11.20, filelock to
  4.3.1, setuptools to 84.2.1; Pillow, requests and urllib3 are no longer
  required. npm: scoped overrides move sharp to 0.35.5 under
  @xenova/transformers and protobufjs to 7.6.6 under onnx-proto; the
  measured library (@xenova/transformers 2.17.2) is unchanged.
- Reproducibility checked after the change: CI's headline medians, bootstrap
  intervals and the five HELD predictions match; `run_all.sh` output is
  byte-identical between the old and new lock; MiniLM embeddings
  (max abs difference 0.0) and Python and JS token ids are identical.
- The exact environment behind the paper stays at tag `v1.0.0`.

## 1.0.0 (2026-11-14)

- First tagged release, matching the camera-ready paper submitted on
  10 November 2026.
- README with study design and cold-start figures, headline results and a
  reproduce section.
- CI that recomputes the Section 5.2 medians and bootstrap intervals and
  re-checks the five pre-registered remedy predictions from committed data.
- CITATION.cff, a CC BY 4.0 data licence and Zenodo metadata.
