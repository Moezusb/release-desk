"""Generate the synthetic lot packages and the scripted extraction responses.

Everything this script writes is invented: the company, the product, the
people and the numbers. Run it again after changing a lot below:

    python scripts/make_lots.py

Per lot it writes:
  data/lots/<lot>/*.md                         the documents a reviewer reads
  data/lots/<lot>/corrections/*.md             corrected versions that arrive later
  data/lots/<lot>/records/*.md                 supporting records an investigator may open
  release_desk/fixtures/<lot>[.<versions>].json what a careful model should extract
                                               (used only by offline mode)
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNER = "> Synthetic document. Fictional company, product and people, created for demonstration."

PEOPLE = ["A. Moreau", "J. Okafor", "P. Lindqvist", "R. Haddad", "S. Tremblay", "M. Chen"]
STEPS = [
    "Dispense and weigh raw materials",
    "Heat water phase to 75 °C",
    "Heat oil phase to 75 °C",
    "Emulsify under homogenizer, 10 min",
    "Cool to 40 °C, add phenoxyethanol and fragrance",
    "Adjust pH and sample for in-process checks",
    "Fill into 50 g tubes and crimp",
    "Code, inspect and pack",
]

BASE = {
    "product_code": "FH-DBC-050",
    "spec_rev": "03",
    "appearance": "White smooth cream",
    "odour": "Characteristic",
    "ph": "5.6",
    "viscosity_cp": "38,200",
    "specific_gravity": "1.00",
    "phenoxyethanol_pct": "0.91",
    "fill_weight_g": "50.6",
    "tamc_cfu_g": "<10",
    "tymc_cfu_g": "<10",
    "pathogens": "Absent in 1 g",
    "approved_by": "M. Chen",
    "yield": ("4,000", "3,936", "98.4"),
    "unverified_step": None,
    "deviations": [],
    "coa_lot_override": None,
}

LOTS = {
    "LC-24031": {"title": "A complete review packet", "summary": "Every result within its limits, every step signed twice, nothing left open.",
                 "mfg": "2026-09-03", "expiry": "2029-03",
                 "note": "Clean lot. Everything within specification."},
    "LC-24032": {"title": "A result above its limit", "summary": "Yeast and mould at four times the limit.",
                 "mfg": "2026-09-10", "expiry": "2029-03", "tymc_cfu_g": "40",
                 "note": "Yeast and mould count above the limit."},
    "LC-24033": {"title": "An unresolved deviation", "summary": "Every result passes, but a temperature deviation is still open.",
                 "mfg": "2026-09-17", "expiry": "2029-03",
                 "deviations": [
                     ("DEV-0412", "Label roll changed mid-run; reconciliation completed", "Closed", "None required"),
                     ("DEV-0417", "Mixer temperature reached 81 °C for 6 minutes during emulsification", "Open, investigation pending", "Not yet assigned"),
                 ],
                 "note": "Results in specification, but a deviation is still open."},
    "LC-24034": {"title": "A missing second signature", "summary": "The filling step was never verified, and pH sits exactly on its limit.",
                 "mfg": "2026-09-24", "expiry": "2029-03", "ph": "6.0", "unverified_step": 7,
                 "note": "Filling step not verified by a second person. pH sits exactly on the upper limit, which passes."},
    "LC-24035": {"title": "Two records that disagree", "summary": "A transposed lot number and a low preservative assay.",
                 "mfg": "2026-10-01", "expiry": "2029-04", "spec_rev": "04", "phenoxyethanol_pct": "0.78",
                 "coa_lot_override": "LC-24053",
                 "note": "Certificate carries a transposed lot number, and the preservative assay is low."},
    "LC-24036": {"title": "A result still pending", "summary": "A microbiology result not yet reported, and an expiry set on the wrong shelf life.",
                 "mfg": "2026-10-08", "expiry": "2029-10", "spec_rev": "04", "tymc_cfu_g": "Pending",
                 "note": "Yeast and mould result not yet reported, and the expiry date uses 36 months instead of 30."},
    "LC-24037": {"title": "The wrong revision", "summary": "Tested against a retired specification; the one in force says otherwise.",
                 "mfg": "2026-10-15", "expiry": "2029-04", "spec_rev": "03", "viscosity_cp": "31,400",
                 "note": "Tested against the retired revision 03. Viscosity passes rev 03 and fails rev 04, which governs this lot."},
}
# Correct expiries: 2026-09 + 30 months = 2029-03; 2026-10 + 30 months = 2029-04.

# Corrected documents that arrive after a first review.
CORRECTIONS = {
    "LC-24035": {"version": "v2", "changes": {"coa_lot_override": None},
                 "why": "Lot number on the certificate corrected by the laboratory. The assay result is unchanged."},
    "LC-24036": {"version": "v2", "changes": {"tymc_cfu_g": "<10", "expiry": "2029-04"},
                 "why": "Yeast and mould result reported, and the expiry corrected to 30 months."},
}

# Supporting records an investigator may open.
RECORDS = {
    "LC-24033": {"DEV-0417.md": [
        "# Deviation record DEV-0417",
        "",
        BANNER,
        "",
        "Lot: LC-24033",
        "Raised: 2026-09-17 by P. Lindqvist",
        "Event: Mixer jacket temperature reached 81 °C for 6 minutes during emulsification (limit 78 °C).",
        "Root cause: Thermocouple TC-2 reading 4 °C low; replaced 2026-09-19.",
        "Product impact assessment: Drafted by R. Haddad. Concludes no impact, citing viscosity and pH within specification.",
        "Impact assessment approval: Awaiting QA approval.",
        "Status: Open",
    ]},
    "LC-24035": {"LAB-NOTE-1102.md": [
        "# Laboratory note LAB-NOTE-1102",
        "",
        BANNER,
        "",
        "Lot: LC-24035",
        "Subject: Phenoxyethanol assay 0.78 % w/w",
        "The assay was repeated in duplicate on 2026-10-06: 0.78 and 0.79 % w/w.",
        "No laboratory error identified. Result confirmed.",
        "Out-of-specification investigation OOS-0233 opened.",
    ]},
}

TESTS = [
    ("appearance", "Appearance", {"03": "White to off-white smooth cream", "04": "White to off-white smooth cream"}),
    ("odour", "Odour", {"03": "Characteristic", "04": "Characteristic"}),
    ("ph", "pH (25 °C)", {"03": "5.0 to 6.0", "04": "5.0 to 6.0"}),
    ("viscosity_cp", "Viscosity, Brookfield RVT sp. 6, 10 rpm, 25 °C (cP)", {"03": "30,000 to 45,000", "04": "32,000 to 45,000"}),
    ("specific_gravity", "Specific gravity (25 °C)", {"03": "0.98 to 1.02", "04": "0.98 to 1.02"}),
    ("phenoxyethanol_pct", "Phenoxyethanol assay, HPLC (% w/w)", {"03": "0.80 to 1.00", "04": "0.80 to 1.00"}),
    ("fill_weight_g", "Fill weight, mean of 10 (g)", {"03": "Not less than 50.0", "04": "Not less than 50.0"}),
    ("tamc_cfu_g", "Total aerobic microbial count (CFU/g)", {"03": "Not more than 100", "04": "Not more than 100"}),
    ("tymc_cfu_g", "Total yeast and mould count (CFU/g)", {"03": "Not more than 10", "04": "Not more than 10"}),
    ("pathogens", "E. coli, P. aeruginosa, S. aureus, C. albicans", {"03": "Absent in 1 g", "04": "Absent in 1 g"}),
]


class Doc:
    """Collects lines and remembers where things were written."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.at: dict[str, int] = {}

    def add(self, text: str, mark: str | None = None) -> None:
        self.lines.append(text)
        if mark:
            self.at[mark] = len(self.lines)

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def cite(doc: Doc, mark: str, value: str | None, quote: str | None = None) -> dict:
    return {"value": value, "line": doc.at[mark], "quote": quote if quote is not None else value}


