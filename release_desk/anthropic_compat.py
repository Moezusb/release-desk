"""Structured answers from Claude models that refuse a forced tool choice.

Continuum asks for a structured answer by offering one schema tool and forcing
the model to call it (`tool_choice: {"type": "tool"}`). Current Claude models
reject a forced choice. Here the same tool is offered with `tool_choice: auto`,
the instructions say to answer through it, and the call is unwrapped into
ordinary content exactly as Continuum would. If the model answers in text
instead, Continuum's own schema validation still applies to that text.
"""

from __future__ import annotations

from typing import Any

from continuum.llm.providers import register_provider
from continuum.llm.providers.anthropic_provider import AnthropicProvider
from continuum.llm.structured_output import STRUCTURED_OUTPUT_TOOL, unwrap_structured_tool_call

ANSWER_THROUGH_TOOL = f"\n\nGive your final answer only by calling the {STRUCTURED_OUTPUT_TOOL} tool, once."


def _offers_schema_tool(kwargs: dict[str, Any]) -> bool:
    return any(t.get("name") == STRUCTURED_OUTPUT_TOOL for t in kwargs.get("tools") or [])


class CompatAnthropicProvider(AnthropicProvider):
    @staticmethod
    def _schema_tool_kwargs(schema: dict[str, Any]) -> dict[str, Any]:
        kwargs = AnthropicProvider._schema_tool_kwargs(schema)
        kwargs["tool_choice"] = {"type": "auto"}
        return kwargs

    def _build_kwargs(self, *args: Any, **kw: Any) -> dict[str, Any]:
        kwargs = super()._build_kwargs(*args, **kw)
        if _offers_schema_tool(kwargs):
            kwargs["system"] = (kwargs.get("system") or "").strip() + ANSWER_THROUGH_TOOL
        return kwargs

    @staticmethod
    def _to_response(raw: Any, config: Any, kwargs: dict[str, Any]):
        response = AnthropicProvider._to_response(raw, config, kwargs)
        return unwrap_structured_tool_call(response) if _offers_schema_tool(kwargs) else response


def install() -> None:
    def make(config, settings):
        return CompatAnthropicProvider(api_key=settings.anthropic_api_key, max_retries=config.max_retries)

    for prefix in ("claude-", "claude/", "anthropic/"):
        register_provider(prefix, make)
