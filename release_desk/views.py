"""What the reviewer's screen needs to show for a lot, shared by the web app and the replay."""

from __future__ import annotations

from .config import Settings
from .documents import DOCUMENTS, LotPackage, corrections, list_records, load_lot, load_specs, read_record


def lot_context(settings: Settings, lot_id: str, pkg: LotPackage) -> dict:
    """Documents, records, corrections on file, and every specification revision."""
    return {
        "documents": {k: {"filename": DOCUMENTS[k], "lines": pkg.docs[k]} for k in DOCUMENTS},
        "versions": pkg.versions,
        "corrections": [{"section": s, "version": v, "filename": DOCUMENTS[s], "applied": pkg.versions.get(s) == v,
                         "lines": load_lot(settings.data_dir, lot_id, {s: v}).docs[s]}
                        for s, v in corrections(settings.data_dir, lot_id)],
        "records": {n: read_record(settings.data_dir, lot_id, n) for n in list_records(settings.data_dir, lot_id)},
        "specs": [{"revision": s["revision"], "effective_from": str(s["effective_from"]),
                   "effective_to": str(s.get("effective_to") or ""), "change_note": s.get("change_note", ""),
                   "tests": [{"name": t["name"], "min": t.get("min"), "max": t.get("max"),
                              "accepted": t.get("accepted"), "unit": t.get("unit", "")} for t in s["tests"]]}
                  for s in load_specs(settings.data_dir)],
    }
