# prostate-seed-dosimetry

Edema-corrected post-implant evaluation of 20 permanent prostate seed implants (iodine-125 and palladium-103,
eight TG-43U1 consensus seed models). From the seed markers found on the post-implant CT, the vendor certificates,
the slice contours of prostate, urethra and rectum, and the prostate volumes before the implant, at the end of the
procedure and on the CT, the agent integrates the TG-43U1 dose rate over time while the swollen prostate shrinks
back, and reports prostate D90, V100 and V150, urethral D10 and D30, rectal V100 and D2cc and four acceptance
criteria per patient.

## Difficulty

A medical physicist does this evaluation for every permanent seed implant: TG-43U1 (Rivard et al., Med Phys
2004;31:633-674) is the dose-calculation protocol every planning system implements, and the indices are the ones
the service's TG-137 report asks for. The textbook method, dose rate at the CT geometry times the mean life, is not
the service's method and gives different answers here: the CT is taken 8.0 to 43.0 days after the implant, when an
edema of 24 to 100 percent of the pre-implant volume has partly resolved (half-lives 5.8 to 23.8 days), so every
seed-to-tissue distance was 1.040 to 1.199 times its CT value at the implant and ends 0.864 to 0.983 times it, and
the static D90 is 0.871 to 1.055 of the edema-corrected one. Getting the time integral right means integrating a
tabulated, piecewise-interpolated dose rate along a distance that changes with time, for 9204394 seed-voxel pairs
within a few hours on one CPU, with the integrand changing form every time the scaled distance crosses a table node.
The protocol itself settles the rest: the 2D formalism with the line-source geometry function for the 1320 seeds
whose two markers were resolved, the 1D formalism of Eq. 11 for the 282 one-marker seeds (11 patients, two seed
models have every seed in this state) with the Appendix C short-distance model Eq. C3 below the first tabulated
anisotropy-factor distance, nearest-neighbour values outside the tables (Eq. C1), F equal to 1 at 90 degrees, mirror
symmetry, log-linear g_L, and apparent activity converted with the vendor's own exposure-rate constant (Appendix E;
4 of the 7 apparent-activity certificates use 1.464 rather than the 1.45 the appendix quotes for iodine-125). The records carry what real
implant records carry: 25 certificates in three units (14 per seed, 4 batch totals, 7 in apparent activity), 5
patients with a second batch, calibration times from vendors in five UTC offsets, 3 certificates dated after the
implant, implant and CT times in New York local time around the 2026 daylight-saving changes, and 11 duplicate
detections in 5 patients. Everything is near the lines that matter: 15 patients are planted so that one criterion
sits 0.3 to 0.6 percent (D90, urethral D10), 0.8 to 1.5 percentage points (V100) or 0.08 to 0.15 cc (rectal V100)
from its threshold, on either side; one patient is planted exactly on the rectal V100 line, 64 rectum voxels at or
above the prescription, which is 1.000 cc and meets the inclusive criterion the instruction states, with the 64th
voxel 0.255 percent above the prescription and the 65th 0.254 percent below it, so a correct implementation within
the tolerance sees the same count and a strict reading of the criterion fails; the remaining 4 are unplanted. The
criteria split 16 yes and 4 no (D90), 3 and 17 (V100), 9 and 11 (urethral D10) and 16 and 4 (rectal V100). Every value is tagged with the misreadings that
would move it past the tolerance: for example 129 values depend on integrating over the edema instead of using the
CT geometry, 148 on scaling distances by the cube root of the volume ratio rather than the ratio, 167 on starting
the integral at the implant rather than the CT, 34 on using the 1D formalism for one-marker seeds, 4 on Eq. C3, 93
on the calibration UTC offset, 22 on the daylight-saving change, 29 on dropping duplicates, 25 on ceiling ranks, 52
on keeping the urethra inside the prostate and 1 on the inclusive criterion (all counts in
authoring/evidence/agreement.txt). Each of the 21
shortcut solutions in authoring/evidence/calibration.txt gets between 1 and 168 of the 220 values wrong and fails
at least one test. The data is synthetic, built by a seeded generator within the ranges of published post-implant
series, and follows the consensus datasets of the report exactly.

