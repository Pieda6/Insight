# sms-send-schedule dev tools (never upload these)

- `generate.py` (seed 64120) writes `tasks/sms-send-schedule/environment/data/`, the identical
  verifier copy in `tests/data/`, `tests/case_tags.json` (rule-family tags) and `tests/golden.json`
  (93 planted messages with hand-worked expected decision and minute).
- `calibrate.py` (needs writable `/app`): oracle == engine == golden, oracle passes, empty output
  fails, and 16 misreadings of 47 CFR 64.1200 each fail at least one test (quiet hours on every
  message, registry on every message, CTIA-only keywords, all/no platforms autodialers, any consent
  record, relationship enough for an autodialer, 18 months for inquiries, UTC relationship date,
  do-not-call forever, consent returning after the do-not-call period, area-code zone, HQ zone,
  frozen pre-DST offset, hourly search, 21:00 excluded). "Do-not-call request does not end the
  relationship" is equivalent by design on this data (reported, not required to fail).

Rules come from the 47 CFR 64.1200 text the author pasted (eCFR, amended through 90 FR 42138,
Aug 29, 2025): (a)(2), (a)(10), (c)(1), (c)(2), (d)(3), (d)(6), (f)(2), (f)(5), (f)(9), (f)(15).
