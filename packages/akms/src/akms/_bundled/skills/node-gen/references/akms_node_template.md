# AKMS Node Template Reference — v2

> This file is the authoritative template for generating AKMS domain knowledge nodes.
> It defines the exact YAML frontmatter, markdown content structure, algorithm format,
> and the existing node inventory for edge guessing.

---

## 1. YAML Frontmatter Template

Every node file starts and ends its frontmatter with `---` delimiters. Reproduce this structure exactly, preserving indentation and field order.

```yaml
---
# ── Identity ──────────────────────────────────────────────────────────
id: [exact snake_case id provided by user]
title: "[exact title provided by user]"
domain: [one of: computational-mechanics | gpu-simulation | theoretical-physics | project-meta]
subdomain: [OPTIONAL — finer grain, e.g.: kinematics, constitutive, spectral-operators, taichi-kernels]
tags:
  - [3 to 6 relevant conceptual tags, snake_case]

# ── Graph Status ──────────────────────────────────────────────────────
status: tentative
confidence: 0.90
source: hybrid
confidence_floor: [OPTIONAL — set 0.70 for foundational/Tier-1 nodes, omit for others]

# ── Structural Edges ─────────────────────────────────────────────────
edges:
  - to: [target-node-id]
    type: [requires | feeds-into | refines | contradicts]
    weight: [0.0–1.0]
    note: "[OPTIONAL — why this edge exists]"

# ── Loadout Hints ─────────────────────────────────────────────────────
context_size: [small | medium | large]
reading_priority: [full | summary | pitfalls-only]
load_with: [OPTIONAL — list of node ids almost always co-loaded]
content_ref: null

# ── Schema Version ────────────────────────────────────────────────────
akms_schema: v2
---
```

### Field Guidance

| Field | How to set it |
|---|---|
| `domain` | Deduce from content. Most mechanics/FEM/FFT topics → `computational-mechanics`. Taichi/GPU patterns → `gpu-simulation`. |
| `subdomain` | Use categories from domain map: `kinematics`, `finite-elements`, `constitutive`, `elasticity`, `plasticity`, `damage`, `fft-galerkin`, `solvers`, `taichi`. |
| `tags` | Prefer reusing tags from the existing node inventory (§5 below). 3–6 tags, snake_case. |
| `edges` | Guess 1–4 edges. `requires` = hard prerequisite, `feeds-into` = downstream consumer, `refines` = specialization. Weight: 1.0 = essential, 0.5–0.8 = moderate. |
| `context_size` | `small` = <500 words, `medium` = 500–1500, `large` = 1500+. Most nodes → `medium`. |
| `reading_priority` | Default `full`. Use `summary` for very large reference nodes. Use `pitfalls-only` for warning-heavy operational nodes. |
| `confidence_floor` | Set `0.70` for foundational nodes that must never collapse. Omit for others. |
| `load_with` | List node ids that are almost always needed together with this node. Omit if none. |

### Fields that MUST always be set exactly as shown

- `status: tentative` — always, for all generated nodes
- `source: hybrid` — always, for NotebookLM-extracted nodes
- `confidence: 0.90` — default starting confidence
- `akms_schema: v2` — always v2, never v1
- `content_ref: null` — always null for self-contained nodes

---

## 2. Markdown Content Structure

Below the closing `---` of the YAML frontmatter, write content using these exact section headings in this exact order:

```markdown
# [Title]

## Summary
[3–5 sentences. MANDATORY. Extracted verbatim by the loadout generator in routing mode.
Must be self-contained: an agent reading only this summary should understand what this
node covers and whether they need the full content.]

## 1. Core Concept
[Brief theoretical definition. Where does this sit in computational mechanics?
1–3 paragraphs max.]

## 2. Mathematical Formulation
[Governing equations in LaTeX $$ blocks. Standard notation. Define variables inline
or in a brief notation table. Be precise — this is what makes the node valuable.]

## 3. Algorithmic Implementation
[All algorithms in algpseudocode LaTeX format (see §3 below). After each algorithm
block, add a brief Taichi Mapping note.]

## 4. Known Pitfalls
[CRITICAL. Warnings, numerical stability issues, boundary condition gotchas,
convergence difficulties, common implementation mistakes.]
```

### Optional Sections (use when source material warrants)

- `## 5. Verification & Benchmarks` — analytical solutions, standard test problems, expected convergence rates
- `## 6. References` — cite specific papers/textbooks from the NotebookLM sources (author, year, key result)

---

## 3. Algorithm Format — `algpseudocode` LaTeX

Every algorithm in `## 3. Algorithmic Implementation` MUST use the `algpseudocode` LaTeX command set inside `$$` math blocks. Downstream tooling parses these into an AST for automated verification.

### Supported Command Set (use ONLY these)

| LaTeX Command | Semantics |
|---|---|
| `\State $lhs = rhs$` | Assignment — content inside `$...$` is parsed as math |
| `\For{$range$}` ... `\EndFor` | Deterministic loop |
| `\While{$cond$}` ... `\EndWhile` | Conditional loop |
| `\If{$cond$}` ... `\EndIf` | Conditional branch |
| `\ElsIf{$cond$}` | Chained condition (inside an If block) |
| `\Else` | Default branch (inside an If block) |
| `\Return $expr$` | Return one or more values |
| `\State \textbf{break}` | Loop break |

### Prohibited Commands (never use)

`\Procedure`, `\Function`, `\Call`, `\Require`, `\Ensure`, or any custom commands.

### Rules

