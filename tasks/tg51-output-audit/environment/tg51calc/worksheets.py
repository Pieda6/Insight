"""Readers for the clinics' calibration worksheets."""
import csv
import json
import os

import numpy as np


def _rows(path):
    f = open(path, 'rb')
    rows = list(csv.DictReader(f))
    f.close()
    return rows


class Worksheets(object):

    def __init__(self, data_dir):
        self.audit = json.load(open(os.path.join(data_dir, 'audit.json')))
        self.chamber = {}
        self.clinic_of = {}
        self.beams = []
        for cl in self.audit['clinics']:
            for ch in cl['chambers']:
                self.chamber[ch['serial']] = ch
            for b in cl['beams']:
                self.clinic_of[b['beam_id']] = cl
                self.beams.append(b)
        self.readings = {}
        for r in _rows(os.path.join(data_dir, 'readings.csv')):
            self.readings.setdefault((r['beam_id'], r['purpose']), []).append(r)
        scans = {}
        for r in _rows(os.path.join(data_dir, 'depth_scans.csv')):
            scans.setdefault((r['beam_id'], r['scan']), []).append((float(r['depth_cm']), float(r['reading'])))
        self.scans = {}
        for k, v in scans.iteritems():
            self.scans[k] = np.array(sorted(v), dtype=np.float)
        self.pdd = {}
        for r in _rows(os.path.join(data_dir, 'electron_pdd.csv')):
            self.pdd.setdefault(r['beam_id'], []).append((float(r['depth_cm']), float(r['pdd_percent'])))
        self.kq_table = _rows(os.path.join(data_dir, 'tg51_photon_kq.csv'))
        self.kecal = dict((r['chamber'], float(r['kecal'])) for r in _rows(os.path.join(data_dir, 'tg51_kecal.csv')))
