# Authoring tools for sediment-basin-routing

These files are not copied into the agent or verifier images. Run them from this folder.

## Provenance
- `generate.py` (seed 61717) builds the 12 sites (9 random, 3 planted), writes both data copies
  (`../environment/data`, `../tests/data`), and `../tests/golden.json`.
  Rainfall is a 6-minute tipping-bucket record of Puerto Rico wet-season storms, with heavier storms from August
  and storm gaps placed just under and over six hours. Curve numbers are TR-55 table 2-2a values by soil group
  (open space good / newly graded / open space fair for the undisturbed, disturbed and stabilized states);
  sheet-flow surfaces are TR-55 table 3-1 descriptions (bare soil when disturbed). Cells are trapezoids or
  surveyed contours, sized around 3,600 cubic feet per acre drained (CGP Part 2.2.12), with HEC-22 outlet
  coefficients (orifice 0.6, sharp-crested weirs 0.37, broad-crested spillways 0.29 to 0.33). Forebay dividers
  sit near the main cell's riser crest so that large storms submerge them.
  Every spillway crest that a peak would come within 0.002 ft of is raised by 0.01 ft and the season re-run, so
  careful implementations cannot disagree on a yes/no. Embankment tops are set above every peak, and surveyed
  contours always extend above the highest water.
- `sim.py` is the generator's own model (third implementation; nested bisection for coupled cells).
- Planted sites (peak inflows worked by hand in the docstrings of `generate.py`):
  - minimum time of concentration: a graded 16-acre area whose flow path gives 0.044 h, raised to the TR-55
    minimum of 0.1 h; storms of 0.50 in and 0.30 + 0.30 in (14.952 and 19.430 cfs);
  - area states: an area graded on the day of a storm (its time of concentration and curve number both change)
    next to a stabilized area with its own flow path (0.302 and 43.279 cfs);
  - a forebay with surveyed contours draining through a divider into its main cell, which drains to a second
    basin, with storms 59, 60 and 61 dry intervals apart.
- `sources/` holds the text of the governing references extracted from the PDFs: NEH Part 630 chapters 10, 16
  and 17, HEC-22 4th edition chapter 10, and TR-55 table 2-2a (TR-55 chapter 3 and appendix F were read from the
  same TR-55 PDF).

## Evidence (outputs saved in `evidence/`)
- `check_agreement.py` -> `evidence/agreement.txt`: solution, engine and generator agree on all 2,201 rows.
- `local_check.py ..` -> `evidence/local_check.txt`: oracle passes every test, empty output fails.
- `calibrate.py` -> `evidence/calibration.txt`: 28 shortcut solutions and how many rows each gets wrong.
- `generate.py` -> `evidence/generate_output.txt`: per-site counts.

## Settled conventions (stated in instruction.md)
Gauge interval as unit duration and time step; six dry hours separate storms; accumulated storm rain at the
average antecedent condition; area state at the storm's start, from the start of its effective date, for both the
curve number and the sheet-flow surface; TR-55 chapter 3 with its minimum; each area its own hydrologic unit;
table 16-1 discharge ratios by linear interpolation; response begins at the start of each increment; conic
contour storage with linear area between contours; divider flow from the higher pool to the lower with the lower
as tailwater; every flow averaged over each step, solved on the continuous relations from dry cells; free outfall
for main cells; nothing through the dewatering orifice below its centroid; values at the 6-minute points from a
storm's start to the next storm's start; first time of the peak stage; spill volume as the sum of spillway flow
times 360 seconds.
