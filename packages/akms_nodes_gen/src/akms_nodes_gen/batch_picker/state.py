"""Read/write the durable batch_assignments.json state file.

Schema (v1):

    {
      "version": 1,
      "batches": {
        "R3_B2": {
          "papers": ["citekey1", "citekey2", ...],
          "nlm_notebook_id": "nb_abc...",
          "nlm_notebook_url": "...",
          "synced_at": "2026-05-07T15:30:00Z",
          "uploaded_papers": ["citekey1", ...],
          "notes": ""
        }
      }
    }
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_VERSION = 1


@dataclass
class BatchAssignment:
    papers: list[str] = field(default_factory=list)
    nlm_notebook_id: str = ""
    nlm_notebook_url: str = ""
    synced_at: str = ""
    uploaded_papers: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state(path: Path) -> dict[str, BatchAssignment]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, BatchAssignment] = {}
    for bid, data in (raw.get("batches") or {}).items():
        out[bid] = BatchAssignment(
            papers=list(data.get("papers") or []),
            nlm_notebook_id=data.get("nlm_notebook_id", ""),
            nlm_notebook_url=data.get("nlm_notebook_url", ""),
            synced_at=data.get("synced_at", ""),
            uploaded_papers=list(data.get("uploaded_papers") or []),
            notes=data.get("notes", ""),
        )
    return out


def save_state(path: Path, state: dict[str, BatchAssignment]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": STATE_VERSION,
        "updated_at": _now_iso(),
        "batches": {bid: asdict(a) for bid, a in sorted(state.items())},
    }
    # atomic write
    fd, tmp = tempfile.mkstemp(
        prefix=".batch_assignments.", suffix=".json", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def get_or_create(state: dict[str, BatchAssignment], batch_id: str) -> BatchAssignment:
    if batch_id not in state:
        state[batch_id] = BatchAssignment()
    return state[batch_id]


def stamp_synced(a: BatchAssignment) -> None:
    a.synced_at = _now_iso()
