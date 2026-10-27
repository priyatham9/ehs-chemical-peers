"""Side-by-side comparison of two peer groups, with exact intervals and tests.

Pure standard library. Reads only committed outputs: ``outputs/summary.json``
(release plant-years by group) and ``docs/data/plants.json`` (hours and
recordable cases by plant-year). It writes ``docs/data/compare.json``, which
the static page ``docs/compare.html`` looks up; the page does no statistics.

Two kinds of rate, each with the interval that fits it:

* Release rate = plant-years with an EPA-reportable release / plant-years
  observed. A proportion: Wilson and Clopper-Pearson (exact binomial) 95%
  intervals. Two groups are compared with Fisher's exact test and a Newcombe
  interval for the difference.
* Injury rate = recordable cases per 200,000 hours. A Poisson rate: exact
  (Garwood) 95% interval. Two groups are compared with the exact conditional
  binomial test (given the combined case count, the first group's share
  should equal its share of hours if the rates are equal).

What "distinguishable from noise" means here: the p-value is below 0.05 under
a model where cases or releases arrive by chance at one common rate. It does
not cover plant-to-plant differences inside a group (the intervals are
narrower than the real uncertainty when plants vary), it does not say why the
rates differ, and with many possible pairs about 1 in 20 unrelated pairs will
pass by chance.
"""
import math

ALPHA = 0.05
PER = 200000.0


# --- regularized incomplete gamma and beta (Numerical Recipes style) ---------

def _gamma_p(a, x):
    """Regularized lower incomplete gamma P(a, x)."""
    if x <= 0:
        return 0.0
    lg = math.lgamma(a)
    if x < a + 1:
        ap, s, d = a, 1.0 / a, 1.0 / a
        for _ in range(100000):
            ap += 1
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 1e-16:
                break
        return s * math.exp(-x + a * math.log(x) - lg)
    tiny = 1e-300
    b = x + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 100000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-16:
            break
    return 1 - math.exp(-x + a * math.log(x) - lg) * h


def poisson_cdf(k, mu):
    """P(X <= k) for X ~ Poisson(mu)."""
    if mu <= 0:
        return 1.0
    return 1.0 - _gamma_p(k + 1, mu)


def _betacf(a, b, x):
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c = 1.0
    d = 1 - qab * x / qap
    d = tiny if abs(d) < tiny else d
    d = 1 / d
    h = d
    for m in range(1, 100000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = tiny if abs(d) < tiny else d
        c = 1 + aa / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = tiny if abs(d) < tiny else d
        c = 1 + aa / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-16:
            break
    return h


def _beta_i(a, b, x):
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1) / (a + b + 2):
        return bt * _betacf(a, b, x) / a
    return 1 - bt * _betacf(b, a, 1 - x) / b


