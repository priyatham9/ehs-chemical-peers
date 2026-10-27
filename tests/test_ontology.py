"""Ontology layer: spec, materialisation from committed data, links, actions, functions, export."""
import contextlib
import copy
import io
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _fixture  # noqa: E402
from chempeers import analysis, build  # noqa: E402
from chempeers.ontology import ActionRejected, SpecError, load_spec  # noqa: E402
from chempeers.ontology import functions as F  # noqa: E402
from chempeers.ontology.__main__ import main as ontology_main  # noqa: E402
from chempeers.ontology.export import export_json, export_sqlite  # noqa: E402
from chempeers.ontology.materialise import (  # noqa: E402
    MATCH_CONFIDENCE, SOURCE_COMMITTED, SOURCE_FIXTURE, build_store, load_committed)
from chempeers.ontology.spec import SPEC_PATH, validate  # noqa: E402

SUMMARY = json.loads((ROOT / "outputs" / "summary.json").read_text())
COV = SUMMARY["coverage"]
PINNED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

_STORE = None


def committed_store():
    """One shared read-only store built from the committed site data."""
    global _STORE
    if _STORE is None:
        _STORE = build_store()
    return _STORE


def plain(x):
    return json.loads(json.dumps(x))


class Spec(unittest.TestCase):
    def test_bundled_spec_is_valid(self):
        spec = load_spec()
        self.assertEqual(len(spec.object_types), 12)
        self.assertEqual(len(spec.link_types), 15)
        self.assertEqual(len(spec.action_types), 4)
        self.assertEqual(len(spec.functions), 6)
        self.assertEqual(set(spec.functions), set(F.REGISTRY))
        self.assertIn("not affiliated with Palantir", spec.raw["ontology"]["description"])

    def test_rmp_osha_link_carries_method_and_confidence(self):
        lk = load_spec().link_types["rmp_osha_match"]
        self.assertEqual(lk["cardinality"], "many_to_many")
        self.assertEqual(lk["through"], "PlantMatch")
        self.assertEqual(lk["link_properties"], ["match_method", "confidence", "review_status"])

    def test_broken_spec_reports_every_error(self):
        raw = json.loads(SPEC_PATH.read_text())
        bad = copy.deepcopy(raw)
        objs = {o["api_name"]: o for o in bad["object_types"]}
        props = {p["api_name"]: p for p in objs["Plant"]["properties"]}
        props["plant_id"]["editable"] = True
        props["state"]["editable"] = False
        links = {lk["api_name"]: lk for lk in bad["link_types"]}
        links["accident_registration"]["foreign_key"] = "year"
        links["rmp_osha_match"]["link_properties"].append("no_such_property")
        acts = {a["api_name"]: a for a in bad["action_types"]}
        acts["mark_plant_for_review"]["edits"][0]["set"]["state"] = "XX"
        acts["reject_match"]["edits"][0]["set"]["review_note"] = "$missing"
        bad["functions"][0]["reuses"] = "chempeers.analysis.no_such_function"
        errors = validate(bad)
        for fragment in ("primary key 'plant_id' must be non-nullable and not editable",
                         "Accident.year type 'integer' does not match RmpRegistration key",
                         "link property 'no_such_property' is not on PlantMatch",
                         "Plant.state is not editable",
                         "$missing is not a parameter",
                         "does not resolve to existing code"):
            self.assertTrue(any(fragment in e for e in errors), (fragment, errors))
        with self.assertRaises(SpecError) as ctx:
            load_spec(bad)
        self.assertEqual(ctx.exception.errors, errors)


