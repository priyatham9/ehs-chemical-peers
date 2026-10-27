"""Peer-stability analysis: engine against a plain reference, known-answer toys,
determinism, and the committed outputs against the code and the docs.

The full build takes about two minutes, so it is only repeated when
CHEMPEERS_FULL_STABILITY=1 is set. Run: python3 -m unittest tests.test_stability
"""
import csv
import json
import math
import os
import random
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from chempeers import stability as S  # noqa: E402
import build_stability  # noqa: E402

PLANTS = json.loads((ROOT / "docs" / "data" / "plants.json").read_text(encoding="utf-8"))
OUT = json.loads((ROOT / "outputs" / "peer_stability.json").read_text(encoding="utf-8"))
GROUPS = json.loads((ROOT / "docs" / "data" / "stability.json").read_text(encoding="utf-8"))
with open(ROOT / "outputs" / "peer_stability.csv", encoding="utf-8", newline="") as fh:
    CSV = list(csv.DictReader(fh))
DOC = (ROOT / "docs" / "stability.md").read_text(encoding="utf-8")
PAGE = (ROOT / "docs" / "compare.html").read_text(encoding="utf-8")


def toy(specs):
    """specs: list of (count, product, family bitmask, size, inv)."""
    recs = []
    for n, prod, fam, size, inv in specs:
        for _ in range(n):
            recs.append({"id": "T%d" % len(recs), "name": "t", "state": "XX", "product": prod,
                         "fam": fam, "n_fam": bin(fam).count("1"), "size": size, "inv": inv})
    return recs


class Engine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recs, cls.skipped = S.features(PLANTS)
        cls.model = S.Model(cls.recs)

    def test_feature_records(self):
        self.assertEqual(len(self.recs) + self.skipped, len(PLANTS))
        self.assertEqual(self.skipped, sum(1 for p in PLANTS if p[13] is None))
        self.assertEqual(sum(len(m) for m in self.model.members), len(self.recs))

    def test_cells_cover_identical_plants_only(self):
        for c, members in enumerate(self.model.members):
            first = self.model.tuples[members[0]]
            for i in members:
                self.assertEqual(self.model.tuples[i], first)

    def test_cell_engine_matches_plain_reference(self):
        sample = random.Random(7).sample(range(self.model.n), 25)
        for scheme, r in (("tiebreak", -1), ("bootstrap", 0), ("bootstrap", 3), ("noise", 1)):
            w = S.weights_for(S.SEED, scheme, r)
            prio = S.priorities(S.SEED, scheme, max(r, 0), self.model.n)
            got = S.peers(self.model, w, prio)
            for i in sample:
                self.assertEqual(got[i], S.naive_peers(self.model, w, prio, i), (scheme, r, i))

    def test_peers_exclude_self_and_have_k(self):
        w = S.weights_for(S.SEED, "tiebreak", -1)
        got = S.peers(self.model, w, S.priorities(S.SEED, "base", 0, self.model.n))
        for i, p in enumerate(got):
            self.assertEqual(len(p), S.K)
            self.assertNotIn(i, p)
            self.assertEqual(len(set(p)), S.K)

    def test_bootstrap_weights_are_resampled_counts(self):
        for r in range(20):
            w = S.weights_for(S.SEED, "bootstrap", r)
            counts = [a / b for a, b in zip(w, S.BASE_WEIGHTS)]
            self.assertEqual(sum(counts), len(S.FEATURES))
            self.assertTrue(all(c == int(c) and c >= 0 for c in counts))
        zero = sum(1 for r in range(200) if 0 in S.weights_for(S.SEED, "bootstrap", r))
        self.assertGreater(zero, 150)  # 15 draws from 15 attributes almost never draw each once

    def test_noise_weights_positive_and_centred(self):
        logs = []
        for r in range(300):
            w = S.weights_for(S.SEED, "noise", r)
            self.assertTrue(all(x > 0 for x in w))
            logs.append(sum(math.log(a / b) for a, b in zip(w, S.BASE_WEIGHTS)) / len(w))
        self.assertAlmostEqual(sum(logs) / len(logs), 0.0, delta=0.05)

    def test_deterministic(self):
        sub = S.Model(self.recs[:400])
        a = S.rows(sub, S.run(sub, replicates=3))
        b = S.rows(sub, S.run(sub, replicates=3))
        self.assertEqual(a, b)
        c = S.rows(sub, S.run(sub, seed=S.SEED + 1, replicates=3))
        self.assertNotEqual(a, c)


