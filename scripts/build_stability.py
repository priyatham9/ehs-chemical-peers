#!/usr/bin/env python3
"""Write the peer-stability outputs from docs/data/plants.json.

Writes outputs/peer_stability.csv (one row per plant), outputs/peer_stability.json
(parameters and aggregates) and docs/data/stability.json (group medians for
compare.html). Seeded and deterministic; uses only committed data.
Usage: python3 scripts/build_stability.py [--replicates N] [--check]
"""
import argparse
import csv
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chempeers import stability as S, taxonomy  # noqa: E402

COLUMNS = ["id", "name", "state", "product_type", "size_band", "n_families", "inventory_level", "k",
           "stability", "neighbourhood_bootstrap", "neighbourhood_noise", "exact_tiebreak_only",
           "exact_bootstrap", "exact_noise", "tied_at_kth"]


def load_plants(root=ROOT):
    return json.loads((root / "docs" / "data" / "plants.json").read_text(encoding="utf-8"))


def build(plants, replicates=S.REPLICATES, progress=None):
    recs, skipped = S.features(plants)
    model = S.Model(recs)
    result = S.run(model, replicates=replicates, progress=progress)
    table = S.rows(model, result)
    doc = {
        "about": "Share of each plant's baseline nearest peers that stay among its nearest peers "
                 "when the similarity weights are perturbed. See docs/stability.md.",
        "parameters": {
            "seed": S.SEED, "k": S.K, "replicates_per_scheme": replicates,
            "noise_sigma": S.NOISE_SIGMA,
            "features": S.FEATURES, "baseline_weights": S.BASE_WEIGHTS,
            "headline_schemes": list(S.HEADLINE),
            "size_bands": [b[0] for b in taxonomy.SIZE_BANDS],
            "inventory_levels": ["no pounds figure"] + [b[0] for b in taxonomy.INVENTORY_BANDS],
        },
        "coverage": {"plants_in_file": len(plants), "plants_scored": len(recs),
                     "plants_skipped_no_employee_count": skipped, "cells": model.n_cells},
        "summary": S.summarise(table),
        "built_from": "docs/data/plants.json",
        "disclaimer": "Independent analysis of public records; not an audit of any plant.",
    }
    groups = {"about": "Median peer stability of the plants in each comparison-page group "
                       "(membership by the plant's own attributes).",
              "k": S.K, "groups": S.group_stability(table, plants)}
    return table, doc, groups


def render_csv(table):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(table)
    return buf.getvalue()


def render_json(doc):
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicates", type=int, default=S.REPLICATES)
    ap.add_argument("--check", action="store_true", help="compare with the committed files, write nothing")
    args = ap.parse_args()
    t0 = time.time()
    table, doc, groups = build(load_plants(), args.replicates)
    files = {ROOT / "outputs" / "peer_stability.csv": render_csv(table),
             ROOT / "outputs" / "peer_stability.json": render_json(doc),
             ROOT / "docs" / "data" / "stability.json": render_json(groups)}
    if args.check:
        bad = [str(p.relative_to(ROOT)) for p, t in files.items()
               if not p.exists() or p.read_text(encoding="utf-8") != t]
        print("differs: %s" % bad if bad else "committed files match a fresh build")
        sys.exit(1 if bad else 0)
    for p, t in files.items():
        p.write_text(t, encoding="utf-8")
        print("wrote", p.relative_to(ROOT))
    print("%d plants, median stability %.3f, %.0fs" % (len(table), doc["summary"]["overall"]["median"],
                                                      time.time() - t0))


if __name__ == "__main__":
    main()
