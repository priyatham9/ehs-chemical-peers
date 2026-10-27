"""Ontology functions: thin adapters over the pipeline's own analysis code.

Nothing here re-implements a rate, a band or a finding. :func:`pipeline_view`
turns objects back into the plant, release and injury records the pipeline
understands, and each function calls the code the spec names under ``reuses``.

Writeback reaches the numbers in two ways:

* a ``rejected`` PlantMatch detaches the OSHA logs from the EPA plant, which
  then counts as an OSHA-only plant, as if the address join had not happened;
* a plant ``under_review`` is left out of the default peer set of
  :func:`funnel_position`, but stays in population counts.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from .. import analysis
from .. import stats as S
from .runtime import ObjectSet, ObjectStore, OntologyObject


def _log_years(store: ObjectStore, plant: OntologyObject, respect_reviews: bool = True):
    """{year: pipeline year record} of the OSHA logs attributed to a plant."""
    est = store.linked(plant, "osha_establishment").one()
    if est is None:
        return {}
    if respect_reviews and any(m["review_status"] == "rejected" for m in store.linked(est, "matches")):
        return {}
    return {y["year"]: {"hours": y["hours"], "emp": y["employees"], "dafw": y["dafw"],
                        "djtr": y["djtr"], "other": y["other"], "plausible": y["plausible"]}
            for y in store.linked(est, "log_years")}


def pipeline_view(store: ObjectStore, respect_reviews: bool = True):
    """Return ``(plants, releases, injuries, build_stats)`` in the shape analysis.py reads.

    With ``respect_reviews``, the logs behind a rejected match become a
    separate OSHA-only plant (id ``I~<osha_key>``).
    """
    plants: Dict[str, dict] = {}
    split = []
    for p in store.objects("Plant"):
        reg = store.linked(p, "rmp_registration").one()
        years = _log_years(store, p, respect_reviews)
        if reg is not None and not years and _log_years(store, p, False):
            split.append((p, _log_years(store, p, False)))
        holdings = sorted(store.linked(reg, "holdings"), key=lambda h: h["rank"]) if reg else []
        plants[p.primary_key] = {
            "id": p.primary_key, "state": p["state"], "years": years, "releases": [],
            "injuries": [], "rmp_id": reg.primary_key if reg else None,
            "rmp_first": reg["rmp_first"] if reg else None,
            "rmp_last": reg["rmp_last"] if reg else None,
            "active": reg["active"] if reg else True,
            "inventory_lb": reg["inventory_lb"] if reg else None,
            "families": list(reg["families"]) if reg else [],
            "chemicals": [(h["chemical_name"], h["quantity_lb"]) for h in holdings]}
    for p, years in split:
        pid = "I~O:" + p.primary_key
        plants[pid] = dict(plants[p.primary_key], id=pid, years=years, releases=[], injuries=[],
                           rmp_id=None, rmp_first=None, rmp_last=None, active=True,
                           inventory_lb=None, families=[], chemicals=[])
    releases = []
    for a in store.objects("Accident"):
        pid = store.linked(a, "registration").one()["plant_id"]
        plants[pid]["releases"].append(len(releases))
        releases.append({"plant": pid, "date": a["date"], "chemicals": list(a["chemicals"]),
                         "worker_inj": a["worker_injuries"]})
    injuries = []
    for s in store.objects("SeriousInjury"):
        pid = s["plant_id"] if s["plant_id"] in plants else None
        if pid:
            plants[pid]["injuries"].append(len(injuries))
        injuries.append({"plant": pid, "date": s["date"], "naics": s["naics"],
                         "energy": s["energy"], "amp": s["amputation"], "hosp": s["hospitalized"]})
    build_stats = {"sir_events": len(injuries),
                   "sir_matched": sum(1 for i in injuries if i["plant"]),
                   "ita_records": store.objects("InjuryLogYear").count(),
                   "rmp_accidents": len(releases)}
    return plants, releases, injuries, build_stats


def coverage(store: ObjectStore, respect_reviews: bool = True) -> Dict[str, Any]:
    """:func:`chempeers.analysis.coverage` on the store.

    ``ita_plant_years`` here counts plant-years (InjuryLogYear objects); the
    committed summary counts establishment-years, before establishments that
    fall on one plant-year are collapsed, so the two differ by design.
    """
    plants, _rel, injuries, bs = pipeline_view(store, respect_reviews)
    return analysis.coverage(plants, injuries, bs)


def size_noise(store: ObjectStore, respect_reviews: bool = True):
    """:func:`chempeers.analysis.size_noise` on the store."""
    return analysis.size_noise(pipeline_view(store, respect_reviews)[0])


def release_predictors(store: ObjectStore, respect_reviews: bool = True):
    """:func:`chempeers.analysis.release_predictors` on the store."""
    plants, releases, _inj, _bs = pipeline_view(store, respect_reviews)
    return analysis.release_predictors(plants, releases)


def green_dashboard(store: ObjectStore, respect_reviews: bool = True):
    """:func:`chempeers.analysis.green_dashboard` on the store."""
    plants, _rel, injuries, _bs = pipeline_view(store, respect_reviews)
    return analysis.green_dashboard(plants, injuries)


def plant_rates(store: ObjectStore, plant: OntologyObject, respect_reviews: bool = True):
    """Pooled TRIR over a plant's screened log years, via :func:`chempeers.stats.rate`."""
    usable = [y for y in _log_years(store, plant, respect_reviews).values() if analysis.usable(y)]
    hours = sum(y["hours"] for y in usable)
    cases = sum(analysis.cases(y) for y in usable)
    return {"plant_id": plant.primary_key, "years": len(usable), "hours": hours, "cases": cases,
            "trir": S.rate(cases, hours), "one_case_swing": S.one_case_swing(hours)}


