"""docs/insights.md quotes numbers from outputs/accident_*; this keeps them honest.

Also checks that the committed tables equal a fresh build and that the SVG is
deterministic. Run: python3 -m unittest tests.test_insights
"""
import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_accident_insights as B  # noqa: E402

DOC = (ROOT / "docs" / "insights.md").read_text(encoding="utf-8")
OUT = ROOT / "outputs"
D = json.loads((OUT / "accident_insights.json").read_text(encoding="utf-8"))


def row(rows, name):
    return next(r for r in rows if r["group"] == name)


def fmt(x, nd=2):
    return ("%." + str(nd) + "f") % x


class DocMatchesTables(unittest.TestCase):
    def need(self, text):
        self.assertIn(text, DOC, "doc should contain %r" % text)

    def test_overall(self):
        o = D["overall"]
        self.need("%s facilities with at least one observed year" % format(o["facilities"], ","))
        self.need("%d accident records over %s facility-years" % (o["accidents"], format(o["facility_years"], ",")))
        self.need("%s per 100 facility-years (exact Poisson 95%% interval %s to %s)" % (
            fmt(o["rate_per_100fy"]), fmt(o["rate_lo"]), fmt(o["rate_hi"])))
        self.need("%d of the %s facilities (%s%%)" % (o["facilities_with_accident"], format(o["facilities"], ","),
                                                     fmt(o["pct_with_accident"])))
        self.need("%s%% of facilities have any record" % fmt(o["pct_with_accident"]))

    def test_finding_1(self):
        sub = D["subsector"]
        p, e = row(sub, "Petrochemicals"), row(sub, "Ethanol & biofuels")
        self.need("%s accident records per 100 facility-years (95%% interval %s to %s; %d facilities)" % (
            fmt(p["rate_per_100fy"]), fmt(p["rate_lo"]), fmt(p["rate_hi"]), p["facilities"]))
        self.need("%s (%s to %s; %d facilities)" % (fmt(e["rate_per_100fy"]), fmt(e["rate_lo"]),
                                                     fmt(e["rate_hi"]), e["facilities"]))
        self.assertEqual(round(p["rate_per_100fy"] / e["rate_per_100fy"]), 14)
        a, f = row(sub, "Acids & inorganics"), row(sub, "Fertilizer & ag chemicals")
        self.need("%s (%s to %s) and fertilizer" % (fmt(a["rate_per_100fy"]), fmt(a["rate_lo"]), fmt(a["rate_hi"])))
        self.need("%s (%s to %s)." % (fmt(f["rate_per_100fy"]), fmt(f["rate_lo"]), fmt(f["rate_hi"])))
        fam = D["family"]
        for name, label in (("Epoxy chain", "epoxy chain"), ("Strong acids", "strong acids"),
                            ("Sulfur compounds", "sulfur compounds"), ("Isocyanates", "isocyanates")):
            self.need("%s (%s)" % (label, fmt(row(fam, name)["rate_per_100fy"])))
        self.assertEqual([r["group"] for r in fam[:3]], ["Epoxy chain", "Strong acids", "Sulfur compounds"])
        self.assertEqual(fam[-1]["group"], "Isocyanates")
        large = [r for r in sub if r["facilities"] >= 100]
        self.assertEqual(large[0]["group"], "Petrochemicals")
        self.assertEqual(large[-1]["group"], "Ethanol & biofuels")

    def test_finding_2(self):
        o = D["overall"]
        none = D["accident_count_distribution"]["0"]
        self.need("%s of %s facilities (%s%%) had no accident record" % (
            format(none, ","), format(o["facilities"], ","), fmt(100.0 * none / o["facilities"])))
        c = {r["top_share_of_facilities_pct"]: r for r in D["concentration"]}
        self.need("The %d facilities in the top 10%% by accident count account for %s%%" % (
            c[10]["facilities"], fmt(c[10]["pct_of_accidents"])))
        self.need("top 1%% (%d facilities) for %s%%" % (c[1]["facilities"], fmt(c[1]["pct_of_accidents"])))
        hi, lo = row(D["inventory"], "5M+ lb"), row(D["inventory"], "Under 100k lb")
        self.need("%s records per 100 facility-years (%s%% had at least one)" % (
            fmt(hi["rate_per_100fy"]), fmt(hi["pct_with_accident"])))
        self.need("against %s (%s%%) for facilities under 100,000 lb" % (
            fmt(lo["rate_per_100fy"]), fmt(lo["pct_with_accident"])))

    def test_finding_3(self):
        s, f, inv = D["split_subsector"], D["split_family"], D["subsector_inventory_rank"]
        self.need("the %d product-type groups" % s["groups"])
        self.need("is %s (Spearman)" % fmt(s["spearman"], 3))
        self.need("Across the %d chemical families it is %s" % (f["groups"], fmt(f["spearman"], 3)))
        self.need("lower in the later half in %d of %d product types" % (s["groups_lower_late"], s["groups"]))
        self.need("Across %d product types, the rank correlation between a group's median inventory and its "
                  "accident rate is %s" % (inv["groups"], fmt(inv["spearman"], 3)))

    def test_distribution_and_chemicals(self):
        dist = D["accident_count_distribution"]
        self.need("%d facilities had two or more, %d had three or more" % (dist["2"] + dist["3+"], dist["3+"]))
        self.need("(%d facilities, %s%%)" % (dist["3+"], fmt(100.0 * dist["3+"] / D["overall"]["facilities"])))
        ch = D["chemicals"]
        self.need("chlorine (%d records at %d facilities)" % (ch[0]["accident_records"], ch[0]["facilities_with_accident"]))
        self.need("anhydrous ammonia (%d records at %d facilities)" % (ch[1]["accident_records"],
                                                                      ch[1]["facilities_with_accident"]))
        self.assertTrue(ch[0]["chemical"] == "Chlorine" and ch[1]["chemical"] == "Ammonia (anhydrous)")
        self.need("hydrofluoric acid (%d)" % ch[2]["accident_records"])
        self.need("2,611 RMP")

    def test_small_groups_claim(self):
        for name in ("Synthetic rubber", "Dyes & pigments", "Explosives", "Fibers"):
            self.assertLess(row(D["subsector"], name)["facilities"], 30)


