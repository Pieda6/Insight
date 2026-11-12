# The disclosure dilemma: Pass@2 versus the deep review, and how to hold both

## The dilemma, proven four times
| What the agent can see | Pass@2 | Deep review |
|---|---|---|
| Rule written in instruction.md | solved 2/2 (vancomycin v1/v3, prostate) | pass |
| Full standard text shipped in /app/data | solved 2/2 (prostate, TG-71 v1) | pass |
| Rule only in the cited standard, not shipped, and it is the only failure point | passes | FAIL: "not uniquely pinned by agent-visible text" (U1-U3), "failures cluster on the ambiguity, not the crux" (G-DIFF) (vancomycin v2, prostate, TG-71 v3) |
| Standard named, text not shipped, many independent rules each in the standard | passed (TG-71 v2) | PASS (TG-71 v2) |

## The playbook (what TG-71 v2 did, plus the v4 fix)
1. **Name the governing documents exactly** in instruction.md (authors, journal, year, volume, pages) and say "No
   other rule or practice applies." Do not ship their text.
2. **Ship the standard's tables as data** (CSV with the table number in the file description). Values are then
   agent-visible; the rules for using them stay in the named report.
3. **State as facts only what the documents leave to the user**: set-up facts, units, leakage levels, interpolation
   ("Tables and curves are interpolated linearly"), barometer readings not corrected to sea level, which method a
   record used when the standard allows two. Never a step, a trap, or a formula.
4. **Many independent rules, not one.** TG-71 v2 had ~15 rule families; failures spread across them. If calibration
   shows one family carries all the difficulty, add more independent ones before running Pass@2.
5. **Pin every decisive rule to a named section.** When a reviewer could argue that a rival reading survives (the
   rectangular-insert rule), add one instruction sentence that names the sections governing that choice without
   stating the rule: "A rectangular insert is taken as the report takes rectangular electron fields, for the output
   factor (Sec. 2.B.2), the effective SSD (Sec. 3.B.2.d) and the air gap factor (Sec. 3.B.2.e)."
6. **Give the reviewer the text.** Save the exact quotes in `authoring/sources/<name>.txt` (strip download stamps such
   as "Downloaded from ... by <institution>") and repeat the key sentence as a comment next to the code in
   tests/engine.py. The deep reviewer reads the repo; it cannot open the PDF. Its "Unresolved" item on TG-71 was
   exactly "needs the TG-71 report to settle".
7. **Accept every reading the documents allow** (union of variants in `engine.allowed()`), keep the union spread under
   the tolerance (test it), and test that every case tag really moves its case outside the tolerance. The reviewer
   flagged both as advisory when they were missing.
8. **Never write the rule out in full to satisfy the reviewer** if the agents got everything else right: the next
   Pass@2 will be solved 2/2. Say so to the person and offer the section-pointer fix instead.

## AVA (adversarial verifier audit) rules
- Every sentence of the output paragraph must be enforced by the tests. "Do not round to whole monitor units" with a
  0.3 percent tolerance was a blocking B2 (a rounded large value passes). Write only the acceptance rule: "Each value
  is accepted within 0.3 percent of the correct value."
- "At least two decimal places" and similar formatting promises are untested requirements: remove them or test them.
- Advisory findings worth fixing in the same push: discriminating case tags verified in the tests, the allowed-variant
  band checked against the tolerance, golden checks independent of the engine.
- AVA evidence arrives as `ava-review-evidence.zip` (ava-gate.json, rendered.md). `blocking_ids` are what must change.

## Instruction-level rules that passed A1-A7 every time
- First paragraph: who needs what (a real job), the outcome per record, the governing documents, "No other rule or
  practice applies."
- Second paragraph: every file and field, plainly, including messy facts (units, signs, corrections).
- Third paragraph: facts the documents leave open. No "first ... then", no "make sure", no lists of steps.
- Fourth paragraph: the output file, exact header, one row per record in a stated order, units, tolerance.
- Last line: "You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific
  to this task."
- Under 1,500 tokens; the static check also warns when a shipped document is many times longer than the instruction
  (non-blocking T16), which disappears when the text is not shipped.
