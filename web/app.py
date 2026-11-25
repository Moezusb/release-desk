"""The reviewer's desk: a small web app over the review pipeline.

    release-desk serve            # http://127.0.0.1:8930
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from release_desk import config
from release_desk.documents import list_lots, load_lot
from release_desk.pipeline import HUMAN_ACTIONS, apply_correction, decide, pending_approver, run_review
from release_desk.views import lot_context
from release_desk.store import Store, metrics

STATIC = Path(__file__).parent / "static"


class Correction(BaseModel):
    section: str
    version: str


class Decision(BaseModel):
    action: str
    reviewer: str
    reason: str = ""


def create_app(settings: config.Settings | None = None) -> FastAPI:
    settings = settings or config.load()
    store = Store(settings.runs_dir)
    tasks: dict[str, asyncio.Task] = {}
    app = FastAPI(title="Release Desk")

    def busy(lot_id: str) -> bool:
        t = tasks.get(lot_id)
        return bool(t and not t.done())

    def summary(lot_id: str) -> dict:
        r = store.get(lot_id)
        d = r.to_dict()
        return {
            "lot_id": lot_id, "stage": r.stage, "status": r.status, "running": busy(lot_id),
            "proposal": (r.proposal or {}).get("decision"), "blocking": len(r.blocking),
            "awaiting_release_approval": d["awaiting_release_approval"],
            "decision": (r.decision or {}).get("action"), "needs_reassessment": r.stage == "needs reassessment",
        }

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/meta")
    async def meta() -> dict:
        return {"mode": "offline" if settings.offline else "live", "model": settings.model,
                "approval_timeout_s": settings.approval_timeout, "actions": HUMAN_ACTIONS, "replay": False}

    @app.get("/api/lots")
    async def lots() -> dict:
        ids = list_lots(settings.data_dir)
        return {"lots": [summary(i) for i in ids], "metrics": metrics([store.get(i) for i in ids])}

    @app.get("/api/lots/{lot_id}")
    async def lot(lot_id: str) -> dict:
        if lot_id not in list_lots(settings.data_dir):
            raise HTTPException(404, "No such lot")
        review = store.get(lot_id)
        pkg = load_lot(settings.data_dir, lot_id, review.versions)
        return {"review": review.to_dict(), "running": busy(lot_id), **lot_context(settings, lot_id, pkg)}

    @app.post("/api/lots/{lot_id}/review")
    async def start(lot_id: str) -> dict:
        if lot_id not in list_lots(settings.data_dir):
            raise HTTPException(404, "No such lot")
        if busy(lot_id):
            raise HTTPException(409, "A review of this lot is already running")
        r = store.get(lot_id)
        if r.status in ("released", "rejected") and r.stage != "needs reassessment":
            raise HTTPException(409, "This lot already has a final decision")
        if r.pending and not r.pending.done():
            raise HTTPException(409, "A release proposal is waiting for a reviewer")
        tasks[lot_id] = asyncio.create_task(run_review(settings, store, lot_id, pending_approver))
        return {"started": lot_id}

    @app.post("/api/lots/{lot_id}/decision")
    async def decision(lot_id: str, body: Decision) -> dict:
        error = decide(settings, store, store.get(lot_id), body.action, body.reviewer, body.reason)
        if error:
            raise HTTPException(400, error)
        await asyncio.sleep(0.3)  # let an approved release finish before we answer
        return {"ok": True}

    @app.post("/api/lots/{lot_id}/correction")
    async def correct(lot_id: str, body: Correction) -> dict:
        error = apply_correction(settings, store, store.get(lot_id), body.section, body.version)
        if error:
            raise HTTPException(400, error)
        return {"ok": True}

    @app.get("/api/evaluation")
    async def evaluation() -> dict:
        from release_desk.config import ROOT

        for name in ("results-live.json", "results-offline.json"):
            path = ROOT / "eval" / name
            if path.exists():
                import json

                data = json.loads(path.read_text(encoding="utf-8"))
                data.pop("runs", None)
                return data
        raise HTTPException(404, "No evaluation has been run yet")

    @app.get("/api/mapping")
    async def mapping_reports() -> dict:
        from release_desk.mapping import check_all

        return check_all(settings.data_dir)

    return app


app = create_app()