def certificate(lot: str, p: dict, version: str | None = None) -> tuple[Doc, dict]:
    c = Doc()
    c.add("# Certificate of Analysis")
    c.add("")
    c.add(BANNER)
    c.add("")
    c.add("Fernhollow Skincare Ltd., Quality Control Laboratory")
    if version:
        c.add(f"Document version: {version}, supersedes v1")
    c.add(f"Product: Daily Barrier Cream, 50 g ({p['product_code']})", "code")
    c.add(f"Lot number: {p['coa_lot_override'] or lot}", "lot")
    c.add(f"Date of manufacture: {p['mfg']}", "mfg")
    c.add(f"Expiry: {p['expiry']}", "exp")
    c.add(f"Tested against specification: {p['product_code']} rev {p['spec_rev']}", "rev")
    c.add("")
    c.add("| Test | Specification | Result |")
    c.add("|---|---|---|")
    results = []
    for key, name, spec in TESTS:
        c.add(f"| {name} | {spec[p['spec_rev']]} | {p[key]} |", key)
        results.append({"key": key, "result": cite(c, key, p[key])})
    c.add("")
    c.add(f"Approved for QC by: {p['approved_by']}, {p['mfg'][:8]}{int(p['mfg'][8:]) + 6:02d}", "appr")
    ext = {
        "lot_id": cite(c, "lot", p["coa_lot_override"] or lot),
        "product_code": cite(c, "code", p["product_code"]),
        "manufacture_date": cite(c, "mfg", p["mfg"]),
        "expiry": cite(c, "exp", p["expiry"]),
        "spec_revision": cite(c, "rev", p["spec_rev"], f"rev {p['spec_rev']}"),
        "approved_by": cite(c, "appr", p["approved_by"]),
        "results": results,
    }
    return c, ext


