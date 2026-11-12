// JS-side half of the Phase 4 tokenisation parity check (RESEARCH_PLAN.md).
// Uses the app's own @xenova/transformers install (node_modules at repo
// root) and the exact model id the app embeds with (embeddingService.js:9),
// so this checks the tokenizer that actually ships in the browser, not a
// generic one.
//
// Run from repo root: node research/harness/tokenization_parity_js.mjs

import { AutoTokenizer } from "@xenova/transformers";
import fs from "fs";

const MODEL = "Xenova/all-MiniLM-L6-v2";

async function main() {
  const texts = JSON.parse(fs.readFileSync("/tmp/parity_texts.json", "utf-8"));
  const tokenizer = await AutoTokenizer.from_pretrained(MODEL);

  const results = [];
  for (const t of texts) {
    const { input_ids } = await tokenizer(t);
    results.push(Array.from(input_ids.data, Number));
  }

  fs.writeFileSync("/tmp/parity_ids_js.json", JSON.stringify(results));
  console.log(`Tokenized ${texts.length} texts with ${MODEL} -> /tmp/parity_ids_js.json`);
}

main();
