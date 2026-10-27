"""How stable is each plant's list of nearest peers?

A plant's "nearest peers" depend on choices: which attributes count, how much
each counts, and how exactly the attributes were recorded. This module asks
how often a plant keeps the same nearest peers when those choices are
perturbed. Everything is seeded, uses only the committed ``docs/data/plants.json``
and the standard library, and gives the same output on every run.

Similarity
----------
Each plant is described by 15 attributes, the same ones the explorer's
"Match my plant" button uses plus inventory:

* product type (first listed, one attribute; differs or not),
* 12 chemical-family flags (each held or not),
* size band (5 ordered levels, from ``taxonomy.SIZE_BANDS``),
* inventory level (0 = no pounds figure, 1-4 = ``taxonomy.INVENTORY_BANDS``).

The distance between two plants is a weighted sum of per-attribute
differences (0 or 1 for the product type and the family flags, level
difference divided by 4 for the two ordered attributes). Baseline weights are
in ``BASE_WEIGHTS``. The ``k`` nearest other plants are the plant's peers.
Equal distances are broken by a seeded random priority, fixed for the
baseline.

Perturbations (each replicate recomputes every plant's peers)
-------------------------------------------------------------
* ``tiebreak``: baseline weights, new random priorities. This isolates how
  arbitrary the peer list is when many plants are exactly as close.
* ``bootstrap``: the 15 attributes are resampled with replacement and each
  attribute's weight is its baseline weight times how often it was drawn
  (zero when it was not drawn). Feature resampling.
* ``noise``: every baseline weight is multiplied by exp(sigma * z) with z
  standard normal. Weight perturbation.

Two scores per plant and scheme, each the mean over replicates:

* ``exact``: share of the baseline peers (the same plants) still among the
  ``k`` nearest.
* ``neighbourhood``: share of the new ``k`` nearest that lie within the
  baseline neighbourhood, meaning no farther (at baseline weights) than the
  baseline k-th peer. Plants that tie at that distance all count, so this
  does not penalise a swap between equally close plants.

The headline ``stability`` is the ``bootstrap`` neighbourhood score (feature
resampling, the more demanding of the two perturbations); the ``noise``
scores are reported beside it. With these coarse attributes hundreds of plants are often
exactly as close as the k-th peer, which is why ``exact`` is low even where
``neighbourhood`` is high.

Because plants with the same attributes are indistinguishable, they are
grouped into cells, and distances are computed between cells. ``naive_peers``
is a plain plant-by-plant implementation that the tests compare against.
"""
import math
import random
from collections import defaultdict

from . import taxonomy

SEED = 20260701
K = 10
REPLICATES = 100
NOISE_SIGMA = 0.5
SCHEMES = ("tiebreak", "bootstrap", "noise")
HEADLINE = ("bootstrap",)

FAMILY_NAMES = [f[0] for f in taxonomy.FAMILIES]
N_FAM = len(FAMILY_NAMES)
FEATURES = ["Product type"] + FAMILY_NAMES + ["Size band", "Inventory level"]
# Baseline weights, in FEATURES order. Product type and size count double, every
# family flag and the inventory level count once. These are judgements, not fitted;
# the perturbations exist to show how much the answer depends on them.
BASE_WEIGHTS = [2.0] + [1.0] * N_FAM + [2.0, 1.0]


def size_level(employees):
    for i, (_label, lo, hi) in enumerate(taxonomy.SIZE_BANDS):
        if lo <= employees < hi:
            return i
    return None


def inventory_level(pounds):
    if not pounds:
        return 0
    for i, (_label, lo, hi) in enumerate(taxonomy.INVENTORY_BANDS):
        if lo <= pounds < hi:
            return i + 1
    return len(taxonomy.INVENTORY_BANDS)


def features(plants):
    """Return one record per plant that has an employee count.

    A record is a dict with id, name, state, product, fam (bitmask), size, inv.
    Plants with no employee count are left out (see ``skipped``).
    """
    idx = {n: i for i, n in enumerate(FAMILY_NAMES)}
    out, skipped = [], 0
    for p in plants:
        if p[13] is None or size_level(p[13]) is None:
            skipped += 1
            continue
        mask = 0
        for f in p[10]:
            mask |= 1 << idx[f]
        out.append({"id": p[0], "name": p[1], "state": p[4],
                    "product": p[9][0] if p[9] else "Other chemical",
                    "fam": mask, "n_fam": len(p[10]), "size": size_level(p[13]),
                    "inv": inventory_level(p[12])})
    return out, skipped


class Model:
    """Plants grouped into cells of identical attributes."""

    def __init__(self, recs):
        self.recs = recs
        prods = sorted({r["product"] for r in recs})
        pid = {p: i for i, p in enumerate(prods)}
        cells = {}
        self.cell_of = []
        self.members = []
        for i, r in enumerate(recs):
            key = (pid[r["product"]], r["fam"], r["size"], r["inv"])
            c = cells.get(key)
            if c is None:
                c = cells[key] = len(self.members)
                self.members.append([])
            self.members[c].append(i)
            self.cell_of.append(c)
        keys = sorted(cells, key=cells.get)
        self.cprod = [k[0] for k in keys]
        self.cfam = [k[1] for k in keys]
        self.csize = [k[2] for k in keys]
        self.cinv = [k[3] for k in keys]
        self.tuples = [(pid[r["product"]], r["fam"], r["size"], r["inv"]) for r in recs]
        self.n = len(recs)
        self.n_cells = len(keys)


