# Evaluation report

Mode: offline (scripted stand-in model). Run: 2026-11-24 15:43 UTC. Lots: 6.

| Measure | Result |
|---|---|
| Unsafe release proposals (must be 0) | 0 |
| Known exceptions found | 7/7 |
| False alarms | 0 |
| Proposals matching the expected one | 6/6 |

| Lot | Expected findings | Missed | Unexpected | Proposal (expected) | Claims refused by evidence check |
|---|---|---|---|---|---|
| LC-24031 | none | none | none | release (release) | 0 |
| LC-24032 | test.tymc_cfu_g.out_of_spec | none | none | hold (hold) | 0 |
| LC-24033 | deviation.open | none | none | hold (hold) | 0 |
| LC-24034 | batch.step_unverified | none | none | hold (hold) | 1 |
| LC-24035 | identity.lot_mismatch, test.phenoxyethanol_pct.out_of_spec | none | none | hold (hold) | 0 |
| LC-24036 | dates.expiry, test.tymc_cfu_g.missing | none | none | hold (hold) | 0 |

Offline mode replays hand-written extractions, so this run tests the evidence check, the rules and the approval path, not a model's reading. Run with ANTHROPIC_API_KEY set for that.
