"""Real-data checks. Skipped when data/raw has not been downloaded."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
sys.path.insert(0, str(ROOT / "src"))

from chempeers import analysis, build  # noqa: E402

HAVE = (RAW / "facilities.csv").exists() and any(RAW.glob("ITA*.zip"))


@unittest.skipUnless(HAVE, "data/raw not downloaded (make data)")
class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plants, cls.releases, cls.injuries, cls.stats = build.assemble(RAW)
        cls.summary = analysis.findings(cls.plants, cls.releases, cls.injuries, cls.stats)

    def test_rebuild_matches_committed_summary(self):
        committed = json.loads((ROOT / "outputs" / "summary.json").read_text())
        self.assertEqual(json.loads(json.dumps(self.summary)), committed)

    def test_site_data_carries_same_summary(self):
        meta = json.loads((ROOT / "docs" / "data" / "meta.json").read_text())
        committed = json.loads((ROOT / "outputs" / "summary.json").read_text())
        self.assertEqual(meta["summary"], committed)

    def test_every_plant_is_chemical_manufacturing(self):
        for p in self.plants.values():
            codes = [p["naics"]] + [y["naics"] for y in p["years"].values()]
            self.assertTrue(any(str(c).startswith("325") for c in codes), p["id"])

    def test_injury_rates_use_screened_years_only(self):
        for p in self.plants.values():
            for y in p["years"].values():
                if y["plausible"]:
                    self.assertGreaterEqual(y["hours"] / y["emp"], 120)
                    self.assertLessEqual(y["hours"] / y["emp"], 4500)

    def test_releases_point_at_epa_plants(self):
        for r in self.releases:
            self.assertTrue(r["plant"].startswith("R"))
            self.assertIsNotNone(self.plants[r["plant"]]["rmp_id"])


if __name__ == "__main__":
    unittest.main()
