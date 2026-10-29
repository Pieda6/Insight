# Authoring tools for storm-drain-energy

These files are not copied into the agent or verifier images. Run them from this folder.

## Provenance
- `generate.py` (seed 92024) builds the 44 systems and writes both data copies (`../environment/data`,
  `../tests/data`). Topology, inlet flows (10-year 0.4 to 5.5 cfs, 100-year 1.5 to 1.9 times larger), slopes
  (mostly flat, about 0.0008 to 0.004, some steep, 0.012 to 0.05), Manning's n (0.011 to 0.013 concrete and PVC,
  0.024 corrugated metal, HEC-22 Table 9.1) and diameters (15 to 60 inches, never decreasing downstream, 100-year
  flow at most 85 percent of the equation 9.2 capacity) come first. Walking upstream from the outfall with its
  own model, it then chooses each pipe's length, each inflow pipe's drop into its structure (crown matched, small,
  medium, large and over 10 diameters) and each rim, placing values on purpose a little to either side of the
  thresholds that change an answer. Every comparison is kept at least 0.001 ft from its threshold in both events.
  Inverts and rims are to 0.01 ft and lengths to 0.1 ft.
- `sim.py` is the generator's own model (third implementation; bisection in depth).
- `sources/hec22_4th_ch9.txt` is the text of HEC-22 4th edition Section 6.1.4 (Manning's equation) and Sections
  9.1.3 to 9.1.6.7 and 9.4 with Example 9.2, extracted from the FHWA PDF (FHWA-HIF-24-006, February 2024).

## Evidence (outputs saved in `evidence/`)
- `check_agreement.py` -> `evidence/agreement.txt`: solution, engine and generator agree on all 1,060 rows, and no
  threshold comparison is closer than 0.001 ft.
- `local_check.py ..` -> `evidence/local_check.txt`: oracle passes every test, empty output fails.
- `calibrate.py` -> `evidence/calibration.txt`: 29 shortcut solutions and how many rows each gets wrong.
- `generate.py` -> `evidence/generate_output.txt`: counts of cases, conditions, surcharges and planted values.

## Settled readings (stated in instruction.md)
Pipe flow is the sum of inlet flows upstream; the receiving water elevation replaces EGLa at the outfall with an
exit loss of one velocity head (equation 9.5, still water); full flow by equations 9.2 and 9.4 as printed, partly
full flow by Manning's equation 6.5 on the circular section (smaller normal depth), critical depth at minimum
specific energy, g = 32.2; first applicable case or condition in table order; face-depth velocity for the case B
and C exit loss (Example 9.2); equation 9.4 friction only for case A, pipe slope otherwise, with the matching
velocity head for the HGL and equation 9.15; condition D resets to normal depth with no outlet control at the
structure, no benching loss without an inflow pipe, and surface inflow plunging from the rim (all Example 9.2); no
intermediate rounding; surcharge when EGLa is above the rim.

## Notes on HEC-22's printed numbers
Example 9.2 rounds intermediate values to two decimals, so the engine's checks against it use tolerances that
cover that rounding (structure 43: printed EGLa 333.68 from Eai - Ei rounded to 0.01, unrounded 333.71). Its
critical depth of 0.80 ft for 6.75 cfs in a 2-ft pipe is not consistent with the critical flow condition (0.92
ft), and its pipe 42-43 normal depth uses a Q/Qf ratio from a slope other than the one printed, so neither is
used as a check.
