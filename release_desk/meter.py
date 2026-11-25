"""Count tokens and time per review, so cost and latency are measured, not guessed."""

from __future__ import annotations

import contextvars
import time
from contextlib import contextmanager

_current: contextvars.ContextVar[dict | None] = contextvars.ContextVar("release_desk_meter", default=None)
_installed = False


def install() -> None:
    """Wrap every provider's acomplete to add its token usage to the active meter."""
    global _installed
    if _installed:
        return
    from continuum.llm.providers.base import BaseProvider

    def wrap(cls):
        original = cls.__dict__.get("acomplete")
        if original is None or getattr(original, "_metered", False):
            return

        async def acomplete(self, *args, **kwargs):
            resp = await original(self, *args, **kwargs)
            m = _current.get()
            if m is not None:
                m["model_calls"] += 1
                usage = getattr(resp, "usage", None)
                if usage is not None:
                    m["input_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
                    m["output_tokens"] += getattr(usage, "completion_tokens", 0) or 0
            return resp

        acomplete._metered = True
        cls.acomplete = acomplete

    def walk(cls):
        for sub in cls.__subclasses__():
            wrap(sub)
            walk(sub)

    import continuum.llm.providers.anthropic_provider  # noqa: F401  (make sure it is loaded)

    walk(BaseProvider)
    _installed = True


@contextmanager
def measure():
    m = {"model_calls": 0, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0}
    token = _current.set(m)
    start = time.perf_counter()
    try:
        yield m
    finally:
        m["seconds"] = round(time.perf_counter() - start, 2)
        _current.reset(token)
