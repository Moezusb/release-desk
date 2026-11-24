"""Tests run offline: no API key, no network, no infrastructure."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from release_desk import config
from release_desk.documents import load_lot, load_spec
from release_desk.evaluate import score
from release_desk.evidence import verify
from release_desk.offline import OfflineProvider
from release_desk.pipeline import decide, deferring_approver, pending_approver, run_review
from release_desk.rules import evaluate, in_range, parse_number
from release_desk.schemas import LotExtraction
from release_desk.store import Store

from continuum.agent.approval import ToolApprovalDecision
from continuum.llm.providers import register_provider
from continuum.llm.types import FunctionCall, LLMResponse, ToolCall, Usage

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path):
    return replace(config.load(offline=True), runs_dir=tmp_path)


def fixture(lot: str) -> LotExtraction:
    return LotExtraction.model_validate_json((ROOT / "release_desk" / "fixtures" / f"{lot}.json").read_text())


# ------------------------------------------------------------------ rules


def test_parse_number_handles_commas_bounds_and_words():
    assert parse_number("38,200") == ("", 38200.0)
    assert parse_number("<10") == ("<", 10.0)
    assert parse_number("Pending") is None
    assert parse_number(None) is None


def test_limits_are_inclusive_and_bounds_are_honest():
    assert in_range("", 6.0, 5.0, 6.0)           # pH exactly on the limit passes
    assert not in_range("", 6.01, 5.0, 6.0)
    assert in_range("<", 10, None, 10)           # '<10' meets 'not more than 10'
    assert not in_range("<", 10, 5, None)        # but can never prove a minimum


def test_missing_result_fails_closed(settings):
    pkg, spec = load_lot(settings.data_dir, "LC-24031"), load_spec(settings.data_dir)
    ext = fixture("LC-24031")
    ext.certificate.results = [r for r in ext.certificate.results if r.key != "tamc_cfu_g"]
    rules = {f.rule: f for f in evaluate(pkg, ext, spec)}
    assert rules["test.tamc_cfu_g.missing"].severity == "critical"


def test_same_person_cannot_verify_their_own_step(settings):
    pkg, spec = load_lot(settings.data_dir, "LC-24031"), load_spec(settings.data_dir)
    ext = fixture("LC-24031")
    step = ext.batch_record.steps[0]
    step.verified_by = step.performed_by.model_copy()
    assert "batch.self_verified" in {f.rule for f in evaluate(pkg, ext, spec)}


# --------------------------------------------------------------- evidence


def test_a_claim_without_evidence_is_treated_as_no_claim(settings):
    pkg = load_lot(settings.data_dir, "LC-24034")
    ext, notes = verify(pkg, fixture("LC-24034"))
    assert [n.field for n in notes] == ["batch_record.step7.verified_by"]
    assert ext.batch_record.steps[6].verified_by.value is None


def test_a_wrong_line_number_is_refused(settings):
    pkg = load_lot(settings.data_dir, "LC-24032")
    ext = fixture("LC-24032")
    tymc = next(r for r in ext.certificate.results if r.key == "tymc_cfu_g")
    tymc.result.value, tymc.result.quote = "<10", "<10"   # the line above says <10; this one says 40
    ext, notes = verify(pkg, ext)
    assert notes and notes[0].field == "certificate.results.tymc_cfu_g"


# -------------------------------------------------------- whole pipeline


async def test_every_lot_matches_the_golden_answers(settings):
    result = await score(settings)
    assert result["unsafe_release_proposals"] == 0
    assert result["exception_recall"] == "7/7"
    assert result["false_alarms"] == 0
    assert result["proposals_matching"] == "6/6"


async def test_no_answer_means_no_release(settings):
    settings = replace(settings, approval_timeout=0.5)
    review = await run_review(settings, Store(settings.runs_dir), "LC-24031", pending_approver)
    assert review.proposal["decision"] == "release"
    assert review.status == "on hold"
    assert any("No approval came back" in t["text"] for t in review.timeline)


async def test_a_crashing_approver_means_no_release(settings):
    async def broken(review, request):
        raise RuntimeError("approval service down")

    review = await run_review(settings, Store(settings.runs_dir), "LC-24031", broken)
    assert review.status == "on hold"


async def test_approved_release_goes_through(settings):
    store = Store(settings.runs_dir)
    task = asyncio.create_task(run_review(settings, store, "LC-24031", pending_approver))
    for _ in range(100):
        await asyncio.sleep(0.05)
        r = store.get("LC-24031")
        if r.pending and not r.pending.done():
            break
    assert decide(store, r, "approve_release", "T. Tester") is None
    review = await task
    assert review.status == "released" and review.stage == "decided"
    log = (settings.runs_dir / "decisions.jsonl").read_text().splitlines()
    assert json.loads(log[-1])["reviewer"] == "T. Tester"


class RecklessProvider(OfflineProvider):
    """Reads like the offline model, but always proposes release."""

    async def acomplete(self, messages, config, tools=None, tool_choice=None):
        if "Role: disposition" not in str(messages[0].get("content")) or any(m.get("role") == "tool" for m in messages):
            return await super().acomplete(messages, config, tools, tool_choice)
        lot = str(messages[-1]["content"]).split("Lot: ")[1].split()[0]
        name = next(t["function"]["name"] for t in tools if t["function"]["name"].endswith("release_lot"))
        args = json.dumps({"lot_id": lot, "rationale": "Looks fine to me.", "finding_ids": []})
        return LLMResponse(model=config.model, tool_calls=[ToolCall(id="r1", function=FunctionCall(name=name, arguments=args))],
                           usage=Usage(), finish_reason="tool_calls")


async def test_even_an_approved_release_is_refused_when_findings_are_open(settings):
    register_provider("reckless/", lambda c, s: RecklessProvider())
    settings = replace(settings, model="reckless/x")
    store = Store(settings.runs_dir)

    async def rubber_stamp(review, request):
        review.decision = {"action": "approve_release", "reviewer": "Rubber Stamp", "reason": "", "at": "", "override": False}
        return ToolApprovalDecision(approved=True, reviewer="Rubber Stamp")

    review = await run_review(settings, store, "LC-24032", rubber_stamp)
    assert review.second_reading["agrees"] is False          # the second reader objected
    assert review.status == "on hold"                        # and the release tool refused anyway
    assert review.decision["outcome"] == "refused by the release tool"


# --------------------------------------------------------------- decisions


async def test_decisions_need_a_name_and_overrides_need_a_reason(settings):
    store = Store(settings.runs_dir)
    review = await run_review(settings, store, "LC-24033", deferring_approver)
    assert decide(store, review, "reject", "", "x") == "A decision needs the reviewer's name."
    assert decide(store, review, "release_over_hold", "T. Tester") == "This decision needs a reason."
    assert decide(store, review, "approve_release", "T. Tester") == "There is no release proposal waiting for approval."
    assert decide(store, review, "confirm_hold", "T. Tester") is None
    assert decide(store, review, "reject", "T. Tester", "late") == "This lot is not waiting for a hold decision."


def test_golden_file_covers_every_lot(settings):
    gold = yaml.safe_load((settings.data_dir / "golden.yaml").read_text())
    assert sorted(gold) == sorted(p.name for p in (settings.data_dir / "lots").iterdir() if p.is_dir())
