"""Record a run of every lot into docs/replay.json, for the static demo page.

A scripted reviewer answers some lots and leaves others waiting, so the replay
shows each state the desk can be in, including a lot whose certificate is
corrected after a decision and then reassessed. The mapping reports are
recorded too. Decisions made on the static page stay in the visitor's browser.

Run offline (scripted model) or live: the page says which it was.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from continuum.agent.approval import ToolApprovalDecision

from .config import ROOT, Settings
from .documents import list_lots, load_lot
from .mapping import check_all
from .pipeline import HUMAN_ACTIONS, apply_correction, decide, run_review
from .store import Store, metrics
from .views import lot_context

REVIEWER = "Demo reviewer"
# What the scripted reviewer does on the first review of each lot. Lots not listed are left waiting.
FIRST = {
    "LC-24031": ("approve_release", ""),
    "LC-24032": ("reject", "Yeast and mould count four times the limit. OOS investigation opened; lot to be destroyed."),
    "LC-24033": ("confirm_hold", ""),
    "LC-24036": ("confirm_hold", ""),
}
# Lots whose correction is applied and reassessed in the recording, and what the reviewer does after.
CORRECT_AND_REASSESS = {"LC-24036": ("certificate", "v2", "approve_release")}
# Lots where the page can show "what happens if you apply the correction", recorded but not applied.
PREVIEW_CORRECTION = {"LC-24035": ("certificate", "v2")}


def _approver(script: dict):
    async def approver(review, request):
        action = script.get(review.lot_id)
        if action == "approve_release":
            review.decision = {"action": action, "reviewer": REVIEWER, "reason": "", "at": review.proposal["at"],
                               "override": False, "fingerprint": review.fingerprint}
            review.log(f"reviewer: {REVIEWER}", HUMAN_ACTIONS[action] + ".")
            return ToolApprovalDecision(approved=True, reviewer=REVIEWER)
        review.deferred = True
        return ToolApprovalDecision(approved=False, deferred=True, reason="left for a reviewer")
    return approver


def _snapshot(settings: Settings, store: Store, lot: str) -> dict:
    review = store.get(lot)
    pkg = load_lot(settings.data_dir, lot, review.versions)
    return {"review": review.to_dict(), "running": False, **lot_context(settings, lot, pkg)}


async def export(settings: Settings) -> Path:
    store = Store(Path(tempfile.mkdtemp(prefix="release-desk-replay-")))
    out: dict = {"lots": {}, "previews": {}}
    first_release = {k: v[0] for k, v in FIRST.items()}
    for lot in list_lots(settings.data_dir):
        review = await run_review(settings, store, lot, _approver(first_release))
        action, reason = FIRST.get(lot, (None, ""))
        if action and action != "approve_release":
            decide(settings, store, review, action, REVIEWER, reason)
        if lot in CORRECT_AND_REASSESS:
            section, version, then = CORRECT_AND_REASSESS[lot]
            apply_correction(settings, store, review, section, version)
            await run_review(settings, store, lot, _approver({lot: then}))
        out["lots"][lot] = _snapshot(settings, store, lot)

    # Recorded "what happens next" for a correction the visitor can choose to apply.
    for lot, (section, version) in PREVIEW_CORRECTION.items():
        side = Store(Path(tempfile.mkdtemp(prefix="release-desk-preview-")))
        await run_review(settings, side, lot, _approver({}))
        apply_correction(settings, side, side.get(lot), section, version)
        await run_review(settings, side, lot, _approver({}))
        out["previews"][lot] = _snapshot(settings, side, lot)

    reviews = [store.get(lot) for lot in out["lots"]]
    out["queue"] = [{"lot_id": r.lot_id, "stage": r.stage, "status": r.status, "running": False,
                     "proposal": (r.proposal or {}).get("decision"), "blocking": len(r.blocking),
                     "awaiting_release_approval": False, "decision": (r.decision or {}).get("action"),
                     "needs_reassessment": False} for r in reviews]
    out["metrics"] = metrics(reviews)
    out["mapping"] = check_all(settings.data_dir)
    out["meta"] = {"mode": "replay", "recorded": "offline (scripted stand-in model)" if settings.offline else f"live ({settings.model})",
                   "model": settings.model, "actions": HUMAN_ACTIONS, "replay": True}

    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    path = docs / "replay.json"
    path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    shutil.copy(ROOT / "web" / "static" / "index.html", docs / "index.html")
    print(f"Wrote {path} and docs/index.html")
    return path
