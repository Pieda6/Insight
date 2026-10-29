# The proposal

Write it only after reading the source document. Send it in one code block so the person can paste
it. No em dashes. Wait for "approved" before building.

## Template (every heading is required)

```
Title: <job> (<standard short name and year>)

Category: Science
Sub-category: <the repo's subcategory, e.g. Medicine>

Summary:
<3 to 5 sentences: who does the job, how many cases, what the agent receives (name the messy
records), what it must output for each case, and the governing standard with full citation.>

Real-world grounding:
<Who does this work for pay and why it matters. Why real records are irregular, and, if true, that
the standard itself says its simple method does not fit such records (cite the page).>

Data provenance:
<Synthetic, seeded generator. Where each parameter range comes from (the standard's ranges,
published ranges). The irregularities. The planted near-threshold cases, named one by one. The
rejection rule: the generator rejects any case where a category or rounded value would change
within the tolerance, so careful implementations cannot disagree.>

Determinacy (how comparison stays fair):
instruction.md cites <standard> and states these as the <office/service>'s practice:
1. <model or method definition, one sentence>
2. <each point the standard leaves open, one sentence each, citing the worked example it follows>
...
Output: /app/output/<file>.csv with header <columns>, one row per <case> sorted by <keys>.
<Which columns exact, which with what tolerance.> Every row must pass.

Why it is hard:
- <the standard method that breaks down on these records, and why>
- <each messy element and what reading it requires>
- <interacting conditions>
- <exact decisions near thresholds>
Why it is hard for an LLM agent in particular: <the shortcut it reaches for, and that it is right on
most cases and wrong on the many that matter>

Solution strategy:
<4 to 6 sentences: the method in order, and the key insight.>

Expert time estimate:
About <N to M> hours for <the professional> who codes: <split by part>.

Inputs: <each file and what it holds>

Output: <path> as described above.

Verification:
An independent engine in the verifier image recomputes every case with a different numerical
approach, and the generator is a third implementation; all three agree far inside the tolerance.
<What published worked examples or closed-form results check the engine.> Tests check formats,
one row per case in order, one test per family (<list>) and then every row. Calibration shows each
shortcut (<list>) fails many rows.
```

## Rules for the content

- Name each settled point as the practice of the office or service, and tie it to the standard or
  its worked example ("as Example 9.2 does"). Never settle a point by an arbitrary tie-break
  (alphabetical, larger ID, whichever comes first) unless the standard itself orders it (for
  example "the first case in table order", which is how the table reads).
- Do not list the traps in the Determinacy section. They go in "Why it is hard" only.
- State the tolerance you will really use. Prefer exact categories.
- If Proposal QC comes back with a determinacy blocker, add one settled point per blocker; if it
  asks for a rules file with the standard's numbers, explain that restating them fails A5 and that
  the instruction cites the standard instead.
