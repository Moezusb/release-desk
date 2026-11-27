# Release Desk

**The model reads the lot. The rules check it. You decide.**

Every lot that leaves a factory carries a promise it cannot speak for itself: that what is inside the tube is what the label says, made the way it was meant to be made. Somewhere a quality reviewer keeps that promise by reading. Certificates, batch records, deviation logs, line by line, lot after lot, until the reading becomes the job and the judgment gets the time that is left over.

Release Desk is a working prototype of a better division of labour. A model does the first read. Plain code checks what it found against the specification that governed the lot. An agent goes looking for the evidence behind each problem. A named person makes the release decision, with every finding one click from the line it came from. The machine is allowed to be fast. It is not allowed to be the one who says yes.

It is built on [Continuum](https://github.com/shyftlabs/continuum), an open-source agent framework by ShyftLabs. All documents, people, products, systems and companies in this repository are invented.

**[Open the live page](https://moezusb.github.io/release-desk/)**: a recorded run of the pipeline, with working decisions, corrections and an acceptance lab. No install; anything you decide stays in your browser.

![The reviewer's screen](docs/screenshot.png)

---

## What happens to a lot

| Step | Who | What |
|---|---|---|
| **Read** | Model | Copies values out of the certificate, batch record and deviation log. Every value must cite its line and quote it. |
| **Check the evidence** | Code | Looks at the cited line. A value that is not there, or is there but belongs to a different test, is refused and treated as missing. Refused claims stay on the record. |
| **Apply the rules** | Code | Picks the specification revision in force on the date of manufacture, then checks results, identity, dates, signatures and deviations. Every rule fails closed. |
| **Investigate** | Agent | For each blocking finding, chooses what to read next: a deviation record, another revision, a corrected document, a range of lines. It writes a note with a next step. It cannot change anything. |
| **Propose** | Model | Holds the lot at once, or proposes release. A second reader checks the proposal against the findings. |
| **Decide** | You | Approve or refuse a proposed release; confirm a hold or reject the lot. Signed, with a reason for every refusal or rejection. There is no button for releasing over a hold: the way out of a hold is better evidence and a reassessment. |

If a corrected document arrives after a decision, the decision is kept but voided: the lot must be reassessed, and the release tool refuses anything decided on old evidence.

## Why it is built this way

**The model reads; it does not judge.** Whether 0.78 is less than 0.80 is not a matter of opinion, and nothing is gained by asking a language model for one. The rules live in `release_desk/rules.py`, where they can be read, tested and argued with.

**A citation is where checking starts, not where it ends.** A value can sit on a real line and still be wrong: the right number from the wrong row, or a result judged against a revision that had been retired. The evidence check confirms the line is about the attribute claimed, and the rules choose the specification by date, not by what the certificate says.

**Workflow where the path is known; an agent where it is not.** Reading, checking and proposing follow a fixed path, because the steps never change. Investigating does not: an open deviation needs its record, a wrong revision needs both revisions, a missing result needs to know whether a correction exists. That is where a model choosing its next tool earns its keep, and it is the only place it is allowed to.

**Saying no is cheap; saying yes needs a person.** A hold costs a little time and can be lifted by anyone who looks. A release cannot be called back from a customer's bathroom shelf. The hold tool runs freely; the release tool waits behind Continuum's approval gate.

**Silence is a no.** If nobody answers in time, or the approval step fails, the call is denied and the lot stays on hold. The desk never mistakes a quiet room for consent.

**Even a yes is checked.** An approval is bound to a fingerprint of the assessment the reviewer saw: the documents, the findings, the proposal and the second reading. After approval, the release tool refuses if a blocking finding is open, if the documents changed, if the assessment no longer matches that fingerprint, or if the call it is about to make differs from the proposal that was approved. An approval is a judgment about a proposal, not a licence to skip the rules. Optimism is a fine quality in a person and a poor one in a release process.

## The acceptance lab

A desk that grades its own homework proves little. `acceptance_lab/` is a separate package that scores what the desk delivers, and the page gives it its own workspace.

**Case results.** The scorer reads a result bundle, labels written by hand in advance (`acceptance_lab/labels.yaml`), and the source documents. It does not import the desk. Each run must cover its lot once, read the original documents, raise every labelled exception at the right severity, and cite a line that actually shows the value, on the row for the right attribute. Five gates follow, all of them required: coverage, no unsafe clearance, exception detection with evidence, useful completion, and reviewer burden. Every metric is shown as a fraction, so a reader can see the denominator.

**Planted failures.** Two candidates are copies of real output with one flaw put in on purpose: a critical exception removed and its hold turned into a release, and a finding that quotes a real line from the wrong row. Both are refused. They prove the scorer bites; they are not measured model failures.

| Candidate | Runs passing | Verdict |
|---|---|---|
| Executed offline workflow (scripted model, 5 runs per lot) | 35/35 | Further evidence required: the checks hold, but a scripted model proves nothing about a real one |
| Missed critical exception (planted) | 6/7 | Not ready for a pilot: fails no unsafe clearance and detection |
| Real quote, wrong attribute (planted) | 6/7 | Not ready for a pilot: fails detection |

**Mapping checks.** Before an implementation vendor builds on a client's systems, someone has to check that the data means what the mapping says. The checker compares a proposed mapping with three things the vendor did not write: the source systems' own data dictionary, the canonical fields the rules depend on, and the documents themselves, lot by lot. Each check ends in one of three states: validated, failed, or needs business confirmation, for questions only the client's Quality team can answer.

The synthetic source extracts in `data/mapping/sources/` carry the quirks real systems have: lot numbers written two ways, a percentage stored as a fraction, a superseded result kept beside its retest, an undocumented date convention, a status whose meaning for release nobody has written down. Six scenarios are included:

| Scenario | Verdict |
|---|---|
| First delivery | Not acceptable. Yeast and mould mapped to the aerobic count, lots lost in the join, duplicate results, test date used as manufacture date, month-first dates in day-first data, preservative 100 times too small, every lot judged by the latest revision |
| Revised delivery | Acceptable once one question is confirmed: whether "Closed - effectiveness check pending" counts as closed for release |
| Same unit, wrong meaning | Caught: both fields are CFU/g; they count different organisms |
| Fraction treated as percent | Caught: the conversion is missing |
| Ambiguous date convention | Caught: the declared convention does not fit the data |
| Equal row count hides a lost lot | Caught: seven packets for seven batches, but one batch twice and one not at all |

Each authored challenge declares the flaw it carries, and the checker reports whether it caught it.

**Business UAT and value.** Labels test the output; they do not test whether a reviewer can use it. Six UAT tasks (find the evidence, recognise missing information, spot the wrong revision, know what an approval authorises, resume after a correction, name the next owner) are written down and marked not yet run, because nobody from a real Quality team has run them. The value worksheet is an illustrative calculator with its formula on the page; machine time and tokens per lot are filled in only from a live run.

## Evaluation

Correctness comes first and consistency second. Five runs that agree on a wrong answer are worse than one run that is right, so every run is scored on its own against answers written before any run (`data/golden.yaml`), each from a clean state.

```bash
release-desk eval --repeat 5
```

| Measure | Why it matters |
|---|---|
| False clears | Release proposed where a hold was due. The one number that must be zero. |
| Blocking findings found | Recall on the problems planted in the lots, across every run. |
| Clean lots proposed for release | A desk that holds everything would ace the first two measures. |
| Lots correct in every run | The average hides the lot that fails one time in three. |
| Agreement between runs | Secondary. Useful only once the runs are right. |
| Time and tokens per lot | Measured, so the cost of the workflow is a number, not a guess. |

Results go to `eval/report-*.md` and a result bundle, `eval/results-*.json`, which the acceptance lab scores independently. Offline runs use a scripted model, so they prove the checks and controls, not a model. The live run in GitHub Actions is the one to read, and it has not been run yet.

## The lots

Seven lots of one fictional product, each written to test one kind of judgment.

| Lot | What is wrong | What a careful reviewer does |
|---|---|---|
| LC-24031 | Nothing | Release |
| LC-24032 | Yeast and mould count of 40 against a limit of 10 | Hold |
| LC-24033 | Results pass, but a deviation is still open; its record is on file | Hold |
| LC-24034 | Filling step has no second signature; pH sits exactly on its limit, which passes | Hold |
| LC-24035 | Transposed lot number on the certificate and a low preservative assay; a corrected certificate fixes only the first | Hold |
| LC-24036 | Yeast and mould result pending and expiry wrong; a corrected certificate fixes both | Hold, then release after reassessment |
| LC-24037 | Tested against retired revision 03; viscosity passes 03 and fails 04, which governs | Hold |

## Try it

Python 3.13. No Docker, no database. Without credentials it runs offline with the scripted model.

```bash
git clone https://github.com/Moezusb/release-desk.git && cd release-desk
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

release-desk serve --offline         # http://127.0.0.1:8930
release-desk review LC-24037         # one lot in the terminal
release-desk eval --repeat 5         # the evaluation
python -m acceptance_lab evaluate eval/results-offline.json
python -m acceptance_lab check-mapping
python -m acceptance_lab build       # the lab's page data, docs/acceptance.json
pytest                               # 28 offline tests, including the live path against a simulated API
```

**Live runs** use a real model through Continuum's Anthropic provider. Locally, set `ANTHROPIC_API_KEY` in `.env`. In GitHub Actions, the **Live evaluation** workflow (Actions, then Run workflow) accepts either an `ANTHROPIC_API_KEY` repository secret or workload identity federation, where GitHub's short-lived identity token is exchanged for a short-lived Anthropic token and no key is stored at all. It runs the evaluation, re-records the public page from the live run, rebuilds the acceptance results, and commits all three.

## Where Continuum does the work

| Need | Continuum feature | File |
|---|---|---|
| Typed extraction the code can trust | `BaseAgent(output_schema=...)` | `release_desk/agents.py` |
| A model that chooses its own next read | Agent loop over in-process tools (`MCPServerFunction`, `ToolExecutor`) | `release_desk/investigate.py` |
| A person before the release tool runs | `AgentConfig(tool_approval=..., approval_handler=..., approval_timeout=...)`, fail-closed | `release_desk/agents.py`, `pipeline.py` |
| One switch between live and scripted models | Provider registry (`register_provider`) | `release_desk/offline.py` |

## Known limits

- **No OCR.** The documents are text. Real batch records are scanned, handwritten and stamped, and reading them well is the hardest part of the problem. This prototype starts after that step.
- **No business validation.** The labels, gates and UAT tasks are a reasoned starting point. Real thresholds, criticality and pilot exit criteria belong to the people who own the process.
- **Small, synthetic, one product.** Seven lots and one specification with two revisions make a smoke test, not a validation. A pilot would use a frozen set built from real history.
- **The scripted investigator is a script.** Offline, it branches on what its tools return, but its paths were written by hand. The live model chooses for itself, and its paths are recorded in the evaluation.
- **Names are typed, not authenticated.** A real system needs proper electronic signatures and access control under whatever regulation applies.
- **Approvals wait in memory.** A server restart while a release is waiting loses the approval and leaves the lot on hold: the safe direction to fail, but still a failure.

## Layout

```
data/spec/          specification revisions with dates in force
data/lots/          documents per lot, plus corrections/ and records/ where they exist
data/mapping/       source extracts, their dictionary, canonical fields, vendor mappings
data/golden.yaml    the answers a careful reviewer would give
release_desk/       reader, evidence check, rules, investigator, proposer, evaluation
acceptance_lab/     independent labels, scorer, planted failures, mapping checks, UAT tasks
web/                the reviewer's screen (FastAPI and one HTML file)
docs/               the page for GitHub Pages (index, replay.json, acceptance.json) and the product spec
eval/               evaluation reports and result bundles
scripts/            generators for the synthetic lots and source extracts
```

The product decisions behind all this are in [docs/SPEC.md](docs/SPEC.md).

---

A release decision is small on any one day: a name, a date, a lot number. Over years it becomes the reputation of everything a company makes. The desk is here to give the person who signs more time to look, and better things to look at. The signature stays theirs.

Built by Mohamed Bah. Claude collaborated on the code; an earlier prototype made with ChatGPT shaped the interface and the idea of a separate acceptance lab. MIT licensed. Continuum is Apache 2.0, by ShyftLabs.
