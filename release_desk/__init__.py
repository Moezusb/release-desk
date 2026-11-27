"""Release Desk: AI reads the lot documents, code checks them, a person decides."""

from . import config  # noqa: F401  (must run before continuum is imported)
from . import anthropic_compat as _compat
from . import offline as _offline

_compat.install()
_offline.install()

__version__ = "0.1.0"
