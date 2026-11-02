# multilang_repo fixture

Tiny mixed-language sample exercising the tree-sitter extractors.

## Layout

| File | Language | Type | Function(s) | Notable edge |
|---|---|---|---|---|
| `python/calc.py` | python | `Foo` (class) | `Foo.run`, `helper` | `helper` → `Foo.run` (CONFIDENT) |
| `rust/shapes.rs` | rust | `Circle` (struct), `Shape` (trait) | `Circle::new`, `Circle::area`, `helper` | `helper` → `Circle::new` (CONFIDENT) |
| `cpp/vec.cpp` | cpp | `Vec3` (struct), `Sphere` (class) | `Vec3::dot`, `Sphere::radius`, `length` | `length` → `Vec3::dot` |
| `julia/geo.jl` | julia | `Circle` (struct) inside `Geo` module | `Geo.area`, `Geo.helper` | `helper` → `area` |

Each language has at least one type and one function. Qualname joiners:
`.` (Python, Julia), `::` (Rust, C++).

Used by the extractor unit tests and the end-to-end test (`test_e2e_multilang.py`).
