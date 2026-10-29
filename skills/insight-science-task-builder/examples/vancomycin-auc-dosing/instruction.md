The infectious diseases pharmacy service is reviewing vancomycin therapy for 240 adults treated for serious MRSA infections. Following the 2020 consensus guideline of ASHP, IDSA, PIDS and SIDP (Rybak et al., Am J Health-Syst Pharm 2020;77:835-864), estimate each patient's exposure from their own measured levels and recommend a dose.

The data is in /app/data/. patients.json gives each patient's details and the vancomycin MIC of their MRSA isolate with the testing method, or null when none was reported. administrations.csv is the administration and infusion pump record; the cumulative volume infused is recorded at every pause, rate change and stop, and not_given marks a held dose. levels.csv holds the vancomycin results as the laboratory reported them, in mg/L or umol/L (vancomycin, 1449.3 g/mol), where a corrected result replaces the earlier result with the same accession, orders.csv holds the vancomycin orders, and hemodialysis.csv lists each dialysis session with the dialyzer's vancomycin clearance. Times are local New York time (America/New_York), to the minute.

The service uses a one-compartment model with first-order elimination at the patient's own clearance, to which the dialyzer's clearance adds while a session runs, fitted to each patient's two usable levels and everything documented as given. A level is usable when the laboratory reported a value for it and it was drawn neither while an administration or a dialysis session was running, pauses included, nor less than 1 hour after an administration stopped; every patient has exactly two.

Restrictions:
- Do not use Bayesian estimation or population pharmacokinetic priors.
- Do not use the ordered doses or schedules to decide what was given or when; only the administration record counts.
- Do not round anything before the final values.

Write /app/output/vancomycin_review.csv with the header patient_id,ke_per_h,volume_l,auc48,auc24,exposure,new_dose_mg and one row per patient, sorted by patient_id:
- ke_per_h: the patient's own elimination rate constant per hour, off dialysis, six decimals.
- volume_l: the volume of distribution in liters, two decimals.
- auc48: AUC in mg·h/L from the start of the first administration to 48 hours later, one decimal.
- auc24: the AUC in mg·h/L over the 24 hours before the later usable level, the guideline's AUC for the sampling period, one decimal.
- exposure: auc24 below, within or above the guideline's AUC target of 400 to 600 mg·h/L. As the guideline's Recommendation 6 advises, the MIC is taken as 1 mg/L for every patient; a measured MIC, by any method, changes neither the target nor the dose.
- new_dose_mg: the dose of the most recently ordered maintenance regimen when exposure is within; otherwise that dose changed in proportion to bring auc24 to 500 mg·h/L, as the guideline describes, rounded to the nearest 250 mg.

Numbers are accepted within 0.5 percent; exposure and new_dose_mg must match exactly. Do not add extra columns, blank lines or explanations.

You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
