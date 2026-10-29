# Difficulty: what got solved, what did not, and how to design for Pass@2

Two forces pull against each other. Pass@2 wants the model to fail (at most 1 of 2 solves). The
deep review and the artificiality check want every answer to follow from the instruction plus the
cited standard, with no invented rules and no ambiguity. So difficulty must come from a real method
applied to real-looking data, where the natural shortcut gives near-right answers that are wrong.

## Record so far

| Task | Track | Result | Lesson |
|---|---|---|---|
| hos-log-audit | TB3 legal | Pass@2 0/2, deep review PASS, Pass@5 3/5 | Lean instruction citing 49 CFR 395 without explaining it; long raw logs; minute-exact clocks; failures were near-threshold cases on filler records |
| bridge, part117, sms, auto-ad, feca | TB3 legal | passed difficulty | exact computation over time or money with a plainly written exclusion |
| hazmat-trailer-check | TB3 legal | solved 2/2 three times | lookups (tables) are easy for models |
| stormwater-inspection-audit | Science (Civil) | failed scientifically-grounded | a regulatory rule engine is not science |
| sediment-basin-routing | Science (Civil) | solved 2/2 twice (27 and 43 min) | an 850-word instruction that listed every convention and trap, plus 0.5 percent tolerances, turned a hard simulation into a recipe |
| storm-drain-energy | Science (Civil) | static pass after rename; later stages pending | HEC-22 Section 9.4 network grade lines with the FHWA access hole method |
| vancomycin-auc-dosing v1 | Science (Medicine) | static, artificiality, oracle/nop, similarity, rubric all PASS; Pass@2 solved 2/2 (56 min) | the instruction defined the model exactly (superposition through both levels), listed which levels count, gave the MIC rule: every settled point removed a trap. All gates before Pass@2 pass with this design, so keep the structure and cut the instruction |
| vancomycin-auc-dosing v2 | Science (Medicine) | Pass@2 0/2 (25 min), then deep review FAIL | both agents reproduced every PK value for all 240 patients and failed only on the MIC rule, which the instruction no longer stated and which I had written against the guideline's own Recommendation 6 (assume MIC 1 mg/L, do not lower the dose for MIC below 1). Lessons: a cited-but-unstated rule that decides answers fails U1/U2/U3; failures driven by a convention fail G-DIFF; and if agents get the whole scientific crux right, the task is too easy no matter what. Retired |
| vancomycin-auc-dosing v3 | Science (Medicine) | MIC fixed per Rec. 6: Pass@2 solved 2/2 (16 min) | as predicted, once the only failure point was fixed the clean PK pipeline was solved |
| vancomycin-auc-dosing v4 | Science (Medicine) | pending | added record realism stated in the instruction: New York local times with 139 of 240 courses crossing a 2026 DST change (ignoring DST: 164 of 240 wrong), a laboratory reporting umol/L (molar mass given), corrected results replacing originals by accession; margins 0.6 percent above the 0.5 percent tolerance |

## Patterns that work

0. **Record realism that is stated but easy to mishandle in code** (what the passing legal tasks had): local times in a named time zone with courses crossing a daylight-saving change, mixed units with the conversion factor given, corrected or amended records that replace originals, held events. State each in one plain sentence in the data paragraph; never explain how to handle it. Avoid the ambiguous repeated hour.

1. **The standard method breaks down partway.** The textbook route (steady-state equations, a
   single formula, assuming clean data) gives plausible numbers that are wrong for a large share of
   cases; the expert uses the general method. Calibration shows the shortcut failing 100+ of 240.
2. **Messy records with one correct reading.** Pump events with cumulative volumes, pauses,
   partial doses, held doses, rejected specimens, flags in result strings, order changes, shuffled
   network files. The reading is fixed by the standard or one settled point, never by a trick.
3. **Many near-threshold cases with exact decisions.** Plant 15 to 20 percent of cases within a
   small band of each boundary (category edges, rounding midpoints, sampling windows), on both
   sides, and keep a minimum margin so no careful implementation can disagree.
4. **Conditions that interact.** Two different tests for the same idea at different points in a
   method (plunging test against Eai versus against Ea), floors and caps, interpolation between
   table columns, a first-match order in a table.
5. **Long continuous or networked computation** where an early error propagates (an outfall to
   every upstream structure; a whole dosing history into each level).

## The two-sided lesson (read this before designing)

- Pass@2 needs the agent to fail. The deep review needs every failure to land on the intended crux, with every rule that decides a graded answer stated in instruction.md (or following uniquely from text shipped or cited, and never contradicted by that text). So difficulty can never come from an unstated rule or convention.
- Therefore the crux itself must be hard to execute even when fully disclosed. Vancomycin v2 showed that a one-compartment superposition fit over messy records, fully specified, is solved perfectly by the current model in 25 minutes. Pick a crux with long interacting computation (HOS clocks, network grade lines, coupled routing with exact categorical outputs) where a fully informed agent still slips.
- Before building, check every rule you write against the source document's own recommendations, including summary recommendations elsewhere in the text (vancomycin Rec. 6 contradicted the MIC rule).
- Margins must exceed tolerances: if continuous outputs are accepted within 0.5 percent, every category boundary and rounding midpoint must be more than 0.5 percent away (the deep review flags this as unresolved), or the categories must be computed from the agent's own numbers.

## The instruction-length lesson

Every rule written into instruction.md is one the agent no longer has to know. Keep only what the standard does not settle, phrase choices among real alternatives as short Restrictions ("Do not use Bayesian estimation or population priors"), and cite the standard for everything it defines. Restrictions must change the answer (so they are verifiable through the output); never ban tools.

## Patterns that fail

1. A recipe instruction. If the instruction names the traps, the model avoids them.
2. Loose tolerances on outputs that hide method errors. Prefer exact categories plus tight numbers.
3. Lookups and tables alone.
4. Rule engines over regulations (fails the science gate).
5. Ambiguity as difficulty (fails deep review).
6. Removing the internet or limiting CPUs (not allowed as difficulty).
7. Targeting a specific model's reported weaknesses (artificial).

## Calibration targets

Write 20 to 30 shortcut versions of solve.py by text replacement (`templates/calibrate.py`). Each
must fail at least one test. Include: the textbook shortcut, each settled point read the other
way, each data irregularity ignored, every rounding alternative, wrong constants (g, Manning
1.49 vs 1.486), intermediate rounding like the worked example, and swapped coefficients. Report the
count of wrong rows for each. If a shortcut passes, plant cases that separate it or drop it with a
reason in the authoring README.

## If Pass@2 solves it

1. Read the trial times. Under 45 minutes for 2/2 means the instruction is doing the work.
2. Check the instruction for recipe content: lists of conventions that are really hints, any
   mention of a trap, any formula the agent could copy.
3. Check the tolerance: could a shortcut sit inside it?
4. Do not stack more rules of the same kind. Propose a redesign to the person: same standard with a
   leaner instruction and more near-threshold planting, or a new idea with the section 4 pattern.
