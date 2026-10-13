# airline-claims-desk dev tools (never upload these)

- `generate.py` (seed 26050) writes `tasks/airline-claims-desk/environment/data/` (claims.json, flights.json,
  airports.json, carrier.json, federal_holidays.json), the identical verifier copy in `tests/data/`,
  `tests/case_tags.json` and `tests/golden.json` (104 planted claims, hand-worked; 332 claims in all).
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, 57 misreadings (source edits of
  the reference solution) each fail at least one test.

## Version 5 (after v3 and v4 were solved 2/2 in 9 and 8 minutes)

Why v3/v4 were easy: every input field was pre-classified in the rule's own words
(`held_confirmed_reserved_space`, `consumer_response: rejected_alternatives`, `new_arrival_shift_minutes`,
`planned_arrival_at_time_arranged`), so each claim was a lookup. The tasks that passed (sms-send-schedule,
auto-ad-clearance, hos-log-audit) all give raw records that must be reconstructed and judged.

v5 data is raw operational records:
- flights.json: schedule history per flight (versions with the UTC moment recorded; local wall times),
  cancellation, door-open time, aircraft substitution.
- claims.json: ticket (purchase time, coupons by flight id), event log (check-in, gate events, volunteers,
  compensation accepted, replacement arranged, change notices with the offered itinerary, replies, boarding,
  baggage reports and deliveries), refund request time.

What the solver must reconstruct: the original itinerary as scheduled at purchase; the offered itinerary as
scheduled at the final notice; whole-itinerary significance (origin departure earlier, destination arrival
later, airports, connection count, class), cumulative across notices; the replacement's arrival as planned
when arranged (later schedule changes ignored); check-in against the contract deadline in local time; bag
delay from the door opening; segment durations across zones; UTC dates for due dates.

Contested readings kept out of the data on purpose:
- no reply after the first flight could leave (so (ii) and (iii) dates never compete);
- silence only where exactly one kind of offer was made (rebooking or voucher, not both);
- silence never follows a change that is not significant;
- no partly flown tickets in change claims (notices always come before travel starts);
- check-in failures never carry paid extras; Part 250-exempt flights (small aircraft, foreign origin) carry
  none either;
- one replacement arrangement per oversale, always to the destination or first stopover airport;
- the denied passenger's span to the first stopover has the same domestic/international character as the ticket;
- award tickets only on single-flight spans;
- every connection has bags checked through and the passenger airside (break in journey turns on 24 h only);
- no wall time in a repeated daylight-saving hour (claims that would need one are rebuilt).
Settled by fact sentences in instruction.md: original itinerary = as scheduled at purchase; offered itinerary
= as scheduled when the notice was sent; an itinerary departs when its first flight does; flight duration is
the scheduled duration; the opportunity to deplane is the door opening; dates are UTC.

## History
- v1: deep review FAIL (unused extras after a voucher; both trials read 260.4 the other way).
- v2/v3: 260.4 per plain text, break in journey, due dates under 260.6(a)(2); v3 Pass@2 2/2 in 9 min.
- v4: local schedule times and daylight saving; Pass@2 2/2 in 8 min.
- v5: raw operational records (this version).

Rule text used (pasted by the author from law.cornell.edu): 14 CFR 250.1, 250.2, 250.2a, 250.2b,
250.5, 250.6, 250.8; 260.2, 260.3, 260.4, 260.5, 260.6, 260.7, 260.10.
