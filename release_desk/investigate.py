"""The investigator: the one part of the desk that is an agent.

Everything else follows a fixed path. Here the model chooses what to read next
based on what it has just read: a deviation record, an older specification, a
corrected certificate, a range of lines in the batch record. Different evidence
leads it down different paths.

What it may do: read. What it may not do: change a finding, change a
specification, apply a correction, or decide anything. Its notes are advice to
the reviewer, shown beside the findings they concern.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from continuum.agent import AgentConfig, AgentRunner, BaseAgent
from continuum.tools import ToolExecutor
from continuum.tools.mcp import FunctionTool, MCPServerFunction

from .config import Settings
from .documents import DOCUMENTS, SECTION_BY_FILE, corrections, list_records, load_lot, load_specs, read_record
from .schemas import InvestigationNote

INSTRUCTIONS = """Role: investigator
You help a quality reviewer understand blocking findings on one manufactured lot.
You can only read. You cannot change findings, specifications or documents, and you do not decide.

Use the tools to look for evidence that explains each finding: supporting records
(deviation records, laboratory notes), other specification revisions, corrected
document versions on file, or the exact lines of the lot documents.
Choose what to read based on what you find. Stop when you can explain the finding,
or when the evidence needed is not on file; then say what is missing.

Finish by calling submit_note once per group of related findings. Each note:
- summary: two or three plain sentences a reviewer can check against the cited lines;
- evidence: the documents and line numbers you relied on;
- next_step: one of the allowed values;
- open_questions: what only a person can answer.
Never claim a finding is resolved. A corrected document on file is not applied until a person applies it.
"""

ToolLog = Callable[[str, dict, str], None]


def _numbered(lines: list[str], start: int = 1, end: int | None = None) -> str:
    end = min(end or len(lines), len(lines))
    start = max(1, start)
    return "\n".join(f"L{i:02d}: {lines[i - 1]}" for i in range(start, end + 1)) or "(no lines in that range)"


async def investigate(
    settings: Settings,
    lot_id: str,
    versions: dict[str, str],
    findings: list[dict],
    log: ToolLog,
) -> list[InvestigationNote]:
    data = settings.data_dir
    pkg = load_lot(data, lot_id, versions)
    notes: list[InvestigationNote] = []

    def tool(name: str, description: str, properties: dict, required: list[str], fn) -> FunctionTool:
        async def run(args: dict) -> str:
            result = fn(**args)
            log(name, args, result)
            return result

        schema = {"type": "object", "properties": properties, "required": required}
        return FunctionTool(name=name, fn=run, input_schema=schema, description=description)

    def read_document(document: str, from_line: int = 1, to_line: int | None = None) -> str:
        section = SECTION_BY_FILE.get(document)
        if not section:
            return f"Unknown document. Choose one of: {', '.join(DOCUMENTS.values())}."
        return _numbered(pkg.docs[section], int(from_line), int(to_line) if to_line else None)

    def list_supporting_records() -> str:
        names = list_records(data, lot_id)
        return "Records on file: " + ", ".join(names) if names else "No supporting records are on file for this lot."

    def open_record(name: str) -> str:
        lines = read_record(data, lot_id, name)
        return _numbered(lines) if lines else f"No record named {name}."

    def get_specification(revision: str) -> str:
        for s in load_specs(data):
            if s["revision"] == str(revision).zfill(2):
                limits = "; ".join(
                    f"{t['name']}: " + (", ".join(t["accepted"]) if t["kind"] == "text"
                                        else f"min {t.get('min', 'none')}, max {t.get('max', 'none')}")
                    for t in s["tests"])
                return (f"Revision {s['revision']}, in force {s['effective_from']} to {s.get('effective_to') or 'now'}. "
                        f"{s.get('change_note', '')} Limits: {limits}")
        return f"No revision {revision}. On file: " + ", ".join(s["revision"] for s in load_specs(data))

    def list_corrected_documents() -> str:
        found = corrections(data, lot_id)
        if not found:
            return "No corrected document versions are on file for this lot."
        return "Corrected versions on file (not applied): " + ", ".join(f"{DOCUMENTS[s]} {v}" for s, v in found)

    def read_corrected_document(document: str, version: str) -> str:
        section = SECTION_BY_FILE.get(document)
        if not section or (section, version) not in corrections(data, lot_id):
            return "No such corrected version on file."
        return _numbered(load_lot(data, lot_id, {**versions, section: version}).docs[section])

    def submit_note(finding_ids: list[str], summary: str, next_step: str, evidence: list[dict] | None = None,
                    open_questions: list[str] | None = None) -> str:
        try:
            notes.append(InvestigationNote(finding_ids=finding_ids, summary=summary, next_step=next_step,
                                           evidence=evidence or [], open_questions=open_questions or []))
        except Exception as exc:
            return f"Note rejected: {exc}"
        return "Note recorded."

    doc_enum = {"type": "string", "enum": list(DOCUMENTS.values())}
    steps = list(InvestigationNote.model_fields["next_step"].annotation.__args__)
    server = MCPServerFunction("lot", [
        tool("read_document", "Read a range of numbered lines from one of the lot's current documents.",
             {"document": doc_enum, "from_line": {"type": "integer"}, "to_line": {"type": "integer"}}, ["document"], read_document),
        tool("list_supporting_records", "List supporting records on file for this lot (deviation records, laboratory notes).",
             {}, [], list_supporting_records),
        tool("open_record", "Open one supporting record by name.", {"name": {"type": "string"}}, ["name"], open_record),
        tool("get_specification", "Read one revision of the product specification: dates in force, change note and limits.",
             {"revision": {"type": "string"}}, ["revision"], get_specification),
        tool("list_corrected_documents", "List corrected versions of this lot's documents that are on file but not applied.",
             {}, [], list_corrected_documents),
        tool("read_corrected_document", "Read a corrected version of a document. Reading it does not apply it.",
             {"document": doc_enum, "version": {"type": "string"}}, ["document", "version"], read_corrected_document),
        tool("submit_note", "Record one investigation note for the reviewer.", {
            "finding_ids": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
            "next_step": {"type": "string", "enum": steps},
            "evidence": {"type": "array", "items": {"type": "object", "properties": {
                "document": {"type": "string"}, "line": {"type": "integer"}}, "required": ["document"]}},
            "open_questions": {"type": "array", "items": {"type": "string"}},
        }, ["finding_ids", "summary", "next_step"], submit_note),
    ])
    executor = ToolExecutor(tool_registry={server: None})
    await executor.initialize()
    agent = BaseAgent(
        name="investigator",
        instructions=INSTRUCTIONS,
        model=settings.model,
        temperature=None,  # current Claude models reject sampling parameters
        max_tokens=3000,  # set on the agent: AgentConfig.max_tokens does not reach the request
        tool_executor=executor,
        tools=executor.get_tool_definitions(),
        config=AgentConfig(temperature=None, max_tokens=3000, max_turns=12),
    )
    message = (f"Lot: {lot_id}\nDocument versions: {pkg.version_label()}\n\n"
               f"FINDINGS_JSON:\n{json.dumps(findings, indent=1)}\nEND_FINDINGS\n")
    await AgentRunner().run(agent, message)
    return notes
