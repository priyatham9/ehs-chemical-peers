#!/usr/bin/env python3
"""Write docs/data/compare.json from outputs/summary.json and docs/data/plants.json.

Uses only the committed outputs, so it runs without data/raw.
Usage: python3 scripts/build_compare.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chempeers import compare, taxonomy  # noqa: E402


def build_doc(root=ROOT):
    summary = json.loads((root / "outputs" / "summary.json").read_text(encoding="utf-8"))
    plants = json.loads((root / "docs" / "data" / "plants.json").read_text(encoding="utf-8"))
    return compare.build(summary, plants, taxonomy.SIZE_BANDS, taxonomy.subsector)


def render(doc):
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def main():
    out = ROOT / "docs" / "data" / "compare.json"
    doc = build_doc()
    out.write_text(render(doc), encoding="utf-8")
    print("wrote %s: %d groups, %d tested pairs" % (out.relative_to(ROOT), len(doc["groups"]),
                                                  len(doc["pairs"])))


if __name__ == "__main__":
    main()
