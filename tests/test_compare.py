"""The comparison page reads docs/data/compare.json; this keeps it honest.

Checks: the statistics against brute-force sums, every group against
outputs/summary.json (releases) and docs/data/plants.json (injuries), every
pair against a recomputation, the committed file against a fresh build, and
the page against the file it reads.
Run: python3 -m unittest tests.test_compare
"""
import json
import math
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from chempeers import compare as C  # noqa: E402
import build_compare  # noqa: E402

SUMMARY = json.loads((ROOT / "outputs" / "summary.json").read_text(encoding="utf-8"))
PAGE = (ROOT / "docs" / "compare.html").read_text(encoding="utf-8")
DATA_PATH = ROOT / "docs" / "data" / "compare.json"
DATA = json.loads(DATA_PATH.read_text(encoding="utf-8"))
GROUPS = {g["id"]: g for g in DATA["groups"]}


def pois_cdf(k, mu):
    return sum(math.exp(-mu + j * math.log(mu) - math.lgamma(j + 1)) for j in range(k + 1))


def binom_cdf(k, n, p):
    return sum(math.exp(math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1)
                        + j * math.log(p) + (n - j) * math.log1p(-p)) for j in range(k + 1))


class Statistics(unittest.TestCase):
    def test_cdfs_match_brute_force(self):
        for k, mu in ((0, 0.5), (3, 2.0), (40, 35.5), (200, 180.0)):
            self.assertAlmostEqual(C.poisson_cdf(k, mu), pois_cdf(k, mu), places=10)
        for k, n, p in ((0, 10, 0.2), (7, 50, 0.3), (60, 400, 0.12)):
            self.assertAlmostEqual(C.binom_cdf(k, n, p), binom_cdf(k, n, p), places=10)

    def test_known_values(self):
        # Rule of three: zero events in 30 trials, exact upper limit 1 - 0.025**(1/30).
        lo, hi = C.clopper_pearson(0, 30)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 1 - 0.025 ** (1 / 30), places=9)
        # Garwood limits for 0 observed: upper = -ln(0.025).
        self.assertAlmostEqual(C.garwood(0)[1], -math.log(0.025), places=9)
        # Garwood for 10 observed (tabulated 4.795, 18.390).
        lo, hi = C.garwood(10)
        self.assertAlmostEqual(lo, 4.7954, places=3)
        self.assertAlmostEqual(hi, 18.3904, places=3)
        # Wilson for 5/20: 0.1119 to 0.4687.
        lo, hi = C.wilson(5, 20)
        self.assertAlmostEqual(lo, 0.1119, places=3)
        self.assertAlmostEqual(hi, 0.4687, places=3)

    def test_interval_coverage_properties(self):
        for x, n in ((3, 40), (50, 400), (355, 2952)):
            lo, hi = C.clopper_pearson(x, n)
            self.assertAlmostEqual(1 - C.binom_cdf(x - 1, n, lo), 0.025, places=8)
            self.assertAlmostEqual(C.binom_cdf(x, n, hi), 0.025, places=8)
            wl, wu = C.wilson(x, n)
            self.assertLess(lo, x / n)
            self.assertLess(x / n, hi)
            self.assertLess(wl, x / n)
            self.assertLess(x / n, wu)

    def test_fisher_matches_enumeration(self):
        # Lady-tasting-tea table 3,1 / 1,3: two-sided p = 34/70.
        self.assertAlmostEqual(C.fisher_two_sided(3, 4, 1, 4), 34 / 70, places=9)
        self.assertAlmostEqual(C.fisher_two_sided(5, 50, 5, 50), 1.0, places=9)

    def test_exact_binomial_matches_enumeration(self):
        # 9 of 10 at p = 0.5: two-sided p = 2 * 11/1024.
        self.assertAlmostEqual(C.exact_binomial_two_sided(9, 10, 0.5), 22 / 1024, places=9)
        self.assertAlmostEqual(C.exact_binomial_two_sided(5, 10, 0.5), 1.0, places=9)


