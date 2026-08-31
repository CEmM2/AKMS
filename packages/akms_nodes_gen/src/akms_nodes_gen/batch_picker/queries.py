"""Saved-query persistence.

A saved query is a named filter spec that can be re-applied later or used
for bulk-add to a batch. Storage: ``saved_queries.json`` next to
``batch_assignments.json``.

Schema (v1)::

    {
      "version": 1,
      "updated_at": "...",
      "queries": {
        "<name>": {
          "filter": { ... FilterSpec ... },
          "created_at": "...",
          "updated_at": "..."
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

QUERIES_VERSION = 1


@dataclass
class SavedQuery:
    name: str
    filter: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_queries(path: Path) -> dict[str, SavedQuery]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, SavedQuery] = {}
    for name, data in (raw.get("queries") or {}).items():
        out[name] = SavedQuery(
            name=name,
            filter=dict(data.get("filter") or {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
    return out


def save_queries(path: Path, queries: dict[str, SavedQuery]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": QUERIES_VERSION,
        "updated_at": _now_iso(),
        "queries": {
            name: {
                "filter": q.filter,
                "created_at": q.created_at,
                "updated_at": q.updated_at,
            }
            for name, q in sorted(queries.items())
        },
    }
    fd, tmp = tempfile.mkstemp(prefix=".saved_queries.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def upsert(queries: dict[str, SavedQuery], name: str, filter_dict: dict[str, Any]) -> SavedQuery:
    existing = queries.get(name)
    now = _now_iso()
    if existing is None:
        q = SavedQuery(name=name, filter=filter_dict, created_at=now, updated_at=now)
    else:
        q = SavedQuery(
            name=name,
            filter=filter_dict,
            created_at=existing.created_at or now,
            updated_at=now,
        )
    queries[name] = q
    return q
