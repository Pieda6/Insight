"""Electron beams, TG-51 Sec. X."""
import math

import numpy as np
import scipy

from tg51calc.corrections import corrected_reading


def r50(ws, beam):
    """Eqs. (16)-(17) from the 50 % ionization depth of the scan."""
    scan = ws.scans[(beam['beam_id'], 'electron')]
    i = scan[:, 1].argmax()
    tail = scan[i:]
    half = scan[i, 1] / 2
    i50 = scipy.interp(half, tail[::-1, 1], tail[::-1, 0])
    if i50 <= 10:
        return 1.029 * i50 - 0.06
    return 1.059 * i50 - 0.37


def k_r50(r):
    """Eq. (19)."""
    return 0.9905 + 0.0710 * math.exp(-r / 3.67)


def p_gr(ws, beam, purpose, main):
    g = ws.readings.get((beam['beam_id'], purpose + '_gradient'))
    if not g:
        return 1.0
    return abs(float(g[0]['reading_nC']) / float(main['reading_nC']))


def dose(ws, beam, ndw_of):
    cl = ws.clinic_of[beam['beam_id']]
    chamber = ws.chamber[beam['reference_chamber']]
    r = r50(ws, beam)
    m, main = corrected_reading(ws.readings[(beam['beam_id'], 'reference')], chamber, cl['electrometer'])
    if chamber.get('calibration') == 'cross-calibrated':
        cc = chamber['cross_calibration']
        cb = [b for b in ws.beams if b['beam_id'] == cc['beam_id']][0]
        cyl = ws.chamber[cc['cylindrical_chamber']]
        rc = r50(ws, cb)
        mc, mainc = corrected_reading(ws.readings[(cb['beam_id'], 'crosscal_cylindrical')], cyl, cl['electrometer'])
        dw = mc * p_gr(ws, cb, 'crosscal_cylindrical', mainc) * k_r50(rc) * ws.kecal[cyl['model']] * ndw_of(cyl)
        mp, _ = corrected_reading(ws.readings[(cb['beam_id'], 'crosscal_plane_parallel')], chamber, cl['electrometer'])
        calib = dw / (mp * k_r50(rc))
    else:
        calib = ws.kecal[chamber['model']] * ndw_of(chamber)
    d_ref = m * 1e-9 * p_gr(ws, beam, 'reference', main) * k_r50(r) * calib * 100.
    depth, pdd = np.array(sorted(ws.pdd[beam['beam_id']])).T
    return d_ref, d_ref / (scipy.interp(0.6 * r - 0.1, depth, pdd) / 100.)
