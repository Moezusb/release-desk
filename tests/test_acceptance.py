"""The acceptance lab must pass honest output and refuse planted failures. Offline, no network."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from acceptance_lab.build import inject_missed_critical, inject_wrong_field
from acceptance_lab.evaluate import evaluate
from acceptance_lab.mapping import check_all

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BUNDLE = ROOT / "eval" / "results-offline.json"


@pytest.fixture(scope="module")
def bundle():
    if not BUNDLE.exists():
        pytest.skip("run `release-desk eval --offline --repeat 5` first")
    return json.loads(BUNDLE.read_text())


def failed_gates(result: dict) -> set[str]:
    return {g["id"] for g in result["gates"] if not g["passed"]}


def test_the_scorer_does_not_import_the_desk():
    tree = ast.parse((ROOT / "acceptance_lab" / "evaluate.py").read_text())
    modules = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    modules |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not any(m.startswith("release_desk") for m in modules)


def test_honest_offline_output_passes_every_gate_but_is_not_called_pilot_ready(bundle):
    result = evaluate(bundle, DATA)
    assert failed_gates(result) == set()
    assert result["metrics"]["critical_exception_recall"]["value"] == 1.0
    assert result["recommendation"]["verdict"] == "Further evidence required"   # scripted model, not a measured one


def test_a_missed_critical_exception_is_refused(bundle):
    result = evaluate(inject_missed_critical(bundle), DATA)
    assert {"unsafe", "detection"} <= failed_gates(result)
    assert result["recommendation"]["verdict"] == "Not ready for a pilot"


def test_a_real_quote_about_the_wrong_attribute_is_refused(bundle):
    result = evaluate(inject_wrong_field(bundle), DATA)
    assert failed_gates(result) == {"detection"}
    case = next(c for c in result["cases"] if c["lot"] == "LC-24032")
    assert not case["passed"] and any(f["present"] and not f["supported"] for f in case["findings"])


def test_every_authored_mapping_challenge_is_caught():
    reports = check_all(DATA)["reports"]
    challenges = [r for r in reports if r["kind"] == "challenge"]
    assert len(challenges) >= 4
    assert all(r["self_check"]["passed"] and r["counts"]["failed"] > 0 for r in challenges)
    first, revised = (next(r for r in reports if r["mapping"] == f) for f in ("vendor-v1.yaml", "vendor-v2.yaml"))
    assert first["counts"]["failed"] > 0
    assert revised["counts"]["failed"] == 0 and revised["counts"]["needs business confirmation"] == 1
