"""Checking that every extracted value is really on the line it cites.

A model can read a document well and still, now and then, report a value that
is not there. The cure is cheap: look. Any value whose citation does not hold
up is discarded and treated as missing, so the rules downstream fail closed
on it instead of trusting it.
"""

from __future__ import annotations

import re
import unicodedata

from .documents import LotPackage
from .schemas import Cited, EvidenceNote, LotExtraction


_DASHES = str.maketrans({c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2212"})


def _norm(text: str | None) -> str:
    """Compare text, not typography: NFKC (so a non-breaking space is a space), one kind of dash, case-free."""
    text = unicodedata.normalize("NFKC", text or "").translate(_DASHES)
    return re.sub(r"\s+", " ", text).strip().lower()


def check_one(pkg: LotPackage, section: str, field: str, cited: Cited, must_mention: list[str] | None = None) -> EvidenceNote | None:
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
    elif must_mention and not any(_norm(w) in _norm(line) for w in must_mention):
        # A real number on a real line can still belong to a different test.
        reason = f"the cited line is not about this attribute (expected it to mention {' or '.join(must_mention)})"
    if reason is None:
        return None
    return EvidenceNote(
        field=field,
        document=pkg.filename(section),
        claimed_value=cited.value,
        cited_line=cited.line,
        reason=reason,
    )


def verify(pkg: LotPackage, ext: LotExtraction, spec: dict | None = None) -> tuple[LotExtraction, list[EvidenceNote]]:
    """Return a copy of the extraction with unsupported values set to None.

    Refused claims are returned as notes and kept in the record. They are
    removed from what the rules see, never from what the reviewer sees.
    """
    ext = ext.model_copy(deep=True)
    notes: list[EvidenceNote] = []
    match = {t["key"]: t.get("match") for t in (spec or {}).get("tests", [])}

    def visit(section: str, field: str, cited: Cited, must_mention: list[str] | None = None) -> None:
        note = check_one(pkg, section, field, cited, must_mention)
        if note:
            notes.append(note)
            cited.value = None

    c = ext.certificate
    for name in ("lot_id", "product_code", "manufacture_date", "expiry", "spec_revision", "approved_by"):
        visit("certificate", f"certificate.{name}", getattr(c, name))
    for r in c.results:
        visit("certificate", f"certificate.results.{r.key}", r.result, match.get(r.key))

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
