"""The README quotes numbers from outputs/summary.json; this test keeps them honest."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def get(d, path):
    for part in re.findall(r"[^.\[\]]+", path):
        d = d[int(part)] if part.isdigit() else d[part]
    return d


# (text as written in the README, summary path, digits)
CLAIMS = [
    ("{} chemical plants", "coverage.plants", 0),
    ("{} EPA-registered, ", "coverage.rmp_plants", 0),
    ("{} filing OSHA injury logs", "coverage.osha_plants", 0),
    ("median of {} hours a year", "size_noise[1].median_hours", 0),
    ("rate by {} points", "size_noise[1].one_case_swing", 2),
    ("In {}% of those plant-years", "size_noise[1].zero_share_pct", 2),
    ("next is {} for plants under 50", "stability[0].rho", 3),
    ("and {} for 50-99", "stability[1].rho", 3),
    ("against {} for plants of 1,000", "stability[4].rho", 3),
    ("the next year in {}% of plant-years; those above it", "trir_vs_outcomes.release_next_year[1].below_median.pct", 1),
    ("those above it, {}%.", "trir_vs_outcomes.release_next_year[1].above_median.pct", 1),
    ("the next year in {}% of plant-years, against", "release_predictors.history.release_in_past_5y.pct", 2),
    ("against {}% for plants without one", "release_predictors.history.no_release_in_past_5y.pct", 2),
    ("({} times as often)", "release_predictors.history_ratio", 1),
    ("or more of regulated chemicals: {}%", "release_predictors.inventory[3].pct", 2),
    ("Under 100,000 lb: {}%", "release_predictors.inventory[0].pct", 1),
    ("{}% of serious injuries", "green_dashboard.prior_year_zero_pct", 2),
    ("Search any of the {} plants", "coverage.plants", 0),
    ("| {} establishment-years", "coverage.ita_plant_years", 0),
    ("| {} facilities, ", "coverage.rmp_plants", 0),
    (", {} releases |", "coverage.releases", 0),
    ("| {} reports |", "coverage.serious_injuries", 0),
    ("{}% of EPA-registered chemical plants join", "coverage.rmp_linked_pct", 2),
    ("and {}% of serious-injury reports join", "coverage.serious_injuries_linked_pct", 2),
]


def fmt(v, digits):
    if digits == 0:
        return "{:,}".format(int(round(v)))
    s = "{:.{d}f}".format(v, d=digits)
    return s.rstrip("0").rstrip(".") if digits and "." in s and s.endswith("0") and digits > 1 else s


class ReadmeNumbers(unittest.TestCase):
    def test_claims_match_summary(self):
        summary_path = ROOT / "outputs" / "summary.json"
        if not summary_path.exists():
            self.skipTest("outputs/summary.json not built")
        summary = json.loads(summary_path.read_text())
        readme = (ROOT / "README.md").read_text()
        for template, path, digits in CLAIMS:
            value = get(summary, path)
            options = {fmt(value, digits), "{:.{d}f}".format(value, d=digits) if digits else fmt(value, 0)}
            ok = any(template.format(o) in readme for o in options)
            with self.subTest(path=path):
                self.assertTrue(ok, "README should say %r with %s = %r" % (template, path, value))


if __name__ == "__main__":
    unittest.main()
