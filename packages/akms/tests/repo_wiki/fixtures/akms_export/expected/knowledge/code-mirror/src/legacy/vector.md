---
akms_schema: "v2"
auto_update: true
confidence: 1.0
content_ref: "code-mirror/src/legacy/vector.md"
domain: "code-mirror"
generated_at: "2026-07-26T00:00:00+00:00"
generated_by_phase: 1
id: "mirror-src-legacy-vector"
source: "generated"
source_file: "src/legacy/vector.py"
status: "established"
title: "Code Mirror: src/legacy/vector.py"
---
# <code>src/legacy/vector.py</code>

_Mirror generated: 2026-07-26T00:00:00+00:00 · phase 1_

## Symbol Index

```json
[
  {
    "symbol_id": "python:src/legacy/vector.py::LegacyVector",
    "kind": "class",
    "start_line": 4,
    "end_line": 9,
    "signature": "class LegacyVector",
    "docstring": "A vector whose method must retain its parent relationship.",
    "calls": [],
    "bases": [],
    "parent_id": null
  },
  {
    "symbol_id": "python:src/legacy/vector.py::LegacyVector.scale",
    "kind": "method",
    "start_line": 7,
    "end_line": 9,
    "signature": "def scale(self, factor: float) -> float",
    "docstring": "Scale one unit vector component.",
    "calls": [],
    "bases": [],
    "parent_id": "python:src/legacy/vector.py::LegacyVector"
  }
]
```

## Complete Source

```python
"""Legacy Python mirror identity and nested-symbol fixture."""


class LegacyVector:
    """A vector whose method must retain its parent relationship."""

    def scale(self, factor: float) -> float:
        """Scale one unit vector component."""
        return factor
```
