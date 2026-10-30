# prostate-seed-dosimetry

Post-implant dosimetry of 60 permanent prostate seed implants under the AAPM TG-43U1 protocol (Rivard et al., Med
Phys 2004;31:633-674). For every listed urethra, rectum and prostate point the agent reports the total dose to
complete decay from all seeds found on the post-implant CT.

## Difficulty

Medical physicists check every permanent seed implant this way, and TG-43U1 is the dose-calculation protocol every
treatment planning system implements. The protocol itself, not the instruction, settles the details that decide
the numbers: the 2D formalism with the line-source geometry function and the line-source radial dose function g_L
(not g_P, which the dataset also carries); nearest-neighbour values of g and F outside the tabulated distances
(Appendix C, Eq. C1), where most seed models tabulate F only from 0.5 or 1 cm out to 5 or 7 cm; F equal to 1 on the
transverse plane by definition (Eq. 8), although every table stops at 80 or 85 degrees and the Theragenics model 200
has F above 1.04 at 85 degrees; mirror symmetry about the transverse plane (Sec. III A), because the tables cover 0
to 90 degrees only; the active length of each model, not the capsule; and apparent activity converted back to
air-kerma strength with the same exposure-rate constant the vendor used (Appendix E), which for 11 of the 19
apparent-activity certificates is not the LIBD value of 1.45 or 1.476. The records carry the details real implant
data has: certificates in air-kerma strength per seed, for the whole batch, or in apparent activity; calibration
times from vendors in four time zones, before or after the implant (17 batches are calibrated after the implant
date); implant times in New York local time near the 2026 daylight-saving changes; a second batch for 22 patients;
and 29 duplicate detections in 16 patients. Seeds lie at real orientations, mostly along the needle direction and
some turned well away from it. The data holds 60 patients, 7 or 8 for each of the eight consensus seed models (46
iodine-125, 14 palladium-103), 2,934 seeds and 1,080 points (480 urethra, 240 rectum, 360 prostate). Each point is
tagged with the rule families whose misreading moves its dose by more than 0.15 percent: for example 51 points
depend on the nearest-neighbour rule for F, 82 on F = 1 at 90 degrees, 164 on the vendor's exposure-rate constant,
483 on the interpolation of g_L and 144 on the daylight-saving change (counts in authoring/evidence/agreement.txt).
Each shortcut tried (authoring/evidence/calibration.txt, 21 in all) gets some points right and others wrong.

## Solution

The reference solution (solution/solve.py) converts each certificate to the air-kerma strength of one seed
(dividing a batch total by its seed count, or multiplying apparent activity by the vendor's exposure-rate constant
and 0.876 cGy per R), decays it from the calibration time, with its UTC offset, to the implant time converted from
New York local time with the US daylight-saving rules, using the Table XIII half-life. It drops duplicate
detections, takes each seed's centre and axis from its end markers, and for every point sums the TG-43U1 2D dose
rate (Eq. 1): the dose-rate constant, the line-source geometry function relative to the reference point, g_L(r)
with ln g linear in r, and F(r, theta) bilinear in r and theta with F = 1 at 90 degrees, angles beyond 90 degrees
mirrored, and nearest-neighbour values outside the tables. The total dose to complete decay is the initial dose rate
times the mean life, T1/2 / ln 2.

## Verification

The verifier recomputes every point with its own independently written engine (tests/engine.py: the opening angle
of the line source from the law of cosines, bisection lookups, interpolation of g_L as a weighted geometric mean)
from a private copy of the inputs that exists only in the verifier image, and never runs agent code. The generator
(authoring/generate.py) is a third implementation; generator and engine agree within a relative 5.1e-14, and the
solution's printed values equal the engine's rounded to three decimals. The engine is checked against the report's
own Table XV (dose rates of all eight seed models at 0.5 to 7 cm with the 1D formalism of Eq. 11, which confirms the
transcribed g_L, phi_an, active lengths and dose-rate constants) and against hand-worked single-seed 2D cases on and
off the transverse plane, beyond 90 degrees, below the first and beyond the last tabulated F distance. Tests check
the input consistency, the value format, one row per point in order, one test per rule family (tests/case_tags.json)
and finally every point, within 0.1 percent. Doses follow deterministically from the tabulated data, so correct
implementations agree to about 1e-12; the tolerance absorbs only the choice of 0.876 or 0.8764 cGy per R (at most
0.05 percent on apparent-activity seeds). Reward is 1 only if every test passes.
