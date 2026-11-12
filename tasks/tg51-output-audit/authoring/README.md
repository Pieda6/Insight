# Authoring tools for tg51-output-audit

These files are not copied into the agent or verifier images. Run them from this folder. None of them writes
`__pycache__`.

## Provenance
- `addendum_kq.csv` is Table I of the TG-51 photon addendum (McEwen et al., Med Phys 2014;41(4):041501);
  `tg51_photon_kq.csv` is Table I and `tg51_kecal.csv` Tables II and III of TG-51 (Almond et al., Med Phys
  1999;26(9):1847-1870), transcribed from the published reports.
- `sources/tg51_sections_VII_to_X.txt` and `sources/addendum_sections_3D_to_4M_and_5C.txt` quote the report text
  for every rule the verifier applies: TG-51 Secs. VII (Eqs. 8-12, Pion limit, Ppol, Pelec), VIII.A-B (scan shift,
  Eqs. 13-15), IX (Eq. 3, dose at other depths), X (Eqs. 16-22, plane-parallel cross-calibration with Pelec = 1, dose
  at dmax from clinical PDD); addendum Secs. 3.D (Eq. 1 and the rule below 63), 3.E (chamber replacements), 4.D, 4.H
  (Eq. 15 for flattened beams), 4.K (lead foil for flattening-filter-free beams), Eq. (3), 5.C.4 (Pleak = 1 below
  0.1 percent) and 5.C.7 (Prp as the average over the chamber's active length).
- `generate.py` (seed 19990901) builds 12 clinics and 138 beams, writes the worksheets to both data copies,
  `../tests/case_tags.json` and `evidence/answers.json`. Readings are scaled so the dose at dmax is 0.985 to 1.015
  cGy/MU; recombination is measured with a voltage ratio of 2.

## Settled readings
Stated as facts in instruction.md: the point of measurement at 10 cm (photons) and at the TG-51 reference depth
(electrons), leakage below 0.1 percent of every reading (so Pleak = 1 by addendum Sec. 5.C.4), barometer readings not
corrected to sea level, linear interpolation, readings signed as displayed, the dose at dmax in the set-up of the dose
measurement.

## Evidence (outputs saved in `evidence/`)
- `agreement.txt`: solution and engine agree on all 138 beams, with every count quoted in the READMEs.
- `local_check.txt` (`python3 local_check.py ..`): oracle passes every test, empty output fails.
- `calibration.txt` (`calibrate.py`): 14 shortcut solutions and how many beams each gets wrong.
- `generate_output.txt`: the number of beams carrying each case tag.
