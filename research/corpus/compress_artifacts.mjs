// Writes precompressed copies (X.gz, X.br) of every artifact the
// serialisation-remedy experiment fetches, so the harness server can serve a
// static Content-Encoding the way a CDN would. Compressing at request time
// instead would put server-side compression inside the browser's measured
// fetch time, which no static deployment pays.
//
// Levels are the common static-asset choices, recorded with the results:
// gzip level 9, brotli quality 9 (quality 11 takes minutes per file at the
// 100,000-document size for a gain that does not change the comparison).
//
// Usage: node compress_artifacts.mjs --sizes=1000,10000,100000 --shards=1000,10000

import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const args = Object.fromEntries(
  process.argv.slice(2).map((a) => {
    const [k, v] = a.replace(/^--/, "").split("=");
    return [k, v];
  })
);
const sizes = (args.sizes || "1000,10000").split(",").map(Number);
const shardSizes = (args.shards || "1000,10000").split(",").map(Number);

const GZIP_LEVEL = 9;
const BROTLI_QUALITY = 9;

function artifacts(size) {
  const files = [`vectors_${size}.json`, `vectors_${size}.bin`, `vectors_${size}.ids.json`];
  for (const s of shardSizes) {
    files.push(`vectors_${size}.shard${s}.manifest.json`);
    const dir = `vectors_${size}.shard${s}`;
    for (const f of fs.readdirSync(path.join(__dirname, dir))) {
      if (f.endsWith(".json")) files.push(path.join(dir, f));
    }
  }
  return files;
}

async function compress(rel) {
  const src = path.join(__dirname, rel);
  await pipeline(fs.createReadStream(src), zlib.createGzip({ level: GZIP_LEVEL }), fs.createWriteStream(src + ".gz"));
  await pipeline(
    fs.createReadStream(src),
    zlib.createBrotliCompress({
      params: {
        [zlib.constants.BROTLI_PARAM_QUALITY]: BROTLI_QUALITY,
        [zlib.constants.BROTLI_PARAM_SIZE_HINT]: fs.statSync(src).size,
      },
    }),
    fs.createWriteStream(src + ".br")
  );
}

for (const size of sizes) {
  if (!fs.existsSync(path.join(__dirname, `vectors_${size}.json`))) {
    console.log(`SKIP corpus_${size}: no vectors_${size}.json`);
    continue;
  }
  const files = artifacts(size);
  for (const f of files) await compress(f);
  const total = (suffix) => files.reduce((a, f) => a + fs.statSync(path.join(__dirname, f + suffix)).size, 0);
  console.log(
    `corpus_${size}: ${files.length} files, identity ${(total("") / 1e6).toFixed(2)} MB, ` +
      `gzip ${(total(".gz") / 1e6).toFixed(2)} MB, br ${(total(".br") / 1e6).toFixed(2)} MB`
  );
}
