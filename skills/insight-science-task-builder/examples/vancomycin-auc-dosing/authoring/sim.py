"""Generator's model for vancomycin-auc-dosing (third implementation).

One-compartment model with constant-rate infusion segments and first-order elimination at the patient's own
clearance, plus the dialyzer's clearance while a hemodialysis session runs. The amount in the body is propagated
in closed form between consecutive breakpoints (infusion and dialysis starts and stops). The patient's clearance
and volume are fitted to the two usable levels by nested bisection: outer on clearance, inner on volume.
"""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import math


def prepare(segs, hd):
    """Intervals between consecutive breakpoints with their infusion rate (mg/h) and dialyzer clearance (L/h)."""
    cuts = {0.0}
    for s, e, _ in list(segs) + list(hd):
        cuts.update(x for x in (s, e) if x > 0)
    cuts = sorted(cuts)
    out = []
    for a, b in zip(cuts, cuts[1:] + [float("inf")]):
        m = a + 1e-9 if b == float("inf") else 0.5 * (a + b)
        out.append((a, b, sum(mg / (e - s) for s, e, mg in segs if s < m < e),
                    sum(c for s, e, c in hd if s < m < e)))
    return out


def _amount(prep, t, cl, V):
    A = 0.0
    for a, b, rate, chd in prep:
        if a >= t:
            break
        k = (cl + chd) / V
        f = math.exp(-k * (min(b, t) - a))
        A = A * f + rate / k * (1 - f)
    return A


def amount_at(t, segs, hd, cl, V):
    return _amount(prepare(segs, hd), t, cl, V)


def _auc(prep, t_from, t_to, cl, V):
    A, total = 0.0, 0.0
    for a, b, rate, chd in prep:
        if a >= t_to:
            break
        k = (cl + chd) / V
        b2 = min(b, t_to)
        lo = max(a, t_from)
        if lo > a:                       # advance to t_from inside this interval
            f = math.exp(-k * (min(lo, b2) - a))
            A_lo = A * f + rate / k * (1 - f)
        else:
            A_lo = A
        if b2 > lo:
            d = b2 - lo
            f = math.exp(-k * d)
            total += A_lo * (1 - f) / k + rate / k * (d - (1 - f) / k)
        f = math.exp(-k * (b2 - a))
        A = A * f + rate / k * (1 - f)
    return total / V


def auc_between(t_from, t_to, segs, hd, cl, V):
    """Integral of the concentration from t_from to t_to (closed form per interval)."""
    return _auc(prepare(segs, hd), t_from, t_to, cl, V)


def _bisect(f, lo, hi, iters=60):
    flo = f(lo)
    for _ in range(iters):
        mid = math.sqrt(lo * hi)
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return math.sqrt(lo * hi)


def _ke_for(prep, V, t1, c1, t2, c2):
    """Elimination rate (patient's own) matching the ratio of the two levels at this volume."""
    target = math.log(c1 / c2)

    def f(ke):
        a1, a2 = _amount(prep, t1, ke * V, V), _amount(prep, t2, ke * V, V)
        return math.log(a1 / a2) - target if a1 > 0 and a2 > 0 else None
    lo, hi = 1e-4, 3.0
    flo, fhi = f(lo), f(hi)
    if flo is None or fhi is None or (flo > 0) == (fhi > 0):
        return None
    for _ in range(46):
        mid = math.sqrt(lo * hi)
        fm = f(mid)
        if fm is None:
            return None
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return math.sqrt(lo * hi)


def fit(segs, hd, t1, c1, t2, c2, scan=30):
    """Return (cl, V, n_solutions): outer search on volume, inner elimination rate from the level ratio."""
    prep = prepare(segs, hd)

    def g(V):
        ke = _ke_for(prep, V, t1, c1, t2, c2)
        if ke is None:
            return None
        return _amount(prep, t1, ke * V, V) / V - c1
    grid = [5.0 * (1500.0 / 5.0) ** (i / scan) for i in range(scan + 1)]
    vals = [g(V) for V in grid]
    brackets = [(grid[i], grid[i + 1]) for i in range(scan)
                if vals[i] is not None and vals[i + 1] is not None and (vals[i] > 0) != (vals[i + 1] > 0)]
    if len(brackets) != 1:
        return None, None, len(brackets)
    lo, hi = brackets[0]
    glo = g(lo)
    for _ in range(50):
        mid = math.sqrt(lo * hi)
        gm = g(mid)
        if gm is None:
            return None, None, 0
        if (gm > 0) == (glo > 0):
            lo, glo = mid, gm
        else:
            hi = mid
    V = math.sqrt(lo * hi)
    ke = _ke_for(prep, V, t1, c1, t2, c2)
    # uniqueness of the elimination rate at the solution
    target = math.log(c1 / c2)
    ks = [1e-4 * (3e4) ** (i / 80) for i in range(81)]
    r = [math.log(_amount(prep, t1, k * V, V) / _amount(prep, t2, k * V, V)) - target for k in ks]
    if sum((r[i] > 0) != (r[i + 1] > 0) for i in range(80)) != 1:
        return None, None, 2
    return ke * V, V, 1


def count_solutions(segs, hd, t1, c1, t2, c2):
    """Distinct exact (clearance, volume) solutions found by Newton from a 7 x 7 grid of starts."""
    prep = prepare(segs, hd)

    def F(u):
        cl, V = math.exp(u[0]), math.exp(u[1])
        a1, a2 = _amount(prep, t1, cl, V), _amount(prep, t2, cl, V)
        if a1 <= 0 or a2 <= 0:
            return None
        return math.log(a1 / V / c1), math.log(a2 / V / c2)
    found = []
    for i in range(7):
        for j in range(7):
            u = [math.log(0.005) + i * math.log(40.0 / 0.005) / 6, math.log(5.0) + j * math.log(400.0) / 6]
            for _ in range(80):
                r = F(u)
                if r is None or abs(u[0]) > 12 or abs(u[1]) > 12:
                    break
                if r[0] ** 2 + r[1] ** 2 < 1e-24:
                    if not any(abs(u[0] - a) < 1e-5 and abs(u[1] - b) < 1e-5 for a, b in found):
                        found.append((u[0], u[1]))
                    break
                h = 1e-7
                ra, rb = F([u[0] + h, u[1]]), F([u[0], u[1] + h])
                if ra is None or rb is None:
                    break
                j11, j21, j12, j22 = (ra[0] - r[0]) / h, (ra[1] - r[1]) / h, (rb[0] - r[0]) / h, (rb[1] - r[1]) / h
                det = j11 * j22 - j12 * j21
                if det == 0:
                    break
                d0, d1 = (-r[0] * j22 + r[1] * j12) / det, (-r[1] * j11 + r[0] * j21) / det
                lim = max(1.0, abs(d0), abs(d1))
                u = [u[0] + d0 / lim, u[1] + d1 / lim]
    plausible = [(a, b) for a, b in found if math.log(1e-3) < a < math.log(60) and math.log(3) < b < math.log(3000)]
    return len(plausible)
