"""Calibration review: dose per MU for every beam in the worksheets."""
import csv

from tg51calc import electrons, photons
from tg51calc.corrections import corrected_reading, ndw_gy_per_c
from tg51calc.worksheets import Worksheets


def main(argv):
    data_dir, out_csv = argv
    ws = Worksheets(data_dir)
    with open(out_csv, 'w', newline='') as out:
        w = csv.writer(out, lineterminator='\n')
        w.writerow(['beam_id', 'dose_ref_cgy_per_mu', 'dose_dmax_cgy_per_mu'])
        for beam in ws.beams:
            if beam['modality'] == 'photon':
                chamber = ws.chamber[beam['reference_chamber']]
                m, _ = corrected_reading(ws.readings[(beam['beam_id'], 'reference')], chamber,
                                         ws.clinic_of[beam['beam_id']]['electrometer'])
                d_ref, d_max = photons.dose(ws, beam, m, ndw_gy_per_c(chamber))
            else:
                d_ref, d_max = electrons.dose(ws, beam)
            w.writerow([beam['beam_id'], '%.5f' % d_ref, '%.5f' % d_max])
