"""Command line.

    release-desk serve                 the reviewer's desk in your browser
    release-desk review LC-24031       review one lot in the terminal (or: all)
    release-desk eval --repeat 5       score every lot against data/golden.yaml, 5 clean runs each
    release-desk check-mapping         check the vendor data mappings in data/mapping
    release-desk export-replay         write docs/replay.json for the static demo

Add --offline to any command to use the scripted stand-in model.
Without ANTHROPIC_API_KEY set, offline mode is used automatically.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from continuum.agent.approval import ToolApprovalDecision

from . import config
from .documents import list_lots
from .store import LotReview, Store


async def terminal_approver(review: LotReview, request) -> ToolApprovalDecision:
    p = review.proposal or {}
    print(f"\n  The desk proposes to RELEASE {review.lot_id}.")
    print(f"  Rationale: {p.get('rationale')}")
    if review.second_reading:
        r = review.second_reading
        print("  Second reader:", "agrees." if r["agrees"] else "disagrees. " + " ".join(r["concerns"]))
    answer = (await asyncio.to_thread(input, "  Approve release? Type your name to approve, or press Enter to refuse: ")).strip()
    if answer:
        review.decision = {"action": "approve_release", "reviewer": answer, "reason": "", "at": review.proposal["at"],
                           "override": False, "snapshot": review.approval_snapshot}
        return ToolApprovalDecision(approved=True, reviewer=answer)
    review.log("reviewer", "Refused at the terminal.")
    return ToolApprovalDecision(approved=False, reason="refused at the terminal")


def _print(review: LotReview) -> None:
    print(f"\n{review.lot_id}: {review.status.upper()}  ({review.mode})")
    for f in review.findings:
        print(f"  {f['id']} [{f['severity']}] {f['title']}: expected {f['expected']}, found {f['observed']}")
    if not review.findings:
        print("  No findings.")
    for n in review.evidence_notes:
        print(f"  Evidence refused: {n['field']} = {n['claimed_value']!r} (line {n['cited_line']}): {n['reason']}")


async def _review(settings: config.Settings, target: str) -> None:
    from .pipeline import run_review

    store = Store(settings.runs_dir)
    lots = list_lots(settings.data_dir) if target == "all" else [target]
    for lot in lots:
        review = await run_review(settings, store, lot, terminal_approver)
        if review.decision:
            store.record_decision(review, {**review.decision, "proposal": review.proposal["decision"]})
        _print(review)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="release-desk", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--offline", action="store_true", help="use the scripted stand-in model")
    parser.add_argument("--offline", action="store_true", help="use the scripted stand-in model")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", parents=[common])
    s.add_argument("--port", type=int, default=8930)
    s.add_argument("--host", default="127.0.0.1")
    r = sub.add_parser("review", parents=[common])
    r.add_argument("lot", help="a lot id, or 'all'")
    e = sub.add_parser("eval", parents=[common])
    e.add_argument("--repeat", type=int, default=1, help="runs per lot, each from a clean state")
    mp = sub.add_parser("check-mapping", parents=[common])
    mp.add_argument("mapping", nargs="?", default="all", help="a file in data/mapping, e.g. vendor-v1.yaml, or 'all'")
    sub.add_parser("export-replay", parents=[common])
    args = parser.parse_args(argv)
    settings = config.load(offline=True if args.offline else None)
    if settings.offline and args.cmd != "check-mapping":
        print("Offline mode: a scripted stand-in model, not a real one. Set ANTHROPIC_API_KEY for live runs.", file=sys.stderr)

    if args.cmd == "serve":
        import uvicorn

        from web.app import create_app

        uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="warning")
    elif args.cmd == "review":
        asyncio.run(_review(settings, args.lot))
    elif args.cmd == "eval":
        from .evaluate import main as run_eval

        result = asyncio.run(run_eval(settings, args.repeat))
        errored = [r for r in result["runs"] if r.get("error")]
        if errored:
            print(f"{len(errored)} of {len(result['runs'])} runs stopped with an error. First: {errored[0]['error'][:400]}", file=sys.stderr)
            raise SystemExit(1)
    elif args.cmd == "check-mapping":
        from acceptance_lab.mapping import check, check_all, to_markdown

        reports = check_all(settings.data_dir)["reports"] if args.mapping == "all" else [check(settings.data_dir, args.mapping)]
        for rep in reports:
            print(to_markdown(rep))
    elif args.cmd == "export-replay":
        from .replay import export

        asyncio.run(export(settings))


if __name__ == "__main__":
    main()
