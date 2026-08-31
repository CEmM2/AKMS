# Schema Compliance — Frozen v2 Reference

> Authoritative source: `03_AKMS_schema_specification.md` (schema) and `04_AKMS_domain_node_inventory.md` (taxonomy).
> These schemas are **frozen**. Nodes that violate them will be rejected by `build_graph.py`.

---

## 1. Required Frontmatter Fields (from §1 of doc 03)

Every generated node MUST include ALL of these fields. Missing any one is a schema violation.

| Field | Type | Constraint |
|-------|------|------------|
| `id` | string | snake_case, unique, stable. Exact match from extraction plan. |
| `title` | string | Double-quoted. Exact match from extraction plan. |
| `domain` | string | From domain taxonomy (see §3 below) |
| `tags` | list[string] | At least 1. Prefer tags from canonical vocabulary (see §4). |
| `status` | enum | **MUST be `tentative`** for all generated nodes |
| `confidence` | float [0.0, 1.0] | Default `0.90` for agent-generated nodes |
| `source` | enum | **MUST be `hybrid`** for NLM-extracted nodes |
| `edges` | list | At least 1 edge. See edge types in §5. |
| `akms_schema` | string | **MUST be `v2`** — never `v1` |

### Optional fields (include when applicable)

| Field | Type | Notes |
|-------|------|-------|
| `subdomain` | string | Finer grain within domain (see §3) |
| `confidence_floor` | float [0.0, 1.0] | Only for foundational nodes that must not collapse |
| `load_with` | list[string] | Co-activation hints (node ids) |
| `context_size` | enum: `small \| medium \| large` | Token budget hint |
| `reading_priority` | enum: `full \| summary \| pitfalls-only` | Default `full` |
| `content_ref` | path or null | Set to `null` for self-contained nodes |

### Forbidden fields in generated nodes

These are **experiential state** and belong ONLY in `local_state.yaml`, never in node frontmatter:
`activations`, `last_activated`, `activated_by_tasks`, `session_refs`, `auto_update`

Including any of these in a global node will cause `schema.py` to raise `SchemaValidationError`.

---

## 2. Generated Node Defaults

Every node produced by this skill MUST use these exact values:

```yaml
status: tentative
source: hybrid
confidence: 0.90
content_ref: null
akms_schema: v2
```

The developer promotes `tentative → established` during review. The skill never sets `established`.

---

## 3. Domain Taxonomy (from doc 04 domain map)

The `domain` field uses the taxonomy from the domain map. Valid values:

**Top-level domains:**
- `computational-mechanics` — kinematics, FEM, constitutive, FFT-Galerkin, solvers
- `gpu-simulation` — Taichi patterns, GPU kernels
- `theoretical-physics` — non-hermitian QM, fractional PDEs (future)
- `project-meta` — shared operational patterns

**Subdomain-as-domain (used when more specific):**
The frozen schema example in doc 03 uses `domain: fft-galerkin` — subdomain values CAN serve as the domain field when the node belongs clearly to a specific area:

- `kinematics`
- `finite-elements`
- `constitutive`
- `elasticity`, `plasticity`, `damage` (under constitutive)
- `fft-galerkin`
- `solvers`
- `taichi`

**Rule:** For FFT-related nodes from the extraction plan, use `domain: fft-galerkin` (not `computational-mechanics`). Use `computational-mechanics` only for nodes that span multiple subdomains.

The `subdomain` field provides additional granularity when domain is broad:
- `spectral-operators`, `discretization`, `solver-algorithms`, `convergence`, `coupled-problems`, etc.

---

## 4. Canonical Tag Vocabulary (from doc 04)

Prefer reusing these exact tags. Only invent new tags if none of these fit.

**Kinematics:** kinematics, finite-strain, tensors, continuum-mechanics, stress-rates, objectivity

**FEM:** fem, total-lagrangian, variational, elements, matrix-free, gpu, linear-algebra, boundary-conditions, nonlinear-solver, convergence

