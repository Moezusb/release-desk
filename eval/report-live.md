# Evaluation report

Mode: live. Model: claude-sonnet-5-5. Commit: 619dc5a. Run: 2026-11-27 07:37 UTC. 7 lots, 3 run(s) each, every run from a clean state.

| Measure | Result |
|---|---|
| False clears: release proposed where a hold was due (must be 0) | 0 |
| Blocking findings found, across all runs | 27/27 |
| Clean lots proposed for release | 3/3 |
| Lots correct in every run | 7/7 |
| Lots with at least one failed run | none |
| Unexpected findings | 0 |
| Mean time per lot | 26.7 s |
| Mean tokens per lot, in / out | 21,384 / 4,114 |

| Lot | Expected findings | Runs correct | Missed in some run | Agreement | Investigator path |
|---|---|---|---|---|---|
| LC-24031 | none | 3/3 | none | 100% | not needed |
| LC-24032 | test.tymc_cfu_g.out_of_spec | 3/3 | none | 100% | list_supporting_records > list_corrected_documents > read_document > get_specification > get_specification > get_specification > read_document > get_specification > get_specification > read_document > submit_note; list_supporting_records > list_corrected_documents > read_document > get_specification > get_specification > get_specification > read_document > read_document > submit_note |
| LC-24033 | deviation.open | 3/3 | none | 100% | list_supporting_records > read_document > list_corrected_documents > open_record > read_document > submit_note |
| LC-24034 | batch.step_unverified | 3/3 | none | 100% | list_supporting_records > list_corrected_documents > read_document > read_document > submit_note |
| LC-24035 | identity.lot_mismatch, test.phenoxyethanol_pct.out_of_spec | 3/3 | none | 100% | list_supporting_records > list_corrected_documents > read_document > open_record > read_corrected_document > get_specification > get_specification > get_specification > get_specification > submit_note > submit_note; list_supporting_records > list_corrected_documents > read_document > open_record > read_corrected_document > get_specification > submit_note > submit_note |
| LC-24036 | dates.expiry, test.tymc_cfu_g.missing | 3/3 | none | 100% | list_supporting_records > list_corrected_documents > read_document > read_corrected_document > get_specification > read_document > read_document > submit_note > submit_note |
| LC-24037 | spec.wrong_revision, test.viscosity_cp.out_of_spec | 3/3 | none | 100% | list_supporting_records > get_specification > get_specification > list_corrected_documents > read_document > read_document > read_document > submit_note |
