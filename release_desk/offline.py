"""A stand-in model, so the desk runs end to end without an API key.

It is a script, not a model, and it should not be mistaken for one:

* The reader returns saved extractions from ``fixtures/``. They were written
  by hand to match the synthetic documents, and one of them (LC-24034) carries
  a deliberate misquote so you can watch the evidence check refuse it.
* The disposition step proposes release when there are no blocking findings
  and a hold otherwise, as a careful model should.
* The second reader agrees when the proposal follows from the findings.
* The investigator follows a fixed plan per kind of finding, but still branches
  on what its tools return: no records on file means a different next step.

Set ANTHROPIC_API_KEY to run the real thing. Every other part of the pipeline
(the evidence check, the rules, the approval gate, the decision log) is the
same code in both modes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from continuum.llm.providers import BaseProvider, register_provider
from continuum.llm.types import FunctionCall, LLMResponse, ToolCall, Usage

FIXTURES = Path(__file__).parent / "fixtures"
_LOT = re.compile(r"Lot: (\S+)")


def _between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0].strip()


def _role(messages: list[dict[str, Any]]) -> str:
    system = " ".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
    m = re.search(r"Role: (\w+)", system)
    return m.group(1) if m else "unknown"


def _user(messages: list[dict[str, Any]]) -> str:
    return "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "user")


def _reply(model: str, content: str) -> LLMResponse:
    return LLMResponse(model=model, content=content, usage=Usage(), finish_reason="stop")


class OfflineProvider(BaseProvider):
    @staticmethod
    def supports_native_schema() -> bool:
        return False

    async def acomplete(self, messages, config, tools=None, tool_choice=None) -> LLMResponse:
        role, text = _role(messages), _user(messages)
        lot = (_LOT.search(text) or [None, "?"])[1]

        if role == "extractor":
            versions = re.search(r"Document versions: (.+)", text)
            tag = ""
            if versions and versions.group(1).strip() != "originals":
                tag = "." + ".".join(
                    part.strip().replace("certificate_of_analysis.md ", "certificate-").replace("batch_record.md ", "batch_record-")
                    .replace("deviation_log.md ", "deviation_log-") for part in versions.group(1).split(","))
            path = FIXTURES / f"{lot}{tag}.json"
            if not path.exists():
                return _reply(config.model, "{}")
            return _reply(config.model, path.read_text(encoding="utf-8"))

        if role == "second_reader":
            proposal = json.loads(_between(text, "PROPOSAL_JSON:", "END_PROPOSAL"))
            findings = json.loads(_between(text, "FINDINGS_JSON:", "END_FINDINGS"))
            blocking = [f for f in findings if f["severity"] in ("critical", "major")]
            if proposal["decision"] == "release" and blocking:
                out = {"agrees": False, "concerns": [f"Release proposed despite {f['id']}: {f['title']}" for f in blocking]}
            elif proposal["decision"] == "hold" and not blocking:
                out = {"agrees": False, "concerns": ["Hold proposed but no blocking finding supports it"]}
            else:
                out = {"agrees": True, "concerns": []}
            return _reply(config.model, json.dumps(out))

        if role == "investigator":
            return _investigate(config.model, messages, text, tools)

        if role == "disposition":
            if any(m.get("role") == "tool" for m in messages):
                return _reply(config.model, "Proposal recorded.")
            findings = json.loads(_between(text, "FINDINGS_JSON:", "END_FINDINGS"))
            blocking = [f for f in findings if f["severity"] in ("critical", "major")]
            names = [t.get("function", {}).get("name", "") for t in (tools or [])]
            if blocking:
                name = next(n for n in names if n.endswith("place_on_hold"))
                rationale = "Blocking findings: " + " ".join(f"{f['id']}: {f['title']}." for f in blocking)
                ids = [f["id"] for f in blocking]
            else:
                name = next(n for n in names if n.endswith("release_lot"))
                rationale = ("Every test is within specification, every step carries two signatures, "
                             "the documents agree on lot and dates, and no deviation is open.")
                ids = []
            args = {"lot_id": lot, "rationale": rationale, "finding_ids": ids}
            call = ToolCall(id="offline-1", function=FunctionCall(name=name, arguments=json.dumps(args)))
            return LLMResponse(model=config.model, tool_calls=[call], usage=Usage(), finish_reason="tool_calls")

        return _reply(config.model, "")

    def complete(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError("offline mode is async only")

    def stream(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    async def astream(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError


def _history(messages: list[dict[str, Any]]) -> list[tuple[str, dict, str]]:
    """(tool name without namespace, arguments, result) for each tool call so far."""
    def clean(text: str) -> str:  # Continuum wraps tool output in tags; the script wants the text
        return re.sub(r"</?[a-z_]+(?: [^>]*)?>", "", text).strip()

    results = {m.get("tool_call_id"): clean(str(m.get("content") or "")) for m in messages if m.get("role") == "tool"}
    out = []
    for m in messages:
        for call in m.get("tool_calls") or []:
            fn = call["function"] if isinstance(call, dict) else call.function
            name = fn["name"] if isinstance(fn, dict) else fn.name
            args = fn["arguments"] if isinstance(fn, dict) else fn.arguments
            cid = call["id"] if isinstance(call, dict) else call.id
            out.append((name.split("__")[-1], json.loads(args or "{}"), results.get(cid, "")))
    return out


def _plan(findings: list[dict]):
    """The scripted investigator. A generator: each `yield` is a tool call, and
    the tool's result is sent back in, so later steps branch on what was found."""
    blocking = [f for f in findings if f["severity"] in ("critical", "major")]
    rules = {f["rule"] for f in blocking}

    def ids(pred):
        return [f["id"] for f in blocking if pred(f)]

    def ev(fids):
        return [{"document": e["document"], "line": e["line"]} for f in blocking if f["id"] in fids
                for e in f.get("evidence", [])[:1] if e.get("line")]

    if "spec.wrong_revision" in rules:
        fids = ids(lambda f: f["rule"] == "spec.wrong_revision" or ("viscosity" in f["rule"] and f["rule"].endswith(".out_of_spec")))
        wrong = next(f for f in blocking if f["rule"] == "spec.wrong_revision")
        named, governing = wrong["observed"].split()[-1], wrong["expected"].split()[1].rstrip(",")
        yield ("get_specification", {"revision": named})
        yield ("get_specification", {"revision": governing})
        yield ("submit_note", {"finding_ids": fids, "next_step": "request_corrected_document",
               "summary": f"The certificate was tested against rev {named}, but rev {governing} was in force on the date of "
                          f"manufacture. The limits differ between the two, so a result can pass the revision cited and fail "
                          f"the one that governs. The laboratory should re-certify against rev {governing}.",
               "evidence": ev(fids), "open_questions": ["Why was the retired revision still in use at the laboratory?"]})

    if "identity.lot_mismatch" in rules or "dates.expiry" in rules or any(r.endswith(".missing") for r in rules):
        fids = ids(lambda f: f["rule"] in ("identity.lot_mismatch", "dates.expiry") or f["rule"].endswith(".missing"))
        listing = yield ("list_corrected_documents", {})
        if "certificate_of_analysis.md" in listing:
            version = listing.rsplit(" ", 1)[-1].strip(" .)")
            yield ("read_corrected_document", {"document": "certificate_of_analysis.md", "version": version})
            yield ("submit_note", {"finding_ids": fids, "next_step": "reassess_with_corrected_document",
                   "summary": f"A corrected certificate ({version}) is on file but not applied. It appears to address "
                              f"{', '.join(fids)}. These findings stand until a person applies the correction and the lot is reassessed.",
                   "evidence": ev(fids) + [{"document": f"corrections/certificate_of_analysis.{version}.md"}],
                   "open_questions": ["Is the corrected version the laboratory's approved one?"]})
        else:
            yield ("submit_note", {"finding_ids": fids, "next_step": "request_missing_evidence",
                   "summary": "No corrected document is on file, so the missing or inconsistent values cannot be resolved from the evidence available.",
                   "evidence": ev(fids)})

    rest = lambda f: f["rule"] == "deviation.open" or (f["rule"].endswith(".out_of_spec") and "viscosity" not in f["rule"])  # noqa: E731
    if any(rest(f) for f in blocking):
        fids = ids(rest)
        listing = yield ("list_supporting_records", {})
        names = listing.split(": ", 1)[1].split(", ") if listing.startswith("Records on file") else []
        if names:
            yield ("open_record", {"name": names[0]})
            dev = names[0].startswith("DEV")
            yield ("submit_note", {"finding_ids": fids,
                   "next_step": "route_to_deviation_owner" if dev else "confirm_with_laboratory",
                   "summary": names[0][:-3] + (" is on file. Its root cause is identified and a drafted impact assessment concludes no "
                               "impact, but the assessment is still awaiting QA approval, so the deviation remains open."
                               if dev else " is on file. The laboratory repeated the test in duplicate and confirmed the result; "
                               "an out-of-specification investigation is open."),
                   "evidence": ev(fids) + [{"document": f"records/{names[0]}"}],
                   "open_questions": ["Will QA approve the impact assessment?" if dev else "What does the OOS investigation conclude?"]})
        else:
            yield ("submit_note", {"finding_ids": fids, "next_step": "confirm_with_laboratory",
                   "summary": "No laboratory note or investigation record is on file for this result. The laboratory should confirm it before any disposition.",
                   "evidence": ev(fids), "open_questions": ["Has a retest or an out-of-specification investigation been started?"]})

    if any(r.startswith("batch.") for r in rules):
        fids = ids(lambda f: f["rule"].startswith("batch."))
        line = next((e["line"] for e in ev(fids)), 12)
        yield ("read_document", {"document": "batch_record.md", "from_line": max(1, line - 1), "to_line": line + 1})
        yield ("submit_note", {"finding_ids": fids, "next_step": "request_missing_evidence",
               "summary": "The batch record lines around the step show the verifier's cell is blank. Nothing on file shows a second-person check took place.",
               "evidence": ev(fids), "open_questions": ["Can the supervisor provide a documented, contemporaneous verification?"]})


def _investigate(model: str, messages, text: str, tools) -> LLMResponse:
    findings = json.loads(_between(text, "FINDINGS_JSON:", "END_FINDINGS"))
    done = _history(messages)
    plan = _plan(findings)
    try:
        action = next(plan)
        for _name, _args, result in done:
            action = plan.send(result)
    except StopIteration:
        return _reply(model, "Investigation complete.")
    names = {t.get("function", {}).get("name", "").split("__")[-1]: t.get("function", {}).get("name", "") for t in (tools or [])}
    name, args = action
    call = ToolCall(id=f"inv-{len(done) + 1}", function=FunctionCall(name=names.get(name, name), arguments=json.dumps(args)))
    return LLMResponse(model=model, tool_calls=[call], usage=Usage(), finish_reason="tool_calls")


def install() -> None:
    register_provider("scripted/", lambda config, settings: OfflineProvider())
