# Evaluation report

Mode: offline (scripted stand-in model). Model: scripted/offline. Commit: d12e5dd. Run: 2026-11-27 01:37 UTC. 7 lots, 5 run(s) each, every run from a clean state.

| Measure | Result |
|---|---|
| False clears: release proposed where a hold was due (must be 0) | 0 |
| Blocking findings found, across all runs | 45/45 |
| Clean lots proposed for release | 5/5 |
| Lots correct in every run | 7/7 |
| Lots with at least one failed run | none |
| Unexpected findings | 0 |
| Mean time per lot | 3.2 s |

| Lot | Expected findings | Runs correct | Missed in some run | Agreement | Investigator path |
|---|---|---|---|---|---|
| LC-24031 | none | 5/5 | none | 100% | not needed |
| LC-24032 | test.tymc_cfu_g.out_of_spec | 5/5 | none | 100% | list_supporting_records > submit_note |
| LC-24033 | deviation.open | 5/5 | none | 100% | list_supporting_records > open_record > submit_note |
| LC-24034 | batch.step_unverified | 5/5 | none | 100% | read_document > submit_note |
| LC-24035 | identity.lot_mismatch, test.phenoxyethanol_pct.out_of_spec | 5/5 | none | 100% | list_corrected_documents > read_corrected_document > submit_note > list_supporting_records > open_record > submit_note |
| LC-24036 | dates.expiry, test.tymc_cfu_g.missing | 5/5 | none | 100% | list_corrected_documents > read_corrected_document > submit_note |
| LC-24037 | spec.wrong_revision, test.viscosity_cp.out_of_spec | 5/5 | none | 100% | get_specification > get_specification > submit_note |

Offline mode replays hand-written extractions and a scripted investigator, so this run tests the evidence check, the rules and the approval path, not a model. Agreement is 100% by construction.
