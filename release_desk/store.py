"""Review state for each lot, and the append-only decision log."""

from __future__ import annotations

import asyncio
import json
import statistics
import copy
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import BLOCKING, EvidenceNote, Finding, SecondReading


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class LotReview:
    lot_id: str
    stage: str = "not started"  # reading, checking, proposing, awaiting reviewer, decided, failed
    status: str = "not reviewed"  # on hold, released, rejected
    findings: list[dict] = field(default_factory=list)
    evidence_notes: list[dict] = field(default_factory=list)
    proposal: dict | None = None  # {decision, rationale, finding_ids, at}
    second_reading: dict | None = None
    decision: dict | None = None  # {action, reviewer, reason, at, override}
    timeline: list[dict] = field(default_factory=list)
    mode: str = ""
    model: str = ""
    error: str | None = None
    deferred: bool = False  # a release proposal left for a reviewer who is not here
    versions: dict = field(default_factory=dict)  # section -> corrected version in use
    fingerprint: str = ""  # hash of the documents this review read
    governing_revision: str | None = None
    investigation: dict = field(default_factory=lambda: {"calls": [], "notes": []})
    history: list[dict] = field(default_factory=list)  # earlier reviews of this lot, never deleted
    usage: dict = field(default_factory=dict)  # seconds and tokens for this review
    approval_snapshot: str = ""  # what the reviewer was shown when asked to approve
    title: str = ""
    summary: str = ""
    pending: asyncio.Future | None = field(default=None, repr=False, compare=False)

    def superseded_reason(self) -> str | None:
        for t in reversed(self.timeline):
            if t["actor"] == "correction":
                return t["text"]
        return None

    def log(self, actor: str, text: str) -> None:
        self.timeline.append({"at": now(), "actor": actor, "text": text})

    @property
    def blocking(self) -> list[dict]:
        return [f for f in self.findings if f["severity"] in BLOCKING]

    def to_dict(self) -> dict[str, Any]:
        d = {f.name: copy.deepcopy(getattr(self, f.name)) for f in fields(self) if f.name != "pending"}
        d["awaiting_release_approval"] = bool(self.pending and not self.pending.done())
        return d


class Store:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.lots: dict[str, LotReview] = {}

    def get(self, lot_id: str) -> LotReview:
        if lot_id not in self.lots:
            path = self.runs_dir / f"{lot_id}.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                data.pop("awaiting_release_approval", None)
                review = LotReview(**data)
                if review.stage not in ("decided", "awaiting reviewer", "failed"):
                    review.stage = "interrupted"
                self.lots[lot_id] = review
            else:
                self.lots[lot_id] = LotReview(lot_id=lot_id)
        return self.lots[lot_id]

    def reset(self, lot_id: str) -> LotReview:
        """Start a new review. The previous one moves into history; nothing is lost."""
        old = self.get(lot_id) if (self.runs_dir / f"{lot_id}.json").exists() or lot_id in self.lots else None
        new = LotReview(lot_id=lot_id)
        if old is not None:
            new.versions = dict(old.versions)
            new.history = list(old.history)
            if old.proposal or old.decision:
                new.history.append({
                    "fingerprint": old.fingerprint, "versions": old.versions, "status": old.status,
                    "proposal": old.proposal, "decision": old.decision,
                    "findings": [f"{f['id']} {f['title']}" for f in old.findings],
                    "superseded_at": now(), "reason": old.superseded_reason() or "reviewed again",
                })
        self.lots[lot_id] = new
        return new

    def save(self, review: LotReview) -> None:
        path = self.runs_dir / f"{review.lot_id}.json"
        path.write_text(json.dumps(review.to_dict(), indent=2), encoding="utf-8")

    def record_decision(self, review: LotReview, entry: dict) -> None:
        with (self.runs_dir / "decisions.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"lot_id": review.lot_id, **entry}) + "\n")


def set_findings(review: LotReview, findings: list[Finding], notes: list[EvidenceNote]) -> None:
    review.findings = [f.model_dump() for f in findings]
    review.evidence_notes = [n.model_dump() for n in notes]


def set_reading(review: LotReview, reading: SecondReading) -> None:
    review.second_reading = reading.model_dump()


AGREE = {("release", "approve_release"), ("hold", "confirm_hold"), ("hold", "reject")}


def metrics(reviews: list[LotReview]) -> dict[str, Any]:
    reviewed = [r for r in reviews if r.proposal]
    decided = [r for r in reviewed if r.decision]
    agreed = [r for r in decided if (r.proposal["decision"], r.decision["action"]) in AGREE]
    minutes = []
    for r in decided:
        try:
            a = datetime.fromisoformat(r.proposal["at"])
            b = datetime.fromisoformat(r.decision["at"])
            minutes.append((b - a).total_seconds() / 60)
        except (KeyError, ValueError):
            pass
    return {
        "lots_reviewed": len(reviewed),
        "blocking_findings": sum(len(r.blocking) for r in reviewed),
        "evidence_rejected": sum(len(r.evidence_notes) for r in reviewed),
        "decided": len(decided),
        "agreed": len(agreed),
        "overridden": len(decided) - len(agreed),
        "median_minutes_to_decision": round(statistics.median(minutes), 1) if minutes else None,
    }
