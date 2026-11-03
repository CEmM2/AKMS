"""Built-in code-mirror providers for AKMS.

Providers are registered lazily via ``akms.graph.mirror_provider``.
The subprocess providers never import the exporter they run: ``builtin`` runs
``python -m akms.repo_wiki`` and ``repo2md`` an external ``repo-wiki``.
"""

from __future__ import annotations

from akms.graph.providers.legacy import LegacyMirrorProvider

__all__ = [
    "LegacyMirrorProvider",
]
