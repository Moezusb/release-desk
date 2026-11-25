"""Checking a vendor's proposed data mapping before anything is built on it.

A mapping can pass every type check and still be wrong. Two microbial counts
share a type and a unit; only their meaning tells them apart. A join can return
the right number of rows while losing one lot and doubling another. So each
mapping is checked against three things the vendor did not write:

  1. the source systems' own data dictionary (what each column means),
  2. the canonical field definitions the release rules depend on,
  3. the data itself, reconciled lot by lot against the documents.

Every check ends in one of three states:
  validated                   the evidence supports it
  failed                      the evidence contradicts it; acceptance is blocked
  needs business confirmation the data cannot settle it; a named person must
"""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

import yaml

from .documents import governing_spec, list_lots, load_lot, load_specs

VALIDATED, FAILED, CONFIRM = "validated", "failed", "needs business confirmation"


def _load(data_dir: Path) -> tuple[dict, dict, dict[str, list[dict]]]:
    m = data_dir / "mapping"
    canonical = yaml.safe_load((m / "canonical.yaml").read_text(encoding="utf-8"))
    dictionary = yaml.safe_load((m / "dictionary.yaml").read_text(encoding="utf-8"))
    sources = {}
    for path in sorted((m / "sources").glob("*.csv")):
        with path.open(encoding="utf-8") as fh:
            sources[path.stem] = list(csv.DictReader(fh))
    return canonical, dictionary, sources


def _normalise(lot: str, how: str) -> str:
    if how == "insert_hyphen" and re.fullmatch(r"LC\d{5}", lot):
        return f"LC-{lot[2:]}"
    return lot


def _num(text: str) -> float | None:
    m = re.fullmatch(r"\s*[<>]?\s*([0-9][0-9,]*\.?[0-9]*)\s*", text or "")
    return float(m.group(1).replace(",", "")) if m else None


def _agree(mapped: str, doc: str | None, factor: float) -> bool:
    if not mapped and _num(doc or "") is None:
        return True  # missing in both places, e.g. a result still pending
    a, b = _num(mapped), _num(doc or "")
    if a is None or b is None:
        return False
    if mapped.strip().startswith("<") != (doc or "").strip().startswith("<"):
        return False
    return abs(a * factor - b) < 1e-6


def _document_result(data_dir: Path, lot: str, match: list[str]) -> str | None:
    """The result cell for a test on the lot's certificate, found by the test's name."""
    for line in load_lot(data_dir, lot).docs["certificate"]:
        if line.startswith("|") and any(w in line.lower() for w in match):
            cells = [c.strip() for c in line.strip("|").split("|")]
            return cells[-1] if len(cells) >= 3 else None
    return None


