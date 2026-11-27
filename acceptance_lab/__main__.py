"""Acceptance lab command line.

    python -m acceptance_lab evaluate eval/results-offline.json   score one result bundle
    python -m acceptance_lab check-mapping [proposal.yaml]       check vendor mappings
    python -m acceptance_lab build                               write docs/acceptance.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .build import DATA, build
from .evaluate import evaluate
from .mapping import check, check_all, to_markdown


def main() -> None:
    p = argparse.ArgumentParser(prog="acceptance_lab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("evaluate")
    e.add_argument("bundle")
    e.add_argument("--output")
    m = sub.add_parser("check-mapping")
    m.add_argument("proposal", nargs="?", default="all")
    sub.add_parser("build")
    a = p.parse_args()
    if a.cmd == "evaluate":
        rep = evaluate(json.loads(Path(a.bundle).read_text()), DATA)
        print(f"{rep['recommendation']['verdict']}. {rep['recommendation']['why']}")
        for g in rep["gates"]:
            print(f"  {'pass' if g['passed'] else 'FAIL'}  {g['gate']}")
        for k, v in rep["metrics"].items():
            print(f"  {v['display']:>7}  {v['label']}")
        if a.output:
            Path(a.output).write_text(json.dumps(rep, indent=1))
    elif a.cmd == "check-mapping":
        reps = check_all(DATA)["reports"] if a.proposal == "all" else [check(DATA, a.proposal)]
        for r in reps:
            print(to_markdown(r))
    else:
        rep = build()
        s = rep["summary"]
        print(f"Wrote docs/acceptance.json: {s['candidates']} candidates, {s['mapping_scenarios']} mapping scenarios.")
        for c in rep["candidates"]:
            print(f"  {c['label']}: {c['recommendation']['verdict']} ({c['metrics']['case_acceptance']['display']} runs pass)")


if __name__ == "__main__":
    main()
