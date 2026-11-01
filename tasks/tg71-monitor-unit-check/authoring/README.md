# Authoring tools for tg71-monitor-unit-check

These files are not copied into the agent or verifier images. Run them from this folder. None of them writes
`__pycache__`.

## Provenance
- The commissioning tables in `environment/data` are TG-71 Tables II (PDDN, 6 MV, SSD 100 cm), III (TPR), IV (Sc,p,
  Sc, Sp), V (open field off-axis ratios), VI (physical wedge factors), VII (9 MeV electron output factors), VIII
  (SSDeff) and IX (9 MeV air gap factors), transcribed from the report. `machine.json` takes D0 = 0.800 cGy/MU at
  SSD0 90 cm and 10 cm depth for 6 MV and 1.000 cGy/MU at SSD 100 cm and dm 2.1 cm for 9 MeV from the Section 8
  examples; the block tray factor 0.970 is the department's measured value. `tg71.txt` is the text of the report.
- `generate.py` (seed 20140301) builds 33 patients and 91 beams and writes `plans.json` to both data copies,
  `evidence/answers.json` and `../tests/case_tags.json`. Draws outside a table's range, or where the MU the protocol
  allows spread by more than 0.3 percent, are redrawn (14 draws).

## Settled readings
From the report: Eqs. (1) to (4), the field size of Sec. 2.A.2 for each factor (tertiary MLC treated as a block),
Eq. (14) and (15) for PDDN at another SSD, the OAR distance projected to 100 cm (Table V), Eqs. (6) to (8), and
Eqs. (10) to (13) and (22) with the geometric mean of SSDeff (Sec. 3.B.2.d and 8.B). Stated as facts in
instruction.md: flat entrance surfaces, jaw settings and shaped-field equivalent squares at the isocenter (the
planning system's value for the field incident on the patient), depth along the central axis and off-axis position in
the plane of the point, electron insert size projected to the isocenter, one dm for every electron insert, linear
interpolation.

## Evidence (outputs saved in `evidence/`)
- `agreement.txt`: solution and engine agree on all 91 beams, with every count quoted in the READMEs.
- `local_check.txt` (`python3 local_check.py ..`): oracle passes every test, empty output fails.
- `calibration.txt` (`calibrate.py`): 13 shortcut solutions and how many beams each gets wrong, and the Eq. (3)
  misreadings counted from the case tags.
- `generate_output.txt`.
