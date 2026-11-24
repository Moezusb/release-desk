"""The release rules, written as plain code.

Comparing 0.78 with 0.80 does not need judgment, and it should not get any.
These checks are deterministic, testable and the same on every run. The model
reads the documents; this module decides what the numbers mean.

Every rule fails closed: a value that is missing, unreadable or unverified
counts as a failure, never as a pass.
"""

from __future__ import annotations

import re
from datetime import date

from .documents import LotPackage
from .schemas import Cited, Evidence, Finding, LotExtraction

_NUM = re.compile(r"^\s*([<>]=?|≤|≥)?\s*([0-9][0-9,]*\.?[0-9]*)\s*$")


def parse_number(text: str | None) -> tuple[str, float] | None:
    """'38,200' -> ('', 38200.0); '<10' -> ('<', 10.0); 'Pending' -> None."""
    if text is None:
        return None
    m = _NUM.match(text)
    if not m:
        return None
    op = {"≤": "<=", "≥": ">="}.get(m.group(1) or "", m.group(1) or "")
    return op, float(m.group(2).replace(",", ""))


def in_range(op: str, value: float, lo: float | None, hi: float | None) -> bool:
    # '<10' means the true value is below 10, so it meets a maximum of 10 or more
    # but can never prove it meets a minimum.
    if op.startswith("<"):
        return lo is None and (hi is None or value <= hi)
    if op.startswith(">"):
        return hi is None and (lo is None or value >= lo)
    return (lo is None or value >= lo) and (hi is None or value <= hi)


def add_months(d: date, months: int) -> tuple[int, int]:
    total = d.year * 12 + (d.month - 1) + months
    return total // 12, total % 12 + 1


class _Collector:
    def __init__(self, pkg: LotPackage) -> None:
        self.pkg = pkg
        self.items: list[Finding] = []

    def ev(self, section: str, cited: Cited | None) -> Evidence:
        line = cited.line if cited else None
        return Evidence(document=self.pkg.filename(section), line=line, text=self.pkg.line(section, line))

    def add(self, rule: str, severity: str, title: str, expected: str, observed: str, evidence: list[Evidence]) -> None:
        self.items.append(
            Finding(id=f"F{len(self.items) + 1}", rule=rule, severity=severity, title=title,
                    expected=expected, observed=observed, evidence=evidence)
        )


def _num(v) -> float | None:
    return None if v is None else float(v)


def _fmt_range(t: dict) -> str:
    unit = f" {t['unit']}" if t.get("unit") else ""
    lo, hi = t.get("min"), t.get("max")
    if lo is not None and hi is not None:
        return f"{lo} to {hi}{unit}"
    if lo is not None:
        return f"not less than {lo}{unit}"
    return f"not more than {hi}{unit}"


