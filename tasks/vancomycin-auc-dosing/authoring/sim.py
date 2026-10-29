"""Generator's model for vancomycin-auc-dosing (third implementation).

Tracks the amount of drug in the body from event to event (state propagation) for a one-compartment model with
zero-order infusion segments and first-order elimination. The elimination rate is found from the two usable
levels by a bracketed secant method on the log of the concentration ratio.
"""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import math


def amount_at(t, segments, ke):
    """Amount in the body per unit volume factor: sum over segments, by propagating a running state."""
    state, clock = 0.0, None
    events = []
    for s, e, mg in segments:
        if e > s:
            events.append((s, mg / (e - s)))
            events.append((e, -mg / (e - s)))
    events.sort()
    rate = 0.0
    for when, dr in events:
        if when >= t:
            break
        if clock is not None:
            dt = when - clock
            state = state * math.exp(-ke * dt) + rate / ke * (1 - math.exp(-ke * dt))
        clock = when
        rate += dr
    if clock is None:
        return 0.0
    dt = t - clock
    return state * math.exp(-ke * dt) + rate / ke * (1 - math.exp(-ke * dt))


def infused_by(t, segments):
    total = 0.0
    for s, e, mg in segments:
        if t > s:
            total += mg * (min(t, e) - s) / (e - s)
    return total


def fit(segments, t1, c1, t2, c2, lo=1e-4, hi=3.0):
    """Return (ke, V, roots) with roots the number of sign changes of the ratio residual on a grid."""
    def g(k):
        a1, a2 = amount_at(t1, segments, k), amount_at(t2, segments, k)
        return math.log(a1 / a2) - math.log(c1 / c2)
    grid = [lo * (hi / lo) ** (i / 400) for i in range(401)]
    vals = [g(k) for k in grid]
    brackets = [(grid[i], grid[i + 1]) for i in range(400) if (vals[i] > 0) != (vals[i + 1] > 0)]
    if len(brackets) != 1:
        return None, None, len(brackets)
    a, b = brackets[0]
    fa, fb = g(a), g(b)
    for _ in range(200):
        m = b - fb * (b - a) / (fb - fa)
        if not (min(a, b) < m < max(a, b)):
            m = 0.5 * (a + b)
        fm = g(m)
        if (fm > 0) == (fa > 0):
            a, fa = m, fm
        else:
            b, fb = m, fm
        if abs(b - a) < 1e-15:
            break
    ke = m
    V = amount_at(t1, segments, ke) / c1
    return ke, V, 1


def auc_to(T, segments, ke, V):
    """Mass balance: integral of C from 0 to T = (amount infused - amount left) / (ke V)."""
    return (infused_by(T, segments) - amount_at(T, segments, ke)) / (ke * V)
