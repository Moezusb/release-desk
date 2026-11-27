"""Assemble the acceptance lab's evidence into docs/acceptance.json for the showcase.

Candidates are result bundles from Release Desk (offline, and live when one has
been recorded) plus two authored failure tests made by altering a copy of the
offline bundle. The failure tests exist to prove the evaluator catches what it
claims to catch; they are not observed model failures.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .evaluate import GATES, evaluate, load_labels
from .mapping import check_all

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

LIMITATIONS = [
    "Seven synthetic lots and hand-written labels. Passing them shows the controls work on these cases, not production readiness or compliance.",
    "Evidence checks confirm that each labelled exception cites a line about the right attribute with the right value. They do not judge free text.",
    "Offline runs use a scripted model, so they test the checks and controls, not a model's reading. Repeats of a scripted run agree by construction.",
    "Repeats of one lot are not independent cases. Agreement is reported apart from correctness.",
    "The failure tests are authored: each alters a copy of real output to plant one known defect.",
    "An acceptance verdict here is not a lot-release decision. Real thresholds, criticality and pilot exit criteria belong to the real stakeholders.",
]


def _first_repeat(bundle: dict) -> dict:
    b = copy.deepcopy(bundle)
    b["runs"] = [r for r in b["runs"] if r.get("run") == 1]
    b["repeat"] = 1
    return b


def inject_missed_critical(bundle: dict) -> dict:
    """Remove the yeast and mould exception on LC-24032 and turn its hold into a release."""
    b = _first_repeat(bundle)
    for r in b["runs"]:
        if r["lot"] == "LC-24032":
            r["findings_detail"] = [f for f in r["findings_detail"] if not f["rule"].startswith("test.tymc_cfu_g")]
            r["findings"] = [f["rule"] for f in r["findings_detail"]]
            r["proposal"] = "release"
    return b


def inject_wrong_field(bundle: dict) -> dict:
    """Keep the right label and the hold on LC-24032, but cite the aerobic-count row instead of yeast and mould."""
    b = _first_repeat(bundle)
    lines = (DATA / "lots" / "LC-24032" / "certificate_of_analysis.md").read_text(encoding="utf-8").splitlines()
    n = next(i for i, t in enumerate(lines, 1) if "aerobic" in t.lower())
    for r in b["runs"]:
        if r["lot"] == "LC-24032":
            for f in r["findings_detail"]:
                if f["rule"].startswith("test.tymc_cfu_g"):
                    f["evidence"] = [{"document": "certificate_of_analysis.md", "line": n, "text": lines[n - 1]}]
    return b


def build(out: Path | None = None) -> dict:
    labels = load_labels()
    candidates = []
    live = ROOT / "eval" / "results-live.json"
    offline = ROOT / "eval" / "results-offline.json"
    if live.exists():
        candidates.append(evaluate(json.loads(live.read_text()), DATA, labels, {
            "id": "executed-live", "label": "Executed live workflow", "kind": "executed_live",
            "description": "Real runs of the Release Desk pipeline with a live model, recorded in GitHub Actions."}))
    if offline.exists():
        bundle = json.loads(offline.read_text())
        candidates.append(evaluate(bundle, DATA, labels, {
            "id": "executed-offline", "label": "Executed offline workflow", "kind": "executed_offline",
            "description": "Real runs of the Release Desk pipeline with the scripted stand-in model. They exercise the checks, "
                           "rules and controls; they do not measure a model."}))
        candidates.append(evaluate(inject_missed_critical(bundle), DATA, labels, {
            "id": "injected-missed-critical", "label": "Injected: missed critical exception", "kind": "authored_failure",
            "description": "A copy of the offline output with the yeast and mould exception on LC-24032 removed and its hold "
                           "turned into a release. Authored to prove the evaluator refuses it."}))
        candidates.append(evaluate(inject_wrong_field(bundle), DATA, labels, {
            "id": "injected-wrong-field", "label": "Injected: valid citation, wrong field", "kind": "authored_failure",
            "description": "Keeps the right exception label and the hold on LC-24032, but cites the aerobic-count row. "
                           "The quote is real; it does not support the finding."}))
    mapping = check_all(DATA)
    uat = yaml.safe_load((Path(__file__).parent / "uat.yaml").read_text(encoding="utf-8"))
    measured = next((c["usage"] for c in candidates if c["kind"] == "executed_live"), None)
    report = {
        "schema_version": "acceptance-lab.report.v2",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "title": "Acceptance lab",
        "labels": labels,
        "gates": GATES,
        "candidates": candidates,
        "mapping": mapping,
        "uat": uat["tasks"],
        "value": {"measured": measured, "assumptions": {"lots_per_month": 100, "manual_minutes": 30, "assisted_minutes": 15,
                                                        "rework_minutes": 5, "operating_hours": 4}},
        "summary": {
            "lots": len(labels["labels"]),
            "labelled_exceptions": sum(len(v["exceptions"]) for v in labels["labels"].values()),
            "critical_exceptions": sum(1 for v in labels["labels"].values() for e in v["exceptions"] if e["severity"] == "critical"),
            "candidates": len(candidates),
            "mapping_scenarios": len(mapping["reports"]),
            "mapping_challenges_caught": sum(1 for r in mapping["reports"] if r["kind"] == "challenge" and r["self_check"]["passed"]),
            "mapping_challenges": sum(1 for r in mapping["reports"] if r["kind"] == "challenge"),
            "failure_tests_refused": sum(1 for c in candidates if c["kind"] == "authored_failure" and not c["summary"]["acceptance_passed"]),
            "live_run": live.exists(),
        },
        "limitations": LIMITATIONS,
    }
    out = out or ROOT / "docs" / "acceptance.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return report
