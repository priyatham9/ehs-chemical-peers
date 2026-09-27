"""Small, dependency-free statistics used by the pipeline and mirrored in the site.

The funnel plot asks one question of each plant: given the hours it worked,
is its injury count further from the peer rate than chance alone would put
it? Chance is modelled as a Poisson count with mean equal to the peer rate
times the plant's hours. Limits are exact Poisson quantiles, not a normal
approximation, because small plants have expected counts well below 5.
"""
import math

PER = 200000.0  # hours in 100 full-time worker-years; the OSHA rate base


def rate(cases, hours):
    """Injury rate per 200,000 hours (TRIR when ``cases`` is all recordables)."""
    return cases * PER / hours if hours and hours > 0 else None


def poisson_cdf(k, mu):
    """P(X <= k) for X ~ Poisson(mu); stable for mu up to a few thousand."""
    if k < 0:
        return 0.0
    if mu <= 0:
        return 1.0
    term = math.exp(-mu)
    if term == 0.0:  # large mu: fall back to the log-space sum
        logp = -mu
        total = 0.0
        for i in range(int(k) + 1):
            if i:
                logp += math.log(mu) - math.log(i)
            total += math.exp(logp)
        return min(total, 1.0)
    total = term
    for i in range(1, int(k) + 1):
        term *= mu / i
        total += term
    return min(total, 1.0)


def poisson_quantile(p, mu):
    """Smallest k with P(X <= k) >= p."""
    if mu <= 0:
        return 0
    k = 0
    lo = max(0, int(mu - 10 * math.sqrt(mu) - 10))
    k = lo
    while poisson_cdf(k, mu) < p:
        k += 1
    return k


def funnel_limits(peer_rate, hours, p=0.975):
    """Lower and upper rate limits for a plant of ``hours`` under ``peer_rate``.

    Returns (low, high) as rates per 200,000 hours. With p=0.975 the band holds
    about 95% of plants that truly run at the peer rate; p=0.999 gives the
    99.8% band.
    """
    mu = peer_rate * hours / PER
    lo_k = poisson_quantile(1 - p, mu)
    hi_k = poisson_quantile(p, mu)
    return rate(lo_k, hours), rate(hi_k, hours)


def classify(cases, hours, peer_rate):
    """'above', 'below' or 'within' the 95% funnel for one plant."""
    lo, hi = funnel_limits(peer_rate, hours)
    r = rate(cases, hours)
    if r is None:
        return "no data"
    if r > hi:
        return "above"
    if r < lo:
        return "below"
    return "within"


def prob_zero(peer_rate, hours):
    """Chance a plant running exactly at the peer rate records zero cases."""
    return math.exp(-peer_rate * hours / PER)


def one_case_swing(hours):
    """How far one recordable moves the rate at ``hours``."""
    return PER / hours if hours else None


def median(values):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def quantile(values, q):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    pos = q * (len(v) - 1)
    i = int(math.floor(pos))
    j = min(i + 1, len(v) - 1)
    return v[i] + (v[j] - v[i]) * (pos - i)


def spearman(xs, ys):
    """Rank correlation with average ranks for ties."""
    def ranks(a):
        order = sorted(range(len(a)), key=lambda i: a[i])
        r = [0.0] * len(a)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and a[order[j + 1]] == a[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for t in range(i, j + 1):
                r[order[t]] = avg
            i = j + 1
        return r
    if len(xs) < 3:
        return None
    rx, ry = ranks(list(xs)), ranks(list(ys))
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None
