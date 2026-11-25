# Evaluation report

Mode: offline (scripted stand-in model). Model: scripted/offline. Commit: f7656cf. Run: 2026-11-25 05:39 UTC. 7 lots, 2 run(s) each, every run from a clean state.

| Measure | Result |
|---|---|
| False clears: release proposed where a hold was due (must be 0) | 0 |
| Blocking findings found, across all runs | 18/18 |
| Clean lots proposed for release | 2/2 |
| Lots correct in every run | 7/7 |
| Lots with at least one failed run | none |
| Unexpected findings | 0 |
| Mean time per lot | 3.1 s |

| Lot | Expected findings | Runs correct | Missed in some run | Agreement | Investigator path |
|---|---|---|---|---|---|
| LC-24031 | none | 2/2 | none | 100% | not needed |
| LC-24032 | test.tymc_cfu_g.out_of_spec | 2/2 | none | 100% | list_supporting_records > submit_note |
| LC-24033 | deviation.open | 2/2 | none | 100% | list_supporting_records > open_record > submit_note |
| LC-24034 | batch.step_unverified | 2/2 | none | 100% | read_document > submit_note |
| LC-24035 | identity.lot_mismatch, test.phenoxyethanol_pct.out_of_spec | 2/2 | none | 100% | list_corrected_documents > read_corrected_document > submit_note > list_supporting_records > open_record > submit_note |
| LC-24036 | dates.expiry, test.tymc_cfu_g.missing | 2/2 | none | 100% | list_corrected_documents > read_corrected_document > submit_note |
| LC-24037 | spec.wrong_revision, test.viscosity_cp.out_of_spec | 2/2 | none | 100% | get_specification > get_specification > submit_note |

Offline mode replays hand-written extractions and a scripted investigator, so this run tests the evidence check, the rules and the approval path, not a model. Agreement is 100% by construction.
