"""Independent acceptance of a Release Desk result bundle.

This module does not import release_desk. It reads three things on its own:
the result bundle a candidate produced, the reference labels in labels.yaml,
and the lot documents themselves. Then it asks, run by run:

  * Is the run well formed, unique, error-free, and made on the original documents?
  * Does the proposal match the label? Above all, is anything released that should be held?
  * Is every labelled exception present, at the right severity?
  * Does each one cite a line that really says what the finding claims:
    the right document, the right attribute, the right value?
  * Did the candidate raise anything nobody expected?

A citation that resolves to real text is not enough. The line must be about the
attribute in question, which is how a correct label with the wrong evidence is
caught.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).parent
DOCS = ("certificate", "batch_record", "deviation_log")
FILES = {"certificate": "certificate_of_analysis.md", "batch_record": "batch_record.md", "deviation_log": "deviation_log.md"}

GATES = [
    {"id": "coverage", "gate": "Coverage and identity",
     "rule": "Every labelled lot appears once per repeat, with a unique run ID, on the original documents, without errors."},
    {"id": "unsafe", "gate": "No unsafe clearance",
     "rule": "No release is proposed for a lot labelled hold."},
    {"id": "detection", "gate": "Exception detection with evidence",
     "rule": "Every labelled exception is present at the right severity, citing a line about the right attribute."},
    {"id": "completion", "gate": "Useful completion",
     "rule": "The clean lot is proposed for release. Holding everything is not a pass."},
    {"id": "burden", "gate": "Reviewer burden",
     "rule": "No unexpected findings. On a finite labelled set, extras are noise a reviewer must clear."},
]


def _norm(s: str | None) -> str:
    return " ".join((s or "").lower().split())


def load_labels(path: Path | None = None) -> dict:
    return yaml.safe_load((path or HERE / "labels.yaml").read_text(encoding="utf-8"))


def _doc_lines(data_dir: Path, lot: str) -> dict[str, list[str]]:
    folder = data_dir / "lots" / lot
    return {FILES[s]: (folder / FILES[s]).read_text(encoding="utf-8").splitlines() for s in DOCS}


def _fingerprint(data_dir: Path, lot: str) -> str:
    """The same recipe the desk documents for its fingerprint, recomputed here from the files."""
    folder = data_dir / "lots" / lot
    h = hashlib.sha256()
    for s in DOCS:
        h.update(s.encode())
        h.update("\n".join((folder / FILES[s]).read_text(encoding="utf-8").splitlines()).encode())
    return h.hexdigest()[:16]


def _metric(label: str, num: int, den: int) -> dict:
    return {"label": label, "numerator": num, "denominator": den, "value": (num / den) if den else None,
            "display": f"{num}/{den}"}


def evaluate(bundle: dict, data_dir: Path, labels: dict | None = None, candidate: dict | None = None) -> dict:
    labels = labels or load_labels()
    ref = labels["labels"]
    runs = bundle.get("runs", [])
    repeat = int(bundle.get("repeat") or 1)
    docs = {lot: _doc_lines(data_dir, lot) for lot in ref}
    prints = {lot: _fingerprint(data_dir, lot) for lot in ref}

    seen_ids, seen_slots = Counter(r.get("run_id") for r in runs), Counter((r.get("lot"), r.get("run")) for r in runs)
    cases, m = [], Counter()
    for r in runs:
        lot = r.get("lot")
        label = ref.get(lot)
        checks = []

        def check(cid, ok, message, expected=None, actual=None):
            checks.append({"id": cid, "passed": bool(ok), "message": message, "expected": expected, "actual": actual})
            return ok

        check("labelled", label is not None, "The lot must be one the reference labels cover.", "a labelled lot", lot)
        if label is None:
            cases.append({"lot": lot, "run": r.get("run"), "passed": False, "checks": checks, "findings": []})
            continue
        check("schema", r.get("schema", "").startswith("release-desk.run") and r.get("mode") in ("offline", "live"),
              "Run schema and execution mode must be declared.", "release-desk.run.*, mode", [r.get("schema"), r.get("mode")])
        check("identity", r.get("run_id") and seen_ids[r.get("run_id")] == 1 and seen_slots[(lot, r.get("run"))] == 1,
              "Run IDs and (lot, repeat) pairs must be unique.", "unique", r.get("run_id"))
        check("no_error", not r.get("error"), "A run that failed cannot pass.", None, r.get("error"))
        check("source_snapshot", r.get("document_fingerprint") == prints[lot] and not r.get("versions"),
              "The run must have read the original documents the labels describe.", prints[lot], r.get("document_fingerprint"))
        proposal = r.get("proposal")
        unsafe = proposal == "release" and label["proposal"] == "hold"
        m["unsafe"] += unsafe
        check("no_unsafe_release", not unsafe, "No release may be proposed for a lot labelled hold.", label["proposal"], proposal)
        check("proposal", proposal == label["proposal"], "The proposal must match the label.", label["proposal"], proposal)

        found = {f["rule"]: f for f in r.get("findings_detail", [])}
        finding_checks = []
        for ex in label["exceptions"]:
            f = found.get(ex["rule"])
            present = f is not None
            sev_ok = present and f["severity"] == ex["severity"]
            support, where = False, None
            for ev in (f or {}).get("evidence", []):
                if ev.get("document") != ex["cite"] or not ev.get("line"):
                    continue
                lines = docs[lot][ex["cite"]]
                text = lines[ev["line"] - 1] if 0 < ev["line"] <= len(lines) else ""
                where = f"{ex['cite']} line {ev['line']}: {text.strip()}"
                if _norm(ex["mentions"]) in _norm(text) and (not ex.get("shows") or _norm(ex["shows"]) in _norm(text)):
                    support = True
                    break
            m["expected"] += 1
            m["found"] += present
            m["supported"] += present and sev_ok and support
            if ex["severity"] == "critical":
                m["critical"] += 1
                m["critical_supported"] += present and sev_ok and support
            finding_checks.append({"rule": ex["rule"], "severity": ex["severity"], "present": present,
                                   "severity_ok": bool(sev_ok), "supported": bool(support), "cited": where,
                                   "needs": f"{ex['cite']}, a line mentioning '{ex['mentions']}'"
                                            + (f" and showing '{ex['shows']}'" if ex.get("shows") else "")})
        check("exceptions", all(fc["present"] and fc["severity_ok"] and fc["supported"] for fc in finding_checks),
              "Every labelled exception must be present, at the right severity, with supporting evidence.",
              [e["rule"] for e in label["exceptions"]], [fc["rule"] for fc in finding_checks if fc["present"]])
        extra = sorted(set(found) - {e["rule"] for e in label["exceptions"]})
        m["extra"] += len(extra)
        check("no_unexpected", not extra, "Unexpected findings are reviewer burden on a finite labelled set.", [], extra)

        # Every citation in the run, labelled or not, must resolve to real text.
        for f in r.get("findings_detail", []):
            for ev in f.get("evidence", []):
                if not ev.get("line"):
                    continue
                lines = docs[lot].get(ev.get("document"), [])
                ok = 0 < ev["line"] <= len(lines) and _norm(lines[ev["line"] - 1]) == _norm(ev.get("text"))
                m["citations"] += 1
                m["citations_ok"] += ok

        passed = all(c["passed"] for c in checks)
        m["runs"] += 1
        m["passed"] += passed
        m["proposal_ok"] += proposal == label["proposal"]
        if label["proposal"] == "release":
            m["clean"] += 1
            m["clean_ok"] += proposal == "release"
        cases.append({"lot": lot, "run": r.get("run"), "run_id": r.get("run_id"), "expected_proposal": label["proposal"],
                      "proposal": proposal, "passed": passed, "reasons": [c["message"] for c in checks if not c["passed"]],
                      "checks": checks, "findings": finding_checks, "unexpected": extra})

    expected_runs = len(ref) * repeat
    missing = sorted({(lot, i) for lot in ref for i in range(1, repeat + 1)} - set(seen_slots))
    agreement = []
    for lot in ref:
        outs = [json.dumps([c["proposal"], sorted(fc["rule"] for fc in c["findings"] if fc["present"]), c["unexpected"]])
                for c in cases if c["lot"] == lot]
        lot_cases = [c for c in cases if c["lot"] == lot]
        agreement.append({"lot": lot, "observations": len(outs), "distinct_outputs": len(set(outs)),
                          "agree": len(set(outs)) <= 1, "all_correct": bool(lot_cases) and all(c["passed"] for c in lot_cases)})

    metrics = {
        "case_acceptance": _metric("Runs passing every check", m["passed"], expected_runs),
        "known_exception_recall": _metric("Labelled exceptions found", m["found"], m["expected"]),
        "supported_exception_recall": _metric("Labelled exceptions found with supporting evidence", m["supported"], m["expected"]),
        "critical_exception_recall": _metric("Critical exceptions found with supporting evidence", m["critical_supported"], m["critical"]),
        "proposal_match": _metric("Proposals matching the label", m["proposal_ok"], expected_runs),
        "clean_completion": _metric("Clean lots proposed for release", m["clean_ok"], m["clean"]),
        "citation_validity": _metric("Citations resolving to the source text", m["citations_ok"], m["citations"]),
    }
    gate_results = {
        "coverage": not missing and m["runs"] == expected_runs and all(
            all(ch["passed"] for ch in c["checks"] if ch["id"] in ("labelled", "schema", "identity", "no_error", "source_snapshot")) for c in cases),
        "unsafe": m["unsafe"] == 0,
        "detection": m["supported"] == m["expected"],
        "completion": m["clean"] > 0 and m["clean_ok"] == m["clean"],
        "burden": m["extra"] == 0,
    }
    live = bundle.get("mode", "").startswith("live")
    if not all(gate_results.values()):
        verdict = "Not ready for a pilot"
        why = "Failed: " + ", ".join(g["gate"].lower() for g in GATES if not gate_results[g["id"]]) + "."
    elif not live:
        verdict = "Further evidence required"
        why = ("Every gate passes, but these runs used a scripted model. They prove the checks and controls, "
               "not a model's reading. A live run on this set is the next piece of evidence.")
    else:
        verdict = "Ready for business validation"
        why = ("Every gate passes on a live model, on seven synthetic lots. That is as far as fixtures can go. "
               "A pilot needs labels, thresholds and lots from the people who own the process.")
    return {
        "schema_version": "acceptance-lab.candidate-report.v2",
        "id": (candidate or {}).get("id", "candidate"), "label": (candidate or {}).get("label", "Candidate"),
        "kind": (candidate or {}).get("kind", "executed"), "description": (candidate or {}).get("description", ""),
        "origin": {"mode": bundle.get("mode"), "model": bundle.get("model"), "commit": bundle.get("commit"),
                   "produced": bundle.get("when"), "repeat": repeat},
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": {"runs_submitted": len(runs), "runs_expected": expected_runs, "runs_passed": m["passed"],
                    "missing_runs": len(missing), "unsafe_release_outputs": m["unsafe"], "unexpected_findings": m["extra"],
                    "acceptance_passed": all(gate_results.values())},
        "metrics": metrics,
        "gates": [{**g, "passed": gate_results[g["id"]]} for g in GATES],
        "recommendation": {"verdict": verdict, "why": why},
        "cases": cases,
        "repeat_agreement": agreement,
        "usage": {k: bundle.get("summary", {}).get(k) for k in
                  ("mean_seconds_per_lot", "mean_input_tokens_per_lot", "mean_output_tokens_per_lot")},
    }
