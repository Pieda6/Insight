"""Photon beams, TG-51 Secs. VIII.B and IX."""
import numpy as np
import scipy

# In-house equivalents for chambers bought after the protocol was published (agreed 2006).
EQUIVALENT = {
    'Exradin A19': 'Exradin A12', 'Exradin A12S': 'NE2577', 'PTW 30012': 'PTW N30004', 'PTW 30013': 'PTW N30001',
    'PTW 30010': 'PTW N30001', 'PTW 30011': 'PTW N30002', 'PTW 31013': 'PTW 31003', 'IBA FC65-G': 'NE2571',
    'IBA FC65-P': 'NE2571', 'IBA FC23-C': 'NE2577', 'IBA CC25': 'Wellhofer IC-10', 'IBA CC13': 'Wellhofer IC-10',
}
KQ_X = [58.0, 63.0, 66.0, 71.0, 81.0, 93.0]


def pdd_at_10(scan):
    """Percentage depth dose at 10 cm. The scanner software reports depths at the effective point."""
    return 100. * scipy.interp(10.0, scan[:, 0], scan[:, 1]) / scan[:, 1].max()


def beam_quality(ws, beam):
    """%dd(10)x, Eqs. (13)-(15)."""
    scans = dict((name, ws.scans[(beam['beam_id'], name)]) for name in beam['scans'])
    pct = pdd_at_10(scans['open'])
    if beam['energy_MV'] < 10:
        return pct
    foil = [n for n in scans if n.startswith('lead_foil')]
    if foil:
        pb = pdd_at_10(scans[foil[0]])
        if pb >= 73.0:
            return (0.8905 + 0.00150 * pb) * pb
        return pb
    return pct


def k_q(ws, model, x):
    """Table I, interpolated linearly in %dd(10)x."""
    model = EQUIVALENT.get(model, model)
    for row in ws.kq_table:
        if row['chamber'] == model:
            ys = [float(row['kq_%d' % v]) for v in KQ_X]
            return scipy.interp(x, KQ_X, ys)
    raise KeyError(model)


def dose(ws, beam, m, ndw):
    """Dose per MU at 10 cm (Eq. 3) and at dmax (Sec. IX.C), cGy."""
    chamber = ws.chamber[beam['reference_chamber']]
    x = beam_quality(ws, beam)
    d10 = m * 1e-9 * k_q(ws, chamber['model'], x) * ndw * 100.
    return d10, d10 / (x / 100.)
