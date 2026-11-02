---
akms_schema: "v2"
auto_update: true
confidence: 1.0
content_ref: "code-mirror/cpp/cpp/vector.hpp.md"
domain: "code-mirror"
generated_at: "2026-07-26T00:00:00+00:00"
generated_by_phase: 1
id: "mirror-cpp-cpp_2fvector_2ehpp"
source: "generated"
source_file: "cpp/vector.hpp"
status: "established"
title: "Code Mirror: cpp/vector.hpp"
---
# <code>cpp/vector.hpp</code>

_Mirror generated: 2026-07-26T00:00:00+00:00 · phase 1_

## Symbol Index

```json
[
  {
    "symbol_id": "cpp:cpp/vector.hpp::cpp.vector",
    "kind": "module",
    "start_line": 1,
    "end_line": 1,
    "signature": null,
    "docstring": null,
    "calls": [],
    "bases": [],
    "parent_id": null
  },
  {
    "symbol_id": "cpp:cpp/vector.hpp::Vector",
    "kind": "class",
    "start_line": 3,
    "end_line": 5,
    "signature": null,
    "docstring": null,
    "calls": [],
    "bases": [],
    "parent_id": "cpp:cpp/vector.hpp::cpp.vector"
  },
  {
    "symbol_id": "cpp:cpp/vector.hpp::Vector::norm",
    "kind": "method",
    "start_line": 3,
    "end_line": 5,
    "signature": "double Vector::norm() const",
    "docstring": null,
    "calls": [],
    "bases": [],
    "parent_id": "cpp:cpp/vector.hpp::Vector"
  }
]
```

## Complete Source

```cpp
#pragma once

struct Vector {
    double norm() const;
};
```
