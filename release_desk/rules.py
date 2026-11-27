"""The release rules, written as plain code.

Comparing 0.78 with 0.80 does not need judgment, and it should not get any.
These checks are deterministic, testable and the same on every run. The model
reads the documents; this module decides what the numbers mean.

Every rule fails closed: a value that is missing, unreadable or unverified
counts as a failure, never as a pass.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from .documents import LotPackage, governing_spec
from .schemas import Cited, Evidence, Finding, LotExtraction

# A number, optionally with a comparison before it and a unit after it ("98.4%", "<10 CFU/g",
# "38,200 cP"), because a model copies values as the document writes them. The unit may hold
# no digits and must start with a letter, %, ° or "(", so "8 x 10^3" and a range
# such as "10-20" stay unreadable and fail closed.
_NUM = re.compile(r"^\s*([<>]=?|≤|≥)?\s*([0-9][0-9,]*\.?[0-9]*)\s*(?:(?:[%°(]|[^\W\d_])[^\d]*)?\s*$")


def parse_number(text: str | None) -> tuple[str, float] | None:
    """'38,200 cP' -> ('', 38200.0); '<10 CFU/g' -> ('<', 10.0); '98.4%' -> ('', 98.4); 'Pending' -> None."""
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


def _fmt(v) -> str:
    x = float(v)
    return f"{x:,.0f}" if x >= 1000 else str(v)


def _fmt_range(t: dict) -> str:
    unit = f" {t['unit']}" if t.get("unit") else ""
    lo, hi = t.get("min"), t.get("max")
    lo = _fmt(lo) if lo is not None else None
    hi = _fmt(hi) if hi is not None else None
    if lo is not None and hi is not None:
        return f"{lo} to {hi}{unit}"
    if lo is not None:
        return f"not less than {lo}{unit}"
    return f"not more than {hi}{unit}"


def _date(text: str | None) -> date | None:
    try:
        return date.fromisoformat(text or "")
    except ValueError:
        return None


# A model may copy a value with its label ("Lot number: LC-24033") or its
# neighbours ("M. Chen, 2026-09-23"). The evidence check has already proved the
# text is on the cited line; these helpers find the part a rule needs in it.
_ISO_DAY = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_ISO_MONTH = re.compile(r"\b(\d{4}-\d{2})(?!-\d)\b")
_DASHES = str.maketrans({c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2212"})
_CODE = re.compile(r"\b[A-Za-z]{1,6}(?:-[A-Za-z0-9]+)+\b")

# What a form holds when nobody signed it. A placeholder is not a signature.
_PLACEHOLDERS = {"", "-", "--", "—", "–", "_", "n/a", "na", "none", "nil", "pending", "tbd", "tbc",
                 "unsigned", "not signed", "blank", "missing", "null", "x", "?"}
# Words that turn an accepted phrase into its opposite: "not absent", "non-characteristic".
_NEGATION = re.compile(r"\b(not|non|no|un|fails?|failed|doesn't|does not)\b|\bnon-|\bun-")


def day(text: str | None) -> date | None:
    m = _ISO_DAY.search(text or "")
    return _date(m.group(1)) if m else None


def month(text: str | None) -> str | None:
    d = _ISO_DAY.search(text or "")
    if d:
        return d.group(1)[:7]
    m = _ISO_MONTH.search(text or "")
    return m.group(1) if m else None


def code(text: str | None) -> str | None:
    """'Lot number: LC-24033' -> 'LC-24033'. The last code on the text, upper case."""
    text = unicodedata.normalize("NFKC", text or "").translate(_DASHES)
    found = _CODE.findall(text)
    return found[-1].upper() if found else (text.strip().upper() if text and text.strip() else None)


def revision(text: str | None) -> int | None:
    """'03', '3', 'rev 03', 'FH-DBC-050 rev 03' -> 3."""
    m = re.search(r"rev(?:ision)?\.?\s*0*(\d+)", text or "", re.I) or re.fullmatch(r"\s*0*(\d+)\s*", text or "")
    return int(m.group(1)) if m else None


def signed(text: str | None) -> str | None:
    """The signer, normalised, or None if the field holds nothing or a placeholder."""
    name = re.sub(r",?\s*\d{4}-\d{2}-\d{2}.*$", "", text or "")       # drop a trailing date
    name = re.sub(r"\s+", " ", name).strip(" .,;:").casefold()
    return None if name in _PLACEHOLDERS or not re.search(r"[^\W\d_]", name) else name


def text_passes(raw: str, accepted: list[str]) -> bool:
    """A text result passes when it starts with an accepted phrase and negates nothing."""
    norm = re.sub(r"\s+", " ", raw).strip().casefold()
    return any(norm.startswith(a.casefold()) for a in accepted) and not _NEGATION.search(norm)


def applicable_spec(specs: list[dict], ext: LotExtraction) -> dict | None:
    """The specification revision that governs this lot: the one in force on its date of manufacture."""
    made = day(ext.batch_record.manufacture_date.value) or day(ext.certificate.manufacture_date.value)
    return governing_spec(specs, made)


def evaluate(pkg: LotPackage, ext: LotExtraction, specs: list[dict] | dict) -> list[Finding]:
    f = _Collector(pkg)
    c, b, d = ext.certificate, ext.batch_record, ext.deviation_log
    specs = [specs] if isinstance(specs, dict) else specs

    # Which revision governs? The one in force when the lot was made, not the latest
    # and not whichever the certificate happens to name.
    spec = applicable_spec(specs, ext)
    if spec is None:
        spec = specs[-1]
        f.add("spec.no_governing_revision", "major", "No specification revision covers the manufacture date",
              "a revision in force on the date of manufacture", "none found; checked against the latest",
              [f.ev("batch_record", b.manufacture_date)])
    elif revision(c.spec_revision.value) != revision(spec["revision"]):
        f.add("spec.wrong_revision", "major",
              f"Certificate tested against the wrong specification revision",
              f"rev {spec['revision']}, in force from {spec['effective_from']}",
              f"rev {c.spec_revision.value}" if c.spec_revision.value else "not stated or unverified",
              [f.ev("certificate", c.spec_revision), f.ev("batch_record", b.manufacture_date)])

    # Identity: the three documents must describe the same lot and product.
    for section, cited, label in (
        ("certificate", c.lot_id, "certificate of analysis"),
        ("batch_record", b.lot_id, "batch record"),
        ("deviation_log", d.lot_id, "deviation log"),
    ):
        if code(cited.value) != pkg.lot_id.upper():
            f.add("identity.lot_mismatch", "critical", f"Lot number on the {label} does not match",
                  pkg.lot_id, cited.value or "missing or unverified", [f.ev(section, cited)])
    for section, cited in (("certificate", c.product_code), ("batch_record", b.product_code)):
        if code(cited.value) != spec["product_code"].upper():
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
            elif not text_passes(raw, t["accepted"]):
                f.add(f"test.{t['key']}.out_of_spec", sev, f"{t['name']} out of specification",
                      " or ".join(t["accepted"]), raw, [f.ev("certificate", cited)])

    # Dates: expiry must equal manufacture month plus shelf life.
    mfg = day(b.manufacture_date.value) or day(c.manufacture_date.value)
    if c.manufacture_date.value and b.manufacture_date.value and day(c.manufacture_date.value) != day(b.manufacture_date.value):
        f.add("dates.manufacture_mismatch", "major", "Manufacture date differs between documents",
              b.manufacture_date.value, c.manufacture_date.value,
              [f.ev("certificate", c.manufacture_date), f.ev("batch_record", b.manufacture_date)])
    if mfg is None:
        f.add("dates.manufacture_missing", "major", "Manufacture date missing or unreadable",
              "a date (YYYY-MM-DD)", "missing or unverified", [f.ev("batch_record", b.manufacture_date)])
    else:
        y, m = add_months(mfg, spec["shelf_life_months"])
        expected = f"{y:04d}-{m:02d}"
        if month(c.expiry.value) != expected:
            f.add("dates.expiry", "major", "Expiry date does not match the approved shelf life",
                  f"{expected} ({spec['shelf_life_months']} months from manufacture)",
                  c.expiry.value or "missing or unverified", [f.ev("certificate", c.expiry)])

    if not signed(c.approved_by.value):
        f.add("coa.not_approved", "major", "Certificate not signed by QC",
              "a QC approver's name", "missing or unverified", [f.ev("certificate", c.approved_by)])

    # Batch record.
    br = spec["batch_record"]
    y = parse_number(b.yield_percent.value)
    lo, hi = br["yield_percent"]["min"], br["yield_percent"]["max"]
    if y is None or not in_range(y[0], y[1], _num(lo), _num(hi)):
        f.add("batch.yield", br["yield_percent"]["severity"], "Yield outside the expected range",
              f"{lo} to {hi}%", b.yield_percent.value or "missing or unverified", [f.ev("batch_record", b.yield_percent)])
    if not signed(b.line_clearance_by.value):
        f.add("batch.line_clearance", br["line_clearance_verified"]["severity"], "Line clearance not verified",
              "a verifier's name", "missing or unverified", [f.ev("batch_record", b.line_clearance_by)])
    sev = br["every_step_performed_and_verified"]["severity"]
    if not b.steps:
        f.add("batch.steps_missing", sev, "No manufacturing steps could be read",
              "every step signed", "none", [f.ev("batch_record", None)])
    for s in b.steps:
        if not signed(s.performed_by.value):
            f.add("batch.step_unperformed", sev, f"Step {s.step} has no operator signature",
                  "operator's name", "blank or unverified", [f.ev("batch_record", s.performed_by)])
        if not signed(s.verified_by.value):
            f.add("batch.step_unverified", sev, f"Step {s.step} ({s.operation}) not verified by a second person",
                  "a second person's name", "blank or unverified", [f.ev("batch_record", s.verified_by)])
        elif signed(s.performed_by.value) and signed(s.verified_by.value) == signed(s.performed_by.value):
            f.add("batch.self_verified", sev, f"Step {s.step} verified by the same person who performed it",
                  "two different people", s.verified_by.value, [f.ev("batch_record", s.verified_by)])

    # Deviations: every one must be closed before release.
    sev = spec["deviations"]["all_closed"]["severity"]
    for dev in d.deviations:
        status = (dev.status.value or "").strip()
        if not status.casefold().startswith("closed") or _NEGATION.search(status.casefold()):
            f.add("deviation.open", sev, f"{dev.id} is not closed: {dev.title}",
                  "Closed", status or "missing or unverified", [f.ev("deviation_log", dev.status)])

    return f.items