def evaluate(pkg: LotPackage, ext: LotExtraction, spec: dict) -> list[Finding]:
    f = _Collector(pkg)
    c, b, d = ext.certificate, ext.batch_record, ext.deviation_log

    # Identity: the three documents must describe the same lot and product.
    for section, cited, label in (
        ("certificate", c.lot_id, "certificate of analysis"),
        ("batch_record", b.lot_id, "batch record"),
        ("deviation_log", d.lot_id, "deviation log"),
    ):
        if cited.value != pkg.lot_id:
            f.add("identity.lot_mismatch", "critical", f"Lot number on the {label} does not match",
                  pkg.lot_id, cited.value or "missing or unverified", [f.ev(section, cited)])
    for section, cited in (("certificate", c.product_code), ("batch_record", b.product_code)):
        if cited.value != spec["product_code"]:
            f.add("identity.product_code", "critical", "Product code does not match the specification",
                  spec["product_code"], cited.value or "missing or unverified", [f.ev(section, cited)])

    # Test results against specification.
    results = {r.key: r.result for r in c.results}
    for t in spec["tests"]:
        cited = results.get(t["key"])
        raw = cited.value if cited else None
        sev = t["severity"]
        if t["kind"] == "range":
            parsed = parse_number(raw)
            if parsed is None:
                f.add(f"test.{t['key']}.missing", sev, f"{t['name']}: no usable result",
                      _fmt_range(t), raw or "missing or unverified", [f.ev("certificate", cited)])
            elif not in_range(parsed[0], parsed[1], _num(t.get("min")), _num(t.get("max"))):
                f.add(f"test.{t['key']}.out_of_spec", sev, f"{t['name']} out of specification",
                      _fmt_range(t), raw, [f.ev("certificate", cited)])
        else:
            if not raw:
                f.add(f"test.{t['key']}.missing", sev, f"{t['name']}: no usable result",
                      " or ".join(t["accepted"]), "missing or unverified", [f.ev("certificate", cited)])
            elif not any(a in raw.lower() for a in t["accepted"]):
                f.add(f"test.{t['key']}.out_of_spec", sev, f"{t['name']} out of specification",
                      " or ".join(t["accepted"]), raw, [f.ev("certificate", cited)])

    # Dates: expiry must equal manufacture month plus shelf life.
    try:
        mfg = date.fromisoformat(b.manufacture_date.value or c.manufacture_date.value or "")
    except ValueError:
        mfg = None
    if c.manufacture_date.value and b.manufacture_date.value and c.manufacture_date.value != b.manufacture_date.value:
        f.add("dates.manufacture_mismatch", "major", "Manufacture date differs between documents",
              b.manufacture_date.value, c.manufacture_date.value,
              [f.ev("certificate", c.manufacture_date), f.ev("batch_record", b.manufacture_date)])
    if mfg is None:
        f.add("dates.manufacture_missing", "major", "Manufacture date missing or unreadable",
              "a date (YYYY-MM-DD)", "missing or unverified", [f.ev("batch_record", b.manufacture_date)])
    else:
        y, m = add_months(mfg, spec["shelf_life_months"])
        expected = f"{y:04d}-{m:02d}"
        if c.expiry.value != expected:
            f.add("dates.expiry", "major", "Expiry date does not match the approved shelf life",
                  f"{expected} ({spec['shelf_life_months']} months from manufacture)",
                  c.expiry.value or "missing or unverified", [f.ev("certificate", c.expiry)])

    if not c.approved_by.value:
        f.add("coa.not_approved", "major", "Certificate not signed by QC",
              "a QC approver's name", "missing or unverified", [f.ev("certificate", c.approved_by)])

    # Batch record.
    br = spec["batch_record"]
    y = parse_number(b.yield_percent.value)
    lo, hi = br["yield_percent"]["min"], br["yield_percent"]["max"]
    if y is None or not in_range(y[0], y[1], _num(lo), _num(hi)):
        f.add("batch.yield", br["yield_percent"]["severity"], "Yield outside the expected range",
              f"{lo} to {hi}%", b.yield_percent.value or "missing or unverified", [f.ev("batch_record", b.yield_percent)])
    if not b.line_clearance_by.value:
        f.add("batch.line_clearance", br["line_clearance_verified"]["severity"], "Line clearance not verified",
              "a verifier's name", "missing or unverified", [f.ev("batch_record", b.line_clearance_by)])
    sev = br["every_step_performed_and_verified"]["severity"]
    if not b.steps:
        f.add("batch.steps_missing", sev, "No manufacturing steps could be read",
              "every step signed", "none", [f.ev("batch_record", None)])
    for s in b.steps:
        if not s.performed_by.value:
            f.add("batch.step_unperformed", sev, f"Step {s.step} has no operator signature",
                  "operator's name", "blank or unverified", [f.ev("batch_record", s.performed_by)])
        if not s.verified_by.value:
            f.add("batch.step_unverified", sev, f"Step {s.step} ({s.operation}) not verified by a second person",
                  "a second person's name", "blank or unverified", [f.ev("batch_record", s.verified_by)])
        elif s.performed_by.value and s.verified_by.value.strip() == s.performed_by.value.strip():
            f.add("batch.self_verified", sev, f"Step {s.step} verified by the same person who performed it",
                  "two different people", s.verified_by.value, [f.ev("batch_record", s.verified_by)])

    # Deviations: every one must be closed before release.
    sev = spec["deviations"]["all_closed"]["severity"]
    for dev in d.deviations:
        status = (dev.status.value or "").strip()
        if not status.lower().startswith("closed"):
            f.add("deviation.open", sev, f"{dev.id} is not closed: {dev.title}",
                  "Closed", status or "missing or unverified", [f.ev("deviation_log", dev.status)])

    return f.items
