"""Build an :class:`ObjectStore` from the pipeline's linked dataset.

The pipeline (:func:`chempeers.build.assemble`) already joins EPA RMP, OSHA
injury logs and OSHA serious-injury reports into plant, release and injury
records. This module splits those records back into one object per real-world
thing and turns each join into a link:

* By default the records come from the committed site data in ``docs/data``
  (real public records, written by :func:`chempeers.export.write`), read back
  into the pipeline's in-memory shape by :func:`load_committed`.
* :func:`build_store` also accepts the output of ``build.assemble`` directly,
  for the raw downloads or the synthetic test fixture.

SizeBand objects always come from the committed ``outputs/summary.json``.
Nothing is written under ``outputs/`` or ``docs/``.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .. import analysis, events, taxonomy
from .runtime import ObjectStore
from .spec import OntologySpec

ROOT = Path(__file__).resolve().parents[3]
SITE_DATA_DIR = ROOT / "docs" / "data"
SUMMARY_PATH = ROOT / "outputs" / "summary.json"

SOURCE_COMMITTED = "committed_site_data"
SOURCE_RAW = "raw_downloads"
SOURCE_FIXTURE = "synthetic_fixture"
SOURCE_SUMMARY = "committed_summary"

#: This ontology's trust rubric over the pipeline's join methods
#: (chempeers.link.AddressIndex.find). It is a judgement, not a pipeline output.
MATCH_CONFIDENCE = {"address": "high", "address+name": "medium", "zip+name": "low"}

Linked = Tuple[Dict[str, dict], List[dict], List[dict]]


def load_committed(site_dir: Path = SITE_DATA_DIR) -> Linked:
    """Read docs/data/*.json back into the (plants, releases, injuries) shape of build.assemble."""
    site_dir = Path(site_dir)
    meta = json.loads((site_dir / "meta.json").read_text(encoding="utf-8"))
    pc, yc = meta["plant_cols"], meta["year_cols"]
    plants: Dict[str, dict] = {}
    for row in json.loads((site_dir / "plants.json").read_text(encoding="utf-8")):
        p = dict(zip(pc, row))
        p["years"] = {int(y): dict(zip(yc, v), plausible=bool(v[yc.index("plausible")]))
                      for y, v in p["years"].items()}
        p["active"] = bool(p["active"])
        p["chemicals"] = [(n, q) for n, q in p["chemicals"]]
        p["size_band"] = taxonomy.band(p["employees"], taxonomy.SIZE_BANDS)
        p["inventory_band"] = taxonomy.band(p["inventory_lb"], taxonomy.INVENTORY_BANDS)
        plants[p["id"]] = p
    releases = [dict(zip(meta["release_cols"], r))
                for r in json.loads((site_dir / "releases.json").read_text(encoding="utf-8"))]
    injuries = [dict(zip(meta["injury_cols"], r))
                for r in json.loads((site_dir / "injuries.json").read_text(encoding="utf-8"))]
    return plants, releases, injuries


def _labels(indices, table):
    return [table[i][1] for i in indices]


def _illness(y):
    return y["illness"] if "illness" in y else y["resp"] + y["pois"] + y["skin"]


def build_store(linked: Optional[Linked] = None, source: str = SOURCE_COMMITTED,
                spec: Optional[OntologySpec] = None, summary_path: Path = SUMMARY_PATH,
                clock=None) -> ObjectStore:
    """Materialise every object type.

    Args:
        linked: ``(plants, releases, injuries)`` from ``build.assemble`` or
            :func:`load_committed`; defaults to the committed site data.
        source: Provenance label written on every record-level object.
        spec: Ontology spec; defaults to the bundled one.
        summary_path: Committed findings used for SizeBand objects.
        clock: Passed to :class:`ObjectStore`.
    """
    from .functions import check_registry

    store = ObjectStore(spec, clock=clock)
    check_registry(store.spec.functions)
    plants, releases, injuries = linked if linked is not None else load_committed()
    src = {"source": source}

    plant_rows, regs, procs, holds, estabs, logs, matches = [], [], [], [], [], [], []
    chems: Dict[str, None] = {}
    for pid, p in plants.items():
        band = p.get("size_band") or None
        sub = p["subsectors"][0]
        plant_rows.append(dict(
            src, plant_id=pid, name=p["name"], company=p["company"], city=p["city"],
            state=p["state"], zip=p["zip"], lat=p["lat"], lng=p["lng"], naics=p["naics"],
            subsector=sub, employees=p["employees"], size_band=band,
            peer_group_key=f"{sub}|{band}" if band else None, match_method=p["match"],
            federal_osha=p["state"] not in analysis.STATE_PLAN))
        epa = p["rmp_id"]
        if epa:
            regs.append(dict(src, epa_facility_id=epa, plant_id=pid, rmp_first=p["rmp_first"],
                             rmp_last=p["rmp_last"], active=p["active"],
                             inventory_lb=p["inventory_lb"],
                             inventory_band=p.get("inventory_band") or None,
                             families=p["families"]))
            procs.extend(dict(src, process_key=f"{epa}|{s}", epa_facility_id=epa, product_type=s,
                              is_primary=i == 0) for i, s in enumerate(p["subsectors"]))
            for rank, (name, qty) in enumerate(p["chemicals"], 1):
                chems[name] = None
                holds.append(dict(src, holding_key=f"{epa}|{name}", epa_facility_id=epa,
                                  chemical_name=name, quantity_lb=qty, rank=rank))
        if p["years"]:
            okey = f"O:{pid}"
            yrs = sorted(p["years"])
            estabs.append(dict(src, osha_key=okey, plant_id=pid,
                               establishment_ids=p.get("ita_ids", []), n_log_years=len(yrs),
                               first_year=yrs[0], last_year=yrs[-1]))
            for yr in yrs:
                y = p["years"][yr]
                logs.append(dict(src, log_key=f"{pid}|{yr}", osha_key=okey, year=yr,
                                 hours=y["hours"], employees=y["emp"], dafw=y["dafw"],
                                 djtr=y["djtr"], other=y["other"], illness=_illness(y),
                                 dafw_days=y["dafw_days"], plausible=y["plausible"]))
            if epa:
                matches.append(dict(src, match_key=f"{epa}|{okey}", epa_facility_id=epa,
                                    osha_key=okey, match_method=p["match"],
                                    confidence=MATCH_CONFIDENCE[p["match"]]))

    accidents = []
    for i, r in enumerate(releases):
        for name in r["chemicals"]:
            chems[name] = None
        accidents.append(dict(
            src, accident_key=f"A{i}", epa_facility_id=plants[r["plant"]]["rmp_id"],
            date=r["date"], year=int(r["date"][:4]), chemicals=r["chemicals"],
            release_type=_labels(r["type"], events.RELEASE_TYPE),
            release_source=_labels(r["source"], events.RELEASE_SOURCE),
            cause=_labels(r["cause"], events.RELEASE_CAUSE),
            fix=_labels(r["fix"], events.RELEASE_FIX),
            worker_injuries=r["worker_inj"], deaths=r["deaths"], evacuated=r["evacuated"]))

    serious = [dict(src, injury_key=f"S{i}", plant_id=s["plant"], date=s["date"],
                    employer=s["employer"], state=s["state"], naics=s["naics"],
                    energy=s["energy"], hospitalized=s["hosp"], amputation=s["amp"],
                    eye_loss=s["eye"], nature=s["nature"], narrative=s["narrative"])
               for i, s in enumerate(injuries)]

    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    rho = {s["band"]: s["rho"] for s in summary["stability"]}
    bands = [dict(band=s["band"], plant_years=s["plant_years"], median_hours=s["median_hours"],
                  one_case_swing=s["one_case_swing"], zero_share_pct=s["zero_share_pct"],
                  pooled_trir=s["pooled_trir"], stability_rho=rho.get(s["band"]),
                  source=SOURCE_SUMMARY)
             for s in summary["size_noise"]]

    cells = Counter(r["peer_group_key"] for r in plant_rows if r["peer_group_key"])
    groups = [dict(src, peer_group_key=k, subsector=k.split("|")[0], size_band=k.split("|")[1],
                   n_plants=n) for k, n in cells.items()]

    store.add_objects("Plant", plant_rows)
    store.add_objects("RmpRegistration", regs)
    store.add_objects("Process", procs)
    store.add_objects("Chemical", (dict(src, chemical_name=c, families=taxonomy.families([c]))
                                   for c in chems))
    store.add_objects("ChemicalHolding", holds)
    store.add_objects("Accident", accidents)
    store.add_objects("OshaEstablishment", estabs)
    store.add_objects("InjuryLogYear", logs)
    store.add_objects("PlantMatch", matches)
    store.add_objects("SeriousInjury", serious)
    store.add_objects("SizeBand", bands)
    store.add_objects("PeerGroup", groups)
    return store