- End the message with one honest line on risk (for example "pharmacokinetic fitting is well known
  to models; the difficulty rests on the messy records and near-threshold cases").

## Example that was approved and then built (vancomycin-auc-dosing)

```
Title: Vancomycin AUC-guided dose adjustment from irregular hospital dosing records (2020 ASHP/IDSA/PIDS/SIDP consensus guideline)

Category: Science
Sub-category: Medicine

Summary:
A clinical pharmacist reviews vancomycin therapy for about 200 hospital patients treated for serious MRSA infections. The agent receives each patient's medication administration record (every infusion with its start, pauses, restarts, stop and the volume actually infused, including late, early, interrupted and partly given doses and loading doses), the measured vancomycin levels with their collection times and raw lab results (some rejected, below the reporting limit, or drawn at the wrong time), the current dosing order, and the MRSA isolate's MIC with the method used to measure it. For every patient it must estimate the patient's elimination rate constant and volume of distribution from the two usable levels, the AUC achieved over the first 48 hours, the steady-state 24-hour AUC on the current regimen, whether exposure is below, within or above the guideline target, and the new dose. The method is AUC-guided dosing and monitoring from the 2020 revised consensus guideline (Rybak et al., Am J Health-Syst Pharm 2020;77:835-864).

Real-world grounding:
Hospital pharmacists adjust vancomycin doses from measured levels every day; since 2020 the consensus guideline recommends AUC-guided dosing (AUC/MIC 400 to 600) instead of trough-only monitoring for serious MRSA infections. Real dosing records are irregular: doses are given late, infusions are paused or stopped early, and levels are drawn early or during an infusion, so the simple steady-state equations the guideline describes often do not apply, which the guideline itself notes.

Data provenance:
All inputs are synthetic. A seeded generator builds about 200 adult patients with realistic weights, ages and kidney function, vancomycin regimens of 15 to 20 mg/kg every 8 to 24 hours with 20 to 35 mg/kg loading doses (guideline ranges), and true individual pharmacokinetic parameters from published adult vancomycin ranges. It writes dosing records with realistic irregularities and levels computed from the true parameters. Planted cases sit near every threshold: exposure just under and over 400 and 600 times the MIC, levels drawn just before and after 1 hour after an infusion ends, MICs reported by broth microdilution and by other methods, and new doses just either side of a 250 mg rounding step. The generator rejects any case where a category or dose would change within the tolerance, so careful implementations cannot disagree.

Determinacy (how comparison stays fair):
instruction.md cites the guideline and states these as the pharmacy's practice:
1. Model: one compartment, each infusion segment given at a constant rate over its documented times, first-order elimination, no vancomycin before the first documented dose; a patient's volume and elimination rate are the values for which this model passes through both usable levels, given every documented infusion.
2. Usable levels: a numeric result, not drawn during an infusion and not within 1 hour after the end of one (the guideline's postdistributional sampling window). Every patient has exactly two usable levels.
3. MIC: the target is AUC/MIC 400 to 600, with the MIC used only when measured by broth microdilution and 1 mg/L otherwise (guideline).
4. Early exposure: the model's AUC from the first dose to 48 hours after it.
5. Steady-state AUC24: the current order's daily dose divided by the patient's clearance.
6. Exposure category: within when AUC24/MIC is from 400 to 600 inclusive, otherwise below or above.
7. New dose: the current dose when within; otherwise the dose at the current interval whose steady-state AUC24/MIC is 500, rounded to the nearest 250 mg.
Output: /app/output/vancomycin_review.csv with header patient_id,ke_per_h,volume_l,auc48,auc24_ss,exposure,new_dose_mg, one row per patient sorted by patient_id. ke within 0.5 percent, volume and AUCs within 0.5 percent; exposure and new_dose_mg exact. Every row must pass.

Why it is hard:
- The guideline's two-level equations assume steady state with both levels in one dosing interval; in these records that is often false (first-day levels, late or missed doses, levels across two intervals), so the patient's parameters must come from superposition of every actual infusion.
- Messy records: paused and restarted infusions, partly infused bags, rate changes and loading doses all change the drug actually given and when.
- Choosing the usable levels: rejected and below-limit results, levels drawn during an infusion or less than an hour after one, judged against the actual end of the infusion, not the scheduled one.
- The MIC rule: only broth microdilution MICs change the target.
- Exact categories and doses near the 400 and 600 lines and near rounding steps.
Why it is hard for an LLM agent in particular: the textbook Sawchuk-Zaske and peak-trough AUC formulas are what an agent reaches for, and they look right on most patients while being wrong on the many whose records are not at steady state; small timing and volume details move patients across the target lines.

Solution strategy:
Parse each record into infusion segments with rates; select the usable levels; write each level as (1/V) times a sum of infusion terms that depends only on ke; solve the ratio of the two levels for ke, then V; integrate the model over 0 to 48 hours; compute clearance, the steady-state AUC24, the category with the right MIC, and the new dose.

Expert time estimate:
About 8 to 12 hours for a clinical pharmacist or pharmacometrician who codes: 3 to 4 hours to parse and clean the records, 3 to 4 hours for the superposition model and fitting, and 2 to 4 hours for checking.

Inputs: patients.json (age, sex, weight, MIC and its method), administrations.csv (infusion events), levels.csv (collection time and raw result), orders.csv (current dose and interval).

Output: /app/output/vancomycin_review.csv as described above.

Verification:
An independent engine in the verifier image recomputes every patient with a different numerical approach, and the generator is a third implementation; all three agree far inside the tolerance. Hand-worked patients check the engine against textbook one-compartment results (single infusion, steady state). Tests check formats, one row per patient in order, one test per family (first-day levels, irregular records, rejected or mistimed levels, broth microdilution MICs, near-threshold exposure, dose rounding) and then every row. Calibration shows each shortcut (steady-state equations, scheduled instead of documented times, using mistimed levels, MIC from any method, no rounding) fails many rows.
```
