# tg51-output-audit

Independent review of annual linac output calibrations under the AAPM TG-51 protocol for clinical reference dosimetry
of high-energy photon and electron beams (Almond et al., Med Phys 1999;26(9):1847-1870) and its addendum for photon
beams (McEwen et al., Med Phys 2014;41(4):041501). Twelve clinics' worksheets cover 138 beams, 71 photon and 67
electron; for every beam the agent reports the absorbed dose to water per MU at the reference point and at dmax.

## Difficulty

Every clinic calibrates its beams this way every year, and a network or audit service checks them independently.
The documents give the formalism; the work is carrying a long chain through raw worksheets with nothing to check
against. Each reading is corrected for temperature and pressure (482 readings: 23 in degrees Fahrenheit, pressures in
kPa, hPa, mmHg and inHg; 90 beams are wrong with the pressure unit left unconverted), for the electrometer range used
(40 wrong with the other range), for polarity from signed readings over the calibration polarity (63 wrong over the
other reading) and for recombination by the two-voltage formula for pulsed beams (129 wrong without it, 119 with the
continuous-beam formula). Photon beam quality comes from raw scans shifted upstream by 0.6 cavity radius (55 wrong
unshifted), with the lead-foil equations for 41 scans (34 with the foil at 50 cm, 7 at 30 cm), the interim formula for
17 flattened beams of 10 MV or more scanned only in the open beam, and the foil for every flattening-filter-free beam
(20 of them). kQ comes from the addendum's Table I (Eq. 1, or linear to 1.000 at 58 below 63) for the chambers it
lists or replaces (Wellhofer IC-10 by IBA CC13, used for 10 beams) and from TG-51 Table I for older chambers (PTW
N30004 and NE2577, 20 beams). The radial-profile correction averages the profile over the chamber's active length (21
wrong over the whole profile). Dose at dmax uses the clinical depth dose of the open scan (40 wrong with %dd(10)x) or
the TMR for the 16 SAD set-ups (16 wrong through the depth dose). Electron beams need R50 from the shifted 50 percent
ionization depth, dref, k'R50 by chamber type (54 wrong with the formulas swapped), the gradient correction, kecal, and
for 12 beams the product from a cross-calibration in the clinic's highest-energy beam with Pelec = 1 (5 wrong with the
electrometer factor kept). Counts are in authoring/evidence/agreement.txt and calibration.txt; each of 14 shortcuts
tried gets beams wrong.

## Solution

The reference solution (solution/solve.py) applies TG-51 Eqs. (8)-(12) with Pleak = 1 and the addendum's Prp, finds
%dd(10) and I50 on the shifted scans, applies Eqs. (13)-(17), takes kQ from addendum Eq. (1) (with the Sec. 3.E
replacements) or TG-51 Table I, and for electrons Eqs. (18)-(22) with TG-51 Tables II and III. Dose at dmax divides by
the open-scan %dd(10) or the TMR (photons) and by the clinical PDD at dref (electrons).

## Verification

The verifier recomputes every beam with its own engine (tests/engine.py) from a private copy of the inputs and never
runs agent code. A row is accepted when both values are within 0.3 percent of one value pair the documents allow: kQ by
Eq. (1) or by interpolating the addendum's tabulated values, Eq. (13)/(14) or Eq. (15) for a flattened beam of 10 MV or
more, and the profile averaged as a mean of samples or by the trapezoid rule. The largest spread among these for one
beam is 0.116 percent. The engine's formulas are checked against hand-worked values (tests/golden.json), and the tests
confirm that every case tag really moves its beam outside the tolerance. The solution agrees with the engine on all 138
beams (authoring/evidence).
