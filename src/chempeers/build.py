"""Assemble plants, releases and serious injuries into one linked dataset."""
from . import events, load, taxonomy
from .link import AddressIndex, state_code

YEARS = list(range(2016, 2025))  # ITA calendar years with complete filings
ILL_KEYS = ("resp", "pois", "skin")


def _new_plant(pid):
    return {"id": pid, "rmp_id": None, "ita_ids": [], "years": {}, "releases": [], "injuries": [],
            "match": ""}


def assemble(raw):
    ita = load.read_ita(raw)
    rmp_fac, rmp_acc = load.read_rmp(raw)
    sir = load.read_sir(raw)

    plants = {}
    index = AddressIndex()

    # 1. every chemical-manufacturing RMP facility is a plant
    for fid, f in sorted(rmp_fac.items()):
        p = _new_plant("R" + fid)
        p.update(rmp_id=fid, name=f["name"], company=f["company"], street=f["street"],
                 city=f["city"], state=f["state"], zip=f["zip"], lat=f["lat"], lng=f["lng"],
                 naics=f["naics"], chemicals=f["chemicals"], fte=f["fte"],
                 rmp_first=f["first_year"], rmp_last=f["last_year"], active=f["active"])
        plants[p["id"]] = p
        index.add(p["id"], f["zip"], f["street"], (f["name"], f["company"]))

    # 2. attach ITA establishment-years; newest first so identity comes from the latest filing
    ita.sort(key=lambda r: (-r["year"], r["est"]))
    est_to_plant = {}
    for r in ita:
        pid = est_to_plant.get(r["est"])
        if pid is None:
            pid, method = index.find(r["zip"], r["street"], (r["name"], r["company"]))
            if pid is None:
                pid = "I" + r["est"]
                p = _new_plant(pid)
                p.update(name=r["name"], company=r["company"], street=r["street"],
                         city=r["city"].title(), state=r["state"], zip=r["zip"], lat=None,
                         lng=None, naics=r["naics"], chemicals=[], fte=None, rmp_first=None,
                         rmp_last=None, active=True, match="osha only")
                plants[pid] = p
                index.add(pid, r["zip"], r["street"], (r["name"], r["company"]))
            elif not plants[pid]["match"]:
                plants[pid]["match"] = method
            est_to_plant[r["est"]] = pid
        p = plants[pid]
        if r["est"] not in p["ita_ids"]:
            p["ita_ids"].append(r["est"])
        prev = p["years"].get(r["year"])
        # two filings for one plant-year: keep the larger workforce, do not add
        if prev is None or r["hours"] > prev["hours"]:
            p["years"][r["year"]] = r
        if p["id"].startswith("R") and not p.get("ita_naics"):
            p["ita_naics"] = r["naics"]

    for p in plants.values():
        if p["id"].startswith("R") and not p["match"]:
            p["match"] = "epa only"

    # 3. releases belong to their RMP plant directly
    releases = []
    for a in sorted(rmp_acc, key=lambda a: a["AccidentDate"]):
        pid = "R" + a["EPAFacilityID"]
        rel = {
            "plant": pid,
            "date": a["AccidentDate"][:10],
            "chemicals": [n for n, _q in load.parse_chemicals(a["AccidentChemicals"])],
            "type": events.flags(a, events.RELEASE_TYPE),
            "source": events.flags(a, events.RELEASE_SOURCE),
            "cause": events.flags(a, events.RELEASE_CAUSE),
            "fix": events.flags(a, events.RELEASE_FIX),
            "worker_inj": load._num(a["InjuriesWorkers"]),
            "responder_inj": load._num(a["InjuriesPublicResponders"]),
            "public_inj": load._num(a["InjuriesPublic"]),
            "deaths": load._num(a["DeathsWorkers"]) + load._num(a["DeathsPublicResponders"])
            + load._num(a["DeathsPublic"]),
            "evacuated": load._num(a["Evacuated"]),
            "sheltered": load._num(a["ShelteredInPlace"]),
            "onsite_damage": load._num(a["OnsitePropertyDamage"]),
            "offsite_damage": load._num(a["OffsitePropertyDamage"]),
        }
        plants[pid]["releases"].append(len(releases))
        releases.append(rel)

    # 4. serious injuries: join on address; unmatched ones still count for the sector view
    injuries = []
    matched = 0
    for s in sorted(sir, key=lambda s: s["date"]):
        st = state_code(s["state"])
        pid, _m = index.find(s["zip"], s["street"], (s["employer"],))
        if pid is not None and plants[pid]["state"] and st and plants[pid]["state"] != st:
            pid = None
        inj = dict(s, state=st, plant=pid, energy=events.energy(s["event"], s["source"]))
        if pid is not None:
            plants[pid]["injuries"].append(len(injuries))
            matched += 1
        injuries.append(inj)

    # 5. labels
    for p in plants.values():
        # The plant's own OSHA filing names its main product; EPA lists every process.
        primary = p.get("ita_naics") or p["naics"]
        codes = [primary] + [c for c in rmp_fac.get(p["rmp_id"] or "", {}).get("naics_all", [])]
        subs = []
        for c in codes:
            label = taxonomy.subsector(c)
            if label and label not in subs:
                subs.append(label)
        p["subsector"] = subs[0] if subs else "Other chemical"
        p["subsectors"] = subs or ["Other chemical"]
        p["families"] = taxonomy.families([n for n, _q in p["chemicals"]])
        p["inventory_lb"] = sum(q for _n, q in p["chemicals"]) or None
        latest = max(p["years"]) if p["years"] else None
        emp = p["years"][latest]["emp"] if latest else (p["fte"] or None)
        p["employees"] = emp
        p["size_band"] = taxonomy.band(emp, taxonomy.SIZE_BANDS)
        p["inventory_band"] = taxonomy.band(p["inventory_lb"], taxonomy.INVENTORY_BANDS)

    stats = {
        "ita_records": len(ita),
        "rmp_facilities": len(rmp_fac),
        "rmp_accidents": len(rmp_acc),
        "sir_events": len(sir),
        "sir_matched": matched,
    }
    return plants, releases, injuries, stats