def binom_cdf(k, n, p):
    """P(X <= k) for X ~ Binomial(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return 1.0 - _beta_i(k + 1, n - k, p)


def _bisect(f, lo, hi, target, increasing):
    """Solve f(x) = target for monotone f on [lo, hi]."""
    for _ in range(200):
        mid = (lo + hi) / 2
        if (f(mid) < target) == increasing:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-15 * max(1.0, abs(hi)):
            break
    return (lo + hi) / 2


# --- intervals ----------------------------------------------------------------

Z = 1.959963984540054  # standard normal 97.5th percentile


def wilson(x, n):
    """Wilson score 95% interval for a proportion."""
    p = x / n
    z2 = Z * Z
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def clopper_pearson(x, n, alpha=ALPHA):
    """Exact binomial (Clopper-Pearson) interval."""
    lo = 0.0 if x == 0 else _bisect(lambda p: 1 - binom_cdf(x - 1, n, p), 0.0, 1.0, alpha / 2, True)
    hi = 1.0 if x == n else _bisect(lambda p: binom_cdf(x, n, p), 0.0, 1.0, alpha / 2, False)
    return lo, hi


def garwood(c, alpha=ALPHA):
    """Exact Poisson interval for an expected count given c observed."""
    lo = 0.0 if c == 0 else _bisect(lambda m: 1 - poisson_cdf(c - 1, m), 0.0, c + 10 + 10 * math.sqrt(c),
                                    alpha / 2, True)
    hi = _bisect(lambda m: poisson_cdf(c, m), 0.0, c + 10 + 10 * math.sqrt(c) + 20, alpha / 2, False)
    return lo, hi


# --- two-group tests ------------------------------------------------------------

def _logpmf_binom(k, n, p):
    if p <= 0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1:
        return 0.0 if k == n else -math.inf
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log1p(-p))


def exact_binomial_two_sided(k, n, p):
    """Two-sided exact p: total probability of outcomes no likelier than k."""
    if n == 0:
        return 1.0
    obs = _logpmf_binom(k, n, p)
    cut = obs + 1e-7
    return min(1.0, sum(math.exp(lp) for lp in (_logpmf_binom(j, n, p) for j in range(n + 1))
                        if lp <= cut))


def fisher_two_sided(a, n1, b, n2):
    """Fisher's exact test on events a of n1 versus b of n2 (two-sided, minimum likelihood)."""
    tot, m = a + b, n1 + n2
    lo, hi = max(0, tot - n2), min(tot, n1)
    denom = math.lgamma(m + 1) - math.lgamma(tot + 1) - math.lgamma(m - tot + 1)

    def lp(i):
        return (math.lgamma(n1 + 1) - math.lgamma(i + 1) - math.lgamma(n1 - i + 1)
                + math.lgamma(n2 + 1) - math.lgamma(tot - i + 1) - math.lgamma(n2 - tot + i + 1)
                - denom)
    cut = lp(a) + 1e-7
    return min(1.0, sum(math.exp(v) for v in (lp(i) for i in range(lo, hi + 1)) if v <= cut))


def newcombe_diff(x1, n1, x2, n2):
    """Newcombe hybrid-score 95% interval for p1 - p2 (from the two Wilson intervals)."""
    p1, p2 = x1 / n1, x2 / n2
    l1, u1 = wilson(x1, n1)
    l2, u2 = wilson(x2, n2)
    d = p1 - p2
    return (d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2),
            d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2))


# --- group tables -------------------------------------------------------------------

def _r(x, nd):
    return None if x is None else round(x, nd)


def release_group(gid, dim, label, n, events):
    wl, wu = wilson(events, n)
    cl, cu = clopper_pearson(events, n)
    return {"id": gid, "metric": "release", "dimension": dim, "label": label, "n": n,
            "events": events, "rate_pct": _r(100 * events / n, 4),
            "wilson_pct": [_r(100 * wl, 4), _r(100 * wu, 4)],
            "exact_pct": [_r(100 * cl, 4), _r(100 * cu, 4)]}


def injury_group(gid, dim, label, plant_years, hours, cases):
    lo, hi = garwood(cases)
    return {"id": gid, "metric": "injury", "dimension": dim, "label": label,
            "plant_years": plant_years, "hours": hours, "events": cases,
            "rate": _r(cases * PER / hours, 4),
            "exact": [_r(lo * PER / hours, 4), _r(hi * PER / hours, 4)]}