class TablesMatchBuild(unittest.TestCase):
    def test_fresh_build_equals_committed(self):
        fresh = B.build()
        self.assertEqual(json.loads(json.dumps(fresh)), D)

    def test_csvs_match_json(self):
        for fname, key in (("accident_by_subsector.csv", "subsector"), ("accident_by_family.csv", "family"),
                           ("accident_by_inventory.csv", "inventory"), ("accident_concentration.csv", "concentration")):
            with open(OUT / fname, newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), len(D[key]))
            for r, j in zip(rows, D[key]):
                for k, v in j.items():
                    self.assertAlmostEqual(float(r[k]), v, places=6) if not isinstance(v, str) else self.assertEqual(r[k], v)

    def test_svg_is_deterministic_and_committed(self):
        s = B.svg(D["subsector"], D["overall"])
        self.assertEqual(s, B.svg(D["subsector"], D["overall"]))
        self.assertEqual(s, (ROOT / "docs" / "img" / "accident_rate_by_group.svg").read_text(encoding="utf-8"))
        self.assertTrue(s.startswith("<svg"))

    def test_counts_tie_to_source_files(self):
        meta, cols, plants, rels = B.load()
        facs = B.facilities(cols, plants, rels)
        self.assertEqual(len(facs), D["overall"]["facilities"])
        self.assertEqual(sum(len(f["acc_years"]) for f in facs), D["overall"]["accidents"])
        self.assertLessEqual(D["overall"]["accidents"], len(rels))


if __name__ == "__main__":
    unittest.main()
