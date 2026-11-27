# Release Desk: product spec

This is the page that came before the code. It records what the desk is for, what it may do on its own, and how we would know it was ready to be trusted with real lots.

## The person

A quality reviewer who decides whether a manufactured lot may be released for sale. They know the specification better than any tool will. They are short of time, not of judgment, and they will be held accountable for every signature.

## The job

For each lot: read the certificate of analysis, the batch record and the deviation log; find anything that does not meet the specification or good manufacturing practice; decide release, hold or reject; record why.

Most lots are clean. The reviewer's time goes into proving that, so less of it is left for the lots that are not.

## What the desk does, and what it may not

| Action | Who does it | Needs a person first? |
|---|---|---|
| Read the documents and extract values with citations | Model | No |
| Check that each citation is real and about the right attribute | Code | No |
| Choose the specification revision in force on the date of manufacture | Code | No |
| Compare values with the specification | Code | No |
| Read records, revisions and corrected documents to explain a finding | Agent | No (it can only read) |
| Propose release or hold | Model | No (it is only a proposal) |
| Place a lot on hold | Tool | No. Holding is safe and reversible |
| Release a lot | Tool | **Yes, a named reviewer, every time** |
| Confirm a hold or reject a lot | Person | It is the person |
| Release over a hold | Nobody | Not offered. A hold is lifted by better evidence and a reassessment |
| Apply a corrected document | Person | It is the person; earlier decisions are voided and kept |

## What counts as an exception

| Severity | Meaning | Examples | Blocks release? |
|---|---|---|---|
| Critical | Product safety or identity in doubt | Microbiology out of limit or missing; lot number or product code disagree between documents | Yes |
| Major | A requirement of the specification or of good practice not met | Assay out of range; unsigned step; open deviation; wrong expiry; uncertified result | Yes |
| Minor | Worth knowing, not worth holding for | None in this version | No |

Rules that apply to everything:

- A value the documents do not support is treated as missing.
- A missing value is a failure of the test it belongs to, at that test's severity.
- Limits are inclusive: a pH of exactly 6.0 meets "5.0 to 6.0".
- A result reported as "<10" meets "not more than 10" but can never prove a minimum.
- A deviation is open unless its status says closed.
- The person who performs a step may not be the one who verifies it.
- A lot is judged by the specification revision in force on its date of manufacture, whatever revision its certificate names.
- A decision is valid only for the documents it was made on. When a document changes, the lot is reassessed.
- An approval is valid only for the assessment the reviewer saw. If the findings, proposal or second reading change, the approval no longer authorises a release.

## When it would be ready for real lots

A pilot would run the desk alongside the current manual review, on lots whose outcome is already known, before anyone relied on it.

| Gate | Bar |
|---|---|
| Unsafe release proposals on the golden set | Zero, with no exceptions |
| Exception recall on the golden set | Every critical exception found; at least 95% of major ones |
| False alarms | Low enough that reviewers still read them. Agreed with the reviewers, then measured |
| Evidence | Every finding links to the exact line it came from |
| Reviewer trust | Reviewers in the pilot would choose to keep using it |

The golden set should come from real history: lots that were released, held and rejected, including the awkward ones.

## What we would measure in use

| Kind | Measure |
|---|---|
| Guardrail | Issues found after release that the desk did not raise; audit findings |
| Benefit | Reviewer time per lot; time from documents complete to decision; review backlog |
| Quality | False alarms per lot; claims refused by the evidence check |
| Trust | How often reviewers refuse a proposed release or reject a held lot, and their reasons |

Baseline the manual process for a few weeks first. Without a before, there is no after.

## Data mappings

Before anything is built on a client's systems, a vendor's mapping is checked against the source dictionary, the canonical fields and the documents. Each check ends as validated, failed, or needs business confirmation. A mapping with any failure is not acceptable; one with open confirmations is acceptable once a named owner confirms them.

## Accepting the delivery

The desk's output is accepted by a separate scorer (`acceptance_lab/`) that does not import the desk. It reads labels written by hand before any run, a result bundle, and the source documents, and applies five gates, all required:

| Gate | Rule |
|---|---|
| Coverage and identity | Every labelled lot appears once per repeat, with a unique run ID, on the original documents, without errors |
| No unsafe clearance | No release is proposed for a lot labelled hold |
| Exception detection with evidence | Every labelled exception is present at the right severity, citing a line about the right attribute |
| Useful completion | The clean lot is proposed for release. Holding everything is not a pass |
| Reviewer burden | No unexpected findings |

Passing every gate on a scripted model earns "further evidence required", not a pilot. Only a live run can earn "ready for business validation": the furthest synthetic fixtures can take it. A pilot needs real labels, thresholds and lots from the people who own the process.

Two planted failures run alongside every build to show the scorer refuses what it should. Business UAT tasks test whether a reviewer can use the desk correctly; they stay "not yet run" until a real reviewer runs them.

## Not in this version

Reading scanned or handwritten documents; more than one product; electronic signatures with real identity; integration with a quality management system; trending across lots.