class KnownAnswers(unittest.TestCase):
    def test_identical_twins_are_arbitrary(self):
        # 40 identical plants and nothing else: every peer is as close as any other.
        m = S.Model(toy([(40, "A", 0, 1, 0)]))
        res = S.run(m, replicates=60, k=5)
        exact = res["exact"]["tiebreak"]
        # expected overlap of two random 5-subsets of the other 39 is 5/39
        for v in exact:
            self.assertAlmostEqual(v, 5 / 39, delta=0.07)
        for v in res["neigh"]["bootstrap"] + res["neigh"]["noise"] + res["neigh"]["tiebreak"]:
            self.assertEqual(v, 1.0)  # everything is inside the all-tied neighbourhood
        self.assertEqual(res["ties"][0], 34)  # 39 others, 5 chosen

    def test_separated_clusters_keep_their_peers_under_noise(self):
        m = S.Model(toy([(6, "A", 1, 0, 0), (6, "B", 2, 4, 4)]))
        res = S.run(m, replicates=40, k=5)
        for v in res["neigh"]["noise"]:
            self.assertEqual(v, 1.0)
        for v in res["exact"]["noise"]:
            self.assertEqual(v, 1.0)  # 5 same-cluster peers of 5 other members: the only choice

    def test_dropping_the_deciding_attribute_loses_neighbourhood(self):
        # Plant 0 differs from group G only in product type; group H differs in size.
        specs = [(1, "A", 0, 2, 0), (8, "B", 0, 2, 0), (8, "A", 0, 4, 0)]
        m = S.Model(toy(specs))
        res = S.run(m, replicates=100, k=5)
        self.assertLess(res["neigh"]["bootstrap"][0], 0.95)
        self.assertGreater(res["neigh"]["bootstrap"][0], 0.0)

    def test_pair_distance(self):
        w = S.BASE_WEIGHTS
        a, b = ("A", 0b1, 0, 0), ("A", 0b11, 4, 2)
        # one family flag differs (1.0), size 4 levels apart (2.0 * 4/4), inventory 2 apart (1.0 * 2/4)
        self.assertAlmostEqual(S.pair_distance(w, (0, a[1], a[2], a[3]), (0, b[1], b[2], b[3])), 1.0 + 2.0 + 0.5)
        self.assertAlmostEqual(S.pair_distance(w, (0, 0, 0, 0), (1, 0, 0, 0)), 2.0)

    def test_levels(self):
        self.assertEqual([S.size_level(x) for x in (0, 49, 50, 99, 100, 250, 999, 1000, 9e5)], [0, 0, 1, 1, 2, 3, 3, 4, 4])
        self.assertEqual([S.inventory_level(x) for x in (None, 0, 5, 1e5, 1e6, 5e6)], [0, 0, 1, 2, 3, 4])

    def test_quantile(self):
        self.assertEqual(S.quantile([1, 2, 3, 4], 0.5), 2.5)
        self.assertEqual(S.quantile([5], 0.25), 5)