def batch_record(lot: str, p: dict) -> tuple[Doc, dict]:
    b = Doc()
    b.add("# Batch Manufacturing Record (excerpt)")
    b.add("")
    b.add(BANNER)
    b.add("")
    b.add(f"Product: Daily Barrier Cream, 50 g ({p['product_code']})", "code")
    b.add(f"Lot number: {lot}", "lot")
    b.add(f"Manufacture date: {p['mfg']}", "mfg")
    b.add(f"Line clearance verified by: J. Okafor, {p['mfg']}", "clear")
    b.add("")
    b.add("| Step | Operation | Performed by | Verified by |")
    b.add("|---|---|---|---|")
    steps = []
    for i, op in enumerate(STEPS, start=1):
        doer, checker = PEOPLE[(i + 1) % 4], PEOPLE[(i + 2) % 4]
        if p["unverified_step"] == i:
            checker = ""
        b.add(f"| {i} | {op} | {doer} | {checker} |", f"s{i}")
        steps.append({"step": i, "operation": op, "performed_by": cite(b, f"s{i}", doer),
                      "verified_by": cite(b, f"s{i}", checker or None, checker or f"| {i} | {op}")})
    b.add("")
    t, a, y = p["yield"]
    b.add(f"Theoretical quantity: {t} units. Actual quantity: {a} units. Yield: {y}%", "yield")
    ext = {
        "lot_id": cite(b, "lot", lot),
        "product_code": cite(b, "code", p["product_code"]),
        "manufacture_date": cite(b, "mfg", p["mfg"]),
        "line_clearance_by": cite(b, "clear", "J. Okafor"),
        "yield_percent": cite(b, "yield", y, f"Yield: {y}%"),
        "steps": steps,
    }
    if p["unverified_step"]:
        # One deliberate slip, so offline mode shows the evidence check at work:
        # the scripted reader claims step 7 was verified by R. Haddad, citing
        # the line for step 7, where that name does not appear.
        s = ext["steps"][p["unverified_step"] - 1]
        s["verified_by"] = {"value": "R. Haddad", "line": s["verified_by"]["line"], "quote": "R. Haddad"}
    return b, ext


def deviation_log(lot: str, p: dict) -> tuple[Doc, dict]:
    d = Doc()
    d.add("# Deviation Log")
    d.add("")
    d.add(BANNER)
    d.add("")
    d.add(f"Lot number: {lot}", "lot")
    d.add("")
    devs = []
    if not p["deviations"]:
        d.add("No deviations were recorded for this lot.")
    else:
        d.add("| ID | Description | Status | CAPA |")
        d.add("|---|---|---|---|")
        for dev_id, desc, status, capa in p["deviations"]:
            d.add(f"| {dev_id} | {desc} | {status} | {capa} |", dev_id)
            devs.append({"id": dev_id, "title": desc, "status": cite(d, dev_id, status)})
    return d, {"lot_id": cite(d, "lot", lot), "deviations": devs}


def main() -> None:
    fixtures = ROOT / "release_desk" / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    for lot, overrides in LOTS.items():
        p = {**BASE, **overrides}
        folder = ROOT / "data" / "lots" / lot
        folder.mkdir(parents=True, exist_ok=True)
        c, cert = certificate(lot, p)
        b, batch = batch_record(lot, p)
        d, log = deviation_log(lot, p)
        (folder / "certificate_of_analysis.md").write_text(c.text(), encoding="utf-8")
        (folder / "batch_record.md").write_text(b.text(), encoding="utf-8")
        (folder / "deviation_log.md").write_text(d.text(), encoding="utf-8")
        readme = f"# {lot}\n\n{BANNER}\n\nWhat this lot is for: {p['note']}\n"
        extraction = {"certificate": cert, "batch_record": batch, "deviation_log": log}
        (fixtures / f"{lot}.json").write_text(json.dumps(extraction, indent=2), encoding="utf-8")

        if lot in CORRECTIONS:
            corr = CORRECTIONS[lot]
            q = {**p, **corr["changes"]}
            c2, cert2 = certificate(lot, q, version=corr["version"])
            (folder / "corrections").mkdir(exist_ok=True)
            (folder / "corrections" / f"certificate_of_analysis.{corr['version']}.md").write_text(c2.text(), encoding="utf-8")
            (folder / "corrections" / "README.md").write_text(f"{BANNER}\n\n{corr['why']}\n", encoding="utf-8")
            fx = {"certificate": cert2, "batch_record": batch, "deviation_log": log}
            (fixtures / f"{lot}.certificate-{corr['version']}.json").write_text(json.dumps(fx, indent=2), encoding="utf-8")
            readme += f"\nA corrected certificate ({corr['version']}) arrives later: {corr['why']}\n"

        if lot in RECORDS:
            (folder / "records").mkdir(exist_ok=True)
            for name, lines in RECORDS[lot].items():
                (folder / "records" / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        (folder / "README.md").write_text(readme, encoding="utf-8")
        (folder / "case.yaml").write_text(
            f"title: {p['title']}\nsummary: {p['summary']}\nproduct_code: {p['product_code']}\n", encoding="utf-8")
        print("wrote", lot)


if __name__ == "__main__":
    main()
