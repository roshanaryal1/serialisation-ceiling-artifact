#!/usr/bin/env python3
"""Import a manual on-device run into results/raw/.

The manual UI exports one JSON array containing every repeat. The automated
harness writes one file per repeat, and analyse.py expects that shape, so this
splits the array and names each file to match the automated convention.

Device labels are normalised (lowercased, spaces to hyphens) because the label
becomes the `browser` grouping key in analysis, and "Redmi note 11" and
"redmi-note-11" would otherwise be treated as two different devices.

Usage:
  python3 ingest_manual_run.py ~/Downloads/manual_run_123.json
  python3 ingest_manual_run.py ~/Downloads/manual_run_123.json --dry-run
"""

import argparse
import json
import re
import shutil
from pathlib import Path

RAW = Path(__file__).parent.parent / "results" / "raw"


def normalise(label):
    return re.sub(r"[^a-z0-9]+", "-", (label or "unknown-device").lower()).strip("-")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("export", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    runs = json.loads(args.export.read_text())
    if not isinstance(runs, list):
        raise SystemExit("Expected a JSON array from the manual UI export.")

    label = normalise(runs[0].get("device_label"))
    if label == "unknown-device":
        raise SystemExit(
            "Export has no device_label. Re-run with the Device label field "
            "filled in, or these results cannot be separated from the desktop "
            "cells in analysis."
        )

    RAW.mkdir(parents=True, exist_ok=True)
    written = 0
    for r in runs:
        cell = r.get("cell") or {}
        r["browser"] = label
        r["device_label"] = label
        r.setdefault("commit_sha", "manual-run")
        name = (f"run_{label}_{cell.get('mode','?')}_{cell.get('corpus_size','?')}"
                f"_t{cell.get('threads','?')}_{cell.get('cache_state','?')}"
                f"_r{r.get('repeat_index','?')}_{args.export.stem.split('_')[-1]}.json")
        dest = RAW / name
        if args.dry_run:
            print(f"would write {dest.name}")
        else:
            dest.write_text(json.dumps(r, indent=2))
        written += 1

    # Keep the original export alongside the split files: it is the primary
    # artifact the device actually produced, and results/raw is append-only.
    if not args.dry_run:
        archive = RAW.parent / "manual_exports"
        archive.mkdir(exist_ok=True)
        shutil.copy2(args.export, archive / args.export.name)

    print(f"{'Would import' if args.dry_run else 'Imported'} {written} repeats "
          f"as device '{label}'")
    if not args.dry_run:
        print(f"Original export archived to results/manual_exports/{args.export.name}")


if __name__ == "__main__":
    main()
