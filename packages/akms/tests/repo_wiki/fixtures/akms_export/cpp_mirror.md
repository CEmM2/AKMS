---
akms_schema: "v2"
auto_update: true
confidence: 1.0
content_ref: "code-mirror/cpp/src/vector.cpp.md"
domain: "code-mirror"
generated_at: "2026-03-07T12:00:00+00:00"
generated_by_phase: 2
id: "mirror-cpp-src_2fvector_2ecpp"
source: "generated"
source_file: "src/vector.cpp"
status: "established"
title: "Code Mirror: src/vector.cpp"
---
# <code>src/vector.cpp</code>

_Mirror generated: 2026-03-07T12:00:00+00:00 · phase 2_

## Symbol Index

```json
[
  {
    "symbol_id": "cpp:src/vector.cpp:Vec",
    "kind": "class",
    "start_line": 3,
    "end_line": 5,
    "signature": "struct Vec",
    "docstring": "Small vector type.",
    "calls": [
      "std::sqrt"
    ],
    "bases": [],
    "parent_id": null
  }
]
```

## Complete Source

```cpp
#include <cmath>

struct Vec {
    double norm() const { return std::sqrt(4.0); }
};
```
