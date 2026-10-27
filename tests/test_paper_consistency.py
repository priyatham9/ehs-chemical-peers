"""docs/paper.md quotes numbers from outputs/summary.json; this test keeps them honest.

Two checks: the generated tables match what scripts/paper_tables.py renders
from the summary, and every number quoted in the prose matches the summary.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import paper_tables  # noqa: E402
from test_readme_consistency import get  # noqa: E402

PAPER = ROOT / "docs" / "paper.md"
SUMMARY = ROOT / "outputs" / "summary.json"

# (text as written in the paper, summary path, digits); digits=0 means a count with commas
CLAIMS = [
    # abstract
    ("The result covers {} plants", "coverage.plants", 0),
    ("{}% of the 2,773 RMP-registered plants", "coverage.rmp_linked_pct", 2),
    ("of the {} RMP-registered plants join", "coverage.rmp_plants", 0),
    ("({} points at the median plant under 50", "size_noise[0].one_case_swing", 2),
    ("rate is {} for those plants against", "stability[0].rho", 3),
    ("against {} for plants of 1,000 or more. Second", "stability[4].rho", 3),
    ("below the median rate had a release in {}% of plant-years and plants above it in",
     "trir_vs_outcomes.release_next_year[1].below_median.pct", 1),
    ("and plants above it in {}%. Third", "trir_vs_outcomes.release_next_year[1].above_median.pct", 1),
    ("had one in {}% of plant-years against", "release_predictors.history.release_in_past_5y.pct", 2),
    ("against {}% for plants without (8.2 times",
     "release_predictors.history.no_release_in_past_5y.pct", 2),
    ("for plants without ({} times as often)", "release_predictors.history_ratio", 1),
    ("regulated chemicals had one in {}% against", "release_predictors.inventory[3].pct", 2),
    ("against {}% for plants under 100,000 lb", "release_predictors.inventory[0].pct", 1),
    # data
    ("Of the {} serious-injury reports, 63.25%", "coverage.serious_injuries", 0),
    ("serious-injury reports, {}% join to a known plant", "coverage.serious_injuries_linked_pct", 2),
    # 4.1
    ("under 50 employees worked {} hours", "size_noise[0].median_hours", 0),
    ("moves its rate by {} points, larger", "size_noise[0].one_case_swing", 2),
    ("pooled rate for that band ({})", "size_noise[0].pooled_trir", 2),
    ("In {}% of those plant-years the plant recorded no cases", "size_noise[0].zero_share_pct", 2),
    ("the median is {} hours", "size_noise[1].median_hours", 0),
    ("the one-case swing is {} points, and", "size_noise[1].one_case_swing", 2),
    ("and {}% of plant-years have zero cases. At 1,000", "size_noise[1].zero_share_pct", 2),
    ("the swing is {} points and", "size_noise[4].one_case_swing", 2),
    ("points and {}% of plant-years have zero cases.", "size_noise[4].zero_share_pct", 2),
    ("with size from {} for plants under 50", "stability[0].rho", 3),
    ("and {} for 50-99 to", "stability[1].rho", 3),
    ("to {} for plants of 1,000 or more. A ranking", "stability[4].rho", 3),
    # 4.2
    ("for {} observed plant-years", "trir_vs_outcomes.release_plant_years", 0),
    ("release in {}% of plant-years and plants above it in 1.80%",
     "trir_vs_outcomes.release_next_year[0].below_median.pct", 2),
    ("plants above it in {}%. At 100-249", "trir_vs_outcomes.release_next_year[0].above_median.pct", 2),
    ("the figures are {}% and", "trir_vs_outcomes.release_next_year[1].below_median.pct", 1),
    ("and {}%; at 250 or more", "trir_vs_outcomes.release_next_year[1].above_median.pct", 1),
    ("at 250 or more, {}% and", "trir_vs_outcomes.release_next_year[2].below_median.pct", 2),
    ("and {}%. The groups are small", "trir_vs_outcomes.release_next_year[2].above_median.pct", 2),
    ("rests on {} and", "trir_vs_outcomes.release_next_year[1].below_median.events", 0),
    ("and {} releases. Release shares", "trir_vs_outcomes.release_next_year[1].above_median.events", 0),
    # 4.3
    ("(Table 5, {} plant-years", "trir_vs_outcomes.sir_plant_years", 0),
    ("at 100-249 employees, {}%,", "trir_vs_outcomes.serious_injury_next_year[1].zero_cases.pct", 2),
    ("{}% and 5.1%;", "trir_vs_outcomes.serious_injury_next_year[1].below_median.pct", 2),
    ("and {}%; at 250", "trir_vs_outcomes.serious_injury_next_year[1].above_median.pct", 1),
    ("at 250 or more, {}%, 6.15%", "trir_vs_outcomes.serious_injury_next_year[2].zero_cases.pct", 2),
    ("{}% and 7.25%", "trir_vs_outcomes.serious_injury_next_year[2].below_median.pct", 2),
    ("and {}%. Under 100", "trir_vs_outcomes.serious_injury_next_year[2].above_median.pct", 2),
    ("does not hold ({}%,", "trir_vs_outcomes.serious_injury_next_year[0].zero_cases.pct", 2),
    ("{}% and 1.54%)", "trir_vs_outcomes.serious_injury_next_year[0].below_median.pct", 2),
    ("and {}%). A higher", "trir_vs_outcomes.serious_injury_next_year[0].above_median.pct", 2),
    ("of the {} serious injuries at joined plants", "green_dashboard.serious_injuries_with_prior_year", 0),
    ("filing, {} (18.21%)", "green_dashboard.prior_year_zero", 0),
    ("(" + "{}%) occurred", "green_dashboard.prior_year_zero_pct", 2),
    # 4.4
    ("Across {} observed RMP plant-years", "release_predictors.plant_years", 0),
    ("plant-years, {}% had at least one", "release_predictors.base.pct", 2),
    ("had one in {}% of cases", "release_predictors.history.release_in_past_5y.pct", 2),
    ("against {}% for plant-years without", "release_predictors.history.no_release_in_past_5y.pct", 2),
    ("a ratio of {}.", "release_predictors.history_ratio", 1),
    ("from {}% for plants holding under", "release_predictors.inventory[0].pct", 1),
    ("to {}% for plants holding 5 million", "release_predictors.inventory[3].pct", 2),
    ("from {}% for plants with one", "release_predictors.chemical_count[0].pct", 2),
    ("to {}% for plants with five or more", "release_predictors.chemical_count[3].pct", 2),
    ("sulfur compounds ({}%)", "release_predictors.family[10].pct", 2),
    ("the epoxy chain ({}%)", "release_predictors.family[1].pct", 2),
    ("strong acids ({}%)", "release_predictors.family[4].pct", 2),
    ("isocyanates ({}%)", "release_predictors.family[5].pct", 2),
    # 4.5
    ("The {} RMP accident records", "release_anatomy_all.releases", 0),
    ("report {} worker injuries", "release_anatomy_all.worker_injuries", 0),
    ("Gas releases ({})", "release_anatomy_all.type[1].n", 0),
    ("liquid spills ({}).", "release_anatomy_all.type[0].n", 0),
    ("equipment failure ({})", "release_anatomy_all.cause[0].n", 0),
    ("human error ({})", "release_anatomy_all.cause[1].n", 0),
    ("better equipment ({})", "release_anatomy_all.fix[0].n", 0),
    ("rewritten procedures ({})", "release_anatomy_all.fix[1].n", 0),
    ("retraining ({})", "release_anatomy_all.fix[2].n", 0),
    ("reported {} times", "release_anatomy_all.fix[8].n", 0),
    ("For the {} releases involving formaldehyde", "release_anatomy_formaldehyde.releases", 0),
    ("liquid spills ({}) outnumber", "release_anatomy_formaldehyde.type[0].n", 0),
    ("gas releases ({}), and", "release_anatomy_formaldehyde.type[1].n", 0),
    ("and {} involved a runaway", "release_anatomy_formaldehyde.type[4].n", 0),
    ("reports, {} involved an amputation and", "injury_anatomy_all.amputations", 0),
    ("and {} an in-patient", "injury_anatomy_all.hospitalizations", 0),
    ("largest group ({})", "injury_anatomy_all.energy[0].n", 0),
    ("falls ({})", "injury_anatomy_all.energy[4].n", 0),
    ("chemical exposure ({})", "injury_anatomy_all.energy[2].n", 0),
    ("{} of 290 reports", "injury_anatomy_resins.amputations", 0),
    ("114 of {} reports", "injury_anatomy_resins.events", 0),
    # limitations
    ("Only {}% of RMP plants join", "coverage.rmp_linked_pct", 2),
]


def forms(v, digits):
    """Accepted spellings: '1,913'; or '3.4', '3.40' and the stored repr for decimals."""
    if digits == 0:
        return {"{:,}".format(int(round(v)))}
    out = {"{:.{d}f}".format(v, d=d) for d in range(digits, 4)}
    out.add(repr(float(v)).rstrip("0").rstrip("."))
    return out


class PaperNumbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SUMMARY.exists() or not PAPER.exists():
            raise unittest.SkipTest("outputs/summary.json or docs/paper.md missing")
        cls.summary = json.loads(SUMMARY.read_text())
        cls.paper = PAPER.read_text()

    def test_tables_match_summary(self):
        rendered, seen = paper_tables.render(self.paper, self.summary)
        self.assertEqual(sorted(seen), sorted(paper_tables.TABLES), "a table marker is missing")
        self.assertEqual(rendered, self.paper,
                         "tables are stale; run python3 scripts/paper_tables.py")

    def test_prose_claims_match_summary(self):
        for template, path, digits in CLAIMS:
            value = get(self.summary, path)
            ok = any(template.format(o) in self.paper for o in forms(value, digits))
            with self.subTest(path=path, text=template):
                self.assertTrue(ok, "paper should say %r with %s = %r" % (template, path, value))

    def test_no_em_or_en_dashes(self):
        self.assertNotIn("—", self.paper)
        self.assertNotIn("–", self.paper)

    def test_citations_and_references_agree(self):
        body, _sep, refs = self.paper.partition("\n## References\n")
        self.assertTrue(refs, "paper has no References section")
        keys = set(re.findall(r"^\[([^\]]+)\]", refs, re.M))
        # bracketed citations in the body: [KEY], [KEY; KEY] or Author [YEAR]
        cited = set()
        for m in re.finditer(r"([A-Z][\w.,' ]*?)? ?\[([^\]]+)\](?!\()", body):
            for part in m.group(2).split("; "):
                if re.fullmatch(r"\d{4}", part):
                    lead = (m.group(1) or "").strip()
                    part = next((k for k in keys if k.endswith(" " + part) and lead.endswith(
                        k[:-5].split(" ")[-1])), lead + " " + part)
                cited.add(part)
        for c in sorted(cited):
            with self.subTest(cited=c):
                self.assertIn(c, keys, "cited in the text but not in References")
        for k in sorted(keys):
            with self.subTest(reference=k):
                self.assertIn(k, cited, "listed in References but never cited")

if __name__ == "__main__":
    unittest.main()
