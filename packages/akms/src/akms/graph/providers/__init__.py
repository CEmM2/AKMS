"""Built-in code-mirror providers for AKMS (A2-4 / A2-5).

Providers are registered lazily via ``akms.graph.mirror_provider``.
Never import repo2md as a Python package from here.
"""

from __future__ import annotations

from akms.graph.providers.legacy import LegacyMirrorProvider

__all__ = [
    "LegacyMirrorProvider",
]
