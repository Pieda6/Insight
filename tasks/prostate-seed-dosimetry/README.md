# prostate-seed-dosimetry

Post-implant dosimetry of 60 permanent prostate seed implants under the AAPM TG-43U1 protocol (Rivard et al., Med
Phys 2004;31:633-674). For every listed urethra, rectum and prostate point the agent reports the total dose to
complete decay from all seeds found on the post-implant CT.

## Difficulty

Medical physicists check every permanent seed implant this way, and TG-43U1 is the dose-calculation protocol every
treatment planning system implements. The instruction names only the formalism and the interpolation scheme (which
the report leaves open for clinical use); everything else that decides the numbers comes from the report: g_L with
the line-source geometry function in 2D (not g_P, which the dataset also carries); nearest-neighbour values of g and
F outside the tabulated distances (Appendix C, Eq. C1), which decides the femoral-head points 8 to 11 cm away, beyond
the last tabulated g distance (7 cm) of two models and the last F distance of six; F equal to 1 on the transverse
plane by definition (Eq. 8), although every table stops at 80 or 85 degrees; mirror symmetry about the transverse
plane (Sec. III A); the source centre at the marker centroid; and apparent activity converted with the vendor's own
coefficient (Appendix E), which for 7 of the 20 apparent-activity certificates is not 1.270 or 1.293. The records
carry real implant detail: certificates per seed, per batch or in apparent activity; vendors in four time zones,
calibrated before or after the implant; New York implant times near the 2026 clock changes; second batches; and
duplicate detections. The data holds 60 patients, 7 or 8 per consensus seed model, 2,939 seeds and 1,200 points;
counts and the points each rule decides are in authoring/evidence/agreement.txt. Each of 22 shortcuts tried
(authoring/evidence/calibration.txt) gets some points right and others wrong.

## Solution

The reference solution (solution/solve.py) converts each certificate to the air-kerma strength of one seed
(dividing a batch total by its seed count, or multiplying apparent activity by the vendor's conversion
coefficient), decays it from the calibration time, with its UTC offset, to the implant time converted from
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
(authoring/generate.py) is a third implementation; generator and engine agree within a relative 9.4e-14, and the
solution's printed values equal the engine's rounded to four decimals. The engine is checked against the report's
own Table XV (dose rates of all eight seed models at 0.5 to 7 cm with the 1D formalism of Eq. 11, which confirms the
transcribed g_L, phi_an, active lengths and dose-rate constants) and against hand-worked single-seed 2D cases on and
off the transverse plane, beyond 90 degrees, below the first and beyond the last tabulated F distance, and beyond the last tabulated g distance. Tests check
the input consistency, the value format, one row per point in order, one test per rule family (tests/case_tags.json)
and finally every point, within 0.1 percent or 0.0005 Gy, whichever is larger. Doses follow deterministically from the
tabulated data, so correct implementations agree to about 1e-12. Reward is 1 only if every test passes.
