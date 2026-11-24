"""Score the desk against the answers a careful reviewer would give.

The numbers that matter, in order:
  1. unsafe proposals: release proposed where a hold was due. Must be zero.
  2. exception recall: share of known problems the desk found.
  3. false alarms: findings nobody expected. Each one costs a reviewer's time.

Nobody approves anything during an evaluation; every release proposal is
left waiting, so a run can never release a lot.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import ROOT, Settings
from .pipeline import deferring_approver, run_review
from .store import Store


async def score(settings: Settings) -> dict:
    gold = yaml.safe_load((settings.data_dir / "golden.yaml").read_text(encoding="utf-8"))
    store = Store(Path(tempfile.mkdtemp(prefix="release-desk-eval-")))
    rows, expected_total, caught_total, false_alarms, unsafe, proposals_right = [], 0, 0, 0, 0, 0
    for lot, answer in gold.items():
        review = await run_review(settings, store, lot, deferring_approver)
        got = {f["rule"] for f in review.findings}
        want = set(answer["expected_findings"])
        caught, extra = want & got, got - want
        proposal = (review.proposal or {}).get("decision", "none")
        expected_total += len(want)
        caught_total += len(caught)
        false_alarms += len(extra)
        unsafe += int(proposal == "release" and answer["expected_proposal"] == "hold")
        proposals_right += int(proposal == answer["expected_proposal"])
        rows.append({"lot": lot, "expected": sorted(want), "missed": sorted(want - got), "extra": sorted(extra),
                     "proposal": proposal, "expected_proposal": answer["expected_proposal"],
                     "refused_claims": len(review.evidence_notes)})
    return {
        "mode": "offline (scripted stand-in model)" if settings.offline else f"live ({settings.model})",
        "when": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "lots": len(rows), "unsafe_release_proposals": unsafe,
        "exception_recall": f"{caught_total}/{expected_total}",
        "false_alarms": false_alarms, "proposals_matching": f"{proposals_right}/{len(rows)}", "rows": rows,
    }


def to_markdown(r: dict) -> str:
    lines = [
        "# Evaluation report", "",
        f"Mode: {r['mode']}. Run: {r['when']}. Lots: {r['lots']}.", "",
        "| Measure | Result |", "|---|---|",
        f"| Unsafe release proposals (must be 0) | {r['unsafe_release_proposals']} |",
        f"| Known exceptions found | {r['exception_recall']} |",
        f"| False alarms | {r['false_alarms']} |",
        f"| Proposals matching the expected one | {r['proposals_matching']} |", "",
        "| Lot | Expected findings | Missed | Unexpected | Proposal (expected) | Claims refused by evidence check |",
        "|---|---|---|---|---|---|",
    ]
    for row in r["rows"]:
        lines.append(f"| {row['lot']} | {', '.join(row['expected']) or 'none'} | {', '.join(row['missed']) or 'none'} | "
                     f"{', '.join(row['extra']) or 'none'} | {row['proposal']} ({row['expected_proposal']}) | {row['refused_claims']} |")
    if r["mode"].startswith("offline"):
        lines += ["", "Offline mode replays hand-written extractions, so this run tests the evidence check, the rules "
                  "and the approval path, not a model's reading. Run with ANTHROPIC_API_KEY set for that."]
    return "\n".join(lines) + "\n"


async def main(settings: Settings) -> None:
    result = await score(settings)
    md = to_markdown(result)
    out = ROOT / "eval" / ("report-offline.md" if settings.offline else "report-live.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"Written to {out}")
