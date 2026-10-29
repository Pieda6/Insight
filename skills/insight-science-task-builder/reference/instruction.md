# Writing instruction.md

The instruction is a brief from a real office to a professional. 350 to 550 words. No em dashes.
It must pass artificiality A1 to A7 and must not hand over the method.

## Structure (four paragraphs and a list)

1. **The request** (2 sentences): who is asking, how many cases, what for, and the governing
   standard with full citation (title, edition, year; journal citation for a guideline). Name the
   method sections ("Section 9.4, with the FHWA inlet and access hole energy loss method of Section
   9.1.6.7").
2. **The data** (one paragraph): each file in `/app/data/`, its fields and units, in the
   vocabulary of the records ("the cumulative volume infused is recorded at every pause, rate
   change and stop"; "not_given marks a dose that was held"). Do not explain how to use them.
3. **"The <office>'s practice settles these points:"** followed by a bulleted list, one sentence
   each, only for:
   - the model or method definition when the standard offers several;
   - places where the standard leaves a choice or its worked example differs from its text
     ("as Example 9.2 does");
   - constants that change results (g = 32.2; Manning constant 1.486 as printed; equations 9.2 and
     9.4 as printed);
   - the window or rule for using a record that the standard states (cite it);
   - rounding ("Nothing is rounded before the final values"; "rounded to the nearest 250 mg").
4. **The output** (one paragraph): exact path, exact header, one row per what, sort keys, meaning
   of each column, decimals, what is compared exactly and the tolerance for the rest, and "Do not
   add extra columns, blank lines or explanations."
5. The fixed last line, exactly:
   `You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.`

## Restrictions list

After the model sentence, add a short "Restrictions:" list of two to four "Do not ..." lines that rule out real alternative methods or readings a professional could choose (population priors, using orders instead of the administration record, intermediate rounding). Each must change the output, so the tests enforce it. Do not ban tools or libraries (rubric requirements_verifiable).

## Never

- List traps, edge cases or "be careful" notes.
- Give equations, coefficients or tables from the standard (A5).
- Invent combinations: "the later of", "the lower of", "whichever comes first" (A6), unless the
  standard says it in those words.
- Write steps: "first parse, then compute, then" (A7).
- Settle by arbitrary order (alphabetical, larger ID, first listed).
- Ask for precision finer than real records support.
- Mention tests, the verifier, golden files or hidden data.
- Use padding ("ensure that", "robust", "your task is to").

## Checklist before zipping

- Every file, field, unit and column named in the instruction exists exactly in the data and code.
- Every settled point is implemented identically in solve.py, engine.py and sim.py, and a shortcut
  that reads it the other way fails in calibration.
- `wc -w instruction.md` is 450 to 600; `grep -c "—" instruction.md` is 0.

## Example (vancomycin-auc-dosing, passed A1 to A7)

See `examples/vancomycin-auc-dosing/instruction.md`. Its settled points: the one-compartment model
with constant-rate stretches between pump events at the bag's concentration; the usable-level rule
(the guideline's 1-hour postdistributional window, judged from the documented stop); auc48 from the
first start; auc24_ss on the most recently ordered maintenance order; the broth microdilution MIC
rule (from the guideline); the exposure band and dose rounding.