def funnel_position(store: ObjectStore, plant: OntologyObject, peers: Optional[ObjectSet] = None):
    """Place a plant against its peers' pooled rate with :func:`chempeers.stats.classify`.

    ``peers`` defaults to the plant's PeerGroup without the plant itself and
    without plants under review. ``status`` is above, below, within, no data,
    no_peers or under_review.
    """
    plant = store.get("Plant", plant.primary_key)  # current state, not a stale view
    base = {"plant_id": plant.primary_key, "peer_rate": None, "low": None, "high": None}
    if plant["review_status"] == "under_review":
        return dict(base, status="under_review")
    if peers is None:
        group = store.linked(plant, "peer_group").one()
        peers = store.linked(group, "plants") if group else ObjectSet(store, "Plant", [])
        peers = peers.filter(lambda q: q.primary_key != plant.primary_key
                             and q["review_status"] != "under_review")
    pooled = [plant_rates(store, q) for q in peers]
    peer_rate = S.rate(sum(r["cases"] for r in pooled), sum(r["hours"] for r in pooled))
    own = plant_rates(store, plant)
    if peer_rate is None:
        return dict(base, status="no_peers", n_peers=len(peers))
    out = dict(base, peer_rate=peer_rate, n_peers=len(peers), trir=own["trir"])
    if not own["hours"]:
        return dict(out, status="no data")
    low, high = S.funnel_limits(peer_rate, own["hours"])
    return dict(out, low=low, high=high, status=S.classify(own["cases"], own["hours"], peer_rate))


#: Function api_name -> implementation, checked against the spec by check_registry.
REGISTRY: Dict[str, Callable[..., Any]] = {
    "coverage": coverage,
    "size_noise": size_noise,
    "release_predictors": release_predictors,
    "green_dashboard": green_dashboard,
    "plant_rates": plant_rates,
    "funnel_position": funnel_position,
}


def check_registry(spec_functions: Dict[str, Dict[str, Any]]) -> None:
    """Raise if the spec and :data:`REGISTRY` disagree on the function set."""
    missing, extra = set(spec_functions) - set(REGISTRY), set(REGISTRY) - set(spec_functions)
    if missing or extra:
        raise ValueError(f"function registry mismatch: missing={sorted(missing)} extra={sorted(extra)}")
