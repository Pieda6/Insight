"""Electron beams: TG-51 Sec. X."""
import math

import numpy as np

from tg51calc.corrections import corrected_reading, ndw_gy_per_c
from tg51calc.photons import shift


def r50(ws, beam):
    """Eqs. (16)-(17) from I50 on the scan shifted upstream by 0.5 rcav."""
    scan = ws.scans[(beam['beam_id'], 'electron')]
    depth = scan[:, 0] - shift(ws, beam['scans']['electron'], 0.5)
    i = int(scan[:, 1].argmax())
    half = scan[i, 1] / 2.0
    tail_d, tail_m = depth[i:], scan[i:, 1]
    k = int(np.argmax(tail_m <= half))
    i50 = tail_d[k - 1] + (tail_m[k - 1] - half) * (tail_d[k] - tail_d[k - 1]) / (tail_m[k - 1] - tail_m[k])
    return 1.029 * i50 - 0.06 if i50 <= 10 else 1.059 * i50 - 0.37


def k_r50(r, kind):
    """Eq. (19) for cylindrical, Eq. (20) for plane-parallel chambers."""
    if kind == 'cylindrical':
        return 0.9905 + 0.0710 * math.exp(-r / 3.67)
    return 1.2239 - 0.145 * r ** 0.214


def p_gr(ws, beam, purpose, main, chamber):
    """Eq. (21) for cylindrical chambers; 1 for plane-parallel."""
    if chamber['type'] != 'cylindrical':
        return 1.0
    g = ws.readings[(beam['beam_id'], purpose + '_gradient')][0]
    return abs((float(g['reading_nC']) / float(g['mu'])) / (float(main['reading_nC']) / float(main['mu'])))


def dose(ws, beam):
    cl = ws.clinic_of[beam['beam_id']]
    chamber = ws.chamber[beam['reference_chamber']]
    cross = chamber.get('calibration') == 'cross-calibrated'
    r = r50(ws, beam)
    m, main = corrected_reading(ws.readings[(beam['beam_id'], 'reference')], chamber, cl['electrometer'], cross)
    if cross:                                                       # Eq. (22)
        cc = chamber['cross_calibration']
        cb = ws.beam[cc['beam_id']]
        cyl = ws.chamber[cc['cylindrical_chamber']]
        rc = r50(ws, cb)
        mc, mainc = corrected_reading(ws.readings[(cb['beam_id'], 'crosscal_cylindrical')], cyl, cl['electrometer'])
        dw = mc * p_gr(ws, cb, 'crosscal_cylindrical', mainc, cyl) * k_r50(rc, 'cylindrical') \
            * ws.kecal[cyl['model']] * ndw_gy_per_c(cyl)
        mp, _ = corrected_reading(ws.readings[(cb['beam_id'], 'crosscal_plane_parallel')], chamber, cl['electrometer'], True)
        calib = dw / (mp * k_r50(rc, chamber['type']))
    else:
        calib = ws.kecal[chamber['model']] * ndw_gy_per_c(chamber)
    d_ref = m * 1e-9 * p_gr(ws, beam, 'reference', main, chamber) * k_r50(r, chamber['type']) * calib * 100.0
    pdd = ws.pdd[beam['beam_id']]
    return d_ref, d_ref / (float(np.interp(0.6 * r - 0.1, pdd[:, 0], pdd[:, 1])) / 100.0)   # Eq. (18), Sec. X.D
