# Authoring tools for prostate-seed-dosimetry

These files are not copied into the agent or verifier images. Run them from this folder. None of them writes
`__pycache__`.

## Provenance
- `sources/tg43u1_excerpt.txt` is the text (pdftotext -layout) of the report pages used: the formalism (Sec. III,
  Eqs. 1 to 11), the consensus methods (Sec. IV, linear-linear interpolation for F and log-linear for g), Tables I
  to XI, Table XIII, Table XV, Appendix C (dose rates at small and large distances, Eqs. C1 to C3) and Appendix E
  (apparent activity). Rivard et al., Med Phys 2004;31:633-674, doi:10.1118/1.1646040, open access.
- `tables.py` transcribes Tables I, II, III, IV to XI and XIII from that text into `source_data.json` (both data
  copies) and recomputes Table XV with Eq. (11): seven models agree within 0.4 percent (0.6 percent for model 200 at
  7 cm), the printed precision of the table; the NASI MED3633 column is a constant 0.6 to 0.8 percent above the
  value from its Table I dose-rate constant of 0.688 at every distance, which shows its g_L and phi_an are
  transcribed correctly and Table XV used a slightly different dose-rate constant for that model. The data uses
  Table I. Output in `evidence/tables_check.txt`.
- `formalism_text.py` writes `tg43u1_formalism.txt` (both data copies) from the excerpt: Section III (printed pages
  637 to 640) and Appendices C, D and E (printed pages 669 to 672), with the PDF's private glyphs mapped back to
  ASCII. The agent therefore has the equations it needs (Eqs. 1, 4, 8, 11, C1, C3 and the Appendix E conversion)
  without network access.
- `generate.py` (seed 20090137) builds the 20 patients and writes both data copies (`../environment/data`,
  `../tests/data`), `evidence/answers.json` (the generator's own metrics and the per-value family tags) and
  `../tests/case_tags.json`. Models in a fixed order (five Theragenics 200, four NASI MED3633, two each of 6702,
  6711, 2301, MED3631-A/M and I25.S06, one IS-12501); prescriptions 145 Gy (iodine-125) and 125 Gy (palladium-103).
  Times: implants 07:00 to 15:59 New York time within 12 days of March 8, November 1 or June 15, 2026; CT 7 to 25
  days after a palladium-103 implant and 14 to 45 days after an iodine-125 implant. Edema: pre-implant volume 25 to
  55 cc, swelling 10 to 100 percent at the end of the procedure, edema half-life 4 to 25 days (the range Waterman et
  al., Int J Radiat Oncol Biol Phys 1998, reported), redrawn until the CT volume is at least 5 percent above the
  pre-implant volume and the post-implant volume at least 8 percent above the CT volume. Contours: an ellipsoidal
  prostate (axis ratios 0.70 to 0.85 and 0.9 to 1.2) scaled so the polygon volume equals the CT volume, sliced at
  z = 1.25 + 2.5 k mm; a 3.0 to 3.5 mm urethra on a gently curved axis; a rectum 1.0 to 2.5 mm below the prostate
  with radii 9 to 13 mm and lateral ratio 1.4 to 1.7, extending two slices beyond the prostate. Polygon vertices are
  written to 0.01 mm with a jitter of up to 0.08 mm and redrawn until no voxel centre lies within 0.02 mm of an
  edge, so voxel membership is never a rounding question. Seeds: 18 to 26 needles of a 0.5 cm template, peripheral
  loading (outer ring, 15 percent of the central positions), at least 0.65 cm from the urethra; seeds 1 cm apart
  along each needle with a Gaussian jitter of 0.12 cm clamped at 0.25 cm; axes tilted 0 to 15 degrees (70 percent),
  15 to 40 degrees (20 percent) or 40 to 90 degrees; markers 3.5 to 4.5 mm apart, written to 0.1 mm, in either order.
  Eleven patients have one-marker seeds: every seed for the two models whose anisotropy factor starts at 1 cm (2301
  and IS-12501, where Eq. C3 matters), one to four seeds otherwise. No voxel centre lies within 0.02 cm of a seed
  centre or within 0.005 cm of a two-marker seed's axis inside the capsule. Strengths 0.35 to 0.65 U (iodine-125) or
  1.4 to 2.3 U (palladium-103) per seed at implant before planting. Certificates: 25 percent apparent activity with
  an exposure-rate constant of 1.45 or 1.464 (iodine-125) or 1.476 or 1.48 (palladium-103), 20 percent batch
  totals, the rest per seed; calibrated at noon vendor time 6 days after to 21 days before the implant, in the
  vendor's zone (Central for Amersham and Imagyn, Eastern for Best, Bebig/Theragenics and Theragenics, Pacific for
  NASI) with daylight saving. 40 percent of patients have a second batch of 4 to 10 seeds; 35 percent have 1 to 3
  duplicate detections (markers within 0.4 mm of the seed they repeat). Planting: a global factor on every seed
  strength puts the planted criterion in its band, D90 and urethral D10 0.3 to 0.6 percent from the threshold, V100
  0.8 to 1.5 percentage points, rectal V100 0.08 to 0.15 cc, on the side the schedule names; one patient is planted
  exactly on the rectal V100 line, 64 rectum voxels at or above the prescription (1.000 cc, which meets the
  inclusive criterion), with the threshold midway between the 64th and 65th voxel doses and those two at least 0.5
  percent apart, so an implementation within the tolerance sees the same 64 voxels; unplanted patients get D90
  between 0.96 and 1.10 of the prescription. Every patient is redrawn until the implant is reportable (D90 0.90
  to 1.30 of the prescription, V100 85 to 99.5 percent, urethral D10 at most 1.9 times the prescription, rectal V100
  at most 3 cc), every criterion is at least the margin from its line (0.3 percent, 0.8 points, 0.08 cc, except the planted
  on-the-line value), a 0.1 percent change of every dose moves V100 and V150 by at most 0.15 points and rectal V100
  by at most 0.015 cc without changing any criterion, and for the on-the-line patient a 0.25 percent change leaves
  the 64 voxels and every criterion (101 patient draws were discarded). Answers are computed from the written values.
