"""Generate synthetic system extracts that sit behind the lot documents.

In a real plant the certificate, batch record and deviation log are views of
three systems: a laboratory system (LIMS), a manufacturing execution system
(MES) and a quality management system (QMS). These extracts imitate them,
including the quirks a data mapping has to survive:

* LIMS writes some older lot numbers without the hyphen (LC24036).
* LIMS stores the preservative assay as a mass fraction, not a percentage.
* LIMS keeps a superseded result next to its retest.
* LIMS dates are written day first, and the convention is not documented.
* QMS has a status whose meaning for release nobody has written down.

    python scripts/make_sources.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_lots import BASE, LOTS  # noqa: E402

OUT = ROOT / "data" / "mapping" / "sources"
LEGACY_LOT_FORMAT = {"LC-24036", "LC-24037"}  # migrated late; LIMS still writes them without the hyphen


def dmy(iso: str, plus_days: int = 0) -> str:
    y, m, d = iso.split("-")
    return f"{int(d) + plus_days:02d}/{m}/{y}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lims, mes, qms = [], [], []
    sample = 5100
    for lot, overrides in LOTS.items():
        p = {**BASE, **overrides}
        lims_lot = lot.replace("-", "") if lot in LEGACY_LOT_FORMAT else lot
        tested = dmy(p["mfg"], 2)
        rows = [
            ("MIC-TAMC", p["tamc_cfu_g"], "CFU/g"),
            ("MIC-TYMC", p["tymc_cfu_g"], "CFU/g"),
            ("PHY-VIS", p["viscosity_cp"].replace(",", ""), "mPa.s"),
            ("ASY-PHX", f"{float(p['phenoxyethanol_pct']) / 100:.4f}", "w/w"),
            ("PHY-PH", p["ph"], ""),
        ]
        for code, value, unit in rows:
            sample += 1
            if value == "Pending":
                lims.append([f"S{sample}", lims_lot, code, "", unit, "pending", tested])
                continue
            if lot == "LC-24035" and code == "ASY-PHX":
                # original result kept as superseded, retest approved: two rows for one test
                lims.append([f"S{sample}", lims_lot, code, "0.0079", unit, "superseded", tested])
                sample += 1
                lims.append([f"S{sample}", lims_lot, code, value, unit, "approved", dmy(p["mfg"], 5)])
                continue
            lims.append([f"S{sample}", lims_lot, code, value, unit, "approved", tested])
        mes.append([lot, p["product_code"], p["mfg"], dmy(p["mfg"], 1), p["yield"][2]])
        for dev_id, _desc, status, _capa in p["deviations"]:
            qms_status = "Open" if status.startswith("Open") else "Closed"
            if dev_id == "DEV-0412":
                qms_status = "Closed - effectiveness check pending"  # closed on paper; is it closed for release?
            qms.append([dev_id, lot, qms_status])

    def write(name, header, rows):
        with (OUT / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)

    write("lims_results.csv", ["sample_id", "lot_ref", "test_code", "result_value", "result_unit", "result_status", "tested_on"], lims)
    write("mes_batches.csv", ["batch_no", "product_code", "mfg_date", "packed_on", "yield_pct"], mes)
    write("qms_deviations.csv", ["dev_id", "batch_no", "status"], qms)
    print(f"wrote {len(lims)} LIMS rows, {len(mes)} MES rows, {len(qms)} QMS rows")


if __name__ == "__main__":
    main()
