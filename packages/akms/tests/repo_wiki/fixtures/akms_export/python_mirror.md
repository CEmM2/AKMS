---
akms_schema: "v2"
auto_update: true
confidence: 1.0
content_ref: "code-mirror/src/vector.md"
domain: "code-mirror"
generated_at: "2026-03-07T12:00:00+00:00"
generated_by_phase: 2
id: "mirror-src-vector"
source: "generated"
source_file: "src/vector.py"
status: "established"
title: "Code Mirror: src/vector.py"
---
# <code>src/vector.py</code>

_Mirror generated: 2026-03-07T12:00:00+00:00 · phase 2_

## Symbol Index

```json
[
  {
    "symbol_id": "python:src/vector.py:Vector",
    "kind": "class",
    "start_line": 3,
    "end_line": 8,
    "signature": "class Vector(BaseVector)",
    "docstring": "A tiny vector.",
    "calls": [],
    "bases": [
      "BaseVector"
    ],
    "parent_id": null
  },
  {
    "symbol_id": "python:src/vector.py:Vector.scale",
    "kind": "method",
    "start_line": 6,
    "end_line": 8,
    "signature": "def scale(self, factor: float) -> float",
    "docstring": "Scale one value.",
    "calls": [
      "helper"
    ],
    "bases": [],
    "parent_id": "python:src/vector.py:Vector"
  }
]
```

## Complete Source

```python
"""Vector helpers."""

class Vector(BaseVector):
    """A tiny vector."""

    def scale(self, factor: float) -> float:
        """Scale one value."""
        return helper(factor)
```