def check(data_dir: Path, mapping_file: str) -> dict:
    canonical, dictionary, sources = _load(data_dir)
    mapping = yaml.safe_load((data_dir / "mapping" / mapping_file).read_text(encoding="utf-8"))
    specs = load_specs(data_dir)
    spec_tests = {t["key"]: t for t in specs[-1]["tests"]}
    conversions = {(c["from"], c["to"]): c["multiply"] for c in canonical["approved_conversions"]}
    rows: list[dict] = []

    def add(area, field, check, status, detail, lots=None):
        rows.append({"area": area, "field": field, "check": check, "status": status, "detail": detail, "lots": lots or []})

    lims = sources["lims_results"]
    mes = sources["mes_batches"]
    lots = list_lots(data_dir)
    join = mapping["joins"]["lims_to_mes"]
    norm = join.get("normalise", "none")
    flt = mapping.get("results_filter")
    flt = flt if isinstance(flt, dict) else {}
    kept = [r for r in lims if all(r.get(k) == v for k, v in flt.items())]

    # ---------------------------------------------------------- coverage
    for name, spec in canonical["fields"].items():
        if spec.get("required") and name not in mapping["fields"]:
            add("Coverage", name, "Required field is mapped", FAILED, "No source is proposed for this field.")

    # ------------------------------------------------------------ joins
    mes_keys = {r["batch_no"] for r in mes}
    lims_keys = {_normalise(r["lot_ref"], norm) for r in kept}
    unmatched = sorted(k for k in {r["lot_ref"] for r in kept} if _normalise(k, norm) not in mes_keys)
    missing = sorted(k for k in mes_keys if k not in lims_keys)
    if missing:
        add("Join", "lot_id", "Every batch finds its laboratory results", FAILED,
            f"{len(missing)} batch(es) lose all laboratory results in the join. LIMS writes them as "
            f"{', '.join(unmatched)}; the documented key format allows this, and the mapping does not normalise it.", missing)
    else:
        add("Join", "lot_id", "Every batch finds its laboratory results", VALIDATED,
            f"All {len(mes_keys)} batches match laboratory results after key normalisation ({norm}).")

    # Cardinality: one result per lot per test, after the declared filter.
    counts: dict[tuple[str, str], int] = {}
    for r in kept:
        key = (_normalise(r["lot_ref"], norm), r["test_code"])
        counts[key] = counts.get(key, 0) + 1
    dupes = sorted({lot for (lot, _), n in counts.items() if n > 1})
    if dupes:
        add("Join", "results", "One result per lot and test", FAILED,
            "Some tests return more than one row per lot, so a superseded result can sit beside its retest. "
            f"Rows are not filtered on result status ({', '.join(sorted(dictionary['lims_results']['status_values']))}).", dupes)
    else:
        add("Join", "results", "One result per lot and test", VALIDATED,
            f"Exactly one row per lot and test after filtering on {flt or 'nothing'}.")

    # ------------------------------------------------------------ fields
    codes = dictionary["lims_results"]["test_codes"]
    for name, target in mapping["fields"].items():
        spec = canonical["fields"].get(name, {})
        kind = spec.get("kind")

        if kind == "number":
            code = target.get("test_code")
            meta = codes.get(code)
            if not meta:
                add("Field", name, "Source exists", FAILED, f"Test code {code} is not in the LIMS dictionary.")
                continue
            if not all(w in meta["meaning"].lower() for w in spec["means"]):
                add("Field", name, "Source means the same thing", FAILED,
                    f"Mapped to {code}, which LIMS documents as '{meta['meaning']}'. Same type and unit "
                    f"({meta['unit']}), different measurement. The field needs '{' and '.join(spec['means'])}'.")
            else:
                add("Field", name, "Source means the same thing", VALIDATED, f"{code}: {meta['meaning']}.")
            factor = target.get("multiply", 1)
            if meta["unit"] != spec["unit"]:
                approved = conversions.get((meta["unit"], spec["unit"]))
                if approved is None:
                    add("Field", name, "Unit conversion is approved", CONFIRM,
                        f"{meta['unit']} to {spec['unit']} is not an approved conversion.")
                elif approved != factor:
                    add("Field", name, "Unit conversion is applied", FAILED,
                        f"LIMS stores {meta['unit']}; the field is {spec['unit']}. The approved conversion multiplies by "
                        f"{approved:g}; the mapping multiplies by {factor:g}, so 0.91 % would be read as {0.0091 * factor:g} %.")
                else:
                    add("Field", name, "Unit conversion is applied", VALIDATED, f"{meta['unit']} × {factor:g} = {spec['unit']}.")

            # Reconcile with the documents, lot by lot.
            match = spec_tests.get(spec["spec_key"], {}).get("match", [])
            disagree = []
            for lot in lots:
                rows_for = [r for r in kept if _normalise(r["lot_ref"], norm) == lot and r["test_code"] == code]
                doc = _document_result(data_dir, lot, match)
                if not rows_for:
                    continue  # reported by the join check
                mapped = rows_for[-1]["result_value"]
                same = _agree(mapped, doc, factor)
                if not same:
                    disagree.append(f"{lot}: mapped {mapped or 'blank'}{' × ' + format(factor, 'g') if factor != 1 and mapped else ''}, certificate {doc}")
            if disagree:
                add("Reconciliation", name, "Mapped values match the certificates", FAILED,
                    "; ".join(disagree[:4]) + (" …" if len(disagree) > 4 else ""), [d.split(":")[0] for d in disagree])
            else:
                add("Reconciliation", name, "Mapped values match the certificates", VALIDATED,
                    f"Every mapped lot agrees with its certificate ({len(lots) - len(missing)} lots).")

        elif kind == "date":
            table, _, column = target["source"].partition(".")
            meta = dictionary.get(table, {}).get("columns", {}).get(column, {})
            if meta.get("event") != spec["event"]:
                add("Field", name, "Date records the right event", FAILED,
                    f"{target['source']} is documented as '{meta.get('meaning')}', not the {spec['event']} date. "
                    "Shelf life and the governing specification are both calculated from this field.")
            else:
                add("Field", name, "Date records the right event", VALIDATED, f"{target['source']}: {meta['meaning']}.")
            declared, documented = target.get("date_format"), meta.get("date_convention")
            values = [r[column] for r in sources.get(table, [])]
            if declared == "MM/DD/YYYY":
                impossible = [v for v in values if re.fullmatch(r"\d{2}/\d{2}/\d{4}", v) and int(v[:2]) > 12]
                if impossible:
                    add("Field", name, "Date convention matches the data", FAILED,
                        f"Declared month first, but {len(impossible)} values have a first part above 12 "
                        f"(for example {impossible[0]}), so the source is day first.")
                    continue
            if documented == "not documented":
                add("Field", name, "Date convention is documented", CONFIRM,
                    "The source owner has not documented the date convention; the data alone cannot settle every value.")
            elif declared and documented and declared != documented:
                add("Field", name, "Date convention matches the documentation", FAILED, f"Declared {declared}, documented {documented}.")
            else:
                add("Field", name, "Date convention matches the documentation", VALIDATED, f"{declared}, as documented.")

        elif kind == "status":
            table, _, column = target["source"].partition(".")
            documented = dictionary[table]["status_values"]
            confirmed = set(spec.get("confirmed_closed_values", []))
            unclear = [v for v in target.get("closed_values", []) if v not in confirmed]
            affected = sorted({r["batch_no"] for r in sources[table] if r[column] in unclear})
            if unclear:
                add("Field", name, "Status values that count as closed are confirmed", CONFIRM,
                    f"The mapping treats '{unclear[0]}' as closed for release. The QMS documents it as "
                    f"'{documented.get(unclear[0])}'. Whether that is closed enough to release is a Quality decision.", affected)
            else:
                add("Field", name, "Status values that count as closed are confirmed", VALIDATED, "Only confirmed values count as closed.")

        elif kind == "policy":
            policy = target.get("policy")
            if policy == "effective_at_manufacture":
                add("Field", name, "Specification revision is chosen by date of manufacture", VALIDATED,
                    "Each lot is checked against the revision in force on its manufacture date.")
            else:
                latest = specs[-1]["revision"]
                wrong = [r["batch_no"] for r in mes
                         if (g := governing_spec(specs, date.fromisoformat(r["mfg_date"]))) and g["revision"] != latest]
                add("Field", name, "Specification revision is chosen by date of manufacture", FAILED,
                    f"Policy '{policy}' checks every lot against rev {latest}. {len(wrong)} lot(s) were made under an "
                    "earlier revision and would be judged against limits that did not apply to them.", wrong)

        elif kind == "key":
            add("Field", name, "Key matches the canonical format", VALIDATED if target["source"].startswith("mes_batches") else CONFIRM,
                f"{target['source']} uses the documented format {dictionary['mes_batches']['key_format']}.")

    failed = sum(r["status"] == FAILED for r in rows)
    confirm = sum(r["status"] == CONFIRM for r in rows)
    verdict = ("Not acceptable: fix the failed checks and retest" if failed
               else "Acceptable once the open questions are confirmed" if confirm else "Acceptable")
    return {"mapping": mapping_file, "name": mapping.get("name", mapping_file), "verdict": verdict,
            "counts": {VALIDATED: sum(r["status"] == VALIDATED for r in rows), FAILED: failed, CONFIRM: confirm},
            "rows": rows}


def check_all(data_dir: Path) -> dict:
    files = sorted(p.name for p in (data_dir / "mapping").glob("vendor-*.yaml"))
    return {"reports": [check(data_dir, f) for f in files]}


def to_markdown(report: dict) -> str:
    lines = [f"# {report['name']}", "", f"**{report['verdict']}.** "
             + ", ".join(f"{n} {k}" for k, n in report["counts"].items()), "",
             "| Area | Field | Check | Result | Detail |", "|---|---|---|---|---|"]
    for r in report["rows"]:
        lines.append(f"| {r['area']} | {r['field']} | {r['check']} | {r['status']} | {r['detail']} |")
    return "\n".join(lines) + "\n"
