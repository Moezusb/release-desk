"""One review, from documents to a person's decision.

    read -> check the evidence -> apply the rules -> investigate -> propose -> a person decides

The model reads, investigates and proposes. Code checks. A person decides.
Nothing in this module lets a lot be released without a named reviewer saying
yes, and no decision outlives the evidence it was made on.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from continuum.agent.approval import ToolApprovalDecision, ToolApprovalRequest

from . import agents, meter
from .config import Settings
from .documents import DOCUMENTS, corrections, load_lot, load_spec, load_specs
from .evidence import verify
from .investigate import investigate
from .rules import applicable_spec, evaluate
from .schemas import Finding
from .store import LotReview, Store, now, set_findings, set_reading

Approver = Callable[[LotReview, ToolApprovalRequest], Awaitable[ToolApprovalDecision]]

HUMAN_ACTIONS = {
    "approve_release": "Approved the proposed release",
    "deny_release": "Refused the proposed release; lot held",
    "confirm_hold": "Confirmed the hold",
    "reject": "Rejected the lot",
    "release_over_hold": "Released the lot over the desk's hold",
}
NEEDS_REASON = {"deny_release", "reject", "release_over_hold"}
BUSY = {"reading", "checking", "investigating", "proposing"}


async def pending_approver(review: LotReview, request: ToolApprovalRequest) -> ToolApprovalDecision:
    """Wait for a person to answer through ``decide``. Used by the web app."""
    review.pending = asyncio.get_running_loop().create_future()
    return await review.pending


async def deferring_approver(review: LotReview, request: ToolApprovalRequest) -> ToolApprovalDecision:
    """Answer that nobody is here yet. Used by the evaluation, which must never release."""
    review.deferred = True
    review.log("desk", "No reviewer in this run. The release proposal is left waiting; the lot stays on hold.")
    return ToolApprovalDecision(approved=False, deferred=True, reason="evaluation run: nobody to approve")


def current_fingerprint(settings: Settings, review: LotReview) -> str:
    return load_lot(settings.data_dir, review.lot_id, review.versions).fingerprint()


def evidence_changed(settings: Settings, review: LotReview) -> bool:
    return bool(review.fingerprint) and current_fingerprint(settings, review) != review.fingerprint


async def run_review(settings: Settings, store: Store, lot_id: str, approver: Approver = pending_approver) -> LotReview:
    meter.install()
    review = store.reset(lot_id)
    review.mode = "offline (scripted stand-in model)" if settings.offline else "live"
    review.model = settings.model

    def stage(name: str) -> None:
        review.stage = name
        store.save(review)

    with meter.measure() as usage:
        try:
            pkg = load_lot(settings.data_dir, lot_id, review.versions)
            specs = load_specs(settings.data_dir)
            review.fingerprint = pkg.fingerprint()

            stage("reading")
            review.log("desk", f"Reading the certificate, batch record and deviation log ({pkg.version_label()}).")
            try:
                extraction = await agents.extract(settings, pkg, load_spec(settings.data_dir))
            except Exception as exc:  # fail closed: an unread lot is a held lot
                review.log("desk", f"Reading failed: {exc}")
                set_findings(review, [Finding(id="F1", rule="extraction.failed", severity="critical",
                                              title="The documents could not be read",
                                              expected="a complete extraction", observed=str(exc)[:200])], [])
            else:
                stage("checking")
                governing = applicable_spec(specs, extraction)
                review.governing_revision = governing["revision"] if governing else None
                extraction, notes = verify(pkg, extraction, governing or specs[-1])
                for n in notes:
                    review.log("evidence check", f"Refused {n.field} ('{n.claimed_value}', line {n.cited_line}): {n.reason}.")
                findings = evaluate(pkg, extraction, specs)
                set_findings(review, findings, notes)
                review.log("rules", f"Checked against rev {review.governing_revision or '?'}: "
                                    f"{len(findings)} finding(s), {len(review.blocking)} blocking.")

            if review.blocking:
                stage("investigating")
                await _investigate(settings, review)

            stage("proposing")
            await _propose(settings, store, review, approver)
        except Exception as exc:
            review.error = str(exc)
            review.status = "on hold"
            review.log("desk", f"Review stopped by an error; the lot stays on hold. {exc}")
            review.usage = dict(usage)
            stage("failed")
            return review
    review.usage = dict(usage)
    store.save(review)
    return review


async def _investigate(settings: Settings, review: LotReview) -> None:
    review.log("investigator", "Looking for evidence that explains the blocking findings.")

    def on_call(name: str, args: dict, result: str) -> None:
        review.investigation["calls"].append({"at": now(), "tool": name, "args": args, "result": result[:600]})
        if name != "submit_note":
            shown = ", ".join(str(v) for v in args.values())
            review.log("investigator", f"{name.replace('_', ' ')}({shown})")

    try:
        notes = await investigate(settings, review.lot_id, review.versions, review.findings, on_call)
    except Exception as exc:  # advice only: a failed investigation never blocks or clears anything
        review.log("investigator", f"Investigation failed and was skipped: {exc}")
        return
    known = {f["id"] for f in review.findings}
    for n in notes:
        n.finding_ids = [i for i in n.finding_ids if i in known]  # a note cannot invent findings
        review.investigation["notes"].append(n.model_dump())
        review.log("investigator", f"Note on {', '.join(n.finding_ids) or 'no finding'}: {n.next_step.replace('_', ' ')}.")


async def _propose(settings: Settings, store: Store, review: LotReview, approver: Approver) -> None:
    async def place_on_hold(lot_id: str, rationale: str, finding_ids: list[str]) -> str:
        if lot_id != review.lot_id:
            return f"REFUSED: this review is for {review.lot_id}, not {lot_id}."
        review.proposal = {"decision": "hold", "rationale": rationale, "finding_ids": finding_ids, "at": now()}
        review.status = "on hold"
        review.log("proposer", f"Placed on hold. {rationale}")
        return "Lot placed on hold pending a reviewer's disposition."

    async def release_lot(lot_id: str, rationale: str, finding_ids: list[str]) -> str:
        # Runs only after a person approved. It still checks, because an approval
        # is a judgment about a proposal, not a licence to skip rules.
        if lot_id != review.lot_id:
            return f"REFUSED: this review is for {review.lot_id}, not {lot_id}."
        if review.blocking or evidence_changed(settings, review):
            review.status = "on hold"
            why = "blocking findings are open" if review.blocking else "the documents changed after review"
            if review.decision:
                review.decision["outcome"] = f"refused by the release tool: {why}"
            review.log("release tool", f"Refused: {why}. The lot stays on hold.")
            return f"REFUSED: {why}."
        review.status = "released"
        review.log("release tool", f"Released, approved by {review.decision['reviewer'] if review.decision else 'unknown'}.")
        return "Lot released."

    async def handler(request: ToolApprovalRequest) -> ToolApprovalDecision:
        args = request.arguments
        review.proposal = {"decision": "release", "rationale": args.get("rationale", ""),
                           "finding_ids": args.get("finding_ids", []), "at": now()}
        review.status = "on hold"  # held until a person says otherwise
        review.log("proposer", f"Proposed release. {args.get('rationale', '')}")
        reading = await agents.second_read(settings, review.lot_id, review.findings, review.proposal)
        set_reading(review, reading)
        review.log("second reader", "Agrees." if reading.agrees else "Disagrees: " + " ".join(reading.concerns))
        review.stage = "awaiting reviewer"
        review.log("desk", "Waiting for a named reviewer to approve or refuse the release.")
        store.save(review)
        return await approver(review, request)

    await agents.propose(settings, review.lot_id, review.findings, release_lot, place_on_hold, handler)

    if review.proposal is None:
        review.proposal = {"decision": "none", "rationale": "", "finding_ids": [], "at": now()}
        review.status = "on hold"
        review.log("desk", "The proposer made no proposal. The lot stays on hold.")
    if review.proposal["decision"] in ("hold", "none") and review.second_reading is None:
        reading = await agents.second_read(settings, review.lot_id, review.findings, review.proposal)
        set_reading(review, reading)
        review.log("second reader", "Agrees." if reading.agrees else "Disagrees: " + " ".join(reading.concerns))

    if review.status == "released" or review.decision:
        review.stage = "decided"
    else:
        if review.pending and not review.pending.done():
            review.pending.cancel()
        if review.proposal["decision"] == "release" and not review.deferred:
            wait = settings.approval_timeout
            span = f"{wait / 60:g} min" if wait >= 60 else f"{wait:g} s"
            review.log("desk", f"No approval came back within {span}: nobody answered, or the approval step failed. "
                               "Release refused; the lot stays on hold.")
        review.pending = None
        review.stage = "awaiting reviewer"


def apply_correction(settings: Settings, store: Store, review: LotReview, section: str, version: str) -> str | None:
    """A person applies a corrected document. Earlier decisions stay on record but no longer authorise anything."""
    if (section, version) not in corrections(settings.data_dir, review.lot_id):
        return "No such corrected document on file."
    if review.stage in BUSY or (review.pending and not review.pending.done()):
        return "Finish or refuse the current proposal first."
    if review.versions.get(section) == version:
        return "That version is already in use."
    review.versions[section] = version
    review.log("correction", f"{DOCUMENTS[section]} replaced by corrected version {version}. "
                             "Earlier findings and decisions were made on different evidence and need reassessment.")
    review.stage = "needs reassessment"
    store.save(review)
    return None


def decide(settings: Settings, store: Store, review: LotReview, action: str, reviewer: str, reason: str = "") -> str | None:
    """Apply a person's decision. Returns an error message, or None on success."""
    reviewer, reason = reviewer.strip(), reason.strip()
    if action not in HUMAN_ACTIONS:
        return "Unknown action."
    if not reviewer:
        return "A decision needs the reviewer's name."
    if action in NEEDS_REASON and not reason:
        return "This decision needs a reason."
    if review.stage == "needs reassessment" or evidence_changed(settings, review):
        return "The documents changed after this review. Reassess the lot before deciding."
    waiting = bool(review.pending and not review.pending.done())
    if action in ("approve_release", "deny_release") and not waiting:
        return "There is no release proposal waiting for approval."
    if action in ("confirm_hold", "reject", "release_over_hold"):
        if waiting or review.status != "on hold" or review.decision:
            return "This lot is not waiting for a hold decision."

    review.decision = {"action": action, "reviewer": reviewer, "reason": reason, "at": now(),
                       "override": action in ("deny_release", "release_over_hold"), "fingerprint": review.fingerprint}
    review.log(f"reviewer: {reviewer}", HUMAN_ACTIONS[action] + (f". Reason: {reason}" if reason else "."))
    store.record_decision(review, {**review.decision, "proposal": review.proposal["decision"] if review.proposal else None,
                                   "versions": review.versions,
                                   "blocking_findings": [f["id"] + " " + f["rule"] for f in review.blocking]})

    if action == "approve_release":
        review.pending.set_result(ToolApprovalDecision(approved=True, reviewer=reviewer))
    elif action == "deny_release":
        review.pending.set_result(ToolApprovalDecision(approved=False, reviewer=reviewer, reason=reason))
    else:
        review.status = {"confirm_hold": "on hold", "reject": "rejected", "release_over_hold": "released"}[action]
        review.stage = "decided"
    store.save(review)
    return None