def fam_table(wfam):
    """Weighted mismatch for every xor of two family bitmasks."""
    t = [0.0] * (1 << N_FAM)
    for m in range(1, 1 << N_FAM):
        low = m & -m
        t[m] = t[m & (m - 1)] + wfam[low.bit_length() - 1]
    return t


def priorities(seed, scheme, r, n):
    rng = random.Random("%d:%s:%d" % (seed, scheme, r))
    return [rng.random() for _ in range(n)]


def weights_for(seed, scheme, r):
    """Weights for replicate r of a scheme (r = -1 is the baseline)."""
    if r < 0 or scheme == "tiebreak":
        return list(BASE_WEIGHTS)
    rng = random.Random("%d:w:%s:%d" % (seed, scheme, r))
    if scheme == "bootstrap":
        counts = [0] * len(FEATURES)
        for _ in FEATURES:
            counts[rng.randrange(len(FEATURES))] += 1
        return [b * c for b, c in zip(BASE_WEIGHTS, counts)]
    if scheme == "noise":
        return [b * math.exp(NOISE_SIGMA * rng.gauss(0.0, 1.0)) for b in BASE_WEIGHTS]
    raise ValueError("unknown scheme %r" % scheme)


def pair_distance(w, a, b):
    """Distance between two (product, fam, size, inv) tuples under weights w."""
    d = w[0] if a[0] != b[0] else 0.0
    x = a[1] ^ b[1]
    for j in range(N_FAM):
        if x >> j & 1:
            d += w[1 + j]
    d += w[1 + N_FAM] * abs(a[2] - b[2]) / (len(taxonomy.SIZE_BANDS) - 1)
    d += w[2 + N_FAM] * abs(a[3] - b[3]) / len(taxonomy.INVENTORY_BANDS)
    return d


def naive_peers(model, w, prio, i, k=K):
    """Plant-by-plant reference: the k nearest other plants to plant i (list of indices)."""
    items = []
    for j in range(model.n):
        if j != i:
            items.append((pair_distance(w, model.tuples[i], model.tuples[j]), prio[j], j))
    items.sort()
    return [j for _d, _p, j in items[:k]]


def peers(model, w, prio, k=K, want_ties=False):
    """The k nearest other plants for every plant (list of lists of indices).

    Distances are between cells; plants in a cell share a sorted candidate pool.
    With ``want_ties`` also return, per plant, how many other plants sit at
    exactly the distance of its k-th peer.
    """
    wprod = w[0]
    t = fam_table(w[1:1 + N_FAM])
    ws = w[1 + N_FAM] / (len(taxonomy.SIZE_BANDS) - 1)
    wi = w[2 + N_FAM] / len(taxonomy.INVENTORY_BANDS)
    cp, cf, cs, ci = model.cprod, model.cfam, model.csize, model.cinv
    rows = list(zip(cp, cf, cs, ci))
    members, cell_of = model.members, model.cell_of
    order_cells = range(model.n_cells)
    out = [None] * model.n
    ties = [0] * model.n if want_ties else None
    for u in order_cells:
        pu, fu, su, iu = rows[u]
        dv = [(wprod if p != pu else 0.0) + t[f ^ fu] + ws * abs(s - su) + wi * abs(i - iu)
              for p, f, s, i in rows]
        cum, bound = 0, None
        for v in sorted(order_cells, key=dv.__getitem__):
            cum += len(members[v])
            if cum >= k + 1:
                bound = dv[v]
                break
        if bound is None:
            bound = max(dv)
        pool = [j for v in order_cells if dv[v] <= bound for j in members[v]]
        pool.sort(key=lambda j: (dv[cell_of[j]], prio[j]))
        head = pool[:k + 1]
        for q in members[u]:
            res = [j for j in head if j != q][:k]
            out[q] = res
            if want_ties:
                dk = dv[cell_of[res[-1]]]
                ties[q] = sum(1 for j in pool if j != q and dv[cell_of[j]] == dk) - len(
                    [j for j in res if dv[cell_of[j]] == dk])
    return (out, ties) if want_ties else out


def baseline_distance_fn(model):
    """Return f(i, j): distance between plants i and j at baseline weights."""
    t = fam_table(BASE_WEIGHTS[1:1 + N_FAM])
    ws = BASE_WEIGHTS[1 + N_FAM] / (len(taxonomy.SIZE_BANDS) - 1)
    wi = BASE_WEIGHTS[2 + N_FAM] / len(taxonomy.INVENTORY_BANDS)
    wp = BASE_WEIGHTS[0]
    tup = model.tuples

    def dist(i, j):
        a, b = tup[i], tup[j]
        return (wp if a[0] != b[0] else 0.0) + t[a[1] ^ b[1]] + ws * abs(a[2] - b[2]) \
            + wi * abs(a[3] - b[3])
    return dist


