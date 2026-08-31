# YAML Safety Rules — Reference

> Common YAML pitfalls when writing LaTeX-heavy AKMS nodes, with fixes.

---

## 1. The Colon Problem

YAML interprets unquoted colons as key-value separators. Tensor contractions use `:` heavily.

**Rule:** All `math:` values in algorithm steps MUST be single-quoted.

```yaml
# CORRECT — single-quoted, \colon for contraction
- cmd: State
  math: '\boldsymbol{\sigma} \gets \mathbb{C} \colon \boldsymbol{\varepsilon}'

# WRONG — unquoted, bare colon breaks YAML
- cmd: State
  math: \boldsymbol{\sigma} \gets \mathbb{C} : \boldsymbol{\varepsilon}

# WRONG — double-quoted, backslashes get interpreted
- cmd: State
  math: "\boldsymbol{\sigma} \gets \mathbb{C} \colon \boldsymbol{\varepsilon}"
```

**Safe zones:** Prose fields using `|` block scalars (summary, core_concept, pitfalls, math_formulation.prose) can use regular colons freely. The block scalar prevents YAML interpretation.

---

## 2. Use `\colon` for Tensor Contractions

Inside single-quoted `math:` fields, always use `\colon` instead of `:`.

```yaml
# CORRECT
math: '\mathbb{C}^0 \colon \boldsymbol{\varepsilon}'

# WRONG — bare colon inside single quotes still causes issues
# if followed by a space and content that looks like a YAML value
math: '\mathbb{C}^0 : \boldsymbol{\varepsilon}'
```

In `|` block scalar fields (prose, latex), regular `:` is fine:
```yaml
math_formulation:
  prose: |
    The stress is computed via the double contraction: $\boldsymbol{\sigma} = \mathbb{C} : \boldsymbol{\varepsilon}$.
```

---

## 3. Single Quotes vs Double Quotes

| Quote type | Behavior | Use for |
|------------|----------|---------|
| Single `'...'` | Literal — no escape processing | `math:` fields in algorithm steps |
| Double `"..."` | Interprets `\n`, `\t`, etc. | Never use for LaTeX |
| Block `\|` | Multi-line literal | Prose, equations, descriptions |

**Escaping single quotes inside single-quoted strings:** double the quote.
```yaml
math: 'x \in \mathbb{R}^{3 \times 3}, \quad x''s eigenvalues are positive'
```

---

## 4. Special Characters in Titles

Titles containing colons must be quoted:
```yaml
# CORRECT
title: "Green's Operator (Γ⁰) in Fourier Space"

# WRONG — colon breaks YAML
title: Green's Operator (Γ⁰): Fourier Space Form
```

---

## 5. Multi-line Equations

Use `|` block scalar for equation LaTeX:
```yaml
equations:
  - label: "Lippmann-Schwinger equation"
    latex: |
      \boldsymbol{\varepsilon}(\mathbf{x}) = \bar{\boldsymbol{\varepsilon}}
      - \int_Y \boldsymbol{\Gamma}^0(\mathbf{x} - \mathbf{x}')
      : \boldsymbol{\tau}(\mathbf{x}') \, d\mathbf{x}'
    where: "τ is the stress polarization, Γ⁰ is the Green's operator, ε̄ is the macroscopic strain"
```

Do NOT try to put multi-line equations in single-quoted strings.

---

## 6. Common Error Patterns and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `could not find expected ':'` | Unquoted math with `:` | Single-quote the value, use `\colon` |
| `found character that cannot start any token` | Unquoted `{` or `}` | Single-quote the value |
| `while scanning a simple key` | Multi-line content without `\|` | Use block scalar `\|` |
| `found unexpected ':'` | Colon in title/label without quotes | Double-quote the string |
| Backslash sequences vanish | Double-quoted LaTeX | Switch to single quotes |

---

## 7. Validation Checklist

Before writing a YAML file, verify:

- [ ] All `math:` values in algorithm steps are single-quoted
- [ ] All tensor contractions use `\colon` (not `:`) inside quoted math
- [ ] Title is double-quoted (handles colons and apostrophes)
- [ ] Prose/equation fields use `|` block scalars
- [ ] No double-quoted strings contain LaTeX backslashes
- [ ] Notation keys are single-quoted: `'\boldsymbol{\sigma}'`: "Cauchy stress"