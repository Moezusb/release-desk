"""Record a run of every lot into docs/replay.json, for the static demo page.

A scripted reviewer answers some lots and leaves the rest waiting, so the
replay shows each state the desk can be in. Decisions made on the static page
are applied in the visitor's browser only.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from continuum.agent.approval import ToolApprovalDecision

from .config import ROOT, Settings
from .documents import DOCUMENTS, list_lots, load_lot
from .pipeline import HUMAN_ACTIONS, decide, run_review
from .store import Store, metrics

SCRIPTED_REVIEWER = "Demo reviewer"
# What the scripted reviewer does with each lot. Lots not listed are left waiting.
SCRIPT = {
    "LC-24031": ("approve_release", ""),
    "LC-24032": ("reject", "Yeast and mould count four times the limit. Investigation opened; lot destroyed."),
    "LC-24033": ("confirm_hold", ""),
}


async def export(settings: Settings) -> Path:
    store = Store(Path(tempfile.mkdtemp(prefix="release-desk-replay-")))

    async def approver(review, request):
        action, reason = SCRIPT.get(review.lot_id, (None, ""))
        if action == "approve_release":
            review.decision = {"action": action, "reviewer": SCRIPTED_REVIEWER, "reason": "", "at": review.proposal["at"], "override": False}
            review.log(f"reviewer: {SCRIPTED_REVIEWER}", HUMAN_ACTIONS[action] + ".")
            return ToolApprovalDecision(approved=True, reviewer=SCRIPTED_REVIEWER)
        return ToolApprovalDecision(approved=False, deferred=True, reason="left for a reviewer")

    out = {"lots": {}}
    for lot in list_lots(settings.data_dir):
        review = await run_review(settings, store, lot, approver)
        action, reason = SCRIPT.get(lot, (None, ""))
        if action and action != "approve_release":
            decide(store, review, action, SCRIPTED_REVIEWER, reason)
        pkg = load_lot(settings.data_dir, lot)
        out["lots"][lot] = {
            "review": review.to_dict(),
            "running": False,
            "documents": {k: {"filename": v, "lines": pkg.docs[k]} for k, v in DOCUMENTS.items()},
        }
    reviews = [store.get(lot) for lot in out["lots"]]
    out["queue"] = [{"lot_id": r.lot_id, "stage": r.stage, "status": r.status, "running": False,
                     "proposal": (r.proposal or {}).get("decision"), "blocking": len(r.blocking),
                     "awaiting_release_approval": False, "decision": (r.decision or {}).get("action")} for r in reviews]
    out["metrics"] = metrics(reviews)
    out["meta"] = {"mode": "replay", "model": settings.model, "actions": HUMAN_ACTIONS, "replay": True}

    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    path = docs / "replay.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    shutil.copy(ROOT / "web" / "static" / "index.html", docs / "index.html")
    print(f"Wrote {path} and docs/index.html")
    return path
