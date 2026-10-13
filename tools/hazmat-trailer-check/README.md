# hazmat-trailer-check dev tools (never upload these)

- `generate.py` (seed 177848) writes `tasks/hazmat-trailer-check/environment/data/` (trailers.json,
  carrier.json), the identical verifier copy in `tests/data/`, `tests/case_tags.json` and
  `tests/golden.json` (91 planted trailers with hand-worked placards and violations). Filler loads
  where DANGEROUS would cover a single leftover category are rejected (left open by the rule).
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, 29 misreadings each fail
  at least one test.

Rule text used (pasted by the author from law.cornell.edu): 49 CFR 172.500, 172.502, 172.504,
172.505, 177.848, and the bulk / non-bulk packaging definitions in 171.8 (added in v2 after Pass@2 was
solved 2/2: bulk packagings and uranium hexafluoride). Both table transcriptions (solve.py, engine.py) were checked for symmetry and
against each other.
