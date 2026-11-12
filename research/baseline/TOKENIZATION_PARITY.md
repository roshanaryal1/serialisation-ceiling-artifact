# Tokenisation parity check (Phase 4 hard-stop gate)

RESEARCH_PLAN.md Phase 4: "Verify tokenisation parity between the Python and
JS pipelines on a sample of 100 documents. Token ID sequences must match. If
they do not match, stop and report. A tokenisation divergence would mean any
measured quality gap is an implementation artifact, not a quantisation
effect, and it would invalidate RQ1 entirely."

## Result: PASS — 0/100 mismatches

## Method

- Sample: first 100 records of `research/corpus/corpus_10000.jsonl`, text = `f"{name}\n\n{description}"` (mirrors the app's own concatenation pattern in `scripts/buildEmbeddings.js:66`).
- Python side: `research/baseline/tokenization_parity_py.py`, `transformers.AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")` (`transformers==4.57.6`, see PROVENANCE.md), truncation on, default settings.
- JS side: `research/harness/tokenization_parity_js.mjs`, `@xenova/transformers`'s `AutoTokenizer.from_pretrained("Xenova/all-MiniLM-L6-v2")` — the exact model id and package version the app itself uses (`embeddingService.js:9`, `@xenova/transformers@2.17.2`), run against the repo's own `node_modules` so this checks what actually ships, not a generic install.
- Compared `input_ids` arrays element-by-element per text, both directions (count and content).

## Why this passes

`Xenova/all-MiniLM-L6-v2` is a same-vocabulary ONNX mirror of `sentence-transformers/all-MiniLM-L6-v2` — both use the identical WordPiece vocab/tokenizer config, only the model weights differ in format (PyTorch vs ONNX) and precision (fp32 vs int8-quantized). Quantisation affects the model's weights, not the tokenizer, so parity here was expected but not assumed — verified per the plan's explicit instruction not to skip this step.

## Conclusion for RQ1

Any quality delta measured between the fp32 Python baseline and the int8 in-browser system in Phase 6/7 can be attributed to quantisation, not to a tokenization-level implementation divergence. RQ1 is not invalidated on this axis.

## Reproduce

```bash
# From repo root:
node research/harness/tokenization_parity_js.mjs
cd research && source .venv/bin/activate && python3 baseline/tokenization_parity_py.py
# then diff /tmp/parity_ids_py.json against /tmp/parity_ids_js.json
```

Raw token ID dumps are written to `/tmp/parity_ids_py.json` / `/tmp/parity_ids_js.json` (not committed — regenerate on demand, deterministic given the same 100 input texts from `corpus_10000.jsonl`).
