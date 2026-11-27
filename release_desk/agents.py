"""The three model roles: the reader, the proposer and the second reader.

Each is a Continuum ``BaseAgent``. Only the proposer has tools, and only one of
its tools can change the world in a way that matters. That one is behind
Continuum's approval gate.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from continuum.agent import AgentConfig, AgentRunner, BaseAgent
from continuum.agent.approval import ToolApprovalDecision, ToolApprovalRequest
from continuum.tools import ToolExecutor
from continuum.tools.mcp import FunctionTool, MCPServerFunction

from .config import Settings
from .documents import LotPackage
from .schemas import LotExtraction, SecondReading

# ------------------------------------------------------------------- reader

EXTRACTOR = """Role: extractor
You read quality documents for one manufactured lot and copy out what they say.
You do not judge whether anything passes. You only report what is written.

Each document is given with line numbers in the form L07: text.
For every value you report, give:
- value: the text exactly as written in the document (keep units out unless they are part of the cell),
- line: the line number it appears on,
- quote: a short verbatim excerpt of that line containing the value.
If a field is blank, absent or illegible, set value to null. Never guess, infer or fill a gap.
A blank table cell is null, even if the cell above or below has a name in it.

Certificate test results must use these keys, one per row:
{test_keys}

For spec_revision, report the revision number the certificate says it was tested against (for example "04").
For the deviation log, list every deviation row; if the log says there were none, return an empty list.
"""


async def extract(settings: Settings, pkg: LotPackage, spec: dict) -> LotExtraction:
    keys = "\n".join(f"- {t['key']}: {t['name']}" for t in spec["tests"])
    agent = BaseAgent(
        name="reader",
        instructions=EXTRACTOR.format(test_keys=keys),
        model=settings.model,
        temperature=None,  # current Claude models reject sampling parameters
        output_schema=LotExtraction,
        config=AgentConfig(temperature=None, max_tokens=8000, max_turns=2),
    )
    message = (
        f"Lot: {pkg.lot_id}\nDocument versions: {pkg.version_label()}\n\n"
        f"## certificate (certificate_of_analysis.md)\n{pkg.numbered('certificate')}\n\n"
        f"## batch_record (batch_record.md)\n{pkg.numbered('batch_record')}\n\n"
        f"## deviation_log (deviation_log.md)\n{pkg.numbered('deviation_log')}\n"
    )
    resp = await AgentRunner().run(agent, message)
    if not isinstance(resp.structured_output, LotExtraction):
        raise RuntimeError(f"The reader returned no usable extraction: {resp.structured_output_error or 'empty'}")
    return resp.structured_output


# ------------------------------------------------------------ second reader

SECOND_READER = """Role: second_reader
You check a proposed release decision for a manufactured lot before a person sees it.
You are given the findings produced by the release rules and the proposal.
A lot may only be proposed for release when there are no critical or major findings.
Say whether the proposal follows from the findings, and list any specific concerns:
a rationale that contradicts a finding, a cited finding that does not exist, or a
blocking finding the rationale ignores. Do not invent new findings.
"""


async def second_read(settings: Settings, lot_id: str, findings: list[dict], proposal: dict) -> SecondReading:
    agent = BaseAgent(
        name="second-reader",
        instructions=SECOND_READER,
        model=settings.model,
        temperature=None,  # current Claude models reject sampling parameters
        output_schema=SecondReading,
        config=AgentConfig(temperature=None, max_tokens=1500, max_turns=2),
    )
    message = (
        f"Lot: {lot_id}\n\nFINDINGS_JSON:\n{json.dumps(findings, indent=1)}\nEND_FINDINGS\n\n"
        f"PROPOSAL_JSON:\n{json.dumps(proposal)}\nEND_PROPOSAL\n"
    )
    resp = await AgentRunner().run(agent, message)
    if isinstance(resp.structured_output, SecondReading):
        return resp.structured_output
    return SecondReading(agrees=False, concerns=["The second reader gave no usable answer."])


# ----------------------------------------------------------------- proposer

DISPOSITION = """Role: disposition
You propose what should happen to one manufactured lot. You do not decide; a person does.
You are given the findings of the release rules. Call exactly one tool:
- place_on_hold, when there is any critical or major finding;
- release_lot, only when there are none.
In the rationale, write two or three plain sentences a quality reviewer can check,
and cite finding ids (F1, F2...) for every finding you rely on. Do not add findings of your own.
After the tool returns, reply with one short sentence and stop.
"""


ToolFn = Callable[[str, str, list[str]], Awaitable[str]]
Handler = Callable[[ToolApprovalRequest], Awaitable[ToolApprovalDecision]]


async def propose(
    settings: Settings,
    lot_id: str,
    findings: list[dict],
    release_lot: ToolFn,
    place_on_hold: ToolFn,
    approval_handler: Handler,
) -> None:
    schema = {
        "type": "object",
        "properties": {
            "lot_id": {"type": "string"},
            "rationale": {"type": "string"},
            "finding_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["lot_id", "rationale", "finding_ids"],
    }

    async def _release(args: dict) -> str:
        return await release_lot(args["lot_id"], args["rationale"], list(args.get("finding_ids") or []))

    async def _hold(args: dict) -> str:
        return await place_on_hold(args["lot_id"], args["rationale"], list(args.get("finding_ids") or []))

    qms = MCPServerFunction("qms", [
        FunctionTool(name="release_lot", fn=_release, input_schema=schema,
                     description="Release the lot for sale. Requires a named quality reviewer's approval."),
        FunctionTool(name="place_on_hold", fn=_hold, input_schema=schema,
                     description="Place the lot on quality hold pending a reviewer's disposition."),
    ])
    executor = ToolExecutor(tool_registry={qms: None})
    await executor.initialize()

    agent = BaseAgent(
        name="proposer",
        instructions=DISPOSITION,
        model=settings.model,
        temperature=None,  # current Claude models reject sampling parameters
        tool_executor=executor,
        tools=executor.get_tool_definitions(),
        config=AgentConfig(
            temperature=None,
            max_tokens=1500,
            max_turns=4,
            # Releasing needs a person. Holding does not: saying no is cheap,
            # and a hold can always be lifted by someone who looks.
            tool_approval={"*release_lot"},
            approval_handler=approval_handler,
            approval_timeout=settings.approval_timeout,
        ),
    )
    message = f"Lot: {lot_id}\n\nFINDINGS_JSON:\n{json.dumps(findings, indent=1)}\nEND_FINDINGS\n"
    await AgentRunner().run(agent, message)
