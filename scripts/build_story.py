#!/usr/bin/env python3
"""Render docs/story.html from docs/story.src.html and outputs/summary.json.

The template never carries a typed number. It holds tokens such as
``{{size_noise[1].one_case_swing}}`` or ``{{derived.small_zero_pct|0}}``:

* the path is resolved against summary.json (dotted keys, ``[i]`` indexes),
  or against the ``derived`` values computed below from the same file plus
  docs/data/meta.json and docs/data/releases.json;
* an optional ``|N`` sets the number of decimals (default: integers get
  thousands separators, floats print as stored, trailing zeros trimmed);
  ``|lower`` lower-cases a text label ("Under 50" -> "under 50");
* an unknown token is a hard error.

``<!--STORY_DATA-->`` becomes a JSON blob (summary + derived) that the page
script draws its charts from.

After writing docs/story.html the script runs the shared engine inliner
(tools/inline_story.py at the Research root) and, when present, the shared
header (scripts/apply_header.py). Running it twice gives the same file.

Usage: python3 scripts/build_story.py
"""
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT.parents[1]
SRC = ROOT / "templates" / "story.src.html"
OUT = ROOT / "docs" / "story.html"
SUMMARY = ROOT / "outputs" / "summary.json"
META = ROOT / "docs" / "data" / "meta.json"
RELEASES = ROOT / "docs" / "data" / "releases.json"
INLINER = RESEARCH / "tools" / "inline_story.py"
HEADER = ROOT / "scripts" / "apply_header.py"

TOKEN = re.compile(r"\{\{\s*([A-Za-z_][\w.\[\]]*)\s*(?:\|\s*(\d|lower))?\s*\}\}")
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


# ---------------------------------------------------------------- derived values
def _poisson_quantile(lam, q):
    """Poisson quantile, interpolated between whole counts so the band is smooth.

    The smallest k with P(X <= k) >= q, moved back by the fraction of that
    step's probability not needed to reach q (the usual funnel-plot smoothing).
    """
    k, p = 0, math.exp(-lam)
    cdf_prev, cdf = 0.0, p
    while cdf < q:
        k += 1
        p *= lam / k
        cdf_prev, cdf = cdf, cdf + p
    return max(0.0, k - (cdf - q) / (cdf - cdf_prev))


def chance_band(rate, hours, lo=0.025, hi=0.975):
    """Rates (per 200,000 hours) that chance alone gives a plant of this size 95% of the time."""
    lam = rate * hours / 200000.0
    return (_poisson_quantile(lam, lo) * 200000.0 / hours,
            _poisson_quantile(lam, hi) * 200000.0 / hours, lam)


def _share(n, total, d=4):  # keep precision; the template rounds once
    return round(100.0 * n / total, d)


