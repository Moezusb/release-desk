"""Checking that every extracted value is really on the line it cites.

A model can read a document well and still, now and then, report a value that
is not there. The cure is cheap: look. Any value whose citation does not hold
up is discarded and treated as missing, so the rules downstream fail closed
on it instead of trusting it.
"""

from __future__ import annotations

import re

from .documents import LotPackage
from .schemas import Cited, EvidenceNote, LotExtraction


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def check_one(pkg: LotPackage, section: str, field: str, cited: Cited) -> EvidenceNote | None:
    if cited.value is None:
        return None  # nothing claimed, nothing to verify
    line = pkg.line(section, cited.line)
    reason = None
    if line is None:
        reason = "cited line does not exist"
    elif _norm(cited.value) not in _norm(line):
        reason = "value does not appear on the cited line"
    elif cited.quote and _norm(cited.quote) not in _norm(line):
        reason = "quoted text does not appear on the cited line"
    if reason is None:
        return None
    return EvidenceNote(
        field=field,
        document=pkg.filename(section),
        claimed_value=cited.value,
        cited_line=cited.line,
        reason=reason,
    )


def verify(pkg: LotPackage, ext: LotExtraction) -> tuple[LotExtraction, list[EvidenceNote]]:
    """Return a copy of the extraction with unsupported values set to None."""
    ext = ext.model_copy(deep=True)
    notes: list[EvidenceNote] = []

    def visit(section: str, field: str, cited: Cited) -> None:
        note = check_one(pkg, section, field, cited)
        if note:
            notes.append(note)
            cited.value = None

    c = ext.certificate
    for name in ("lot_id", "product_code", "manufacture_date", "expiry", "approved_by"):
        visit("certificate", f"certificate.{name}", getattr(c, name))
    for r in c.results:
        visit("certificate", f"certificate.results.{r.key}", r.result)

    b = ext.batch_record
    for name in ("lot_id", "product_code", "manufacture_date", "line_clearance_by", "yield_percent"):
        visit("batch_record", f"batch_record.{name}", getattr(b, name))
    for s in b.steps:
        visit("batch_record", f"batch_record.step{s.step}.performed_by", s.performed_by)
        visit("batch_record", f"batch_record.step{s.step}.verified_by", s.verified_by)

    d = ext.deviation_log
    visit("deviation_log", "deviation_log.lot_id", d.lot_id)
    for dev in d.deviations:
        visit("deviation_log", f"deviation_log.{dev.id}.status", dev.status)

    return ext, notes
