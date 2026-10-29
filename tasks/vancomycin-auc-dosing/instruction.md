The infectious diseases pharmacy service is reviewing vancomycin therapy for 240 adults treated for serious MRSA infections. Following the 2020 consensus guideline of ASHP, IDSA, PIDS and SIDP (Rybak et al., Am J Health-Syst Pharm 2020;77:835-864), estimate each patient's exposure from their own measured levels and recommend a dose.

The data is in /app/data/. patients.json gives each patient's details and the vancomycin MIC of their MRSA isolate with the testing method, or null when none was reported. administrations.csv is the administration and infusion pump record; the cumulative volume infused is recorded at every pause, rate change and stop, and not_given marks a held dose. levels.csv holds the vancomycin results as the laboratory reported them, and orders.csv the vancomycin orders. Times are local, to the minute.

The service uses a one-compartment model with first-order elimination, fitted to each patient's two usable levels and everything documented as given. A level is usable when the laboratory reported a value for it and it was drawn neither while an administration was running, pauses included, nor less than 1 hour after one stopped; every patient has exactly two.

Restrictions:
- Do not use Bayesian estimation or population pharmacokinetic priors.
- Do not use the ordered doses or schedules to decide what was given or when; only the administration record counts.
- Do not round anything before the final values.

Write /app/output/vancomycin_review.csv with the header patient_id,ke_per_h,volume_l,auc48,auc24_ss,exposure,new_dose_mg and one row per patient, sorted by patient_id:
- ke_per_h: the elimination rate constant per hour, five decimals.
- volume_l: the volume of distribution in liters, two decimals.
- auc48: AUC in mg·h/L from the start of the first administration to 48 hours later, one decimal.
- auc24_ss: steady-state 24-hour AUC in mg·h/L on the most recently ordered maintenance regimen, one decimal.
- exposure: below, within or above the guideline's AUC/MIC target, using the MIC the guideline says to use.
- new_dose_mg: the current dose when exposure is within; otherwise the dose at the current interval for an AUC/MIC of 500, rounded to the nearest 250 mg.

Numbers are accepted within 0.5 percent; exposure and new_dose_mg must match exactly. Do not add extra columns, blank lines or explanations.

You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
