"""Tests run offline: no API key, no network, no infrastructure."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from release_desk import config
from release_desk.documents import load_lot, load_spec, load_specs
from release_desk.evaluate import score
from release_desk.evidence import verify
from release_desk.offline import OfflineProvider
from release_desk.pipeline import apply_correction, decide, deferring_approver, pending_approver, run_review
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
    pkg, spec = load_lot(settings.data_dir, "LC-24031"), load_specs(settings.data_dir)
    ext = fixture("LC-24031")
    ext.certificate.results = [r for r in ext.certificate.results if r.key != "tamc_cfu_g"]
    rules = {f.rule: f for f in evaluate(pkg, ext, spec)}
    assert rules["test.tamc_cfu_g.missing"].severity == "critical"


def test_same_person_cannot_verify_their_own_step(settings):
    pkg, spec = load_lot(settings.data_dir, "LC-24031"), load_specs(settings.data_dir)
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


def test_a_real_number_from_the_wrong_row_is_refused(settings):
    pkg, spec = load_lot(settings.data_dir, "LC-24032"), load_specs(settings.data_dir)[0]
    ext = fixture("LC-24032")
    tymc = next(r for r in ext.certificate.results if r.key == "tymc_cfu_g")
    tamc = next(r for r in ext.certificate.results if r.key == "tamc_cfu_g")
    tymc.result = tamc.result.model_copy()   # '<10' really is on that line, but it is the aerobic count
    ext, notes = verify(pkg, ext, spec)
    assert notes and "not about this attribute" in notes[0].reason


def test_the_governing_revision_is_chosen_by_date_of_manufacture(settings):
    pkg, specs = load_lot(settings.data_dir, "LC-24037"), load_specs(settings.data_dir)
    ext, _ = verify(pkg, fixture("LC-24037"), specs[-1])
    rules = {f.rule for f in evaluate(pkg, ext, specs)}
    assert rules == {"spec.wrong_revision", "test.viscosity_cp.out_of_spec"}
    # The same certificate would pass if judged by the revision it names.
    assert not {f.rule for f in evaluate(pkg, ext, specs[:1])} & {"test.viscosity_cp.out_of_spec"}


# -------------------------------------------------------- whole pipeline


async def test_every_lot_matches_the_golden_answers(settings):
    result = await score(settings)
    s = result["summary"]
    assert s["false_clears"] == 0
    assert s["blocking_findings_found"] == "9/9"
    assert s["unexpected_findings"] == 0
    assert s["all_runs_correct_lots"] == "7/7"
    assert s["clean_case_completion"] == "1/1"


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
    assert decide(settings, store, r, "approve_release", "T. Tester") is None
    review = await task
    assert review.status == "released" and review.stage == "decided"
    log = (settings.runs_dir / "decisions.jsonl").read_text().splitlines()
    assert json.loads(log[-1])["reviewer"] == "T. Tester"


async def test_an_approval_is_bound_to_the_assessment_the_reviewer_saw(settings):
    store = Store(settings.runs_dir)
    task = asyncio.create_task(run_review(settings, store, "LC-24031", pending_approver))
    for _ in range(100):
        await asyncio.sleep(0.05)
        r = store.get("LC-24031")
        if r.pending and not r.pending.done():
            break
    r.second_reading = {**r.second_reading, "agrees": False, "concerns": ["changed after the reviewer looked"]}
    assert decide(settings, store, r, "approve_release", "T. Tester").startswith("The assessment changed")
    assert decide(settings, store, r, "deny_release", "T. Tester", "stale") is None
    review = await task
    assert review.status == "on hold"


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
        review.decision = {"action": "approve_release", "reviewer": "Rubber Stamp", "reason": "", "at": "", "override": False,
                           "snapshot": review.approval_snapshot}
        return ToolApprovalDecision(approved=True, reviewer="Rubber Stamp")

    review = await run_review(settings, store, "LC-24032", rubber_stamp)
    assert review.second_reading["agrees"] is False          # the second reader objected
    assert review.status == "on hold"                        # and the release tool refused anyway
    assert review.decision["outcome"].startswith("refused by the release tool")


# --------------------------------------------------------------- decisions


async def test_decisions_need_a_name_and_overrides_need_a_reason(settings):
    store = Store(settings.runs_dir)
    review = await run_review(settings, store, "LC-24033", deferring_approver)
    assert decide(settings, store, review, "reject", "", "x") == "A decision needs the reviewer's name."
    assert decide(settings, store, review, "deny_release", "T. Tester") == "This decision needs a reason."
    assert decide(settings, store, review, "release_over_hold", "T. Tester", "x") == "Unknown action."  # removed on purpose
    assert decide(settings, store, review, "approve_release", "T. Tester") == "There is no release proposal waiting for approval."
    assert decide(settings, store, review, "confirm_hold", "T. Tester") is None
    assert decide(settings, store, review, "reject", "T. Tester", "late") == "This lot is not waiting for a hold decision."


async def test_the_investigator_reads_but_never_changes_findings(settings):
    review = await run_review(settings, Store(settings.runs_dir), "LC-24033", deferring_approver)
    tools = [c["tool"] for c in review.investigation["calls"]]
    assert tools == ["list_supporting_records", "open_record", "submit_note"]
    assert review.investigation["notes"][0]["next_step"] == "route_to_deviation_owner"
    assert [f["rule"] for f in review.findings] == ["deviation.open"]


async def test_different_evidence_takes_the_investigator_down_different_paths(settings):
    store = Store(settings.runs_dir)
    a = await run_review(settings, store, "LC-24036", deferring_approver)
    b = await run_review(settings, store, "LC-24037", deferring_approver)
    assert [c["tool"] for c in a.investigation["calls"]][0] == "list_corrected_documents"
    assert [c["tool"] for c in b.investigation["calls"]][0] == "get_specification"


async def test_a_correction_voids_the_old_decision_and_keeps_it_on_record(settings):
    store = Store(settings.runs_dir)
    review = await run_review(settings, store, "LC-24036", deferring_approver)
    assert decide(settings, store, review, "confirm_hold", "T. Tester") is None
    assert apply_correction(settings, store, review, "certificate", "v2") is None
    assert review.stage == "needs reassessment"
    assert decide(settings, store, review, "reject", "T. Tester", "x").startswith("The documents changed")
    again = await run_review(settings, store, "LC-24036", deferring_approver)
    assert again.history[-1]["decision"]["action"] == "confirm_hold"       # the old decision survives
    assert again.findings == [] and again.proposal["decision"] == "release"  # the new evidence is clean


def test_mapping_v1_is_blocked_and_v2_needs_one_confirmation(settings):
    from acceptance_lab.mapping import FAILED, check

    v1, v2 = check(settings.data_dir, "vendor-v1.yaml"), check(settings.data_dir, "vendor-v2.yaml")
    failed = {(r["field"], r["check"]) for r in v1["rows"] if r["status"] == FAILED}
    assert ("tymc_cfu_g", "Source means the same thing") in failed     # same type and unit, wrong meaning
    assert ("lot_id", "Every batch finds its laboratory results") in failed
    assert ("results", "One result per lot and test") in failed
    assert v2["counts"]["failed"] == 0 and v2["counts"]["needs business confirmation"] == 1


def test_golden_file_covers_every_lot(settings):
    gold = yaml.safe_load((settings.data_dir / "golden.yaml").read_text())
    assert sorted(gold) == sorted(p.name for p in (settings.data_dir / "lots").iterdir() if p.is_dir())


def test_numbers_are_read_with_their_units_but_ranges_and_words_fail_closed():
    from release_desk.rules import parse_number
    assert parse_number("98.4%") == ("", 98.4)          # the first live run copied the % sign
    assert parse_number("<10 CFU/g") == ("<", 10.0)
    assert parse_number("38,200 cP") == ("", 38200.0)
    assert parse_number("0.80% w/w") == ("", 0.8)
    for unreadable in ("Pending", "8 x 10^3", "10-20", "NMT 10", ""):
        assert parse_number(unreadable) is None


def test_a_negated_result_never_passes_a_text_test():
    from release_desk.rules import text_passes
    assert text_passes("Absent", ["absent"]) and text_passes("Absent in 1 g", ["absent"])
    for result in ("Not absent", "Present", "absence not confirmed"):
        assert not text_passes(result, ["absent"]), result          # pathogens are critical
    for result in ("Uncharacteristic", "Non-characteristic", "Not characteristic"):
        assert not text_passes(result, ["characteristic"]), result


def test_a_placeholder_is_not_a_signature():
    from release_desk.rules import signed
    assert signed("M. Chen, 2026-09-23") == "m. chen"
    for blank in ("N/A", "—", "-", "pending", "unsigned", "  ", "2026-09-17", None):
        assert signed(blank) is None, blank


def test_values_copied_with_their_labels_read_the_same():
    from release_desk.rules import code, day, month, revision
    assert code("Lot number: LC-24033") == "LC-24033"
    assert code("Product: Daily Barrier Cream, 50 g (FH-DBC-050)") == "FH-DBC-050"
    assert code("LC-24053") == "LC-24053"                       # a transposed lot stays transposed
    assert revision("rev 03") == revision("3") == revision("03") == 3
    assert day("Date of manufacture: 2026-09-17").isoformat() == "2026-09-17"
    assert month("Expiry: 2029-03") == month("2029-03-01") == "2029-03"


def test_typography_does_not_change_a_value():
    from release_desk.evidence import _norm
    from release_desk.rules import code
    assert code("FH‑DBC‑050") == "FH-DBC-050"               # non-breaking hyphens
    assert _norm("LC–24033") in _norm("Lot number: LC-24033")   # an en dash
