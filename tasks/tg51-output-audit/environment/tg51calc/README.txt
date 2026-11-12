tg51calc 1.4.2
==============

Calibration review calculations for the network's member clinics, following AAPM TG-51
(Almond et al., Med Phys 26:1847, 1999).

    python -m tg51calc /path/to/worksheets review.csv

Needs Python 2.6 or 2.7, numpy and scipy.

Inputs are the worksheet exports (audit.json, readings.csv, depth_scans.csv, electron_pdd.csv) and the
protocol tables (tg51_photon_kq.csv, tg51_kecal.csv). Depth scans are taken as exported by the scanner
software, which reports depths at the effective point of measurement.

History
-------
1.0    2004  first version, photon beams only
1.2    2005  electron beams, cross-calibration of plane-parallel chambers
1.3    2006  in-house kQ equivalents for chambers bought after 1999
1.4    2009  hPa barometers; csv report
1.4.2  2009  last change