def derive(s, meta, releases):
    d = {}
    # --- source years, read from the files the build used
    files = list(meta["built_from"])
    ita = [int(m.group(1)) for f in files for m in [re.search(r"ITA_Data_CY_(\d{4})", f)] if m]
    ita += [int(m.group(1)) for f in files for m in [re.search(r"ITA_300A_Summary_Data_(\d{4})_", f)] if m]
    d["ita_first_year"], d["ita_last_year"] = min(ita), max(ita)
    sir = next(re.search(r"([A-Za-z]+)(\d{4})to([A-Za-z]+)(\d{4})", f) for f in files
               if re.search(r"[A-Za-z]+\d{4}to[A-Za-z]+\d{4}", f))
    d["sir_first_year"], d["sir_last_month"], d["sir_last_year"] = int(sir.group(2)), sir.group(3), int(sir.group(4))
    assert d["sir_last_month"] in MONTHS
    years = sorted(int(r[1][:4]) for r in releases)
    d["rmp_first_year"], d["rmp_last_year"] = years[0], years[-1]
    for k in [k for k in d if k.endswith("_year")]:
        d[k] = str(d[k])  # years print as text, never "2,016"
    d["min_hours_per_employee"] = meta["plausibility"]["min_hours_per_employee"]
    d["max_hours_per_employee"] = meta["plausibility"]["max_hours_per_employee"]
    d["state_plan_count"] = len(meta["state_plan"])

    # --- beat 2: one injury is the whole score
    sn = s["size_noise"]
    d["swing_vs_rate_small_pct"] = round(100 * sn[1]["one_case_swing"] / sn[1]["pooled_trir"])
    d["swing_vs_rate_large_pct"] = round(100 * sn[4]["one_case_swing"] / sn[4]["pooled_trir"])
    d["hours_ratio_large_small"] = round(sn[4]["median_hours"] / sn[1]["median_hours"])
    d["swing_ratio_small_large"] = round(sn[1]["one_case_swing"] / sn[4]["one_case_swing"])

    # --- beat 4: the chance band for a typical 50-99 person plant at its own size group's rate
    lo, hi, lam = chance_band(sn[1]["pooled_trir"], sn[1]["median_hours"])
    d["band_small_lo"], d["band_small_hi"], d["band_small_expected"] = round(lo, 2), round(hi, 2), round(lam, 1)
    lo, hi, lam = chance_band(sn[4]["pooled_trir"], sn[4]["median_hours"])
    d["band_large_lo"], d["band_large_hi"], d["band_large_expected"] = round(lo, 2), round(hi, 2), round(lam, 1)
    # the drawn funnel (x = hours worked, log scale) around the 50-99 group's rate
    ref = sn[1]["pooled_trir"]
    h0, h1 = 20000, 5000000
    pts = []
    for i in range(61):
        h = h0 * (h1 / h0) ** (i / 60)
        a, b, _ = chance_band(ref, h)
        pts.append([round(h), round(a, 3), round(b, 3)])
    d["funnel"] = {"rate": ref, "points": pts}

    # --- beat 5: gap between halves, largest absolute difference across size groups
    rel = s["trir_vs_outcomes"]["release_next_year"]
    for half in ("below_median", "above_median", "zero_cases"):
        n = sum(r[half]["n"] for r in rel)
        ev = sum(r[half]["events"] for r in rel)
        d["rel_%s_pooled_pct" % half.split("_")[0]] = _share(ev, n, 2)
    d["release_gap_max_pts"] = round(max(abs(r["below_median"]["pct"] - r["above_median"]["pct"]) for r in rel), 1)

    # --- beat 6
    rp = s["release_predictors"]
    d["inventory_ratio"] = round(rp["inventory"][-1]["pct"] / rp["inventory"][0]["pct"], 1)
    d["chem_count_ratio"] = round(rp["chemical_count"][-1]["pct"] / rp["chemical_count"][0]["pct"], 1)
    fam = sorted(rp["family"], key=lambda r: -r["pct"])
    d["family_top"], d["family_top_pct"] = fam[0]["family"], fam[0]["pct"]
    d["family_low"], d["family_low_pct"] = fam[-1]["family"], fam[-1]["pct"]
    d["family_formaldehyde_pct"] = next(r["pct"] for r in rp["family"] if r["family"] == "Formaldehyde")

    # --- beat 7
    si = s["trir_vs_outcomes"]["serious_injury_next_year"]
    d["si_mid_below"], d["si_mid_above"] = si[1]["below_median"]["pct"], si[1]["above_median"]["pct"]
    gd = s["green_dashboard"]
    d["green_one_in"] = round(gd["serious_injuries_with_prior_year"] / gd["prior_year_zero"])

    # --- beat 8
    ia = s["injury_anatomy_all"]
    en = sorted(ia["energy"], key=lambda r: -r["n"])
    d["energy_ranked"] = en
    for key, label in [("caught", "Caught in machinery"), ("fall", "Slip, trip or fall"),
                       ("chem", "Chemical exposure"), ("heat", "Heat, steam & hot material"),
                       ("struck", "Struck by object or vehicle"), ("vehicle", "Vehicle or forklift"),
                       ("fire", "Fire or explosion")]:
        n = next(r["n"] for r in ia["energy"] if r["label"] == label)
        d["energy_" + key + "_n"] = n
        d["energy_" + key + "_pct"] = _share(n, ia["events"])
    d["amputation_pct"] = _share(ia["amputations"], ia["events"])
    rs = s["injury_anatomy_resins"]
    d["resin_caught_pct"] = _share(next(r["n"] for r in rs["energy"] if r["label"] == "Caught in machinery"), rs["events"])

    # --- beat 9: formaldehyde release anatomy, as shares of its releases
    fa = s["release_anatomy_formaldehyde"]
    for part in ("type", "source", "cause", "fix"):
        for r in fa[part]:
            slug = re.sub(r"[^a-z]+", "_", r["label"].lower()).strip("_")
            d["fa_%s_%s_pct" % (part, slug)] = _share(r["n"], fa["releases"], 0)
    return d


# ---------------------------------------------------------------- narrative checks
def _order(rows, labels):
    """True when these labels are the top rows, in this order, by n."""
    ranked = [r["label"] for r in sorted(rows, key=lambda r: -r["n"])]
    return ranked[:len(labels)] == labels


