"""Generate the synthetic lot packages and the scripted extraction responses.

Everything this script writes is invented: the company, the product, the
people and the numbers. Run it again after changing a lot below:

    python scripts/make_lots.py

It writes two things per lot:
  data/lots/<lot>/*.md                    the documents a reviewer would read
  release_desk/fixtures/<lot>.json        what a careful model should extract,
                                          used only by offline mode
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
    "LC-24031": {"mfg": "2026-09-03", "expiry": "2029-03",
                 "note": "Clean lot. Everything within specification."},
    "LC-24032": {"mfg": "2026-09-10", "expiry": "2029-03", "tymc_cfu_g": "40",
                 "note": "Yeast and mould count above the limit."},
    "LC-24033": {"mfg": "2026-09-17", "expiry": "2029-03",
                 "deviations": [
                     ("DEV-0412", "Label roll changed mid-run; reconciliation completed", "Closed", "None required"),
                     ("DEV-0417", "Mixer temperature reached 81 °C for 6 minutes during emulsification", "Open, investigation pending", "Not yet assigned"),
                 ],
                 "note": "Results in specification, but a deviation is still open."},
    "LC-24034": {"mfg": "2026-09-24", "expiry": "2029-03", "ph": "6.0", "unverified_step": 7,
                 "note": "Filling step not verified by a second person. pH sits exactly on the upper limit, which passes."},
    "LC-24035": {"mfg": "2026-10-01", "expiry": "2029-04", "phenoxyethanol_pct": "0.78", "coa_lot_override": "LC-24053",
                 "note": "Certificate carries a transposed lot number, and the preservative assay is low."},
    "LC-24036": {"mfg": "2026-10-08", "expiry": "2029-10", "tymc_cfu_g": "Pending",
                 "note": "Yeast and mould result not yet reported, and the expiry date uses 36 months instead of 30."},
}
# Correct expiries: 2026-09 + 30 months = 2029-03; 2026-10 + 30 months = 2029-04.

TESTS = [
    ("appearance", "Appearance", "White to off-white smooth cream"),
    ("odour", "Odour", "Characteristic"),
    ("ph", "pH (25 °C)", "5.0 to 6.0"),
    ("viscosity_cp", "Viscosity, Brookfield RVT sp. 6, 10 rpm, 25 °C (cP)", "30,000 to 45,000"),
    ("specific_gravity", "Specific gravity (25 °C)", "0.98 to 1.02"),
    ("phenoxyethanol_pct", "Phenoxyethanol assay, HPLC (% w/w)", "0.80 to 1.00"),
    ("fill_weight_g", "Fill weight, mean of 10 (g)", "Not less than 50.0"),
    ("tamc_cfu_g", "Total aerobic microbial count (CFU/g)", "Not more than 100"),
    ("tymc_cfu_g", "Total yeast and mould count (CFU/g)", "Not more than 10"),
    ("pathogens", "E. coli, P. aeruginosa, S. aureus, C. albicans", "Absent in 1 g"),
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
    line = doc.at[mark]
    return {"value": value, "line": line, "quote": quote if quote is not None else value}


def build(lot: str, p: dict) -> dict:
    p = {**BASE, **p}
    mfg_month = p["mfg"][:7]
    coa_lot = p["coa_lot_override"] or lot

    # Certificate of analysis
    c = Doc()
    c.add("# Certificate of Analysis")
    c.add("")
    c.add(BANNER)
    c.add("")
    c.add("Fernhollow Skincare Ltd., Quality Control Laboratory")
    c.add(f"Product: Daily Barrier Cream, 50 g ({p['product_code']})", "code")
    c.add(f"Lot number: {coa_lot}", "lot")
    c.add(f"Date of manufacture: {p['mfg']}", "mfg")
    c.add(f"Expiry: {p['expiry']}", "exp")
    c.add("")
    c.add("| Test | Specification | Result |")
    c.add("|---|---|---|")
    results = []
    for key, name, spec in TESTS:
        value = p[key]
        c.add(f"| {name} | {spec} | {value} |", key)
        results.append({"key": key, "result": cite(c, key, value)})
    c.add("")
    c.add(f"Approved for QC by: {p['approved_by']}, {p['mfg'][:8]}{int(p['mfg'][8:]) + 6:02d}", "appr")
    certificate = {
        "lot_id": cite(c, "lot", coa_lot),
        "product_code": cite(c, "code", p["product_code"]),
        "manufacture_date": cite(c, "mfg", p["mfg"]),
        "expiry": cite(c, "exp", p["expiry"]),
        "approved_by": cite(c, "appr", p["approved_by"]),
        "results": results,
    }

    # Batch record
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
        doer = PEOPLE[(i + 1) % 4]
        checker = PEOPLE[(i + 2) % 4]
        if p["unverified_step"] == i:
            checker = ""
        b.add(f"| {i} | {op} | {doer} | {checker} |", f"s{i}")
        steps.append({
            "step": i,
            "operation": op,
            "performed_by": cite(b, f"s{i}", doer),
            "verified_by": cite(b, f"s{i}", checker or None, f"| {i} | {op}" if not checker else checker),
        })
    b.add("")
    t, a, y = p["yield"]
    b.add(f"Theoretical quantity: {t} units. Actual quantity: {a} units. Yield: {y}%", "yield")
    batch = {
        "lot_id": cite(b, "lot", lot),
        "product_code": cite(b, "code", p["product_code"]),
        "manufacture_date": cite(b, "mfg", p["mfg"]),
        "line_clearance_by": cite(b, "clear", "J. Okafor"),
        "yield_percent": cite(b, "yield", y, f"Yield: {y}%"),
        "steps": steps,
    }

    # Deviation log
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
    log = {"lot_id": cite(d, "lot", lot), "deviations": devs}

    folder = ROOT / "data" / "lots" / lot
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "certificate_of_analysis.md").write_text(c.text(), encoding="utf-8")
    (folder / "batch_record.md").write_text(b.text(), encoding="utf-8")
    (folder / "deviation_log.md").write_text(d.text(), encoding="utf-8")
    (folder / "README.md").write_text(f"# {lot}\n\n{BANNER}\n\nWhat this lot is for: {p['note']}\n", encoding="utf-8")

    extraction = {"certificate": certificate, "batch_record": batch, "deviation_log": log}

    # One deliberate slip, so offline mode shows the evidence check at work:
    # the scripted model claims step 7 was verified by R. Haddad, citing the
    # line for step 7, where that name does not appear.
    if p["unverified_step"]:
        s = extraction["batch_record"]["steps"][p["unverified_step"] - 1]
        s["verified_by"] = {"value": "R. Haddad", "line": s["verified_by"]["line"], "quote": "R. Haddad"}
    return extraction


def main() -> None:
    fixtures = ROOT / "release_desk" / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    for lot, p in LOTS.items():
        extraction = build(lot, p)
        (fixtures / f"{lot}.json").write_text(json.dumps(extraction, indent=2), encoding="utf-8")
        print("wrote", lot)


if __name__ == "__main__":
    main()
