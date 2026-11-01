# tg71-monitor-unit-check

Independent monitor unit check under the report of AAPM Task Group 71, Monitor unit calculations for photon and
electron beams (Gibbons et al., Med Phys 2014;41(3):031501), for 91 beams of 33 treatment plans on a Varian Clinac
21EX: 80 beams of 6 MV photons and 11 of 9 MeV electrons. The commissioning data are the report's own example tables
(Tables II to IX). For every beam the agent reports the monitor units that deliver the planned dose to the beam's
calculation point.

## Difficulty

Every clinic must check each plan's monitor units independently before the first fraction, and TG-71 is the method.
The report gives the formalism; the work is applying all of it, beam by beam, where each factor takes its own field
size and distance. For a photon beam the in-air output ratio Sc takes the jaw field by Eq. (4), because the MLC is
tertiary and blocks hang on a tray (48 beams are wrong if it takes the shaped field); the phantom scatter factor, TPR
and wedge factor take the field incident on the patient projected to the depth of the point (24 beams wrong without
the projection); in Eq. (3) Sp takes the field at the normalization depth (80 wrong at the surface field), PDDN comes
from the SSD 100 cm table converted by the Mayneord factor of Eq. (14) and (15) (45 wrong without it) and the
inverse square runs to SSD plus d0 (77 wrong to the point). D0 is defined at SSD0 90 cm and 10 cm depth (80 wrong
with SSD0 100 cm). Off-axis ratios use the radial distance projected to 100 cm (15 points off axis), the block tray
factor applies to 10 beams, 9 beams carry physical wedges of 15 to 60 degrees, and 10 beams
behind lung use the RTAR (4) or power law (6) correction of Eqs. (6) to (8) from the layer record (6 wrong with the
power-law distances swapped). 57 photon beams are isocentric, 20 of them with the point away from the isocenter
depth, and 23 are fixed-SSD setups at 90 to 120 cm; 43 have asymmetric jaws. Electron beams use the square-root rule
of Eq. (13) for 11 rectangular inserts, the isodose line of the prescription, and at extended distance (8 beams at
105 to 115 cm) the effective SSD of Eq. (11) or the air gap factor of Eq. (12) and (22), as each plan states. Nothing
in the data lets a solver check its own answer. Each of 13 shortcuts tried (authoring/evidence/calibration.txt)
gets beams wrong.

## Solution

The reference solution (solution/solve.py) uses Eq. (1) for every photon beam: Sc from the jaws by Eq. (4), Sp, TPR
and the wedge factor at the shaped (or jaw) equivalent square times SPD/SAD, the off-axis ratio at the radial
distance times SAD/SPD, the tray factor for blocks, the inverse square ((SSD0 + d0)/SPD)^2, and the heterogeneity
factor from the radiological depth (Eq. (6), (7)) or the power law (Eq. (8)). Electron beams use Eq. (10) with
Eq. (13), and Eq. (11) with the geometric mean of SSDeff or Eq. (12) with Eq. (22). Tables are interpolated linearly.

## Verification

The verifier recomputes every beam with its own engine (tests/engine.py) from a private copy of the inputs and never
runs agent code. An MU is accepted within 0.3 percent of any MU the protocol allows for that beam: Eq. (1) or Eq. (3)
for photons, with or without the bracket of Eq. (14), the wedge-factor field at the depth or at the isocenter, and
SSDeff as the geometric mean of the sides or of the two corrections for electrons. The largest spread among these
for one beam is 0.289 percent. The engine reproduces the six worked examples of TG-71 Section 8 (266, 156, 135, 200,
252 and 250 MU; tests/golden.json). The solution agrees with the engine on all 91 beams (authoring/evidence).