1. Wrap every algorithm in `\begin{algorithmic}` ... `\end{algorithmic}` inside `$$` delimiters
2. All math inside `\State`, `\For`, `\While`, `\If`, `\Return` must be wrapped in `$...$`
3. Use descriptive LaTeX variable names (`\boldsymbol{\sigma}`, `\Delta\gamma`) NOT code variable names (`sigma`, `dgamma`)
4. Name each algorithm with a bold label before the block: **Algorithm: [Name]**
5. For multi-step algorithms (e.g., Newton iteration with inner return mapping), use separate `\begin{algorithmic}` blocks with clear labels

### Worked Example — Radial Return (J2 Plasticity)

**Algorithm: Radial Return**

$$
\begin{algorithmic}
\State $\boldsymbol{\sigma}^{\text{trial}} = \mathbb{C} : (\boldsymbol{\varepsilon}_{n+1} - \boldsymbol{\varepsilon}^p_n)$
\State $f^{\text{trial}} = \|\text{dev}(\boldsymbol{\sigma}^{\text{trial}})\| - \sqrt{2/3}\,\sigma_Y$
\If{$f^{\text{trial}} \leq 0$}
    \State $\boldsymbol{\sigma}_{n+1} = \boldsymbol{\sigma}^{\text{trial}}$
    \Return $\boldsymbol{\sigma}_{n+1}$
\EndIf
\State $\Delta\gamma = \frac{f^{\text{trial}}}{2\mu + \frac{2}{3}H}$
\State $\mathbf{n} = \frac{\text{dev}(\boldsymbol{\sigma}^{\text{trial}})}{\|\text{dev}(\boldsymbol{\sigma}^{\text{trial}})\|}$
\State $\boldsymbol{\sigma}_{n+1} = \boldsymbol{\sigma}^{\text{trial}} - 2\mu\,\Delta\gamma\,\mathbf{n}$
\State $\boldsymbol{\varepsilon}^p_{n+1} = \boldsymbol{\varepsilon}^p_n + \Delta\gamma\,\mathbf{n}$
\Return $\boldsymbol{\sigma}_{n+1},\,\boldsymbol{\varepsilon}^p_{n+1}$
\end{algorithmic}
$$

**Taichi Mapping:** This return mapping runs per Gauss point. Map to a `@ti.kernel` iterating over all Gauss points with `ti.grouped(ti.ndrange(...))`. Store `\boldsymbol{\varepsilon}^p` as a `ti.field` for history. The elastic predictor and return corrector are fully local — no atomics needed.

---

## 4. Taichi Mapping Reference

When noting how an algorithm maps to Taichi GPU paradigms, use these standard mappings:

| Computational Pattern | Taichi Paradigm |
|---|---|
| Element loop | `@ti.kernel` with `ti.grouped` range |
| Gauss point operations | Inner loop with `ti.static` |
| History/state variables | `ti.field` storage |
| Global assembly | `ti.atomic_add` |
| Matrix-free operators | Action-only kernels, no global matrix |
| Compile-time unrolling | `ti.static(range(...))` |
| Conditional execution | Standard Python `if` inside `ti.static` for compile-time, regular `if` for runtime |

---

## 5. Existing Node Inventory — For Edge Guessing

When setting `edges[].to` targets, use these known node ids. If the target doesn't exist yet, invent a plausible snake_case id and add a YAML comment `# not yet created`.

### Tier 1 — Established Global Nodes

- `skill-taichi-gpu-sim`
- `skill-computational-mechanics`
- `skill-gen-test`
- `skill-sim-setup`
- `skill-repo-documentor`

### Tier 2 — Planned/In-Progress Global Nodes

**Kinematics:**
`kinematics-multiplicative-decomp`, `kinematics-deformation-measures`, `kinematics-objectivity`, `kinematics-incremental`

**Finite Elements:**
`fem-total-lagrangian`, `fem-updated-lagrangian`, `fem-elements-hex`, `fem-elements-tet`, `fem-matrix-free`, `fem-bc-loads`, `fem-convergence`

**Elasticity:**
`elastic-hyperelastic`, `elastic-small-strain`

**Plasticity:**
`plasticity-perzyna`, `plasticity-return-mapping`, `plasticity-barlat`, `plasticity-finite-evp`, `plasticity-crystal`

**Damage:**
`damage-phase-field`, `damage-phase-field-impl`, `damage-gtn`, `damage-porous-ductile`

**FFT-Galerkin:**
`fft-galerkin-basics`, `fft-lippmann-schwinger`, `fft-convergence-schemes`, `fft-freq-grid`, `fft-finite-strain`, `fft-phase-field`, `fft-periodic-bc`

**Solvers:**
`solver-iterative`, `solver-preconditioning`, `solver-nonlinear`

**Taichi:**
`taichi-snode-layout`, `taichi-kernel-patterns`, `taichi-debugging`, `taichi-autodiff`

### Common Tag Vocabulary

Prefer these existing tags when tagging nodes:

kinematics, finite-strain, plasticity, tensors, continuum-mechanics, stress-rates, objectivity, fem, total-lagrangian, variational, elements, hex8, hex20, tet4, tet10, matrix-free, gpu, linear-algebra, boundary-conditions, nonlinear-solver, convergence, elasticity, hyperelastic, small-strain, viscoplasticity, perzyna, rate-dependent, return-mapping, time-integration, barlat, anisotropy, sheet-metal, crystal-plasticity, polycrystal, phase-field, fracture, damage, gtn, ductile-fracture, porosity, fft-galerkin, spectral, homogenization, green-operator, lippmann-schwinger, micromechanics, periodic-bc, accelerated-schemes, freq-grid, solvers, iterative, preconditioning, multigrid, newton, taichi, snode, kernels, debugging, autodiff, differentiation
