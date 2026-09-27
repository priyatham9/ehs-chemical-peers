#!/usr/bin/env python3
"""Link the raw public files and write outputs/summary.json and docs/data/*.json.

Usage: python3 scripts/build_data.py [--raw data/raw]
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chempeers import analysis, build, export  # noqa: E402


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(ROOT / "data" / "raw"))
    args = ap.parse_args()
    t0 = time.time()
    plants, releases, injuries, stats = build.assemble(args.raw)
    summary = analysis.findings(plants, releases, injuries, stats)
    built_from = {p.name: digest(p) for p in sorted(Path(args.raw).iterdir())
                  if p.suffix in (".zip", ".csv")}
    (ROOT / "outputs").mkdir(exist_ok=True)
    (ROOT / "outputs" / "summary.json").write_text(json.dumps(summary, indent=1))
    export.write(ROOT / "docs" / "data", plants, releases, injuries, summary, built_from)
    print("plants %d, releases %d, serious injuries %d in %.1fs"
          % (len(plants), len(releases), len(injuries), time.time() - t0))


if __name__ == "__main__":
    main()
