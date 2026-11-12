"""Readers for the clinics' calibration worksheets."""
import csv
import json
import os

import numpy as np


def _rows(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


class Worksheets:

    def __init__(self, data_dir):
        with open(os.path.join(data_dir, 'audit.json')) as f:
            self.audit = json.load(f)
        self.chamber, self.clinic_of, self.beams = {}, {}, []
        for cl in self.audit['clinics']:
            for ch in cl['chambers']:
                self.chamber[ch['serial']] = ch
            for b in cl['beams']:
                self.clinic_of[b['beam_id']] = cl
                self.beams.append(b)
        self.beam = {b['beam_id']: b for b in self.beams}
        self.readings = {}
        for r in _rows(os.path.join(data_dir, 'readings.csv')):
            self.readings.setdefault((r['beam_id'], r['purpose']), []).append(r)
        self.scans = self._series(os.path.join(data_dir, 'depth_scans.csv'), ('beam_id', 'scan'), 'depth_cm', 'reading')
        self.profiles = self._series(os.path.join(data_dir, 'profiles.csv'), ('beam_id',), 'position_cm', 'relative_dose')
        self.pdd = self._series(os.path.join(data_dir, 'electron_pdd.csv'), ('beam_id',), 'depth_cm', 'pdd_percent')
        self.kq_tg51 = {r['chamber']: r for r in _rows(os.path.join(data_dir, 'tg51_photon_kq.csv'))}
        self.kq_addendum = {r['chamber']: r for r in _rows(os.path.join(data_dir, 'addendum_kq.csv'))}
        self.kecal = {r['chamber']: float(r['kecal']) for r in _rows(os.path.join(data_dir, 'tg51_kecal.csv'))}

    @staticmethod
    def _series(path, key, x, y):
        out = {}
        for r in _rows(path):
            k = tuple(r[c] for c in key)
            out.setdefault(k if len(k) > 1 else k[0], []).append((float(r[x]), float(r[y])))
        return {k: np.array(sorted(v), dtype=float) for k, v in out.items()}