**Elasticity:** elasticity, hyperelastic, small-strain

**Plasticity:** viscoplasticity, perzyna, return-mapping, time-integration, barlat, anisotropy, crystal-plasticity, polycrystal, plasticity

**Damage:** phase-field, fracture, damage, gtn, ductile-fracture

**FFT-Galerkin:** fft-galerkin, spectral, homogenization, green-operator, lippmann-schwinger, micromechanics, periodic-bc, accelerated-schemes, freq-grid

**Solvers:** solvers, iterative, preconditioning, multigrid, newton, quasi-newton, spectral-step-size, nesterov, krylov-solver, conjugate-gradient, polarization

**Discretization:** finite-difference, staggered-grid, discretization

**Taichi:** taichi, snode, kernels

---

## 5. Edge Types (from FR-G05 of doc 01, §1 of doc 03)

The frozen schema defines exactly these edge types:

| Edge type | Meaning | Propagation multiplier |
|-----------|---------|----------------------|
| `requires` | Hard prerequisite — node A cannot be understood without node B | 1.0 |
| `feeds-into` | Downstream consumer — node A produces output consumed by node B | 0.5 |
| `refines` | Specialization — node A is a more specific version of node B | 0.7 |
| `contradicts` | Disagreement — node A presents an alternative to node B | 0.0 |
| `pitfall` | Warning — node A documents a pitfall related to node B | 0.0 |
| `implements` | Code mirror — node A is a code implementation of node B | 0.0 |

**For domain nodes generated by this skill**, primarily use: `requires`, `feeds-into`, `refines`.
Use `contradicts` when two approaches conflict (e.g., different discretization methods).
Use `pitfall` only when the edge target is a session node (`domain: session`).
Do NOT use `implements` — that edge type is reserved for code-mirror nodes.

---

## 6. Edge Target Validation (from doc 04 inventory)

When setting `edges[].to`, use exact node ids from the inventory. The full list is in `references/akms_node_template.md` §6.

**Priority order for edge targets:**
1. Exact id from the inventory (preferred)
2. Another node from the same extraction plan (use the plan's id)
3. Invented plausible snake_case id (last resort — log as "INVENTED EDGE TARGET: {id}")

**Weight guidelines:**
- `1.0` — essential dependency (cannot implement without this)
- `0.7–0.9` — strong relationship
- `0.5–0.6` — moderate relationship
- `0.3–0.4` — weak/tangential

---

## 7. Markdown Body Structure (from converter expectations)

The converter (`akms_node_convert.py`) produces markdown with these exact section headings:

```
# [Title]

## Summary
[from summary field]

## 1. Core Concept
[from core_concept field]

## 2. Mathematical Formulation
[from math_formulation field — prose + equations + notation]

## 3. Algorithmic Implementation
[from algorithms field — rendered as LaTeX algorithmic blocks]

## 4. Known Pitfalls
[from pitfalls field]

## 5. Verification & Benchmarks (optional)
[from verification field]

## N. References (optional)
[from references field]
```

The validator (`akms_node_clean.py`) checks for all required sections and flags missing ones as errors.

---

## 8. Pre-Write Checklist

Before writing any YAML file, verify:

- [ ] `akms_schema: v2` (never v1)
- [ ] `status: tentative` (never established, draft, or deprecated)
- [ ] `source: hybrid` (for NLM-extracted nodes)
- [ ] `content_ref: null`
- [ ] `domain` matches taxonomy (§3) — use `fft-galerkin` for FFT nodes, not `computational-mechanics`
- [ ] Tags from canonical vocabulary (§4)
- [ ] Edge types from frozen set (§5) — no invented types
- [ ] Edge targets from inventory (§6) — log any invented ids
- [ ] No experiential fields (`activations`, `session_refs`, etc.)
- [ ] All `math:` values in algorithms are single-quoted
- [ ] All symbols defined in `notation` or `where`