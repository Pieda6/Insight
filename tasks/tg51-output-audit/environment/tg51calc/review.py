"""Calibration review: dose per MU for every beam in the worksheets."""
import csv

from tg51calc import electrons, photons
from tg51calc.corrections import corrected_reading
from tg51calc.worksheets import Worksheets


def ndw_gy_per_c(chamber):
    if chamber['ndw_unit'] == 'cGy/nC':
        return chamber['ndw'] * 1e7
    return chamber['ndw']


def main(argv):
    data_dir, out_csv = argv
    ws = Worksheets(data_dir)
    out = open(out_csv, 'wb')
    w = csv.writer(out)
    w.writerow(['beam_id', 'dose_ref_cgy_per_mu', 'dose_dmax_cgy_per_mu'])
    for beam in ws.beams:
        if beam['modality'] == 'photon':
            chamber = ws.chamber[beam['reference_chamber']]
            m, _ = corrected_reading(ws.readings[(beam['beam_id'], 'reference')], chamber,
                                     ws.clinic_of[beam['beam_id']]['electrometer'])
            d_ref, d_max = photons.dose(ws, beam, m, ndw_gy_per_c(chamber))
        else:
            d_ref, d_max = electrons.dose(ws, beam, ndw_gy_per_c)
        w.writerow([beam['beam_id'], '%.5f' % d_ref, '%.5f' % d_max])
        print beam['beam_id'], '%.5f' % d_ref, '%.5f' % d_max
    out.close()
