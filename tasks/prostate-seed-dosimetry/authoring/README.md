# Authoring tools for prostate-seed-dosimetry

These files are not copied into the agent or verifier images. Run them from this folder. None of them writes
`__pycache__`.

## Provenance
- `sources/tg43u1_excerpt.txt` is the text (pdftotext -layout) of the report pages used: the formalism (Sec. III,
  Eqs. 1 to 11), the consensus methods (Sec. IV, linear-linear interpolation for F and log-linear for g), Tables I
  to XI, Table XIII, Table XV, Appendix C (dose rates at small and large distances) and Appendix E (apparent
  activity). Rivard et al., Med Phys 2004;31:633-674, doi:10.1118/1.1646040, open access.
- `tables.py` transcribes Tables I, II, III, IV to XI and XIII from that text into `source_data.json` (both data
  copies) and recomputes Table XV with Eq. (11): seven models agree within 0.4 percent (0.6 percent for model 200 at
  7 cm), the printed precision of the table; the NASI MED3633 column is a constant 0.6 to 0.8 percent above the
  value from its Table I dose-rate constant of 0.688 at every distance, which shows its g_L and phi_an are
  transcribed correctly and Table XV used a slightly different dose-rate constant for that model. The data uses
  Table I. Output in `evidence/tables_check.txt`.
- `generate.py` (seed 20040301) builds the 60 patients and writes both data copies, `evidence/answers.json` and
  `../tests/case_tags.json`. Prostate semi-axes 1.9 to 2.5, 1.4 to 1.9 and 1.8 to 2.4 cm; 16 to 24 needles on a 0.5
  cm template at least 0.5 cm from the urethra, seeds 1 cm apart along each needle with 1.2 mm jitter; seed axes
  tilted 0 to 15 degrees (70 percent), 15 to 40 degrees (20 percent) or 40 to 90 degrees; end markers 3.5 to 4.5 mm
  apart, written to 0.1 mm, either order. Air-kerma strength 0.35 to 0.65 U (iodine-125) or 1.4 to 2.3 U
  (palladium-103) per seed at implant. Certificates: 25 percent apparent activity with a vendor conversion coefficient
  of 1.270 or 1.282 U/mCi (iodine-125) or 1.293 or 1.297 (palladium-103), 20 percent batch totals, the rest per seed;
  calibrated at noon vendor time 6 days after to 21 days before the implant, in the vendor's zone (Central for
  Amersham and Imagyn, Eastern for Best, Bebig/Theragenics and Theragenics, Pacific for NASI). Implants 07:00 to
  15:59 New York time, mostly within 12 days of the March 8 or November 1, 2026 change. 35 percent of patients have
  a second batch of 4 to 10 seeds; 30 percent have 1 to 3 duplicate detections (markers within 0.4 mm of the seed
  they repeat). Points: 8 urethra, 4 rectum, 3 on the prostate surface, 3 inside it and the two femoral heads 8.0
  to 10.8 cm lateral; every point is at least
  0.30 cm from every seed centre (more than L/2, where the report says the polar formalism breaks down) and 0.05
  cm off every seed axis (174 drawn patients were redrawn for this). Answers are computed from the written values.
- Families: a point carries a family tag when the generator's dose with that one rule misread differs by more
  than 0.15 percent from the correct dose.

## Evidence (outputs saved in `evidence/`)
- `check_agreement.py` -> `evidence/agreement.txt`: solution, engine and generator agree on all 1,200 points; it
  prints every count quoted in the READMEs.
- `local_check.py ..` -> `evidence/local_check.txt`: oracle passes every test, empty output fails.
- `calibrate.py` -> `evidence/calibration.txt`: 22 shortcut solutions and how many points each gets wrong.
- `tables.py` -> `evidence/tables_check.txt`: the Table XV check.
- `generate.py` -> `evidence/generate_output.txt`.

## Settled readings
Stated in instruction.md as facts: New York local implant times; certificate units and the vendor's conversion
coefficient; calibration times with UTC offsets; duplicate detections named in review; seeds fixed at their CT
positions from the implant on; the 2D formalism with the line-source geometry function; ln g_L linear in r and F
bilinear in r and theta (the report allows any appropriate interpolation for clinical use and used these for its
consensus data, Sec. IV); total dose to complete decay; nothing rounded before the final doses. Settled by the
report: the source centre at the marker centroid with the axis through the markers (Sec. III A); g_L with G_L (Eqs.
1, 6); F(r, 90 degrees) = 1 (Eq. 8); symmetry about the transverse plane (Sec. III A); nearest neighbour outside the
tabulated distances for both g and F in 2D (Appendix C, Eq. C1); active length L from the dataset; apparent activity
times the vendor's own coefficient (Appendix E); half-lives (Table XIII, also in the data). Physics: mean life
T1/2 / ln 2.
