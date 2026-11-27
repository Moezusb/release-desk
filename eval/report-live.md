# Evaluation report

Mode: live. Model: claude-sonnet-5-5. Commit: 5d0b73e. Run: 2026-11-27 06:49 UTC. 7 lots, 3 run(s) each, every run from a clean state.

| Measure | Result |
|---|---|
| False clears: release proposed where a hold was due (must be 0) | 0 |
| Blocking findings found, across all runs | 27/27 |
| Clean lots proposed for release | 0/3 |
| Lots correct in every run | 0/7 |
| Lots with at least one failed run | LC-24031, LC-24032, LC-24033, LC-24034, LC-24035, LC-24036, LC-24037 |
| Unexpected findings | 21 |
| Mean time per lot | 35.2 s |
| Mean tokens per lot, in / out | 29,244 / 5,189 |

| Lot | Expected findings | Runs correct | Missed in some run | Agreement | Investigator path |
|---|---|---|---|---|---|
| LC-24031 | none | 0/3 | none | 100% | read_document > list_supporting_records > list_corrected_documents > get_specification > get_specification > read_document > get_specification > get_specification > submit_note; read_document > list_supporting_records > list_corrected_documents > get_specification > read_document > get_specification > get_specification > read_document > submit_note; read_document > list_supporting_records > list_corrected_documents > get_specification > read_document > read_document > get_specification > get_specification > submit_note |
| LC-24032 | test.tymc_cfu_g.out_of_spec | 0/3 | none | 100% | list_supporting_records > list_corrected_documents > read_document > read_document > get_specification > get_specification > get_specification > read_document > submit_note > submit_note; list_supporting_records > list_corrected_documents > read_document > read_document > read_document > get_specification > get_specification > get_specification > submit_note > submit_note |
| LC-24033 | deviation.open | 0/3 | none | 100% | read_document > read_document > list_supporting_records > list_corrected_documents > open_record > get_specification > read_document > get_specification > get_specification > submit_note > submit_note; read_document > read_document > list_supporting_records > list_corrected_documents > open_record > read_document > get_specification > get_specification > get_specification > get_specification > get_specification > submit_note > submit_note |
| LC-24034 | batch.step_unverified | 0/3 | none | 100% | read_document > list_supporting_records > list_corrected_documents > read_document > read_document > get_specification > get_specification > get_specification > get_specification > get_specification > submit_note > submit_note; read_document > list_supporting_records > list_corrected_documents > read_document > read_document > get_specification > get_specification > get_specification > submit_note > submit_note |
| LC-24035 | identity.lot_mismatch, test.phenoxyethanol_pct.out_of_spec | 0/3 | none | 100% | list_supporting_records > list_corrected_documents > read_document > read_document > read_document > open_record > read_corrected_document > get_specification > get_specification > get_specification > submit_note > submit_note > submit_note; read_document > read_document > read_document > list_supporting_records > list_corrected_documents > open_record > read_corrected_document > get_specification > get_specification > get_specification > submit_note > submit_note > submit_note; read_document > read_document > read_document > list_supporting_records > list_corrected_documents > open_record > read_corrected_document > get_specification > submit_note > submit_note > submit_note |
| LC-24036 | dates.expiry, test.tymc_cfu_g.missing | 0/3 | none | 100% | list_supporting_records > list_corrected_documents > read_document > read_document > read_corrected_document > get_specification > read_document > get_specification > get_specification > submit_note > submit_note; list_supporting_records > list_corrected_documents > read_document > read_document > read_document > read_corrected_document > get_specification > get_specification > get_specification > get_specification > submit_note > submit_note; read_document > read_document > read_document > list_supporting_records > list_corrected_documents > read_corrected_document > get_specification > get_specification > get_specification > get_specification > get_specification > submit_note > submit_note |
| LC-24037 | spec.wrong_revision, test.viscosity_cp.out_of_spec | 0/3 | none | 100% | list_supporting_records > list_corrected_documents > get_specification > get_specification > read_document > read_document > get_specification > get_specification > read_document > submit_note > submit_note |
