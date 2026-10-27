#!/usr/bin/env python3
"""RMP accident histories by chemical-plant peer group (backlog B7).

Reads only committed files (docs/data/plants.json, releases.json, meta.json),
so it runs without data/raw. Writes outputs/accident_*.csv,
outputs/accident_insights.json and docs/img/accident_rate_by_group.svg.
Output is deterministic: no randomness, fixed number formats.
Usage: python3 scripts/build_accident_insights.py
"""
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chempeers import compare, taxonomy  # noqa: E402

FIRST, LAST = 2010, 2024          # same observation window as docs/paper.md
SPLIT = 2016                      # early half 2010-2016, late half 2017-2024
MIN_FY = 100                      # a group needs this many facility-years in each half to be ranked
PER = 100.0                       # rates are per 100 facility-years


def load(root=ROOT):
    d = root / "docs" / "data"
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    cols = {c: i for i, c in enumerate(meta["plant_cols"])}
    plants = json.loads((d / "plants.json").read_text(encoding="utf-8"))
    rels = json.loads((d / "releases.json").read_text(encoding="utf-8"))
    return meta, cols, plants, rels


def facilities(cols, plants, rels):
    """One record per EPA-registered facility with at least one observed year."""
    out = []
    for p in plants:
        g = lambda c: p[cols[c]]  # noqa: E731
        if not g("rmp_id") or not g("rmp_first"):
            continue
        end = LAST if g("active") else min(g("rmp_last") or LAST, LAST)
        start = max(FIRST, g("rmp_first") - 5)
        if end < start:
            continue
        years = list(range(start, end + 1))
        acc = [int(rels[k][1][:4]) for k in g("releases")]
        acc = [y for y in acc if start <= y <= end]
        out.append({"id": g("id"), "name": g("name"), "state": g("state"),
                    "subsectors": g("subsectors"), "families": g("families"),
                    "inventory": g("inventory_lb") or 0, "years": years, "acc_years": acc,
                    "chemicals": g("chemicals"), "releases": [rels[k] for k in g("releases")
                                                              if start <= int(rels[k][1][:4]) <= end]})
    return out


def _r(x, nd=3):
    return None if x is None else round(x, nd)


def group_row(label, members, key_name="group"):
    fy = sum(len(f["years"]) for f in members)
    acc = sum(len(f["acc_years"]) for f in members)
    with1 = sum(1 for f in members if f["acc_years"])
    lo, hi = compare.garwood(acc)
    plo, phi = compare.clopper_pearson(with1, len(members))
    return {key_name: label, "facilities": len(members), "facility_years": fy, "accidents": acc,
            "rate_per_100fy": _r(PER * acc / fy, 4), "rate_lo": _r(PER * lo / fy, 4),
            "rate_hi": _r(PER * hi / fy, 4),
            "facilities_with_accident": with1, "pct_with_accident": _r(100.0 * with1 / len(members), 2),
            "pct_lo": _r(100 * plo, 2), "pct_hi": _r(100 * phi, 2)}


