# tg51-output-audit

Repair and port of a physics network's legacy calibration review program, tg51calc (Python 2, numpy, scipy, written
for the 1999 protocol), so that it runs on Python 3 with current numpy and scipy and reviews annual linac output
calibrations under the AAPM TG-51 protocol for clinical reference dosimetry
of high-energy photon and electron beams (Almond et al., Med Phys 1999;26(9):1847-1870) and its addendum for photon
beams (McEwen et al., Med Phys 2014;41(4):041501). Twelve clinics' worksheets cover 138 beams, 71 photon and 67
electron; for every beam the agent reports the absorbed dose to water per MU at the reference point and at dmax.

## Difficulty

Every clinic calibrates its beams this way every year, and a network or audit service checks them independently,
often with an in-house program that predates the 2014 addendum. Here that program (environment/tg51calc) no longer
runs: it uses Python 2 syntax, numpy and scipy calls removed since (np.float, scipy.interp), a barometer table without
inHg, and the 1999 protocol only. Porting it mechanically gets 128 of the 138 beams wrong. The work is bringing the
whole chain up to the documents with nothing in the data to check against. Each reading is corrected for temperature and pressure (482 readings: 23 in degrees Fahrenheit, pressures in
kPa, hPa, mmHg and inHg; 90 beams are wrong with the pressure unit left unconverted), for the electrometer range used
(52 wrong with one range for every reading), for polarity from signed readings over the calibration polarity (14 wrong over the
positive reading) and for recombination by the two-voltage formula for pulsed beams (119 wrong with the
continuous-beam formula). Photon beam quality comes from raw scans shifted upstream by 0.6 cavity radius (55 wrong
taken as already shifted), with the lead-foil equations for 41 scans (34 with the foil at 50 cm, 7 at 30 cm), the interim formula for
17 flattened beams of 10 MV or more scanned only in the open beam, and the foil for every flattening-filter-free beam
(20 of them). kQ comes from the addendum's Table I (Eq. 1, or linear to 1.000 at 58 below 63) for the chambers it
lists or replaces (Wellhofer IC-10 by IBA CC13, used for 10 beams) and from TG-51 Table I for older chambers (PTW
N30004 and NE2577, 20 beams). The radial-profile correction averages the profile over the chamber's active length (3
wrong without it). Dose at dmax uses the clinical depth dose of the open scan or the TMR for the 16 SAD
set-ups (56 wrong with %dd(10)x and the depth dose for every set-up). Electron beams need R50 from the shifted 50 percent
ionization depth, dref, k'R50 by chamber type (27 wrong with Eq. 19 for plane-parallel chambers), the gradient correction, kecal, and
for 12 beams the product from a cross-calibration in the clinic's highest-energy beam with Pelec = 1 (5 wrong with the
electrometer factor kept). Counts are in authoring/evidence/agreement.txt and calibration.txt; each of 10 shortcuts
tried (the legacy behaviours one at a time, and the mechanical port) gets beams wrong.

## Solution

The reference solution (solution/tg51calc, installed over /app/tg51calc by solution/solve.sh) is the program ported to
Python 3 with numpy and repaired. It applies TG-51 Eqs. (8)-(12) with Pleak = 1 and the addendum's Prp, finds
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
