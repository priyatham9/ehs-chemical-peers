"""The findings behind the story, computed from the linked dataset.

Every number the story or README quotes comes from ``findings()`` and is
written to outputs/summary.json. Nothing here is typed by hand.

Coverage notes that shape the method:
* Serious-injury reports exist only for states where federal OSHA covers
  private employers. Plants in state-plan states are left out of every
  serious-injury comparison (STATE_PLAN below).
* An RMP accident is on file only if it fell in the five years before one of
  the plant's RMP submissions, so a plant-year counts as "observed" for
  releases only when a submission covers it.
* Injury rates use the ehs-osha-analysis plausibility screen (120-4,500
  hours per employee); filings outside it are dropped from every rate.
"""
import collections

from . import events, taxonomy
from . import stats as S

# States that run their own OSHA plan for private employers (serious-injury
# reports from these states do not reach the federal file).
STATE_PLAN = {"AK", "AZ", "CA", "HI", "IN", "IA", "KY", "MD", "MI", "MN", "NV", "NM", "NC", "OR",
              "SC", "TN", "UT", "VT", "VA", "WA", "WY", "PR"}
SIZE_GROUPS = [("Under 100", 0, 100), ("100-249", 100, 250), ("250+", 250, float("inf"))]
STABILITY_BANDS = [("Under 50", 0, 50), ("50-99", 50, 100), ("100-249", 100, 250),
                   ("250-999", 250, 1000), ("1,000+", 1000, float("inf"))]
RELEASE_YEARS = range(2010, 2025)


def cases(y):
    return y["dafw"] + y["djtr"] + y["other"]


def usable(y):
    return bool(y) and y["plausible"] and y["hours"] > 0


def _pct(num, den):
    return round(100.0 * num / den, 2) if den else None


def _group(rows, key):
    n = len(rows)
    return {"n": n, "events": sum(1 for r in rows if r[key]), "pct": _pct(sum(1 for r in rows if r[key]), n)}


def covered_years(plant, submissions_years=None):
    """Years in which an RMP accident at this plant would be on file."""
    if not plant["rmp_first"]:
        return set()
    end = 2024 if plant["active"] else min(plant["rmp_last"] or 2024, 2024)
    start = max(RELEASE_YEARS.start, plant["rmp_first"] - 5)
    return set(range(start, end + 1))


def size_noise(plants):
    """How much one recordable moves the rate, and how often plants see zero."""
    out = []
    for label, lo, hi in taxonomy.SIZE_BANDS:
        hours, zero, n, c = [], 0, 0, 0.0
        for p in plants.values():
            for y in p["years"].values():
                if usable(y) and lo <= y["emp"] < hi:
                    n += 1
                    hours.append(y["hours"])
                    c += cases(y)
                    zero += cases(y) == 0
        med = S.median(hours)
        out.append({"band": label, "plant_years": n, "median_hours": round(med) if med else None,
                     "one_case_swing": round(S.one_case_swing(med), 2) if med else None,
                     "zero_share_pct": _pct(zero, n),
                     "pooled_trir": round(S.rate(c, sum(hours)), 2) if hours else None})
    return out


def stability(plants):
    """Rank correlation of a plant's rate in one year with its rate the next."""
    out = []
    for label, lo, hi in STABILITY_BANDS:
        xs, ys = [], []
        for p in plants.values():
            for yr in range(2016, 2024):
                a, b = p["years"].get(yr), p["years"].get(yr + 1)
                if usable(a) and usable(b) and lo <= a["emp"] < hi:
                    xs.append(S.rate(cases(a), a["hours"]))
                    ys.append(S.rate(cases(b), b["hours"]))
        rho = S.spearman(xs, ys)
        out.append({"band": label, "pairs": len(xs), "rho": round(rho, 3) if rho is not None else None})
    return out


def _next_year_rows(plants, releases, injuries):
    rows = []
    for p in plants.values():
        sir_years = collections.Counter(int(injuries[k]["date"][:4]) for k in p["injuries"])
        rel_years = collections.Counter(int(releases[k]["date"][:4]) for k in p["releases"])
        cov = covered_years(p)
        for yr in range(2016, 2024):
            a = p["years"].get(yr)
            if not usable(a):
                continue
            rows.append({
                "federal": p["state"] not in STATE_PLAN, "rmp": p["rmp_id"] is not None,
                "covered": (yr + 1) in cov, "emp": a["emp"],
                "trir": S.rate(cases(a), a["hours"]), "zero": cases(a) == 0,
                "sir": sir_years.get(yr + 1, 0) > 0, "rel": rel_years.get(yr + 1, 0) > 0,
            })
    return rows


def _split_by_trir(rows, key):
    out = []
    for label, lo, hi in SIZE_GROUPS:
        g = [r for r in rows if lo <= r["emp"] < hi]
        nz = [r for r in g if not r["zero"]]
        med = S.median([r["trir"] for r in nz])
        out.append({
            "size": label,
            "zero_cases": _group([r for r in g if r["zero"]], key),
            "below_median": _group([r for r in nz if r["trir"] <= med], key),
            "above_median": _group([r for r in nz if r["trir"] > med], key),
            "median_trir_nonzero": round(med, 2) if med is not None else None,
        })
    return out


def trir_vs_outcomes(plants, releases, injuries):
    rows = _next_year_rows(plants, releases, injuries)
    sir_rows = [r for r in rows if r["federal"]]
    rel_rows = [r for r in rows if r["rmp"] and r["covered"]]
    return {
        "serious_injury_next_year": _split_by_trir(sir_rows, "sir"),
        "release_next_year": _split_by_trir(rel_rows, "rel"),
        "sir_plant_years": len(sir_rows), "release_plant_years": len(rel_rows),
    }


