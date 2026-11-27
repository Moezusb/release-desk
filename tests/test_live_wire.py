"""The live path, end to end, against a simulated Anthropic API. No network, no cost.

Every request the desk would send to Claude goes through the real provider code
to `AsyncMessages.create`, which is replaced here by a strict stand-in. It
refuses what current Claude models refuse (sampling parameters, a forced tool
choice, a tool call left without its result), and answers in Anthropic's wire
format: content blocks, tool_use blocks, thinking blocks, usage. The answers
themselves come from the scripted model, so the run can be scored.

Three answer styles are tried, because a live model is not obliged to answer
the same way twice: through the schema tool; in text, inside a code fence,
after some prose; and with a thinking block before the answer.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from anthropic.resources.messages import AsyncMessages
from anthropic.types import Message, TextBlock, ThinkingBlock, ToolUseBlock, Usage

from continuum.llm.config import LLMConfig
from continuum.llm.structured_output import STRUCTURED_OUTPUT_TOOL
from release_desk import config
from release_desk.evaluate import score
from release_desk.offline import OfflineProvider

pytestmark = pytest.mark.asyncio


class Rejected(AssertionError):
    pass


def _check(kw: dict) -> None:
    """What the real API refuses, refused here too."""
    for key in ("temperature", "top_p", "top_k"):
        if key in kw:
            raise Rejected(f"{key} is not accepted by current Claude models")
    choice = kw.get("tool_choice") or {}
    if choice.get("type") in ("tool", "any"):
        raise Rejected('tool_choice: type "tool" and "any" are not supported for this model')
    if "max_tokens" not in kw or not kw["messages"]:
        raise Rejected("max_tokens and messages are required")
    if kw["messages"][0]["role"] != "user":
        raise Rejected("the first message must come from the user")
    pending: set[str] = set()
    for m in kw["messages"]:
        blocks = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        if m["role"] == "user":
            answered = {b["tool_use_id"] for b in blocks if b.get("type") == "tool_result"}
            if pending - answered:
                raise Rejected("tool_use ids were found without tool_result blocks immediately after")
            pending = set()
        else:
            pending = {b["id"] for b in blocks if b.get("type") == "tool_use"}


def _to_continuum(kw: dict) -> tuple[list[dict], list[dict]]:
    """Anthropic request back into the message shape the scripted model reads."""
    msgs: list[dict] = [{"role": "system", "content": kw.get("system") or ""}]
    for m in kw["messages"]:
        if isinstance(m["content"], str):
            msgs.append({"role": m["role"], "content": m["content"]})
            continue
        texts = [b["text"] for b in m["content"] if b.get("type") == "text"]
        if m["role"] == "assistant":
            calls = [{"id": b["id"], "function": {"name": b["name"], "arguments": json.dumps(b["input"])}}
                     for b in m["content"] if b.get("type") == "tool_use"]
            msgs.append({"role": "assistant", "content": "\n".join(texts), "tool_calls": calls})
        else:
            for b in m["content"]:
                if b.get("type") == "tool_result":
                    content = b["content"] if isinstance(b["content"], str) else "".join(c.get("text", "") for c in b["content"])
                    msgs.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": content})
            if texts:
                msgs.append({"role": "user", "content": "\n".join(texts)})
    tools = [{"type": "function", "function": {"name": t["name"]}}
             for t in kw.get("tools") or [] if t["name"] != STRUCTURED_OUTPUT_TOOL]
    return msgs, tools


def simulated_api(style: str, log: list[dict]):
    scripted = OfflineProvider()

    async def create(self, **kw):
        _check(kw)
        log.append(kw)
        msgs, tools = _to_continuum(kw)
        answer = await scripted.acomplete(msgs, LLMConfig(model=kw["model"]), tools=tools or None)
        schema_tool = any(t["name"] == STRUCTURED_OUTPUT_TOOL for t in kw.get("tools") or [])
        blocks: list = []
        if style == "thinking":
            blocks.append(ThinkingBlock(type="thinking", thinking="Checking each line.", signature="sig"))
        stop = "end_turn"
        if answer.tool_calls:
            blocks += [ToolUseBlock(type="tool_use", id=f"toolu_{len(log)}_{i}", name=c.function.name,
                                    input=json.loads(c.function.arguments or "{}")) for i, c in enumerate(answer.tool_calls)]
            stop = "tool_use"
        elif schema_tool and style != "text":
            blocks.append(ToolUseBlock(type="tool_use", id=f"toolu_{len(log)}", name=STRUCTURED_OUTPUT_TOOL,
                                       input=json.loads(answer.content)))
            stop = "tool_use"
        elif schema_tool:
            blocks.append(TextBlock(type="text", text=f"Here is the result.\n\n```json\n{answer.content}\n```\n"))
        else:
            blocks.append(TextBlock(type="text", text=answer.content or ""))
        return Message(id=f"msg_{len(log)}", type="message", role="assistant", model=kw["model"], content=blocks,
                       stop_reason=stop, stop_sequence=None,
                       usage=Usage(input_tokens=len(json.dumps(kw["messages"])) // 4, output_tokens=200))

    return create


@pytest.mark.parametrize("style", ["tool", "text", "thinking"])
async def test_the_live_path_runs_clean_against_a_strict_api(style, monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-simulated")
    log: list[dict] = []
    monkeypatch.setattr(AsyncMessages, "create", simulated_api(style, log))
    settings = replace(config.load(offline=False), runs_dir=tmp_path, approval_timeout=5)
    assert not settings.offline and settings.model.startswith("claude-")

    result = await score(settings, repeat=1)

    errors = [r["error"] for r in result["runs"] if r.get("error")]
    assert not errors, errors[0]
    s = result["summary"]
    assert s["false_clears"] == 0
    assert s["all_runs_correct_lots"] == "7/7", s
    assert s["mean_input_tokens_per_lot"] > 0, "usage must be metered on the live path"
    assert any(t["name"] == STRUCTURED_OUTPUT_TOOL for kw in log for t in kw.get("tools") or [])
