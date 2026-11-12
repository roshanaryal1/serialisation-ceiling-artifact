#!/usr/bin/env python3
"""Python-side half of the Phase 4 tokenisation parity check
(RESEARCH_PLAN.md: "Verify tokenisation parity between the Python and JS
pipelines on a sample of 100 documents. Token ID sequences must match. If
they do not match, stop and report.").

Tokenizes the same 100 texts (dumped to /tmp/parity_texts.json by the
caller) with the reference HF checkpoint's tokenizer, for comparison against
the JS side's @xenova/transformers tokenizer for the ONNX mirror
(research/harness/tokenization_parity_js.mjs).
"""

import json
from transformers import AutoTokenizer

MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def main():
    with open("/tmp/parity_texts.json") as f:
        texts = json.load(f)

    tok = AutoTokenizer.from_pretrained(MODEL)
    results = []
    for t in texts:
        ids = tok(t, truncation=True)["input_ids"]
        results.append(ids)

    with open("/tmp/parity_ids_py.json", "w") as f:
        json.dump(results, f)

    print(f"Tokenized {len(texts)} texts with {MODEL} -> /tmp/parity_ids_py.json")


if __name__ == "__main__":
    main()
