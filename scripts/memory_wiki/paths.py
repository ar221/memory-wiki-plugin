"""Path helpers for the Hermes Memory Wiki.

All path resolution delegates to hermes_constants.get_hermes_home() to honour
HERMES_HOME / profile-awareness. Never use Path.home() / ".hermes" directly.
"""

from pathlib import Path

from hermes_constants import get_hermes_home


def hermes_home() -> Path:
    """Return the Hermes home directory, honouring HERMES_HOME env var."""
    return get_hermes_home()


def wiki_root() -> Path:
    """Return the root of the Memory Wiki tree: <HERMES_HOME>/memory-wiki."""
    return hermes_home() / "memory-wiki"
