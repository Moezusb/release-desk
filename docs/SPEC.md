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
| Check that each citation is real | Code | No |
| Compare values with the specification | Code | No |
| Propose release or hold | Model | No (it is only a proposal) |
| Place a lot on hold | Tool | No. Holding is safe and reversible |
| Release a lot | Tool | **Yes, a named reviewer, every time** |
| Reject a lot, or release over a hold | Person | It is the person |

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
| Trust | How often reviewers overrule the desk, and their reasons |

Baseline the manual process for a few weeks first. Without a before, there is no after.

## Not in this version

Reading scanned or handwritten documents; more than one product; electronic signatures with real identity; integration with a quality management system; trending across lots.