class CommittedOutputs(unittest.TestCase):
    def test_parameters_match_code(self):
        p = OUT["parameters"]
        self.assertEqual(p["seed"], S.SEED)
        self.assertEqual(p["k"], S.K)
        self.assertEqual(p["replicates_per_scheme"], S.REPLICATES)
        self.assertEqual(p["noise_sigma"], S.NOISE_SIGMA)
        self.assertEqual(p["features"], S.FEATURES)
        self.assertEqual(p["baseline_weights"], S.BASE_WEIGHTS)
        self.assertEqual(p["headline_schemes"], list(S.HEADLINE))

    def test_csv_covers_scored_plants(self):
        recs, skipped = S.features(PLANTS)
        self.assertEqual([r["id"] for r in CSV], [r["id"] for r in recs])
        cov = OUT["coverage"]
        self.assertEqual(cov["plants_scored"], len(CSV))
        self.assertEqual(cov["plants_skipped_no_employee_count"], skipped)
        self.assertEqual(cov["plants_in_file"], len(PLANTS))
        self.assertEqual(list(CSV[0]), build_stability.COLUMNS)

    def test_csv_values_in_range(self):
        for r in CSV:
            for c in build_stability.COLUMNS[8:14]:
                self.assertTrue(0.0 <= float(r[c]) <= 1.0, (r["id"], c))
            self.assertEqual(r["stability"], r["neighbourhood_bootstrap"])
            self.assertGreaterEqual(int(r["tied_at_kth"]), 0)
            # the neighbourhood score can never be below the exact score
            self.assertGreaterEqual(float(r["neighbourhood_bootstrap"]) + 1e-9, float(r["exact_bootstrap"]))
            self.assertGreaterEqual(float(r["neighbourhood_noise"]) + 1e-9, float(r["exact_noise"]))

    def test_summary_recomputes_from_csv(self):
        table = []
        for r in CSV:
            t = dict(r)
            for c in build_stability.COLUMNS[8:14]:
                t[c] = float(r[c])
            t["tied_at_kth"] = int(r["tied_at_kth"])
            table.append(t)
        self.assertEqual(S.summarise(table), OUT["summary"])

    def test_group_medians_recompute(self):
        table = [{"id": r["id"], "size_band": r["size_band"], "product_type": r["product_type"],
                  "stability": float(r["stability"])} for r in CSV]
        self.assertEqual(S.group_stability(table, PLANTS), GROUPS["groups"])

    def test_group_ids_exist_on_compare_page_data(self):
        ids = {g["id"] for g in json.loads((ROOT / "docs" / "data" / "compare.json").read_text(encoding="utf-8"))["groups"]}
        shared = set(GROUPS["groups"]) & ids
        self.assertTrue(any(i.startswith("inj-size-") for i in shared))
        self.assertTrue(any(i.startswith("rel-fam-") for i in shared))

    def test_page_reads_the_file(self):
        self.assertIn('fetch("data/stability.json")', PAGE)
        self.assertIn("Peer stability", PAGE)

    @unittest.skipUnless(os.environ.get("CHEMPEERS_FULL_STABILITY") == "1", "set CHEMPEERS_FULL_STABILITY=1 (about two minutes)")
    def test_committed_files_match_fresh_build(self):
        table, doc, groups = build_stability.build(PLANTS)
        self.assertEqual(build_stability.render_csv(table), (ROOT / "outputs" / "peer_stability.csv").read_text(encoding="utf-8"))
        self.assertEqual(doc, OUT)
        self.assertEqual(groups, GROUPS)


class DocClaims(unittest.TestCase):
    def test_numbers_quoted_in_docs(self):
        s = OUT["summary"]
        ov = s["overall"]
        claims = [
            "The median `stability` is %.3f (middle half %.3f to %.3f)" % (ov["median"], ov["q25"], ov["q75"]),
            "%.2f%% of plants score at least 0.5" % (100 * s["share_stability_at_least_0_5"]),
            "the median neighbourhood score is %.3f" % s["neighbourhood_noise"]["median"],
            "median exact retention is %.3f under `bootstrap` and %.3f even under `tiebreak`" % (
                s["exact_bootstrap"]["median"], s["exact_tiebreak_only"]["median"]),
            "the median plant has %d other plants exactly" % s["tied_at_kth"]["median"],
            "%s of the %s plants have 100 or more" % (
                format(sum(1 for r in CSV if int(r["tied_at_kth"]) >= 100), ","), format(len(CSV), ",")),
            "(%s plants with an employee count)" % format(len(CSV), ","),
            "Plants without an employee count (%d)" % OUT["coverage"]["plants_skipped_no_employee_count"],
        ]
        for c in claims:
            self.assertIn(c, DOC)
        self.assertEqual(s["share_stability_at_least_0_9"], 0.0)
        by = s["by_size_band"]
        want = "Under 50, %.3f; 50-99, %.3f; 100-249, %.3f; 250-999, %.3f; 1,000+, %.3f" % tuple(
            by[b]["median"] for b in ("Under 50", "50-99", "100-249", "250-999", "1,000+"))
        self.assertIn(want, DOC)
        self.assertTrue(re.search(r"100 replicates", DOC))


if __name__ == "__main__":
    unittest.main()