class CommittedJoin(unittest.TestCase):
    """Counts and join integrity against the committed coverage numbers."""

    @classmethod
    def setUpClass(cls):
        cls.store = committed_store()

    def count(self, t):
        return self.store.objects(t).count()

    def test_object_counts_match_committed_coverage(self):
        self.assertEqual(self.count("Plant"), COV["plants"])
        self.assertEqual(self.count("RmpRegistration"), COV["rmp_plants"])
        self.assertEqual(self.count("OshaEstablishment"), COV["osha_plants"])
        self.assertEqual(self.count("PlantMatch"), COV["linked_plants"])
        self.assertEqual(self.count("Accident"), COV["releases"])
        self.assertEqual(self.count("SeriousInjury"), COV["serious_injuries"])
        # plant-years after two filings for one plant-year are collapsed
        self.assertLessEqual(self.count("InjuryLogYear"), COV["ita_plant_years"])

    def test_link_integrity(self):
        rep = self.store.integrity_report()
        for name, counts in rep.items():
            self.assertEqual(counts["dangling"], 0, name)
            self.assertEqual(counts.get("duplicate_targets", 0), 0, name)
        self.assertEqual(rep["serious_injury_plant"]["resolved"], COV["serious_injuries_linked"])
        self.assertEqual(rep["serious_injury_plant"]["null"],
                         COV["serious_injuries"] - COV["serious_injuries_linked"])
        self.assertEqual(rep["rmp_osha_match"], {"resolved": COV["linked_plants"], "hidden": 0, "dangling": 0})
        self.assertEqual(rep["accident_registration"]["resolved"], COV["releases"])

    def test_match_method_and_confidence(self):
        matches = self.store.objects("PlantMatch").to_records()
        methods = Counter(m["match_method"] for m in matches)
        plants = Counter(p["match_method"] for p in self.store.objects("Plant").to_records())
        for method in MATCH_CONFIDENCE:
            self.assertEqual(methods[method], plants[method])
        self.assertEqual(sum(methods.values()), COV["linked_plants"])
        self.assertTrue(all(m["confidence"] == MATCH_CONFIDENCE[m["match_method"]] for m in matches))
        self.assertEqual(plants["epa only"] + len(matches), COV["rmp_plants"])
        self.assertEqual(plants["osha only"] + len(matches), COV["osha_plants"])

    def test_provenance(self):
        self.assertEqual({p["source"] for p in self.store.objects("Plant").to_records()}, {SOURCE_COMMITTED})
        self.assertEqual({b["source"] for b in self.store.objects("SizeBand").to_records()}, {"committed_summary"})

    def test_size_bands_are_committed_findings(self):
        for row in SUMMARY["size_noise"]:
            band = self.store.get("SizeBand", row["band"])
            self.assertEqual(band["plant_years"], row["plant_years"])
            self.assertEqual(band["one_case_swing"], row["one_case_swing"])
        self.assertEqual(self.store.get("SizeBand", "Under 50")["stability_rho"], SUMMARY["stability"][0]["rho"])


class Functions(unittest.TestCase):
    """Functions reuse the pipeline and reproduce outputs/summary.json."""

    @classmethod
    def setUpClass(cls):
        cls.store = committed_store()

    def test_coverage(self):
        got = F.coverage(self.store)
        for key, value in COV.items():
            if key != "ita_plant_years":
                self.assertEqual(got[key], value, key)

    def test_findings_match_summary(self):
        self.assertEqual(plain(F.size_noise(self.store)), SUMMARY["size_noise"])
        self.assertEqual(plain(F.release_predictors(self.store)), SUMMARY["release_predictors"])
        self.assertEqual(plain(F.green_dashboard(self.store)), SUMMARY["green_dashboard"])

    def test_plant_rates_and_funnel(self):
        plant = next(p for p in self.store.objects("Plant").where(match_method="address")
                     if F.plant_rates(self.store, p)["hours"] > 0)
        r = F.plant_rates(self.store, plant)
        self.assertAlmostEqual(r["trir"], r["cases"] * 200000.0 / r["hours"])
        pos = F.funnel_position(self.store, plant)
        self.assertIn(pos["status"], ("above", "below", "within"))
        self.assertLessEqual(pos["low"], pos["high"])
        group = self.store.linked(plant, "peer_group").one()
        self.assertEqual(pos["n_peers"], group["n_plants"] - 1)


