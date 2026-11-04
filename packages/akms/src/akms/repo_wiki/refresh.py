"""The incremental graph refresh shared by ``changes --refresh`` and the git hooks.

It is ``repo-wiki build --changed-only --no-summaries --no-index`` (the fastest rebuild of
``symbol_graph.json`` and ``flows.json``) run under the build lock, so it never overlaps
another build.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from akms.repo_wiki.locking import acquire_build_lock

#: How long a refresh waits for a running build before giving up.
REFRESH_WAIT_SECONDS = 600.0


def refresh_graph(
    repo_root: Path,
    *,
    wait_seconds: float | None = None,
    on_wait: Any = None,
) -> dict[str, object]:
    """Rebuild changed files' graph entries and the flows; report what it did."""
    from akms.repo_wiki.manifest import build_repo

    wait = REFRESH_WAIT_SECONDS if wait_seconds is None else wait_seconds
    lock = acquire_build_lock(repo_root, wait_seconds=wait, on_wait=on_wait)
    started = time.monotonic()
    try:
        summary = build_repo(
            repo_root, changed_only=True, no_summaries=True, no_index=True
        )
    finally:
        lock.release()
    return {
        "seconds": round(time.monotonic() - started, 3),
        "parsed": summary.parsed,
        "errors": len(summary.errors),
    }