def check_narrative(s):
    """The prose states orderings and directions; fail the build if the data stops saying them."""
    sn, rp = s["size_noise"], s["release_predictors"]
    rel = s["trir_vs_outcomes"]["release_next_year"]
    si = s["trir_vs_outcomes"]["serious_injury_next_year"]
    fa = s["release_anatomy_formaldehyde"]
    gaps = [abs(r["below_median"]["pct"] - r["above_median"]["pct"]) for r in rel]
    checks = {
        "smallest plants: one injury exceeds the typical rate": sn[0]["one_case_swing"] > sn[0]["pooled_trir"],
        "stability rises from smallest to largest": s["stability"][0]["rho"] < s["stability"][-1]["rho"],
        "release gap is largest at the largest plants": gaps.index(max(gaps)) == len(gaps) - 1,
        "largest plants: higher-rate half had fewer releases": rel[-1]["above_median"]["pct"] < rel[-1]["below_median"]["pct"],
        "inventory ladder climbs": all(a["pct"] < b["pct"] for a, b in zip(rp["inventory"], rp["inventory"][1:])),
        "chemical-count ladder climbs": all(a["pct"] < b["pct"] for a, b in zip(rp["chemical_count"], rp["chemical_count"][1:])),
        "serious injury: mid-size higher half above lower half": si[1]["above_median"]["pct"] > si[1]["below_median"]["pct"],
        "serious injury: smallest group flips": si[0]["above_median"]["pct"] < si[0]["below_median"]["pct"],
        "serious injury: largest gap smaller than mid-size gap":
            abs(si[2]["above_median"]["pct"] - si[2]["below_median"]["pct"]) < abs(si[1]["above_median"]["pct"] - si[1]["below_median"]["pct"]),
        "serious injury: zero-year plants lowest in every group":
            all(r["zero_cases"]["pct"] < min(r["below_median"]["pct"], r["above_median"]["pct"]) for r in si),
        "energy: machinery leads": _order(s["injury_anatomy_all"]["energy"], ["Caught in machinery"]),
        "formaldehyde type: spills then gas": _order(fa["type"], ["Liquid spill", "Gas release"]),
        "formaldehyde source: vessel, tank, piping": _order(fa["source"], ["Process vessel or reactor", "Storage tank", "Piping"]),
        "formaldehyde cause: human error, equipment, procedure":
            _order(fa["cause"], ["Human error", "Equipment failed", "Procedure wrong or not followed"]),
        "formaldehyde fix: retrained, rewrote, equipment": _order(fa["fix"], ["Retrained people", "Rewrote procedures", "Better equipment"]),
        "fix[8] is 'Held less chemical'": fa["fix"][8]["label"] == "Held less chemical",
    }
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        raise SystemExit("build_story: the data no longer supports these sentences:\n  " + "\n  ".join(bad))


# ---------------------------------------------------------------- tokens
def resolve(path, ctx):
    cur = ctx
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        if part.startswith("["):
            i = int(part[1:-1])
            if not isinstance(cur, list) or i >= len(cur):
                raise KeyError(path)
            cur = cur[i]
        else:
            if not isinstance(cur, dict) or part not in cur:
                raise KeyError(path)
            cur = cur[part]
    return cur


def fmt(v, digits=None):
    if isinstance(v, bool) or v is None:
        raise ValueError("not a number: %r" % (v,))
    if isinstance(v, str):
        if digits is not None:
            raise ValueError("digits on a string token")
        return v
    if digits is not None:
        v = round(float(v), digits)
        if digits == 0:
            return "{:,}".format(int(v))
        return "{:,.{d}f}".format(v, d=digits)
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer() and abs(v) >= 1000):
        return "{:,}".format(int(v))
    s = "{:,.2f}".format(v).rstrip("0").rstrip(".")
    return s


def render(src, ctx):
    missing = []

    def sub(m):
        try:
            v = resolve(m.group(1), ctx)
            if m.group(2) == "lower":
                if not isinstance(v, str):
                    raise ValueError("|lower on a number")
                return v.lower()
            return fmt(v, int(m.group(2)) if m.group(2) else None)
        except (KeyError, ValueError) as e:
            missing.append("%s (%s)" % (m.group(0), e))
            return m.group(0)

    out = TOKEN.sub(sub, src)
    if missing:
        raise SystemExit("build_story: unresolved tokens:\n  " + "\n  ".join(missing))
    if "{{" in out:
        left = re.findall(r"\{\{[^}]*\}\}", out)[:5]
        raise SystemExit("build_story: malformed tokens left: %s" % left)
    return out


def context():
    s = json.loads(SUMMARY.read_text(encoding="utf-8"))
    meta = json.loads(META.read_text(encoding="utf-8"))
    releases = json.loads(RELEASES.read_text(encoding="utf-8"))
    check_narrative(s)
    ctx = dict(s)
    ctx["derived"] = derive(s, meta, releases)
    return ctx


def build():
    ctx = context()
    html = render(SRC.read_text(encoding="utf-8"), ctx)
    blob = json.dumps(ctx, separators=(",", ":"), ensure_ascii=True).replace("</", "<\\/")
    tag = '<script type="application/json" id="story-data">' + blob + "</script>"
    if "<!--STORY_DATA-->" not in html:
        raise SystemExit("build_story: template has no <!--STORY_DATA--> marker")
    html = html.replace("<!--STORY_DATA-->", tag)
    OUT.write_text(html, encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT))
    subprocess.run([sys.executable, str(INLINER), str(OUT)], check=True)
    if HEADER.exists():
        subprocess.run([sys.executable, str(HEADER), str(OUT)], check=True)
    else:
        print("note: scripts/apply_header.py not found; shared header not applied")


if __name__ == "__main__":
    build()
