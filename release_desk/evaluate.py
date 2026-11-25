"""Score the desk against the answers a careful reviewer would give.

Correctness comes first; consistency second. Five runs that agree on a wrong
answer are worse than useless, so each run is judged on its own against
data/golden.yaml before any agreement between runs is counted.

The measures, in order of importance:
  false clears             a release proposed where a hold was due. Must be zero.
  blocking findings found  share of the planted problems found, across every run
  clean-case completion    clean lots proposed for release; a desk that holds
                           everything would score perfectly on the first two
  all-runs-correct lots    lots right in every run, not just on average
  lots with any failure    where to look first
  agreement                how often runs produce the same findings (secondary)

Nobody approves anything during an evaluation; release proposals are left
waiting, so an evaluation can never release a lot. Each run starts from a
clean state. Results are written as a bundle (eval/results-*.json) that other
tools can score independently.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import ROOT, Settings
from .pipeline import deferring_approver, run_review
from .store import Store


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except Exception:  # pragma: no cover
        return "unknown"


async def score(settings: Settings, repeat: int = 1) -> dict:
    gold = yaml.safe_load((settings.data_dir / "golden.yaml").read_text(encoding="utf-8"))
    lots, runs_out = [], []
    for lot, answer in gold.items():
        want = set(answer["expected_findings"])
        runs = []
        for i in range(repeat):
            store = Store(Path(tempfile.mkdtemp(prefix="release-desk-eval-")))  # clean state per run
            review = await run_review(settings, store, lot, deferring_approver)
            got = {f["rule"] for f in review.findings}
            proposal = (review.proposal or {}).get("decision", "none")
            run = {
                "lot": lot, "run": i + 1, "findings": sorted(got), "missed": sorted(want - got), "extra": sorted(got - want),
                "proposal": proposal, "expected_proposal": answer["expected_proposal"],
                "false_clear": proposal == "release" and answer["expected_proposal"] == "hold",
                "refused_claims": len(review.evidence_notes),
                "investigator_calls": [c["tool"] for c in review.investigation.get("calls", [])],
                "notes": [n["next_step"] for n in review.investigation.get("notes", [])],
                "usage": review.usage, "error": review.error,
            }
            run["correct"] = not run["missed"] and not run["extra"] and proposal == answer["expected_proposal"] and not review.error
            runs.append(run)
            runs_out.append(run)
        sets = Counter(tuple(r["findings"]) for r in runs)
        lots.append({
            "lot": lot, "expected": sorted(want), "expected_proposal": answer["expected_proposal"],
            "runs_correct": sum(r["correct"] for r in runs), "runs": repeat,
            "all_correct": all(r["correct"] for r in runs), "any_failure": not all(r["correct"] for r in runs),
            "false_clears": sum(r["false_clear"] for r in runs),
            # A blocking finding seen in any run stays visible, even if other runs missed it.
            "seen_in_any_run": sorted(set().union(*(set(r["findings"]) for r in runs))),
            "missed_in_some_run": sorted(set().union(*(set(r["missed"]) for r in runs))),
            "agreement": round(sets.most_common(1)[0][1] / repeat, 2),
            "investigator_paths": sorted({" > ".join(r["investigator_calls"]) for r in runs}),
        })

    expected_total = sum(len(l["expected"]) * repeat for l in lots)
    found_total = sum(len(set(r["findings"]) & set(next(l for l in lots if l["lot"] == r["lot"])["expected"])) for r in runs_out)
    clean = [r for r in runs_out if r["expected_proposal"] == "release"]
    usage = [r["usage"] for r in runs_out if r.get("usage")]
    mean = lambda k: round(sum(u.get(k, 0) for u in usage) / len(usage), 1) if usage else None  # noqa: E731
    return {
        "bundle_version": 1,
        "mode": "offline (scripted stand-in model)" if settings.offline else "live",
        "model": settings.model, "commit": _commit(),
        "when": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "repeat": repeat, "lots": len(lots),
        "summary": {
            "false_clears": sum(r["false_clear"] for r in runs_out),
            "blocking_findings_found": f"{found_total}/{expected_total}",
            "clean_case_completion": f"{sum(r['proposal'] == 'release' for r in clean)}/{len(clean)}",
            "all_runs_correct_lots": f"{sum(l['all_correct'] for l in lots)}/{len(lots)}",
            "lots_with_any_failure": [l["lot"] for l in lots if l["any_failure"]],
            "unexpected_findings": sum(len(r["extra"]) for r in runs_out),
            "mean_seconds_per_lot": mean("seconds"),
            "mean_input_tokens_per_lot": mean("input_tokens"),
            "mean_output_tokens_per_lot": mean("output_tokens"),
        },
        "per_lot": lots,
        "runs": runs_out,
    }


def to_markdown(r: dict) -> str:
    s = r["summary"]
    lines = [
        "# Evaluation report", "",
        f"Mode: {r['mode']}. Model: {r['model']}. Commit: {r['commit']}. Run: {r['when']}. "
        f"{r['lots']} lots, {r['repeat']} run(s) each, every run from a clean state.", "",
        "| Measure | Result |", "|---|---|",
        f"| False clears: release proposed where a hold was due (must be 0) | {s['false_clears']} |",
        f"| Blocking findings found, across all runs | {s['blocking_findings_found']} |",
        f"| Clean lots proposed for release | {s['clean_case_completion']} |",
        f"| Lots correct in every run | {s['all_runs_correct_lots']} |",
        f"| Lots with at least one failed run | {', '.join(s['lots_with_any_failure']) or 'none'} |",
        f"| Unexpected findings | {s['unexpected_findings']} |",
    ]
    if s["mean_seconds_per_lot"] is not None:
        lines.append(f"| Mean time per lot | {s['mean_seconds_per_lot']} s |")
    if s["mean_input_tokens_per_lot"]:
        lines.append(f"| Mean tokens per lot, in / out | {s['mean_input_tokens_per_lot']:,.0f} / {s['mean_output_tokens_per_lot']:,.0f} |")
    lines += ["", "| Lot | Expected findings | Runs correct | Missed in some run | Agreement | Investigator path |",
              "|---|---|---|---|---|---|"]
    for l in r["per_lot"]:
        lines.append(f"| {l['lot']} | {', '.join(l['expected']) or 'none'} | {l['runs_correct']}/{l['runs']} | "
                     f"{', '.join(l['missed_in_some_run']) or 'none'} | {l['agreement']:.0%} | "
                     f"{'; '.join(p for p in l['investigator_paths'] if p) or 'not needed'} |")
    if r["mode"].startswith("offline"):
        lines += ["", "Offline mode replays hand-written extractions and a scripted investigator, so this run tests the "
                  "evidence check, the rules and the approval path, not a model. Agreement is 100% by construction."]
    return "\n".join(lines) + "\n"


async def main(settings: Settings, repeat: int = 1) -> dict:
    result = await score(settings, repeat)
    tag = "offline" if settings.offline else "live"
    out = ROOT / "eval"
    out.mkdir(exist_ok=True)
    (out / f"report-{tag}.md").write_text(to_markdown(result), encoding="utf-8")
    (out / f"results-{tag}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(to_markdown(result))
    print(f"Written to eval/report-{tag}.md and eval/results-{tag}.json")
    return result
