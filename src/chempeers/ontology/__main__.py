"""Build the ontology and export it: ``python3 -m chempeers.ontology --out DIR``.

Objects come from the committed linked dataset (docs/data) unless ``--raw``
points at downloaded source files, which are then linked with
chempeers.build.assemble. Output goes to ``--out`` only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

from . import functions
from .export import export_json, export_sqlite
from .materialise import SOURCE_COMMITTED, SOURCE_RAW, build_store


def main(argv: Optional[List[str]] = None) -> int:
    """Materialise, print a census and the link integrity report, write ontology.sqlite/json."""
    ap = argparse.ArgumentParser(description="Build and export the chemical plant ontology.")
    ap.add_argument("--out", required=True, help="directory for ontology.sqlite and ontology.json")
    ap.add_argument("--raw", help="raw source files to link instead of the committed site data")
    args = ap.parse_args(argv)

    if args.raw:
        from ..build import assemble

        plants, releases, injuries, _stats = assemble(args.raw)
        store = build_store((plants, releases, injuries), source=SOURCE_RAW)
    else:
        store = build_store(source=SOURCE_COMMITTED)
    out = Path(args.out)
    export_sqlite(store, out / "ontology.sqlite")
    export_json(store, out / "ontology.json")
    census = {t: store.objects(t).count() for t in store.spec.object_types}
    print(json.dumps({"objects": census, "integrity": store.integrity_report(),
                      "coverage": functions.coverage(store)}, indent=1))
    print(f"wrote {out / 'ontology.sqlite'} and {out / 'ontology.json'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