def release_groups(summary):
    rp = summary["release_predictors"]
    out = []
    sizes = {}
    for row in summary["trir_vs_outcomes"]["release_next_year"]:
        n = sum(row[k]["n"] for k in ("zero_cases", "below_median", "above_median"))
        e = sum(row[k]["events"] for k in ("zero_cases", "below_median", "above_median"))
        sizes[row["size"]] = (n, e)
    for label, (n, e) in sizes.items():
        out.append(release_group("rel-size-" + label, "size", label, n, e))
    for key, label in (("release_in_past_5y", "Release in past 5 years"),
                       ("no_release_in_past_5y", "No release in past 5 years")):
        h = rp["history"][key]
        out.append(release_group("rel-hist-" + key, "history", label, h["n"], h["events"]))
    for row in rp["inventory"]:
        out.append(release_group("rel-inv-" + row["band"], "inventory", row["band"], row["n"], row["events"]))
    for row in rp["chemical_count"]:
        out.append(release_group("rel-nchem-" + row["label"], "chemicals", row["label"],
                                 row["n"], row["events"]))
    for row in rp["family"]:
        out.append(release_group("rel-fam-" + row["family"], "family", row["family"],
                                 row["n"], row["events"]))
    return [g for g in out if g["n"] > 0]


def injury_groups(plants, size_bands, subsector_of):
    """Pool usable plant-years (hours > 0, passes the plausibility screen) by size and product type."""
    size = {b: [0, 0, 0] for b, _lo, _hi in size_bands}
    prod = {}
    for p in plants:
        sub = subsector_of(p[8])
        for y in p[17].values():
            hours, emp, dafw, djtr, other, _ill, _days, ok = y
            if not ok or not hours or hours <= 0:
                continue
            c = dafw + djtr + other
            for b, lo, hi in size_bands:
                if lo <= emp < hi:
                    s = size[b]
                    s[0] += 1
                    s[1] += hours
                    s[2] += c
            if sub:
                s = prod.setdefault(sub, [0, 0, 0])
                s[0] += 1
                s[1] += hours
                s[2] += c
    out = [injury_group("inj-size-" + b, "size", b, *size[b]) for b, _l, _h in size_bands if size[b][1]]
    out += [injury_group("inj-prod-" + k, "product", k, *v) for k, v in sorted(prod.items()) if v[1]]
    return out


# --- pairs ----------------------------------------------------------------------------

def release_pair(a, b):
    p = fisher_two_sided(a["events"], a["n"], b["events"], b["n"])
    lo, hi = newcombe_diff(a["events"], a["n"], b["events"], b["n"])
    return {"a": a["id"], "b": b["id"], "test": "Fisher exact", "p": _r(p, 6),
            "diff_pct": _r(100 * (a["events"] / a["n"] - b["events"] / b["n"]), 4),
            "diff_ci_pct": [_r(100 * lo, 4), _r(100 * hi, 4)],
            "distinguishable": p < ALPHA}


def injury_pair(a, b):
    total = a["events"] + b["events"]
    share = a["hours"] / (a["hours"] + b["hours"])
    p = exact_binomial_two_sided(a["events"], total, share)
    ra, rb = a["events"] / a["hours"], b["events"] / b["hours"]
    return {"a": a["id"], "b": b["id"], "test": "Exact conditional binomial", "p": _r(p, 6),
            "diff": _r((ra - rb) * PER, 4), "ratio": _r(ra / rb, 4) if rb else None,
            "distinguishable": p < ALPHA}


def build(summary, plants, size_bands, subsector_of):
    rel = release_groups(summary)
    inj = injury_groups(plants, size_bands, subsector_of)
    # Only groups from one non-overlapping dimension are tested against each other.
    # Product-family groups overlap (a plant holds several families) and groups from
    # different dimensions overlap too, so the page shows intervals but no test for those.
    pairs = []
    for groups, fn in ((rel, release_pair), (inj, injury_pair)):
        for a in groups:
            for b in groups:
                if a is not b and a["dimension"] == b["dimension"] and a["dimension"] != "family":
                    pairs.append(fn(a, b))
    return {
        "alpha": ALPHA,
        "disclaimer": ("Independent analysis of public records. Not affiliated with, endorsed by or "
                       "sponsored by Palantir Technologies. Quiver is a Palantir product name; this "
                       "page only borrows the idea of a side-by-side analysis view."),
        "built_from": ["outputs/summary.json", "docs/data/plants.json"],
        "groups": rel + inj,
        "pairs": pairs,
    }
