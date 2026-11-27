# Evaluation report

Mode: live. Model: claude-sonnet-5-5. Commit: eaee16e. Run: 2026-11-27 05:12 UTC. 7 lots, 5 run(s) each, every run from a clean state.

| Measure | Result |
|---|---|
| False clears: release proposed where a hold was due (must be 0) | 0 |
| Blocking findings found, across all runs | 0/45 |
| Clean lots proposed for release | 0/5 |
| Lots correct in every run | 0/7 |
| Lots with at least one failed run | LC-24031, LC-24032, LC-24033, LC-24034, LC-24035, LC-24036, LC-24037 |
| Unexpected findings | 35 |
| Mean time per lot | 0.0 s |

| Lot | Expected findings | Runs correct | Missed in some run | Agreement | Investigator path |
|---|---|---|---|---|---|
| LC-24031 | none | 0/5 | none | 100% | not needed |
| LC-24032 | test.tymc_cfu_g.out_of_spec | 0/5 | test.tymc_cfu_g.out_of_spec | 100% | not needed |
| LC-24033 | deviation.open | 0/5 | deviation.open | 100% | not needed |
| LC-24034 | batch.step_unverified | 0/5 | batch.step_unverified | 100% | not needed |
| LC-24035 | identity.lot_mismatch, test.phenoxyethanol_pct.out_of_spec | 0/5 | identity.lot_mismatch, test.phenoxyethanol_pct.out_of_spec | 100% | not needed |
| LC-24036 | dates.expiry, test.tymc_cfu_g.missing | 0/5 | dates.expiry, test.tymc_cfu_g.missing | 100% | not needed |
| LC-24037 | spec.wrong_revision, test.viscosity_cp.out_of_spec | 0/5 | spec.wrong_revision, test.viscosity_cp.out_of_spec | 100% | not needed |
