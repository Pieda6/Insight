# Writing instruction.md

You write it. It is the only thing the trial agent reads, and the artificiality check scores it for
sounding like a real person's work brief. A complete example that passed every check is
`example/hos-log-audit/task/instruction.md`.

## Shape

- Plain paragraphs only. No headings, bullet points, tables or code blocks.
- 550 to 900 words.
- Plain, slightly formal business English, like a manager briefing a capable analyst.
- No em dashes. No exclamation marks. No "Note:" or "Important:" labels.
- Absolute paths (`/app/data/...`, `/app/output/...`).
- The last line is exactly:
  `You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.`

## What goes in, in this order

1. **The situation.** Who the business is (a fictional company), who needs the result, what
   decision it supports. One short paragraph.
2. **The governing rule and its version.** "The sole governing authority is 49 CFR Part 395 as in
   force on October 1, 2026; no other rules, guidance, state law or company policy applies."
3. **Each input file**, with what its fields mean and their units. Name every file. Mention
   notes or optional fields and what their values mean.
4. **Facts about the situation that close open questions.** Only facts, never rule explanations.
   Good: "Every driver operates a property-carrying commercial motor vehicle in interstate
   commerce." "A flight counts as cancelled from the moment Lakeshore notifies the passenger."
   "Where a record notes adverse driving conditions that were not known beforehand, those
   conditions kept the driver from completing the run safely within the normal limits."
5. **The output.** Exact path, exact header line, what one row means, value formats with one
   example, sort order, what to write when there is nothing ("none", or no rows), and "the file is
   compared exactly, so no extra columns, blank lines or explanations".
6. The fixed last line.

## What must stay out

| Never write | Why | Instead |
|---|---|---|
| The rule's numbers, tables, thresholds, lists of exceptions | Artificiality A5, and it removes the difficulty | Cite the rule and version date |
| Which rule applies to which case, how rules combine, which exception wins | Artificiality A6 | Leave it to the cited rule; settle open questions with facts or by keeping cases out of the data |
| Steps or procedures ("first compute X, then for each row ...") | Artificiality A7 | Define the output ("the earliest compliant time within seven days") |
| Named traps ("watch out for the 24-hour stopover") | Gives the answer away; reads as engineered | Nothing |
| Example answers or counts ("about 40 violations") | Gives answers away | Nothing |
| Padding ("treat these as fixed facts", "apply consistently", "do not change the records") | Reads as machine-written | Say it once, if at all ("The records are complete and correct.") |
| Mentions of tests, verifiers, golden files, engines | Breaks the scenario | Nothing |

## Before and after (real edits that fixed failures; the "before" lines are paraphrased)

- A7 failure. Before: "For each message, search minute by minute from the scheduled time for up
  to seven days and pick the first allowed minute; if none is found, mark it BLOCK."
  After: "For RESCHEDULE it is the earliest compliant time within seven days after the scheduled
  time, and for BLOCK, which means there is no compliant time in that period, it is left empty."
- A6 failure. Before: "Written consent is required for messages sent with an autodialer, while the
  registry and calling hours apply to telephone solicitations."
  After: (deleted). The data was regenerated so both readings give the same answer, and a leaf fact
  was kept: "A consent record counts for any purpose under the rule only if it meets the rule's
  definition of prior express written consent."
- Deep-review fix (airline), a fact added: "A passenger who turns down or does not answer the
  alternatives offered for a cancelled or significantly changed flight uses no part of that
  ticket."

## Final checklist (run it every time)

1. Every file name, field name, status value and unit in the text exists in the built data,
   spelled the same way.
2. The output header in the text equals the header the tests require.
3. The sort order and value formats in the text equal what the tests check.
4. No number from the rule appears (section citations like "§ 395.3(b)" are fine; they name the
   rule, they do not restate it).
5. No step lists, no "first ... then", no "for each ... do".
6. No em dashes (search for the character).
7. Word count between 550 and 900.
8. Last line exact.