def run(model, seed=SEED, k=K, replicates=REPLICATES, progress=None):
    """Run every scheme; return per-plant results (lists indexed by plant)."""
    n = model.n
    base_w = weights_for(seed, "tiebreak", -1)
    base, ties = peers(model, base_w, priorities(seed, "base", 0, n), k, want_ties=True)
    dist0 = baseline_distance_fn(model)
    base_sets = [set(b) for b in base]
    dk = [dist0(i, base[i][-1]) + 1e-9 for i in range(n)]
    exact = {s: [0.0] * n for s in SCHEMES}
    neigh = {s: [0.0] * n for s in SCHEMES}
    for scheme in SCHEMES:
        ex, ng = exact[scheme], neigh[scheme]
        for r in range(replicates):
            w = weights_for(seed, scheme, r)
            cur = peers(model, w, priorities(seed, scheme, r, n), k)
            for i in range(n):
                c = cur[i]
                ex[i] += len(base_sets[i] & set(c))
                lim = dk[i]
                ng[i] += sum(1 for j in c if dist0(i, j) <= lim)
            if progress:
                progress(scheme, r)
        for i in range(n):
            ex[i] /= k * replicates
            ng[i] /= k * replicates
    return {"base": base, "ties": ties, "exact": exact, "neigh": neigh}


def rows(model, result, k=K):
    out = []
    ex, ng = result["exact"], result["neigh"]
    for i, r in enumerate(model.recs):
        head = sum(ng[s][i] for s in HEADLINE) / len(HEADLINE)
        out.append({
            "id": r["id"], "name": r["name"], "state": r["state"], "product_type": r["product"],
            "size_band": taxonomy.SIZE_BANDS[r["size"]][0], "n_families": r["n_fam"],
            "inventory_level": r["inv"], "k": k,
            "stability": round(head, 4),
            "neighbourhood_bootstrap": round(ng["bootstrap"][i], 4),
            "neighbourhood_noise": round(ng["noise"][i], 4),
            "exact_tiebreak_only": round(ex["tiebreak"][i], 4),
            "exact_bootstrap": round(ex["bootstrap"][i], 4),
            "exact_noise": round(ex["noise"][i], 4),
            "tied_at_kth": result["ties"][i],
        })
    return out


def quantile(xs, q):
    s = sorted(xs)
    if not s:
        return None
    pos = (len(s) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def describe(values):
    return {"n": len(values), "min": round(min(values), 4), "q25": round(quantile(values, .25), 4),
            "median": round(quantile(values, .5), 4), "q75": round(quantile(values, .75), 4),
            "max": round(max(values), 4), "mean": round(sum(values) / len(values), 4)}


def summarise(table):
    """Aggregate per-plant rows: overall, by size band, by product type."""
    def group(keyf):
        g = defaultdict(list)
        for r in table:
            g[keyf(r)].append(r["stability"])
        return {k: describe(v) for k, v in sorted(g.items())}
    allv = [r["stability"] for r in table]
    return {
        "overall": describe(allv),
        "neighbourhood_bootstrap": describe([r["neighbourhood_bootstrap"] for r in table]),
        "neighbourhood_noise": describe([r["neighbourhood_noise"] for r in table]),
        "exact_tiebreak_only": describe([r["exact_tiebreak_only"] for r in table]),
        "exact_bootstrap": describe([r["exact_bootstrap"] for r in table]),
        "exact_noise": describe([r["exact_noise"] for r in table]),
        "tied_at_kth": describe([float(r["tied_at_kth"]) for r in table]),
        "share_stability_at_least_0_5": round(sum(1 for v in allv if v >= 0.5) / len(allv), 4),
        "share_stability_at_least_0_9": round(sum(1 for v in allv if v >= 0.9) / len(allv), 4),
        "by_size_band": group(lambda r: r["size_band"]),
        "by_product_type": group(lambda r: r["product_type"]),
    }


def group_stability(table, plants):
    """Median stability for groups named like the comparison page's groups.

    Keys are ``inj-size-<band>``, ``inj-prod-<product type>`` and ``rel-fam-<family>``.
    Membership is by the plant's own attributes (current size band, first
    listed product type, families held), not by plant-year.
    """
    fams = {p[0]: p[10] for p in plants}
    g = defaultdict(list)
    for r in table:
        g["inj-size-" + r["size_band"]].append(r["stability"])
        g["inj-prod-" + r["product_type"]].append(r["stability"])
        for f in fams.get(r["id"], []):
            g["rel-fam-" + f].append(r["stability"])
    return {k: {"n": len(v), "median": round(quantile(v, .5), 4),
                "q25": round(quantile(v, .25), 4), "q75": round(quantile(v, .75), 4)}
            for k, v in sorted(g.items())}
