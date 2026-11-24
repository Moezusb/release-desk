"""A stand-in model, so the desk runs end to end without an API key.

It is a script, not a model, and it should not be mistaken for one:

* The reader returns saved extractions from ``fixtures/``. They were written
  by hand to match the synthetic documents, and one of them (LC-24034) carries
  a deliberate misquote so you can watch the evidence check refuse it.
* The disposition step proposes release when there are no blocking findings
  and a hold otherwise, as a careful model should.
* The second reader agrees when the proposal follows from the findings.

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
            path = FIXTURES / f"{lot}.json"
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


def install() -> None:
    register_provider("scripted/", lambda config, settings: OfflineProvider())
