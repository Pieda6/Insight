# hazmat-trailer-check dev tools (never upload these)

- `generate.py` (seed 177848) writes `tasks/hazmat-trailer-check/environment/data/` (trailers.json,
  carrier.json), the identical verifier copy in `tests/data/`, `tests/case_tags.json` and
  `tests/golden.json` (163 planted trailers with hand-worked placards and violations). Filler loads
  where DANGEROUS would cover a single leftover category are rejected (left open by the rule).
  Default-packed loads heavier than one real package are split into several identical drums, boxes,
  cases or cylinders in the same bay (pairs in the hand-worked answers expand with them).
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, 68 misreadings each fail
  at least one test (29 placarding and segregation, 39 blend classification).

Rule text used (pasted by the author from law.cornell.edu): 49 CFR 172.500, 172.502, 172.504,
172.505, 177.848, the bulk / non-bulk packaging definitions in 171.8 (v2), and for v3 (house blends
classified from lab data, added after Pass@2 was solved 2/2 twice) 173.2a, 173.115, 173.116,
173.120, 173.121, 173.132, 173.133, 173.136, 173.137, 173.150 and 172.402. All table transcriptions
(solve.py, engine.py) were checked against each other, and the precedence table in solve.py was
checked cell by cell against the pasted text.
