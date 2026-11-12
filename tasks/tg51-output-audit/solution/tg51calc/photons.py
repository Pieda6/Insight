"""Photon beams: TG-51 Secs. VIII.A-B and IX with the 2014 addendum."""
import numpy as np

# Addendum Sec. 3.E (i) and (ii): chambers with no new data that take the data of their replacement.
REPLACED_BY = {'PTW 31003': 'PTW 31013', 'Wellhofer IC-10': 'IBA CC13'}
TG51_X = np.array([58.0, 63.0, 66.0, 71.0, 81.0, 93.0])


def shift(ws, serial, fraction):
    ch = ws.chamber[serial]
    return fraction * ch['cavity_radius_cm'] if ch['type'] == 'cylindrical' else 0.0


def pdd_at_10(ws, beam, name):
    """%dd(10) on the depth-ionization curve shifted upstream by 0.6 rcav (Sec. VIII.A)."""
    scan = ws.scans[(beam['beam_id'], name)]
    depth = scan[:, 0] - shift(ws, beam['scans'][name], 0.6)
    return 100.0 * np.interp(10.0, depth, scan[:, 1]) / scan[:, 1].max()


def beam_quality(ws, beam):
    """%dd(10)x: Eqs. (13)-(15); the foil for every flattening-filter-free beam (addendum Sec. 4.K)."""
    open_pct = pdd_at_10(ws, beam, 'open')
    if beam['energy_MV'] < 10 and not beam['fff']:
        return open_pct, open_pct
    foil = [n for n in beam['scans'] if n.startswith('lead_foil')]
    if foil:
        pb = pdd_at_10(ws, beam, foil[0])
        if foil[0] == 'lead_foil_50cm':
            x = (0.8905 + 0.00150 * pb) * pb if pb >= 73.0 else pb
        else:
            x = (0.8116 + 0.00264 * pb) * pb if pb >= 71.0 else pb
        return x, open_pct
    x = 1.267 * open_pct - 20.0 if open_pct > 75.0 else open_pct
    return x, open_pct


def k_q(ws, model, x):
    """Addendum Table I (Eq. 1; below 63 linear to 1.000 at 58), otherwise TG-51 Table I."""
    model = REPLACED_BY.get(model, model)
    if model in ws.kq_addendum:
        r = ws.kq_addendum[model]
        if x <= 63.0:
            return float(np.interp(x, [58.0, 63.0], [1.0, float(r['kq_63'])]))
        return float(r['A']) + float(r['B']) * 1e-3 * x + float(r['C']) * 1e-5 * x * x
    r = ws.kq_tg51[model]
    return float(np.interp(x, TG51_X, [float(r['kq_%d' % v]) for v in TG51_X]))


def p_rp(ws, beam, chamber):
    """Addendum Sec. 5.C.7: centre value over the average along the chamber's active length."""
    prof = ws.profiles[beam['beam_id']]
    inside = np.abs(prof[:, 0]) <= chamber['active_length_cm'] / 2 + 1e-9
    return float(np.interp(0.0, prof[:, 0], prof[:, 1]) / prof[inside, 1].mean())


def dose(ws, beam, m, ndw):
    """Dose per MU at the reference point (Eq. 3) and at dmax (Sec. IX.C), cGy."""
    chamber = ws.chamber[beam['reference_chamber']]
    x, open_pct = beam_quality(ws, beam)
    d10 = m * 1e-9 * p_rp(ws, beam, chamber) * k_q(ws, chamber['model'], x) * ndw * 100.0
    if beam['setup'] == 'SAD':
        return d10, d10 / beam['tmr_10']
    return d10, d10 / (open_pct / 100.0)
