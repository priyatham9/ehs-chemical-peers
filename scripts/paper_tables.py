#!/usr/bin/env python3
"""Render the tables in docs/paper.md from outputs/summary.json.

Each table in the paper sits between two markers:

    <!-- BEGIN table:NAME -->
    ...
    <!-- END table:NAME -->

    python3 scripts/paper_tables.py           # rewrite the tables in docs/paper.md
    python3 scripts/paper_tables.py --check   # exit 1 if any table differs from the summary

Nothing in a table is typed by hand. tests/test_paper_consistency.py runs the
check, so a rebuild that changes outputs/summary.json fails the tests until
the paper is regenerated.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "outputs" / "summary.json"
PAPER = ROOT / "docs" / "paper.md"
BLOCK = re.compile(r"(<!-- BEGIN table:([a-z_]+) -->\n)(.*?)(<!-- END table:\2 -->)", re.S)


def n(v):
    return "{:,}".format(int(v))


def pct(v, digits=2):
    return "{:.{d}f}".format(v, d=digits)


def cell(g):
    """'events / n (pct%)' for one group."""
    return "%s / %s (%s%%)" % (n(g["events"]), n(g["n"]), pct(g["pct"]))


def table(header, rows, align=None):
    align = align or ["---"] + ["--:"] * (len(header) - 1)
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(align) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def t_coverage(s):
    c = s["coverage"]
    rows = [
        ("Plants in the linked dataset", n(c["plants"])),
        ("EPA RMP-registered plants (NAICS 325)", n(c["rmp_plants"])),
        ("Plants with at least one OSHA Form 300A filing", n(c["osha_plants"])),
        ("RMP plants joined to an OSHA filing", "%s (%s%%)" % (n(c["linked_plants"]),
                                                             pct(c["rmp_linked_pct"]))),
        ("OSHA Form 300A establishment-years kept", n(c["ita_plant_years"])),
        ("RMP accident-history records (releases)", n(c["releases"])),
        ("OSHA Severe Injury Reports (NAICS 325)", n(c["serious_injuries"])),
        ("Severe Injury Reports joined to a plant", "%s (%s%%)" % (
            n(c["serious_injuries_linked"]), pct(c["serious_injuries_linked_pct"]))),
    ]
    return table(["Quantity", "Value"], rows)


def t_size_noise(s):
    rows = [(r["band"], n(r["plant_years"]), n(r["median_hours"]), pct(r["one_case_swing"]),
             pct(r["zero_share_pct"]), pct(r["pooled_trir"])) for r in s["size_noise"]]
    return table(["Average employees", "Plant-years", "Median hours", "One-case swing (TRIR points)",
                  "Plant-years with zero cases (%)", "Pooled TRIR"], rows)


def t_stability(s):
    rows = [(r["band"], n(r["pairs"]), "{:.3f}".format(r["rho"])) for r in s["stability"]]
    return table(["Average employees (first year)", "Consecutive-year pairs", "Spearman rho"], rows)


def _split(groups):
    return [(g["size"], cell(g["zero_cases"]), cell(g["below_median"]), cell(g["above_median"]),
             pct(g["median_trir_nonzero"])) for g in groups]


def t_trir_release(s):
    return table(["Average employees", "Zero cases", "TRIR at or below median", "TRIR above median",
                  "Median TRIR (non-zero)"], _split(s["trir_vs_outcomes"]["release_next_year"]))


def t_trir_serious(s):
    return table(["Average employees", "Zero cases", "TRIR at or below median", "TRIR above median",
                  "Median TRIR (non-zero)"],
                 _split(s["trir_vs_outcomes"]["serious_injury_next_year"]))


def t_release_predictors(s):
    rp = s["release_predictors"]
    rows = [("All covered plant-years", cell(rp["base"])),
            ("Release on file in the previous five years", cell(rp["history"]["release_in_past_5y"])),
            ("No release on file in the previous five years",
             cell(rp["history"]["no_release_in_past_5y"]))]
    rows += [("Inventory: " + r["band"], cell(r)) for r in rp["inventory"]]
    rows += [("Regulated chemicals held: " + r["label"], cell(r)) for r in rp["chemical_count"]]
    return table(["Group", "Plant-years with a release / plant-years (%)"], rows)


def t_families(s):
    rows = [(r["family"], cell(r)) for r in s["release_predictors"]["family"]]
    return table(["Chemical family held", "Plant-years with a release / plant-years (%)"], rows)


def t_release_anatomy(s):
    a = s["release_anatomy_all"]
    rows = []
    for key, name in (("type", "What happened"), ("source", "Where from"),
                      ("cause", "Contributing cause"), ("fix", "Change made afterwards")):
        for r in a[key]:
            rows.append((name, r["label"], n(r["n"])))
    return table(["Field", "Flag", "Releases flagged"], rows, ["---", "---", "--:"])


def t_injury_anatomy(s):
    rows = [(r["label"], n(r["n"])) for r in s["injury_anatomy_all"]["energy"]]
    return table(["Energy group", "Reports"], rows)


TABLES = {
    "coverage": t_coverage,
    "size_noise": t_size_noise,
    "stability": t_stability,
    "trir_release": t_trir_release,
    "trir_serious": t_trir_serious,
    "release_predictors": t_release_predictors,
    "families": t_families,
    "release_anatomy": t_release_anatomy,
    "injury_anatomy": t_injury_anatomy,
}


def render(text, summary):
    """Return ``text`` with every marked table regenerated, and the names seen."""
    seen = []

    def sub(m):
        name = m.group(2)
        if name not in TABLES:
            raise KeyError("unknown table %r in paper" % name)
        seen.append(name)
        return m.group(1) + TABLES[name](summary) + m.group(4)

    return BLOCK.sub(sub, text), seen


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    summary = json.loads(SUMMARY.read_text())
    text = PAPER.read_text()
    new, seen = render(text, summary)
    missing = sorted(set(TABLES) - set(seen))
    if a.check:
        if new != text or missing:
            print("docs/paper.md tables are out of date (or missing: %s); run "
                  "python3 scripts/paper_tables.py" % ", ".join(missing), file=sys.stderr)
            return 1
        print("%d tables match outputs/summary.json" % len(seen))
        return 0
    PAPER.write_text(new)
    print("wrote %d tables to %s" % (len(seen), PAPER.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
