"""Write the compact JSON files the explorer reads.

Plants are written as arrays, not objects, to keep the download small; the
column order is recorded in meta.json so the page never guesses.
"""
import json
from pathlib import Path

from . import events, taxonomy

PLANT_COLS = ["id", "name", "company", "city", "state", "zip", "lat", "lng", "naics",
              "subsectors", "families", "chemicals", "inventory_lb", "employees", "rmp_id",
              "active", "match", "years", "releases", "injuries", "rmp_first", "rmp_last"]
YEAR_COLS = ["hours", "emp", "dafw", "djtr", "other", "illness", "dafw_days", "plausible"]
RELEASE_COLS = ["plant", "date", "chemicals", "type", "source", "cause", "fix", "worker_inj",
                "responder_inj", "public_inj", "deaths", "evacuated", "sheltered",
                "onsite_damage", "offsite_damage"]
INJURY_COLS = ["plant", "date", "employer", "city", "state", "naics", "energy", "hosp", "amp",
               "eye", "nature", "body", "source", "narrative"]
NARRATIVE_MAX = 420


def _r(x, nd=0):
    if x is None:
        return None
    return int(round(x)) if nd == 0 else round(x, nd)


def plant_row(p):
    years = {}
    for yr, y in sorted(p["years"].items()):
        years[str(yr)] = [_r(y["hours"]), _r(y["emp"]), _r(y["dafw"]), _r(y["djtr"]),
                          _r(y["other"]), _r(y["resp"] + y["pois"] + y["skin"]),
                          _r(y["dafw_days"]), 1 if y["plausible"] else 0]
    return [p["id"], p["name"], p["company"], p["city"], p["state"], p["zip"],
            _r(p["lat"], 4), _r(p["lng"], 4), p["naics"], p["subsectors"], p["families"],
            [[n, _r(q)] for n, q in p["chemicals"][:10]], _r(p["inventory_lb"]),
            _r(p["employees"]), p["rmp_id"], 1 if p["active"] else 0, p["match"], years,
            p["releases"], p["injuries"], p["rmp_first"], p["rmp_last"]]


def release_row(r):
    return [r[c] if not isinstance(r[c], float) else _r(r[c]) for c in RELEASE_COLS]


def injury_row(i):
    text = i["narrative"]
    if len(text) > NARRATIVE_MAX:
        text = text[:NARRATIVE_MAX].rsplit(" ", 1)[0] + "…"
    return [i["plant"], i["date"], i["employer"], i["city"], i["state"], i["naics"], i["energy"],
            _r(i["hosp"]), _r(i["amp"]), _r(i["eye"]), i["nature"], i["body"], i["source"], text]


def write(out_dir, plants, releases, injuries, summary, built_from):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    order = sorted(plants.values(), key=lambda p: (p["state"], p["city"], p["name"]))
    dump = dict(separators=(",", ":"), ensure_ascii=False)
    (out / "plants.json").write_text(json.dumps([plant_row(p) for p in order], **dump))
    (out / "releases.json").write_text(json.dumps([release_row(r) for r in releases], **dump))
    (out / "injuries.json").write_text(json.dumps([injury_row(i) for i in injuries], **dump))
    meta = {
        "plant_cols": PLANT_COLS, "year_cols": YEAR_COLS, "release_cols": RELEASE_COLS,
        "injury_cols": INJURY_COLS,
        "release_type": [lab for _c, lab in events.RELEASE_TYPE],
        "release_source": [lab for _c, lab in events.RELEASE_SOURCE],
        "release_cause": [lab for _c, lab in events.RELEASE_CAUSE],
        "release_fix": [lab for _c, lab in events.RELEASE_FIX],
        "energy": events.ENERGY_ORDER,
        "subsectors": [lab for lab, _p in taxonomy.SUBSECTORS] + ["Other chemical"],
        "families": [{"name": f, "about": d} for f, d, _k in taxonomy.FAMILIES],
        "size_bands": [b[0] for b in taxonomy.SIZE_BANDS],
        "inventory_bands": [b[0] for b in taxonomy.INVENTORY_BANDS],
        "state_plan": sorted(__import__("chempeers.analysis", fromlist=["x"]).STATE_PLAN),
        "plausibility": {"min_hours_per_employee": 120, "max_hours_per_employee": 4500},
        "built_from": built_from,
        "summary": summary,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