- `sim.py` is the generator's own model (third implementation): the time integral in the volume variable by
  tanh-sinh quadrature with the endpoint distance carried exactly, pairs beyond 0.6 cm read from a per-patient
  table of the smooth quotient K r^2 G_L(r, 90) / G_L(r, theta) on a uniform r grid and a 0.5-degree theta grid,
  ray-casting membership. It also implements every misreading of `SHORTCUTS` (20 families) for the family tags.
- Families: a value carries a family tag when the generator's result with that one rule misread differs from the
  correct value by more than 1.5 times the tolerance (0.15 percent, 0.45 points, 0.045 cc) or changes the criterion.

## Evidence (outputs saved in `evidence/`)
- `check_agreement.py` -> `evidence/agreement.txt`: solution, engine and generator agree on all 220 values; it
  prints every count quoted in the READMEs.
- `local_check.py ..` -> `evidence/local_check.txt`: oracle passes every test, empty output fails.
- `calibrate.py` -> `evidence/calibration.txt`: 21 shortcut solutions and how many values each gets wrong; every
  one fails at least one test (the strict-inequality shortcut is caught only by the on-the-line patient).
- `tables.py` -> `evidence/tables_check.txt`: the Table XV check.
- `generate.py` -> `evidence/generate_output.txt`: per-patient summary and the tag counts.
- `evidence/pytest_run.txt`: the real pytest run on a scratch copy of `tests/` with the oracle output (all pass,
  with the run time) and without it (fails).

## Settled readings (stated in instruction.md)
Centre and axis from the markers; 2D formalism with G_L for two-marker seeds; 1D formalism (Eq. 11) with G_L for
one-marker seeds and Eq. C3 below the first phi_an distance; ln g_L linear in r, F bilinear, phi_an linear; nearest
neighbour beyond the tables (Eq. C1); F interpolated to 1 at 90 degrees above the last tabulated angle; the
exponential edema model with lambda_e fitted to the CT volume; uniform scaling of every seed-to-tissue distance by
(V(t) / V_CT)^(1/3) with fixed orientations; integral from the implant to complete decay with strengths decayed from
the certificate to the implant; 2.5 mm voxels at (i + 1/2) 2.5 mm in x and y and the slice positions in z, even-odd
membership, urethra not subtracted; D_p at ceiling rank, V100 and V150 in percent, rectal V100 in cc, D2cc at rank
ceil(2 cc / voxel volume); inclusive criteria (at or above, at or below, which decides the on-the-line patient); no intermediate rounding; the CSV contract and tolerances. Settled by
the report and the data: g_L with G_L (Eqs. 1, 6); F(r, 90) = 1 (Eq. 8); mirror symmetry (Sec. III A); active
length from the dataset; apparent activity times the vendor's own exposure-rate constant (Appendix E); half-lives
(Table XIII). Physics: 0.876 cGy air kerma per roentgen (the factor behind Appendix E's 1.270 = 1.45 x 0.876 and
1.293 = 1.476 x 0.876); the time integral of exp(-lambda t) is the mean life T1/2 / ln 2.

## Notes on the report's printed numbers
- Table XV (1D dose rates) is reproduced within its printed precision by Eq. 11 from the transcribed tables for
  seven models; the golden tolerance is 0.65 percent (0.85 percent for the MED3633 column, whose constant offset is
  described above).
- Table XV lists values at 0.5 cm for the Best 2301 and IS-12501 models, whose anisotropy factor is tabulated from
  1 cm. The report does not say how those two entries were extrapolated, and they do not follow Eq. C3 (which the
  instruction settles for the task), so they are not used as golden checks; the 1.0 to 7 cm entries of both models
  are. Eq. C3 itself is checked by four hand-worked values (2301 at 0.5 cm, IS-12501 at 0.7 cm, 6711 at 0.3 cm,
  200 at 0.2 cm).
- The closed-form checks of the edema integral are the inverse-square point source with lambda / lambda_e = 1 and
  2, where the integral is elementary, and the limit of a vanishing edema, where the integral is the dose rate times
  the mean life.
- The index set and the four criteria are the service's practice as stated in instruction.md. The TG-137
  reference (Nath et al., Med Phys 2009;36:5310-5322) is cited for the report format only; its PDF is not in
  `sources/`, and the sentence attributing the report format to it should be checked against the published text
  before submission.