class Links(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = committed_store()

    def test_traverse_both_directions(self):
        s = self.store
        acc = next(iter(s.objects("Accident")))
        reg = s.linked(acc, "registration").one()
        plant = s.linked(reg, "plant").one()
        self.assertEqual(plant.primary_key, "R" + reg.primary_key)
        self.assertIn(acc.primary_key, s.linked(reg, "accidents").primary_keys())
        self.assertEqual(s.linked(plant, "rmp_registration").one().primary_key, reg.primary_key)
        self.assertEqual(s.linked(acc, "chemicals_released").primary_keys(), list(dict.fromkeys(acc["chemicals"])))

    def test_match_link_properties(self):
        s = self.store
        m = next(iter(s.objects("PlantMatch").where(match_method="zip+name")))
        reg = s.linked(m, "registration").one()
        rows = s.link_rows(reg, "osha_establishments")
        self.assertEqual([r["object"].primary_key for r in rows], [m["osha_key"]])
        self.assertEqual(rows[0]["link_properties"],
                         {"match_method": "zip+name", "confidence": "low", "review_status": "unreviewed"})
        est = rows[0]["object"]
        self.assertEqual(s.linked(est, "rmp_registrations").primary_keys(), [reg.primary_key])
        self.assertEqual(s.linked(est, "plant").one()["plant_id"], reg["plant_id"])
        with self.assertRaises(TypeError):
            s.link_rows(reg, "accidents")
        with self.assertRaises(KeyError):
            s.linked(reg, "no_such_link")

    def test_search_around_and_read_only(self):
        s = self.store
        ests = s.objects("RmpRegistration").search_around("osha_establishments")
        self.assertEqual(ests.count(), COV["linked_plants"])
        self.assertEqual(ests.search_around("log_years").count(),
                         sum(e["n_log_years"] for e in ests))
        holders = s.objects("Chemical").where(chemical_name="Chlorine").search_around("holdings")
        self.assertGreater(holders.count(), 0)
        plant = next(iter(s.objects("Plant")))
        with self.assertRaises(TypeError):
            plant.properties["name"] = "x"


class Actions(unittest.TestCase):
    """Actions on a private store so the shared one stays untouched."""

    @classmethod
    def setUpClass(cls):
        cls.store = build_store(clock=lambda: PINNED)

    def test_reject_match_hides_link_and_moves_numbers(self):
        s = self.store
        m = next(iter(s.objects("PlantMatch").where(match_method="address+name")))
        reg = s.linked(m, "registration").one()
        plant = s.linked(reg, "plant").one()
        self.assertTrue(F._log_years(s, plant))
        entry = s.apply("reject_match", {"match": m, "reason": "different_operator_at_shared_address"},
                        actor="reviewer@example.org")
        self.assertEqual(entry.timestamp, PINNED.isoformat())
        self.assertEqual(s.get("PlantMatch", m.primary_key)["review_status"], "rejected")
        self.assertEqual(s.edit_history("PlantMatch", m.primary_key)[0]["before"], "unreviewed")
        self.assertEqual(s.linked(reg, "osha_establishments").count(), 0)
        self.assertEqual(len(s.link_rows(reg, "osha_establishments", include_hidden=True)), 1)
        self.assertEqual(s.integrity_report()["rmp_osha_match"]["hidden"], 1)
        self.assertEqual(F._log_years(s, plant), {})
        cov = F.coverage(s)
        self.assertEqual(cov["linked_plants"], COV["linked_plants"] - 1)
        self.assertEqual(cov["plants"], COV["plants"] + 1)
        self.assertEqual(cov["osha_plants"], COV["osha_plants"])
        self.assertEqual(cov["rmp_linked_pct"], round(100.0 * (COV["linked_plants"] - 1) / COV["rmp_plants"], 2))
        self.assertEqual(F.coverage(s, respect_reviews=False)["linked_plants"], COV["linked_plants"])
        n = len(s.action_log)
        with self.assertRaises(ActionRejected) as ctx:
            s.apply("reject_match", {"match": m.primary_key, "reason": "name_match_wrong"}, actor="a")
        self.assertEqual(ctx.exception.errors, ["Match is already rejected."])
        with self.assertRaises(ActionRejected):
            s.apply("confirm_match", {"match": m.primary_key, "note": "checked against permit"}, actor="a")
        self.assertEqual(len(s.action_log), n)

    def test_confirm_match(self):
        s = self.store
        m = next(iter(s.objects("PlantMatch").where(match_method="zip+name")))
        s.apply("confirm_match", {"match": m.primary_key, "note": "Same operator in EPA FRS record."},
                actor="reviewer@example.org")
        self.assertEqual(s.get("PlantMatch", m.primary_key)["review_status"], "confirmed")
        est = s.get("OshaEstablishment", m["osha_key"])
        self.assertEqual(s.linked(est, "rmp_registrations").count(), 1)

    def test_invalid_submissions_change_nothing(self):
        s = self.store
        m = list(s.objects("PlantMatch").where(match_method="address"))[0]
        n = len(s.action_log)
        cases = [
            ("reject_match", {"match": m.primary_key, "reason": "other"}, "x", "note is required"),
            ("reject_match", {"match": m.primary_key, "reason": "typo"}, "x", "reason must be one of"),
            ("reject_match", {"match": "nope", "reason": "name_match_wrong"}, "x", "no PlantMatch"),
            ("reject_match", {"match": m.primary_key, "reason": "name_match_wrong", "zzz": 1}, "x", "unknown parameters"),
            ("reject_match", {"match": m.primary_key, "reason": "name_match_wrong"}, " ", "actor is required"),
            ("confirm_match", {"match": m.primary_key, "note": "short"}, "x", "at least 10"),
            ("clear_plant_review", {"plant": m["osha_key"][2:], "note": "nothing to clear"}, "x", "not under review"),
        ]
        for action, params, actor, fragment in cases:
            with self.subTest(fragment=fragment):
                with self.assertRaises(ActionRejected) as ctx:
                    s.apply(action, params, actor=actor)
                self.assertTrue(any(fragment in e for e in ctx.exception.errors), ctx.exception.errors)
        self.assertEqual(len(s.action_log), n)
        self.assertEqual(s.get("PlantMatch", m.primary_key)["review_status"], "unreviewed")

    def test_plant_review_leaves_peer_set(self):
        s = self.store
        plant = next(p for p in s.objects("Plant").where(match_method="osha only")
                     if F.funnel_position(s, p)["status"] in ("above", "below", "within"))
        group = s.linked(plant, "peer_group").one()
        peer = next(q for q in s.linked(group, "plants") if q.primary_key != plant.primary_key)
        before = F.funnel_position(s, plant)["n_peers"]
        s.apply("mark_plant_for_review", {"plant": peer.primary_key, "reason": "hours_suspect"}, actor="a")
        self.assertEqual(F.funnel_position(s, plant)["n_peers"], before - 1)
        self.assertEqual(F.funnel_position(s, peer)["status"], "under_review")
        with self.assertRaises(ActionRejected):
            s.apply("mark_plant_for_review", {"plant": peer.primary_key, "reason": "hours_suspect"}, actor="a")
        s.apply("clear_plant_review", {"plant": peer.primary_key, "note": "Hours confirmed by plant."}, actor="a")
        self.assertEqual(F.funnel_position(s, plant)["n_peers"], before)
        hist = s.edit_history("Plant", peer.primary_key)
        self.assertEqual([h["action_type"] for h in hist if h["property"] == "review_status"],
                         ["mark_plant_for_review", "clear_plant_review"])


class Fixture(unittest.TestCase):
    """The same layer over build.assemble on the synthetic fixture, plus export and CLI."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.raw = _fixture.build(Path(cls.tmp.name) / "raw")
        cls.plants, cls.releases, cls.injuries, cls.stats = build.assemble(cls.raw)
        cls.store = build_store((cls.plants, cls.releases, cls.injuries), source=SOURCE_FIXTURE)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_join_objects(self):
        s = self.store
        self.assertEqual(s.get("PlantMatch", "900|O:R900")["confidence"], "high")
        self.assertEqual(s.get("PlantMatch", "901|O:R901")["match_method"], "zip+name")
        self.assertEqual(s.get("OshaEstablishment", "O:R900")["establishment_ids"], ("1",))
        self.assertIsNone(s.linked(s.get("Plant", "I2"), "rmp_registration").one())
        self.assertEqual(s.linked(s.get("Plant", "R900"), "serious_injuries").count(), 1)

    def test_functions_equal_pipeline_on_fixture(self):
        f = analysis.findings(self.plants, self.releases, self.injuries, self.stats)
        self.assertEqual(plain(F.coverage(self.store)), plain(f["coverage"]))
        self.assertEqual(plain(F.size_noise(self.store)), plain(f["size_noise"]))
        self.assertEqual(plain(F.release_predictors(self.store)), plain(f["release_predictors"]))
        self.assertEqual(plain(F.green_dashboard(self.store)), plain(f["green_dashboard"]))

    def test_export_sqlite_and_json(self):
        s = build_store((self.plants, self.releases, self.injuries), source=SOURCE_FIXTURE)
        s.apply("reject_match", {"match": "901|O:R901", "reason": "name_match_wrong"}, actor="a")
        with tempfile.TemporaryDirectory() as d:
            db = export_sqlite(s, Path(d) / "o.sqlite")
            con = sqlite3.connect(str(db))
            try:
                for t in s.spec.object_types:
                    n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                    self.assertEqual(n, s.objects(t).count(), t)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM link_rmp_osha_match").fetchone()[0], 1)
                self.assertEqual(json.loads(con.execute(
                    "SELECT families FROM RmpRegistration WHERE epa_facility_id='900'").fetchone()[0]),
                    ["Formaldehyde", "Ammonia"])
                self.assertEqual(con.execute("SELECT action_type FROM action_log").fetchall(), [("reject_match",)])
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute("INSERT INTO Plant (plant_id, subsector, match_method, federal_osha, "
                                "review_status, source) VALUES ('R900', 'x', 'x', 1, 'none', 'x')")
            finally:
                con.close()
            doc = json.loads(export_json(s, Path(d) / "o.json").read_text())
            self.assertEqual(len(doc["objects"]["Plant"]), s.objects("Plant").count())
            self.assertEqual(doc["integrity"]["rmp_osha_match"]["hidden"], 1)
            self.assertEqual(doc["action_log"][0]["edits"][0]["after"], "rejected")

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ontology_main(["--out", d, "--raw", str(self.raw)]), 0)
            self.assertTrue((Path(d) / "ontology.sqlite").exists())
        self.assertIn('"PlantMatch": 2', out.getvalue())


class DocNumbers(unittest.TestCase):
    """Counts quoted in docs/ontology.md come from the committed data."""

    def test_doc_counts(self):
        text = (ROOT / "docs" / "ontology.md").read_text()
        store = committed_store()
        plants = load_committed()[0]
        methods = Counter(p["match"] for p in plants.values())
        claims = {
            "Plant": store.objects("Plant").count(),
            "RmpRegistration": store.objects("RmpRegistration").count(),
            "Process": store.objects("Process").count(),
            "Chemical": store.objects("Chemical").count(),
            "ChemicalHolding": store.objects("ChemicalHolding").count(),
            "Accident": store.objects("Accident").count(),
            "OshaEstablishment": store.objects("OshaEstablishment").count(),
            "InjuryLogYear": store.objects("InjuryLogYear").count(),
            "PlantMatch": store.objects("PlantMatch").count(),
            "SeriousInjury": store.objects("SeriousInjury").count(),
            "SizeBand": store.objects("SizeBand").count(),
            "PeerGroup": store.objects("PeerGroup").count(),
        }
        for name, n in claims.items():
            with self.subTest(name=name):
                self.assertRegex(text, r"\| %s \| [^|]*\| %s \|" % (name, re.escape("{:,}".format(n))))
        for method in MATCH_CONFIDENCE:
            self.assertIn("| `%s` | %s |" % (method, "{:,}".format(methods[method])), text)
        for n in (COV["ita_plant_years"], COV["serious_injuries_linked"], COV["serious_injuries"]):
            self.assertIn("{:,}".format(n), text)


if __name__ == "__main__":
    unittest.main()
