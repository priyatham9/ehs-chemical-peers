"""Pipeline tests on the synthetic fixture (no network, no real data needed)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _fixture  # noqa: E402
from chempeers import analysis, build, events, export, load, taxonomy  # noqa: E402
from chempeers import stats as S  # noqa: E402
from chempeers.link import AddressIndex, state_code  # noqa: E402


class FixturePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        raw = _fixture.build(Path(cls.tmp.name) / "raw")
        cls.plants, cls.releases, cls.injuries, cls.stats = build.assemble(raw)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_non_chemical_rmp_facility_dropped(self):
        self.assertNotIn("R902", self.plants)
        self.assertEqual(len(self.releases), 1)

    def test_address_join(self):
        a = self.plants["R900"]
        self.assertEqual(a["match"], "address")
        self.assertEqual(sorted(a["years"]), [2018, 2019, 2020])
        self.assertEqual(a["subsectors"][0], "Resins & plastics")
        self.assertIn("Other basic organics (incl. formaldehyde)", a["subsectors"])
        self.assertEqual(a["families"], ["Formaldehyde", "Ammonia"])
        self.assertEqual(a["inventory_lb"], 3200000)

    def test_name_join_when_street_differs(self):
        c = self.plants["R901"]
        self.assertEqual(c["match"], "zip+name")
        self.assertEqual(len(c["years"]), 3)

    def test_osha_only_plant(self):
        b = self.plants["I2"]
        self.assertEqual(b["match"], "osha only")
        self.assertFalse(b["years"][2021]["plausible"])
        self.assertTrue(b["years"][2019]["plausible"])

    def test_release_coding(self):
        r = self.releases[0]
        self.assertEqual(r["plant"], "R900")
        self.assertEqual([events.RELEASE_TYPE[i][1] for i in r["type"]], ["Liquid spill"])
        self.assertEqual([events.RELEASE_CAUSE[i][1] for i in r["cause"]], ["Human error"])
        self.assertEqual(r["worker_inj"], 1)

    def test_serious_injuries(self):
        self.assertEqual(len(self.injuries), 2)  # bakery is not NAICS 325
        first = self.injuries[0]
        self.assertEqual(first["plant"], "R900")
        self.assertEqual(first["state"], "TX")
        self.assertEqual(first["energy"], "Caught in machinery")
        self.assertIsNone(self.injuries[1]["plant"])
        self.assertEqual(self.stats["sir_matched"], 1)

    def test_findings_and_export(self):
        f = analysis.findings(self.plants, self.releases, self.injuries, self.stats)
        self.assertEqual(f["coverage"]["rmp_plants"], 2)
        self.assertEqual(f["coverage"]["linked_plants"], 2)
        self.assertEqual(f["release_anatomy_formaldehyde"]["releases"], 1)
        self.assertEqual(f["green_dashboard"]["serious_injuries_with_prior_year"], 1)
        self.assertEqual(f["green_dashboard"]["prior_year_zero"], 0)  # 2019 had one case
        with tempfile.TemporaryDirectory() as d:
            export.write(d, self.plants, self.releases, self.injuries, f, {})
            meta = json.loads((Path(d) / "meta.json").read_text())
            plants = json.loads((Path(d) / "plants.json").read_text())
            self.assertEqual(len(plants[0]), len(meta["plant_cols"]))
            self.assertEqual(len(plants), len(self.plants))


class Stats(unittest.TestCase):
    def test_poisson_cdf_known_values(self):
        self.assertAlmostEqual(S.poisson_cdf(0, 1.0), 0.36787944, places=6)
        self.assertAlmostEqual(S.poisson_cdf(2, 3.0), 0.42319008, places=6)
        self.assertAlmostEqual(S.poisson_cdf(1500, 1500.0), 0.50687, places=3)

    def test_quantile_inverts_cdf(self):
        for mu in (0.2, 1.5, 7.0, 40.0):
            for p in (0.025, 0.5, 0.975):
                k = S.poisson_quantile(p, mu)
                self.assertGreaterEqual(S.poisson_cdf(k, mu), p)
                if k:
                    self.assertLess(S.poisson_cdf(k - 1, mu), p)

    def test_funnel_narrows_with_hours(self):
        small = S.funnel_limits(2.0, 100000)
        big = S.funnel_limits(2.0, 10000000)
        self.assertGreater(small[1] - small[0], big[1] - big[0])
        self.assertEqual(small[0], 0.0)

    def test_classify(self):
        self.assertEqual(S.classify(3, 1220928, 2.01), "below")
        self.assertEqual(S.classify(12, 1220928, 2.01), "within")
        self.assertEqual(S.classify(40, 1220928, 2.01), "above")

    def test_rate_and_swing(self):
        self.assertAlmostEqual(S.rate(1, 200000), 1.0)
        self.assertIsNone(S.rate(1, 0))
        self.assertAlmostEqual(S.one_case_swing(100000), 2.0)

    def test_spearman(self):
        self.assertAlmostEqual(S.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(S.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)
        self.assertIsNone(S.spearman([1, 2], [1, 2]))


class Labels(unittest.TestCase):
    def test_subsector(self):
        self.assertEqual(taxonomy.subsector("325211.00"), "Resins & plastics")
        self.assertEqual(taxonomy.subsector("325188"), "Acids & inorganics")
        self.assertEqual(taxonomy.subsector("32519"), "Other basic organics (incl. formaldehyde)")
        self.assertEqual(taxonomy.subsector("325193"), "Ethanol & biofuels")
        self.assertEqual(taxonomy.subsector("311812"), "")

    def test_families_do_not_confuse_oxides_with_flammables(self):
        self.assertEqual(taxonomy.families(["Ethylene oxide [Oxirane]"]), ["Reactive oxides"])
        self.assertEqual(taxonomy.families(["Ethylene oxide", "Ethylene [Ethene]"]),
                         ["Reactive oxides", "Flammable gases & liquids"])
        self.assertIn("Strong acids", taxonomy.families(["Hydrogen fluoride/Hydrofluoric acid"]))

    def test_energy(self):
        self.assertEqual(events.energy("6411"), "Caught in machinery")
        self.assertEqual(events.energy("5311"), "Heat, steam & hot material")
        self.assertEqual(events.energy("4212"), "Slip, trip or fall")
        self.assertEqual(events.energy("6200", "Forklift"), "Vehicle or forklift")
        self.assertEqual(events.energy(""), "Unclassified")

    def test_parse_chemicals(self):
        self.assertEqual(load.parse_chemicals("Chlorine {70000} • Ammonia  (anhydrous) {5}"),
                         [("Chlorine", 70000.0), ("Ammonia (anhydrous)", 5.0)])

    def test_state_code_and_index(self):
        self.assertEqual(state_code("NORTH CAROLINA"), "NC")
        self.assertEqual(state_code("nc"), "NC")
        ix = AddressIndex()
        ix.add("a", "28301", "1411 Industrial Drive", ("Plant One Inc",))
        self.assertEqual(ix.find("28301", "1411 Industrial Dr", ("x",)), ("a", "address"))
        self.assertEqual(ix.find("28301", "9 Other", ("Plant One",)), ("a", "zip+name"))
        self.assertEqual(ix.find("28301", "9 Other", ("Unrelated",)), (None, None))


if __name__ == "__main__":
    unittest.main()