## Solution

The reference solution (solution/solve.py) converts each certificate to the air-kerma strength of one seed
(dividing a batch total by its seed count, or multiplying apparent activity by the vendor's exposure-rate constant
and 0.876 cGy per R), decays it from the calibration time, with its UTC offset, to the implant time converted from
New York local time with the US daylight-saving rules, and drops the duplicate detections. It fits the edema model
to the three volumes, which gives the time dependence of the scale factor s(t), and rewrites the time integral of
exp(-lambda t) times the dose rate at distance s(t) r in the variable y = V(t) - V_pre, whose weight is a power of
y: it integrates the piece up to the first table-node crossing by Gauss-Jacobi quadrature (nodes and weights from
the Golub-Welsch eigenvalue method) and the rest by Gauss-Legendre on geometrically growing pieces split at every
crossing. The dose rate is the TG-43U1 2D formalism (Eq. 1) with the line-source geometry function, log-linear
g_L, bilinear F with F = 1 at 90 degrees, mirrored angles and nearest-neighbour values outside the tables, or the
1D formalism (Eq. 11) with linear phi_an and Eq. C3 below its first distance for one-marker seeds. It sums the
total over all seeds at every voxel centre inside each structure's slice polygon (even-odd rule), sorts each
structure's doses, and reads the indices at ceiling ranks.

## Verification

The verifier recomputes every value with its own engine (tests/engine.py) from a private copy of the inputs that
exists only in the verifier image, and never runs agent code. The engine shares no code or method with the
solution: the opening angle of the line source from the law of cosines; the time integral taken in t by
Gauss-Legendre on pieces of at most two edema half-lives between the node-crossing times, with the tail in
w = exp(-lambda_e t) by Gauss-Jacobi whose abscissae come from Newton iteration on the Jacobi recurrence; the dose
per unit strength tabulated per patient on a fine distance and 1-degree angle grid as a smooth quotient and read by
interpolation, with pairs closer than 0.6 cm integrated directly; voxels classified by the winding number. The
generator's model (authoring/sim.py) is a third implementation with tanh-sinh quadrature; generator and engine
agree within a relative 1.8e-06 on doses and exactly on every percentage, volume and criterion, and the solution
agrees with the engine within 7.6e-06 on doses, 0.005 percentage points and 0.0005 cc. The generator guarantees
that every criterion value except the planted on-the-line one sits at least 0.3 percent (D90 and urethral D10), 0.8
percentage points (V100) or 0.08 cc (rectal V100) from its threshold, more than two and a half times the tolerance,
that scaling every dose by 0.1 percent changes no criterion, and that scaling the on-the-line patient's doses by 0.25
percent leaves its 64 voxels. The engine is checked against 87 golden values: 70 dose rates of TG-43U1 Table XV (all eight
models, 0.5 to 7 cm, within the table's printed precision), 6 hand-worked 2D cases (the reference point, the
transverse plane, interpolated and mirrored angles, nearest-neighbour F with F = 1 at 90 degrees, log-linear g_L
below the first F distance), 4 hand-worked Eq. C3 values, 4 closed-form time integrals of an inverse-square point
source under the edema model with lambda / lambda_e equal to 1 and 2, and 3 cases where an edema of one part per
million reproduces the static dose rate times the mean life. The 25 tests check the golden values, the consistency
of the private inputs, the value formats, one row per patient in order, each of the 20 rule families by name
(tests/case_tags.json) and finally every value: doses within 0.1 percent, percentages within 0.30 points, rectal
V100 within 0.030 cc, criteria exact. The engine runs in 118 s and the full test run in 130.53 s with four other jobs sharing the machine, inside the
300 s verifier limit. Reward is 1 only if every test passes.