def green_dashboard(plants, injuries):
    """Serious injuries at plants that logged zero recordables the year before."""
    total, zero = 0, 0
    for p in plants.values():
        if p["state"] in STATE_PLAN:
            continue
        for k in p["injuries"]:
            prev = p["years"].get(int(injuries[k]["date"][:4]) - 1)
            if usable(prev):
                total += 1
                zero += cases(prev) == 0
    return {"serious_injuries_with_prior_year": total, "prior_year_zero": zero,
            "prior_year_zero_pct": _pct(zero, total)}


def release_predictors(plants, releases):
    """What does raise the odds of a release next year: history, inventory, chemistry."""
    rows = []
    for p in plants.values():
        if not p["rmp_id"]:
            continue
        rel_years = collections.Counter(int(releases[k]["date"][:4]) for k in p["releases"])
        cov = covered_years(p)
        for yr in RELEASE_YEARS:
            if yr not in cov:
                continue
            rows.append({
                "prior": sum(rel_years.get(y, 0) for y in range(yr - 5, yr)) > 0,
                "rel": rel_years.get(yr, 0) > 0,
                "inv": p["inventory_lb"] or 0,
                "fams": p["families"],
                "n_chem": len(p["chemicals"]),
            })
    base = _group(rows, "rel")
    hist = {"release_in_past_5y": _group([r for r in rows if r["prior"]], "rel"),
            "no_release_in_past_5y": _group([r for r in rows if not r["prior"]], "rel")}
    inv = [dict(band=b, **_group([r for r in rows if lo <= r["inv"] < hi], "rel"))
           for b, lo, hi in taxonomy.INVENTORY_BANDS]
    fam = [dict(family=f, **_group([r for r in rows if f in r["fams"]], "rel"))
           for f, _d, _k in taxonomy.FAMILIES]
    nchem = [dict(label=lab, **_group([r for r in rows if lo <= r["n_chem"] < hi], "rel"))
             for lab, lo, hi in (("1 chemical", 1, 2), ("2", 2, 3), ("3-4", 3, 5), ("5+", 5, 999))]
    ratio = None
    a, b = hist["release_in_past_5y"]["pct"], hist["no_release_in_past_5y"]["pct"]
    if a and b:
        ratio = round(a / b, 1)
    return {"plant_years": base["n"], "base": base, "history": hist, "history_ratio": ratio,
            "inventory": inv, "family": fam, "chemical_count": nchem}


def release_anatomy(plants, releases, family=None):
    """Counts of type, source, cause and fix across releases.

    With ``family``, only releases that involved a chemical of that family
    (e.g. a formaldehyde release, not any release at a plant that also holds
    formaldehyde).
    """
    sel = [r for r in releases if family is None or family in taxonomy.families(r["chemicals"])]
    def tally(key, table):
        c = collections.Counter(j for r in sel for j in r[key])
        return [{"label": table[j][1], "n": c.get(j, 0)} for j in range(len(table))]
    return {"releases": len(sel),
            "worker_injuries": int(sum(r["worker_inj"] for r in sel)),
            "type": tally("type", events.RELEASE_TYPE),
            "source": tally("source", events.RELEASE_SOURCE),
            "cause": tally("cause", events.RELEASE_CAUSE),
            "fix": tally("fix", events.RELEASE_FIX)}


def injury_anatomy(injuries, subsector=None, plants=None):
    sel = [i for i in injuries if subsector is None
           or taxonomy.subsector(i["naics"]) == subsector]
    c = collections.Counter(i["energy"] for i in sel)
    return {"events": len(sel),
            "amputations": int(sum(1 for i in sel if i["amp"] > 0)),
            "hospitalizations": int(sum(1 for i in sel if i["hosp"] > 0)),
            "energy": [{"label": e, "n": c.get(e, 0)} for e in events.ENERGY_ORDER if c.get(e)]}


def coverage(plants, injuries, build_stats):
    n = len(plants)
    rmp = [p for p in plants.values() if p["rmp_id"]]
    both = [p for p in rmp if p["years"]]
    return {
        "plants": n,
        "rmp_plants": len(rmp),
        "osha_plants": sum(1 for p in plants.values() if p["years"]),
        "linked_plants": len(both),
        "rmp_linked_pct": _pct(len(both), len(rmp)),
        "serious_injuries": build_stats["sir_events"],
        "serious_injuries_linked": build_stats["sir_matched"],
        "serious_injuries_linked_pct": _pct(build_stats["sir_matched"], build_stats["sir_events"]),
        "ita_plant_years": build_stats["ita_records"],
        "releases": build_stats["rmp_accidents"],
    }


def findings(plants, releases, injuries, build_stats):
    return {
        "coverage": coverage(plants, injuries, build_stats),
        "size_noise": size_noise(plants),
        "stability": stability(plants),
        "trir_vs_outcomes": trir_vs_outcomes(plants, releases, injuries),
        "green_dashboard": green_dashboard(plants, injuries),
        "release_predictors": release_predictors(plants, releases),
        "release_anatomy_all": release_anatomy(plants, releases),
        "release_anatomy_formaldehyde": release_anatomy(plants, releases, "Formaldehyde"),
        "injury_anatomy_all": injury_anatomy(injuries),
        "injury_anatomy_resins": injury_anatomy(injuries, "Resins & plastics"),
    }