class ReleaseGroupsMatchSummary(unittest.TestCase):
    def check(self, gid, n, events):
        g = GROUPS[gid]
        self.assertEqual((g["n"], g["events"]), (n, events), gid)
        self.assertAlmostEqual(g["rate_pct"], 100 * events / n, places=3)
        lo, hi = g["exact_pct"]
        self.assertLessEqual(lo, g["rate_pct"])
        self.assertGreaterEqual(hi, g["rate_pct"])

    def test_groups_equal_summary(self):
        rp = SUMMARY["release_predictors"]
        for row in rp["inventory"]:
            self.check("rel-inv-" + row["band"], row["n"], row["events"])
        for row in rp["family"]:
            self.check("rel-fam-" + row["family"], row["n"], row["events"])
        for row in rp["chemical_count"]:
            self.check("rel-nchem-" + row["label"], row["n"], row["events"])
        for key, row in rp["history"].items():
            self.check("rel-hist-" + key, row["n"], row["events"])
        for row in SUMMARY["trir_vs_outcomes"]["release_next_year"]:
            parts = [row[k] for k in ("zero_cases", "below_median", "above_median")]
            self.check("rel-size-" + row["size"], sum(p["n"] for p in parts),
                       sum(p["events"] for p in parts))

    def test_every_summary_group_is_present(self):
        rp = SUMMARY["release_predictors"]
        expected = len(rp["inventory"]) + len(rp["family"]) + len(rp["chemical_count"]) + 2 + 3
        self.assertEqual(sum(1 for g in DATA["groups"] if g["metric"] == "release"), expected)

    def test_history_groups_add_up_to_base(self):
        rp = SUMMARY["release_predictors"]
        h = [GROUPS["rel-hist-release_in_past_5y"], GROUPS["rel-hist-no_release_in_past_5y"]]
        self.assertEqual(sum(g["n"] for g in h), rp["base"]["n"])
        self.assertEqual(sum(g["events"] for g in h), rp["base"]["events"])


class InjuryGroupsMatchData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plants = json.loads((ROOT / "docs" / "data" / "plants.json").read_text(encoding="utf-8"))

    def test_size_bands_match_summary_pooled_trir(self):
        for row in SUMMARY["size_noise"]:
            g = GROUPS["inj-size-" + row["band"]]
            self.assertEqual(g["plant_years"], row["plant_years"])
            self.assertEqual(round(g["rate"], 2), row["pooled_trir"])

    def test_groups_recomputed_independently(self):
        bands = {"Under 50": (0, 50), "50-99": (50, 100), "100-249": (100, 250),
                 "250-999": (250, 1000), "1,000+": (1000, 10 ** 9)}
        tot = {b: [0, 0] for b in bands}
        for p in self.plants:
            for y in p[17].values():
                if y[7] and y[0] > 0:
                    for b, (lo, hi) in bands.items():
                        if lo <= y[1] < hi:
                            tot[b][0] += y[0]
                            tot[b][1] += y[2] + y[3] + y[4]
        for b, (h, c) in tot.items():
            g = GROUPS["inj-size-" + b]
            self.assertEqual((g["hours"], g["events"]), (h, c))

    def test_product_groups_partition_all_usable_plant_years(self):
        usable = sum(1 for p in self.plants for y in p[17].values() if y[7] and y[0] > 0)
        in_prod = sum(g["plant_years"] for g in DATA["groups"] if g["dimension"] == "product")
        self.assertEqual(in_prod, usable)
        self.assertEqual(sum(g["plant_years"] for g in DATA["groups"]
                             if g["metric"] == "injury" and g["dimension"] == "size"),
                         sum(r["plant_years"] for r in SUMMARY["size_noise"]))

    def test_intervals_contain_rate(self):
        for g in DATA["groups"]:
            if g["metric"] == "injury":
                self.assertLessEqual(g["exact"][0], g["rate"], g["id"])
                self.assertGreaterEqual(g["exact"][1], g["rate"], g["id"])


