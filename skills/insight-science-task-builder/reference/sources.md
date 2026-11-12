# Source documents: what we have, how to get more

## Documents already used (ask the person to re-upload only if the file is not in the session)
| Document | Use | Notes |
|---|---|---|
| HEC-22 4th ed. (2024), FHWA, Sec. 9.4 | storm-drain-energy | recent edition the model half remembers |
| Rybak et al. 2020 vancomycin consensus guideline (AJHP) | vancomycin tasks | Rec. 6 contradicts "lower dose for MIC below 1" |
| AAPM TG-43U1, Rivard et al., Med Phys 2004;31(3):633-674 | prostate-seed-dosimetry | Appendix C extrapolation rule; Table XV dose rates for checks |
| KDIGO Clinical Practice Guideline for AKI, Kidney Int Suppl 2012;2:1-138 | kdigo-aki-staging | Recs 2.1.1, 2.1.2, Table 2 |
| AAPM TG-71, Gibbons et al., Med Phys 2014;41(3):031501 (AAPM Report 258) | tg71-mu-check | Tables II-IX (6 MV, 9 MeV), Sec. 8 worked examples as goldens |
| AAPM TG-51, Almond et al., Med Phys 1999;26(9):1847-1870 | tg51-output-audit | Eqs 8-22, Tables I-III; the Wiley PDF carries "Downloaded ... by <institution>" lines: strip them |
| TG-51 photon addendum, McEwen et al., Med Phys 2014;41(4):041501 | tg51-output-audit | Table I (Eq. 1 fits), Secs 3.E, 4.D, 4.H, 4.K, 5.C.4, 5.C.7 |
| FECA files (instruction.md, Dockerfile, data JSON) | style reference | the "name the standard, describe the data, state facts" instruction style |

## Getting a document yourself first
- Try `curl -sSL` through the proxy. If the proxy refuses a host (403 CONNECT, or the web-fetch agent reports
  ENOTFOUND), propose adding the exact host to the environment with `update_environment` (call `get_environment`
  first, say in one sentence why). `www.aapm.org` was added this way; `aapm.onlinelibrary.wiley.com` and `dx.doi.org`
  stay blocked, so Wiley PDFs must come from the person.
- AAPM: `https://www.aapm.org/pubs/reports/RPT_<n>.pdf` and `RPT_<n>_Addendum.pdf`; some redirect to Wiley.
- Never give a link from memory: verify by search or by fetching before sending.

## Extracting
`pdftotext file.pdf raw.txt` and `pdftotext -layout file.pdf lay.txt`; for a table page use
`pdftotext -f N -l N -layout`. Transcribe tables into CSV by hand or parse the layout text, then spot-check every row
against the PDF and against any worked example in the report (build goldens from the worked examples).
