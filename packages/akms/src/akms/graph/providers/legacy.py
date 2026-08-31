"""Legacy Python-AST mirror provider (A2-4).

Wraps the pre-provider ``generate_mirror`` implementation so the default
AKMS path stays byte-compatible while orchestration goes through the
MirrorProvider protocol.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from akms.graph.mirror_provider import MirrorRequest, MirrorResult

if TYPE_CHECKING:
    from akms.schema.models import MirrorConfig

logger = logging.getLogger(__name__)


class LegacyMirrorProvider:
    """In-process Python AST mirror generator (historical default)."""

    name = "legacy"

    def generate(self, request: MirrorRequest, config: MirrorConfig) -> MirrorResult:
        # Local import avoids circular import: generate_mirror → mirror_provider
        # → providers.legacy → generate_mirror internals.
        from akms.graph.generate_mirror import generate_mirror_legacy

        summary = generate_mirror_legacy(
            repo_root=request.repo_root,
            phase=request.phase,
            parent_branch=request.parent_branch,
            source_files=request.source_files,
            drift_check=request.drift_check,
            llm_fn=request.llm_fn,
            generated_at=request.generated_at,
        )
        return MirrorResult(
            mirrors=list(summary.get("mirrors", [])),
            drift_warnings=list(summary.get("drift_warnings", [])),
            files_processed=int(summary.get("files_processed", 0)),
            definitions_total=int(summary.get("definitions_total", 0)),
            provider=self.name,
            provider_metadata={
                "kind": "in_process",
                "language_coverage": ["python"],
                "repo_root": str(Path(request.repo_root)),
            },
            errors=[],
            success=True,
            fallback_used=False,
        )
