# Kyoto checks (repos such as science-london-medicine-...)

Some Insight repos run three extra blocking checks inside the Artificiality (C1) stage, plus a stricter category
alignment. The rule text is in the private orchestration repo; what follows is everything the logs revealed. Read the
artificiality log for `Kyoto` sections and for `Category and field alignment`.

## Category and field alignment (blocking)
- It compares task.toml `field` with the field derived from the repo name: `science-london-medicine-...` gives
  "london medicine". `field = "Medicine"` was blocked ("Mismatch: repository field london medicine vs metadata field
  Medicine"). Set `field = "London Medicine"`. For other repos derive the field the same way and match it exactly
  (case does not matter).

## Kyoto: allowed tool use (blocking)
- A listed tool must be genuinely used on the path that writes the graded output, and installed in the agent image.
  The reviewer named: torch, jax, numpy, scipy, statsmodels, sympy ("or any other listed tool"). Verifier-only use
  and pytest do not count.
- Failure code seen: `NOT_USED` ("solution/solve.py imports only csv, json, math ...").
- Fix pattern: pin the tool in environment/Dockerfile (`RUN pip install --no-cache-dir numpy==2.2.6 scipy==1.15.3`,
  ==-pinned for the static check), and make the reference solution use it for real work (arrays, np.interp, fits).
  The verifier engine may stay standard-library only.

## Kyoto: allowed task type (blocking)
Allowed types and what the reviewer said each needs:
- **REPRODUCE**: ship the actual input data of a published work and recover the exact numbers it reports; the
  verifier's reference must trace to a figure or table of that publication, not to the author's recomputation.
- **EXTRACT**: ship real documents (PDFs) and extract structured values from them (not pre-structured CSV).
- **TRAIN_EVAL**: a labelled dataset and a model trained and evaluated on it.
- **REPAIR_PORT**: legacy code shipped in environment/ that must be repaired or ported.
Failure code seen: `ARTIFICIAL` ("implements the TG-51 protocol on synthetic clinic data; the results are
author-computed"). Applying a standard to synthetic records is not an allowed type.

## Kyoto: runs offline (blocking)
Nothing may be fetched after the image build: all inputs shipped, installs only at build time, no downloads in
solve.sh or test.sh, no ENTRYPOINT that installs. Citations as background are fine.

## The REPAIR_PORT design that keeps a science task (tg51-output-audit v2)
1. Write a realistic legacy program in `environment/tg51calc/` (package with `__main__.py`, README.txt with a version
   history) in the style of an in-house tool from the standard's older edition: Python 2 syntax (print statements,
   `iteritems`, `open(path, 'rb')` for csv), APIs removed since (`np.float`, `scipy.interp`, `scipy.integrate.simps`),
   and realistic gaps and faults: the older edition only, in-house "equivalents" for newer equipment, a unit table
   missing one unit (inHg crashes), formulas for the wrong case (continuous-beam Pion, one kR50 formula for every
   chamber), one electrometer range for every reading, a polarity denominator that assumes positive calibration, the
   scanner "already shifted" assumption, dmax from the wrong quantity, Pelec kept for cross-calibrated chambers.
   Faults must each be plausible for a real 2004 program and each must move answers (check with calibration).
2. The instruction states background facts only: the program, its age and protocol, that it does not run with the
   installed Python/numpy/scipy, that the network now reviews against the new edition, and the outcome needed. Never
   list the faults and never require "use the program" (not enforceable; AVA would flag it).
3. The reference solution is the repaired port in `solution/tg51calc/`; `solution/solve.sh` copies it over
   `/app/tg51calc` and runs `python3 -m tg51calc /app/data /app/output/<file>.csv`. `solution/solve.py` is a local
   runner for the authoring checks (inserts its own folder on sys.path, clears cached `tg51calc` modules, calls main).
4. Calibration (authoring/calibrate.py): run the repaired package with each legacy behaviour put back (one file
   edit each), and the legacy package ported mechanically (only syntax and removed-API fixes). Every one must fail;
   report wrong-row counts. Run it with a Python that has the pinned numpy/scipy (create a venv in the scratchpad:
   `python3 -m venv $V && $V/bin/pip install numpy==2.2.6 scipy==1.15.3`), and silence the legacy prints.
5. The authoring README says honestly that the legacy program was written for the task in the manner of an in-house
   tool, and where each fault comes from.
6. task.toml tags include `legacy-code-port`, `numpy`, `scipy`; description says "Repair and port of ...".