def by_group(facs, labels, member):
    groups = [(lab, [f for f in facs if member(f, lab)]) for lab in labels]
    return [group_row(lab, m) for lab, m in groups if m]


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def spearman(a, b):
    ra, rb = ranks(a), ranks(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else None


def half_rates(members):
    out = []
    for lo, hi in ((FIRST, SPLIT), (SPLIT + 1, LAST)):
        fy = sum(1 for f in members for y in f["years"] if lo <= y <= hi)
        ac = sum(1 for f in members for y in f["acc_years"] if lo <= y <= hi)
        out.append((fy, ac))
    return out


def split_half(facs, labels, member):
    rows = []
    for lab in labels:
        (fy1, a1), (fy2, a2) = half_rates([f for f in facs if member(f, lab)])
        if fy1 >= MIN_FY and fy2 >= MIN_FY:
            rows.append({"group": lab, "fy_early": fy1, "acc_early": a1, "rate_early": _r(PER * a1 / fy1),
                         "fy_late": fy2, "acc_late": a2, "rate_late": _r(PER * a2 / fy2)})
    rho = spearman([r["rate_early"] for r in rows], [r["rate_late"] for r in rows]) if len(rows) > 2 else None
    return rows, rho


def concentration(facs):
    counts = sorted((len(f["acc_years"]) for f in facs), reverse=True)
    n, total = len(counts), sum(counts)
    rows = []
    for pct in (1, 5, 10, 25):
        k = max(1, int(math.ceil(n * pct / 100.0)))
        rows.append({"top_share_of_facilities_pct": pct, "facilities": k, "accidents": sum(counts[:k]),
                     "pct_of_accidents": _r(100.0 * sum(counts[:k]) / total, 2)})
    dist = {}
    for c in counts:
        k = str(c) if c < 3 else "3+"
        dist[k] = dist.get(k, 0) + 1
    return rows, dist


def chemical_table(facs, top=10):
    acc, fac_with = {}, {}
    for f in facs:
        seen = set()
        for r in f["releases"]:
            for name in r[2]:
                acc[name] = acc.get(name, 0) + 1
                seen.add(name)
        for name in seen:
            fac_with[name] = fac_with.get(name, 0) + 1
    rows = [{"chemical": n, "accident_records": acc[n], "facilities_with_accident": fac_with[n]}
            for n in acc]
    rows.sort(key=lambda r: (-r["accident_records"], r["chemical"]))
    return rows[:top]


def build(root=ROOT):
    meta, cols, plants, rels = load(root)
    facs = facilities(cols, plants, rels)
    sub_labels = meta["subsectors"]
    fam_labels = [f["name"] for f in meta["families"]]
    inv_labels = meta["inventory_bands"]
    in_list = lambda key: (lambda f, lab: lab in f[key])  # noqa: E731
    in_inv = lambda f, lab: taxonomy.band(f["inventory"], taxonomy.INVENTORY_BANDS) == lab  # noqa: E731
    out = {
        "window": [FIRST, LAST], "split_year": SPLIT, "min_facility_years_per_half": MIN_FY,
        "overall": group_row("All EPA-registered NAICS 325 facilities", facs, "group"),
        "subsector": by_group(facs, sub_labels, in_list("subsectors")),
        "family": by_group(facs, fam_labels, in_list("families")),
        "inventory": by_group(facs, inv_labels, in_inv),
    }
    out["subsector"].sort(key=lambda r: (-r["rate_per_100fy"], r["group"]))
    out["family"].sort(key=lambda r: (-r["rate_per_100fy"], r["group"]))
    for name, labels, member in (("subsector", sub_labels, in_list("subsectors")),
                                 ("family", fam_labels, in_list("families"))):
        rows, rho = split_half(facs, labels, member)
        out["split_" + name] = {"rows": rows, "spearman": _r(rho), "groups": len(rows),
                                "groups_lower_late": sum(1 for r in rows if r["rate_late"] < r["rate_early"])}
    # Group-level association between typical inventory and accident rate.
    sub_inv = []
    for r in out["subsector"]:
        mem = [f for f in facs if r["group"] in f["subsectors"]]
        vals = sorted(f["inventory"] for f in mem)
        med = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
        sub_inv.append((r["group"], med, r["rate_per_100fy"], r["facility_years"]))
    big = [x for x in sub_inv if x[3] >= MIN_FY]
    out["subsector_inventory_rank"] = {
        "groups": len(big), "spearman": _r(spearman([x[1] for x in big], [x[2] for x in big])),
        "rows": [{"group": g, "median_inventory_lb": m, "rate_per_100fy": r} for g, m, r, _ in big]}
    out["concentration"], out["accident_count_distribution"] = concentration(facs)
    out["chemicals"] = chemical_table(facs)
    return out


def write_csv(path, rows):
    keys = list(rows[0])
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def svg(rows, overall):
    """Dot plot of accident rate with exact Poisson 95% intervals, one row per subsector group."""
    rows = [r for r in rows if r["facility_years"] >= MIN_FY]
    W, left, right, top, rh = 760, 250, 30, 64, 28
    H = top + rh * len(rows) + 56
    xmax = math.ceil(max(r["rate_hi"] for r in rows) / 2.0) * 2.0
    sx = lambda v: left + (W - left - right) * v / xmax  # noqa: E731
    o = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
         'role="img" aria-labelledby="t d" font-family="system-ui, sans-serif" font-size="12">' % (W, H, W, H),
         '<title id="t">RMP accidents per 100 facility-years by product-type peer group</title>',
         '<desc id="d">Dot plot of accident-history records per 100 observed facility-years, 2010-2024, '
         'with exact Poisson 95 percent intervals. Dashed line is the all-facility rate.</desc>',
         '<rect width="%d" height="%d" fill="#ffffff"/>' % (W, H),
         '<text x="16" y="24" font-size="15" font-weight="600" fill="#1a1a1a">RMP accident records per 100 '
         'facility-years, by product type</text>',
         '<text x="16" y="42" fill="#555">EPA-registered NAICS 325 facilities, 2010-2024. Dot = rate, bar = exact '
         'Poisson 95% interval. Groups overlap.</text>']
    t = 0
    while t <= xmax:
        x = sx(t)
        o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#e3e3e3"/>' % (x, top - 8, x, H - 40))
        o.append('<text x="%.1f" y="%d" text-anchor="middle" fill="#555">%g</text>' % (x, H - 24, t))
        t += 2
    ox = sx(overall["rate_per_100fy"])
    o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#b33a3a" stroke-dasharray="4 3"/>'
             % (ox, top - 8, ox, H - 40))
    o.append('<text x="%.1f" y="%d" text-anchor="middle" fill="#b33a3a">all facilities %.2f</text>'
             % (ox, H - 8, overall["rate_per_100fy"]))
    for i, r in enumerate(rows):
        y = top + rh * i + rh / 2
        o.append('<text x="%d" y="%.1f" text-anchor="end" fill="#1a1a1a">%s (n=%d)</text>'
                 % (left - 10, y + 4, r["group"].replace("&", "&amp;"), r["facilities"]))
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#2b6cb0" stroke-width="2"/>'
                 % (sx(r["rate_lo"]), y, sx(r["rate_hi"]), y))
        o.append('<circle cx="%.1f" cy="%.1f" r="4.5" fill="#2b6cb0"/>' % (sx(r["rate_per_100fy"]), y))
    o.append('<text x="%.1f" y="%d" text-anchor="middle" fill="#555">accident records per 100 facility-years'
             '</text>' % ((left + W - right) / 2, H - 24 + 0))
    o.append("</svg>")
    return "\n".join(o) + "\n"


def main():
    res = build()
    out = ROOT / "outputs"
    (out / "accident_insights.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n",
                                                encoding="utf-8")
    write_csv(out / "accident_by_subsector.csv", res["subsector"])
    write_csv(out / "accident_by_family.csv", res["family"])
    write_csv(out / "accident_by_inventory.csv", res["inventory"])
    write_csv(out / "accident_concentration.csv", res["concentration"])
    write_csv(out / "accident_split_half_subsector.csv", res["split_subsector"]["rows"])
    write_csv(out / "accident_top_chemicals.csv", res["chemicals"])
    img = ROOT / "docs" / "img"
    img.mkdir(exist_ok=True)
    (img / "accident_rate_by_group.svg").write_text(svg(res["subsector"], res["overall"]), encoding="utf-8")
    print("wrote outputs/accident_* and docs/img/accident_rate_by_group.svg")


if __name__ == "__main__":
    main()