class Pairs(unittest.TestCase):
    def test_pairs_recomputed(self):
        for p in DATA["pairs"]:
            a, b = GROUPS[p["a"]], GROUPS[p["b"]]
            self.assertEqual(a["metric"], b["metric"])
            self.assertEqual(a["dimension"], b["dimension"])
            self.assertNotEqual(a["dimension"], "family")
            if a["metric"] == "release":
                exp = C.fisher_two_sided(a["events"], a["n"], b["events"], b["n"])
            else:
                exp = C.exact_binomial_two_sided(
                    a["events"], a["events"] + b["events"], a["hours"] / (a["hours"] + b["hours"]))
            self.assertAlmostEqual(p["p"], exp, places=5)
            self.assertEqual(p["distinguishable"], p["p"] < DATA["alpha"])

    def test_pairs_are_antisymmetric_and_complete(self):
        idx = {(p["a"], p["b"]): p for p in DATA["pairs"]}
        for (a, b), p in idx.items():
            q = idx[(b, a)]
            self.assertAlmostEqual(p["p"], q["p"], places=5)
            key = "diff_pct" if "diff_pct" in p else "diff"
            self.assertAlmostEqual(p[key], -q[key], places=3)
        for a in GROUPS.values():
            for b in GROUPS.values():
                if (a["metric"] == b["metric"] and a["dimension"] == b["dimension"]
                        and a["dimension"] != "family" and a is not b):
                    self.assertIn((a["id"], b["id"]), idx)

    def test_headline_findings_agree_with_readme(self):
        # README: a release in the past five years vs none is far beyond noise;
        # a low injury rate vs a high one among size bands is too.
        p = next(x for x in DATA["pairs"] if x["a"] == "rel-hist-release_in_past_5y"
                 and x["b"] == "rel-hist-no_release_in_past_5y")
        self.assertTrue(p["distinguishable"])
        self.assertAlmostEqual(p["diff_pct"], SUMMARY["release_predictors"]["history"]["release_in_past_5y"]["pct"]
                               - SUMMARY["release_predictors"]["history"]["no_release_in_past_5y"]["pct"],
                               places=1)
        q = next(x for x in DATA["pairs"] if x["a"] == "inj-size-Under 50" and x["b"] == "inj-size-1,000+")
        self.assertTrue(q["distinguishable"])


class BuildAndPage(unittest.TestCase):
    def test_committed_file_equals_fresh_build(self):
        fresh = build_compare.render(build_compare.build_doc())
        self.assertEqual(DATA_PATH.read_text(encoding="utf-8"), fresh,
                         "docs/data/compare.json is stale: run make compare")

    def test_page_reads_the_file_and_carries_disclaimer(self):
        self.assertIn('fetch("data/compare.json")', PAGE)
        self.assertIn("Not affiliated with", DATA["disclaimer"])
        self.assertIn("Palantir", DATA["disclaimer"])
        self.assertIn('id="disclaimer"', PAGE)

    def test_page_dimensions_cover_every_group(self):
        labels = set(re.findall(r'(\w+): "[^"]+"', PAGE.split("var DIM = {")[1].split("};")[0]))
        self.assertTrue({g["dimension"] for g in DATA["groups"]} <= labels)

    def test_page_has_no_hand_typed_data_figures(self):
        # Numbers in the page body come from the JSON; only the 95% level and 0.05 appear in prose.
        body = re.sub(r"<(script|style)\b.*?</\1>", " ", PAGE, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", body)
        self.assertEqual([n for n in re.findall(r"\d[\d,.]*", text) if n not in ("95", "300", "325", "2016", "2024")], [])

    def test_listed_in_sitemap(self):
        self.assertIn("compare.html", (ROOT / "docs" / "sitemap.xml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
