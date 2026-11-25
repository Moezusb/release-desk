"""Settings, read once from the environment (and a local .env file if present).

Continuum reads its own settings at import time, so this module must be
imported before anything from ``continuum``. The package __init__ does that.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parents[1]

# Release Desk needs none of Continuum's optional infrastructure. Each run is
# stateless, so long-term memory, Redis sessions and Langfuse stay off unless
# you turn them on yourself.
for key, value in {
    "MEMORY_ENABLED": "false",
    "SESSION_ENABLED": "false",
    "LANGFUSE_ENABLED": "false",
    "LOG_LEVEL": "ERROR",
}.items():
    os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    model: str
    offline: bool
    approval_timeout: float
    data_dir: Path
    runs_dir: Path


def load(offline: bool | None = None) -> Settings:
    # A static key, or workload identity federation (a short-lived identity token
    # exchanged by the Anthropic SDK), which is how the GitHub Actions runs work.
    has_key = any(os.environ.get(k) for k in (
        "ANTHROPIC_API_KEY", "ANTHROPIC_IDENTITY_TOKEN_FILE", "ANTHROPIC_IDENTITY_TOKEN", "ANTHROPIC_PROFILE"))
    if offline is None:
        offline = os.environ.get("RELEASE_DESK_OFFLINE", "").lower() in {"1", "true", "yes"} or not has_key
    return Settings(
        model="scripted/offline" if offline else os.environ.get("RELEASE_DESK_MODEL", "claude-sonnet-5-5"),
        offline=offline,
        approval_timeout=float(os.environ.get("RELEASE_DESK_APPROVAL_TIMEOUT", "900")),
        data_dir=Path(os.environ.get("RELEASE_DESK_DATA", ROOT / "data")),
        runs_dir=Path(os.environ.get("RELEASE_DESK_RUNS", ROOT / "runs")),
    )
