The radiation oncology physics service is reviewing post-implant dosimetry for 60 patients treated with permanent prostate seed implants of iodine-125 or palladium-103. Following the AAPM TG-43U1 protocol (Rivard et al., Update of AAPM Task Group No. 43 Report: A revised AAPM protocol for brachytherapy dose calculations, Med Phys 2004;31:633-674), calculate the dose each listed point receives from the implanted seeds.

The data is in /app/data/. patients.json gives each patient's implant time in local New York time (America/New_York), to the minute. batches.csv gives each seed batch's model and the source strength from its vendor certificate: strength_unit is U_per_seed (the air-kerma strength of each seed), U_total (the air-kerma strength of the whole batch of seeds_in_batch seeds) or mCi_apparent (the apparent activity of each seed, with the exposure-rate constant the vendor used, in R·cm²·mCi⁻¹·h⁻¹), and calibrated_at is the certificate's calibration time with its UTC offset. seeds.csv lists every seed found on the post-implant CT with the positions of its two end markers in millimetres; review names the seed that a duplicate detection repeats. points.csv gives the dose points in the same CT coordinates. source_data.json holds the report's consensus dosimetry data for each seed model (Tables I to XI, with the half-lives of Table XIII).

Each seed's centre is the midpoint of its end markers and its longitudinal axis runs through them, and every seed stays where the CT shows it from the implant time on.

Restrictions:
- Use the report's 2D formalism with the line-source geometry function for every seed.
- Between tabulated values, interpolate ln g_L(r) linearly in r, and F(r, θ) linearly in r and in θ.
- Do not round anything before the final values.

Write /app/output/point_doses.csv with the header patient_id,point_id,dose_gy and one row per point, sorted by patient_id and then point_id, where dose_gy is the total dose in Gy the point receives from the implant time until the seeds have fully decayed, with three decimals. Doses are accepted within 0.1 percent. Do not add extra columns, blank lines or explanations.

You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
