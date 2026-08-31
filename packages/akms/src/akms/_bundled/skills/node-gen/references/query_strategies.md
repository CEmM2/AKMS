# NLM Query Strategies — Reference

> Adaptive query patterns for NotebookLM extraction.
> Not every node needs the same queries — match the strategy to the node type.
>
> **All queries run via CLI:** `nlm notebook query <NLM_ID> "query text" --timeout 180`
> Use `--timeout 180` or higher — extraction prompts need more time than the 120s default.

---

## 1. Node Type Classification

Before querying, classify the node. Use the title and tags from the extraction plan:

| Type | Signal in title/tags | Examples |
|------|---------------------|----------|
| **concept** | theory, problem, formulation, principle, framework | "Periodic Cell Problem", "RVE Theory" |
| **equation** | equation, operator, Green's, Γ, Lippmann-Schwinger | "Green's Operator", "Lippmann-Schwinger Equation" |
| **solver** | solver, scheme, method, iteration, accelerated | "Basic Scheme", "Barzilai-Borwein", "Newton-Krylov" |
| **discretization** | discretization, grid, finite, staggered, Galerkin | "Moulinec-Suquet Discretization", "Fourier-Galerkin" |
| **coupling** | coupled, multi-physics, phase-field, chemo-mechanical | "FFT-Phase-Field Coupling" |

If ambiguous, default to **solver** (the most query-intensive type) to avoid under-extracting.

---

## 2. Query Templates Per Type

### Concept nodes (3 queries)

```
Q1 — Definition:
"What is {title}? Define the concept and its role in FFT-based computational homogenization."

Q2 — Equations:
"What are the governing equations for {title}? Write out all equations with full variable definitions."

Q3 — Pitfalls:
"What are the known pitfalls, numerical issues, or limitations of {title}?"
```

Skip: algorithm query (concepts don't have step-by-step algorithms).
Skip: targeted query unless `source` has `Eq.` references.

### Equation/Operator nodes (4 queries)

```
Q1 — Definition:
"What is {title}? Define the mathematical object and its physical meaning in micromechanics."

Q2 — Full derivation:
"Write out the complete mathematical definition of {title} with ALL symbol definitions. Include the Fourier-space and real-space forms if both exist."

Q3 — Pitfalls:
"What are the numerical issues or implementation pitfalls for {title}? Include symmetry, singularity at ξ=0, and discretization effects."

Q4 — Targeted (always run):
"Write out {specific_equation_from_source} in full, defining every symbol."
```

The `Q4` query text comes from the extraction plan's `source` field. Example:
- source: "Schneider §2.1, Eq. 2.13–2.14" → Q4: "Write out Eq. 2.13 and Eq. 2.14 from Schneider in full, defining every symbol."

### Solver nodes (5+ queries)

```
Q1 — Definition:
"What is {title}? Explain the solver's approach and what class of problems it targets."

Q2 — Equations:
"What are the governing equations for {title}? Write out all equations including the fixed-point iteration or update formula."

Q3 — Algorithm:
"What is the step-by-step algorithm for {title}? List each computational step with the actual mathematical operation — not descriptions, the actual formulas. Include initialization, iteration loop, and convergence check."

Q4 — Pitfalls:
"What are the convergence issues, parameter sensitivity, or failure modes for {title}? Include stiffness contrast limits and reference medium sensitivity."

Q5 — Convergence:
"What is the convergence criterion for {title}? Write the exact formula used to check convergence, including the norm definition."
```

If the solver has variants (e.g., polarization schemes with α=1 vs α=2), add:
```
Q6 — Variants:
"What are the different variants of {title}? List each variant with its specific parameter choices and the resulting update formula."
```

### Discretization nodes (4 queries)

```
Q1 — Definition:
"What is {title}? Explain the discretization approach and how it differs from alternatives."

Q2 — Equations:
"What are the discrete equations for {title}? Write out the discretized operators, including the frequency grid definition and any modified Green's operator."

Q3 — Algorithm:
"What is the step-by-step procedure for implementing {title}? Include grid setup, operator construction, and how it integrates with solvers."

Q4 — Pitfalls:
"What are the known issues with {title}? Include ringing, Gibbs phenomena, compatibility, and accuracy for high-contrast materials."
```

### Coupling/Multi-physics nodes (5 queries)

```
Q1 — Definition:
"What is {title}? Explain the coupled problem formulation and which physics are linked."

Q2 — Equations:
"What are the governing equations for {title}? Write out the coupled PDE system with all constitutive links between fields."

Q3 — Algorithm:
"What is the staggered or monolithic solution algorithm for {title}? List each step with the actual formulas, including which field is solved in each sub-step."

Q4 — Pitfalls:
"What are the stability and convergence issues specific to the coupling in {title}? Include operator splitting errors and time-step constraints."

Q5 — Targeted:
Derived from `source` field if it references specific equations or sections.
```

---

## 3. Targeted Query Construction

When the extraction plan's `source` field contains specific references, always run a targeted query. Construction rules:

| Source pattern | Query template |
|----------------|---------------|
| `Eq. X.Y` | "Write out Eq. X.Y in full with all symbol definitions." |
| `§X.Y` | "Summarize the content of section X.Y, writing out all equations and algorithms explicitly." |
| `Eq. X.Y–X.Z` | "Write out equations X.Y through X.Z in full with all symbol definitions." |
| Multiple sources (e.g., "Schneider §2.1, Lucarini §3") | Run separate queries per source |

---

## 4. Query Reformulation on Failure

If a query returns insufficient content (too short, no equations, generic text):

**Step 1 — Narrow the terminology.** Replace the title with more specific terms:
- "Basic Scheme" → "Moulinec-Suquet fixed-point iteration with reference medium C⁰"
- "Green's Operator" → "modified Green's operator Γ̂⁰ in Fourier space for linear elasticity"

**Step 2 — Get the raw source text.** Run `nlm source content <SOURCE_ID>` to read the paper text directly. Then extract the relevant content yourself rather than asking NLM to synthesize. To find source IDs, run `nlm notebook get <NLM_ID>` first.

**Step 3 — Get an AI summary of the source.** Run `nlm source describe <SOURCE_ID>` to identify which sections contain the relevant content, then query those sections specifically.

**Step 4 — Get the notebook-level summary.** Run `nlm notebook describe <NLM_ID>` to see suggested topics. If the target content appears under a different name, reformulate the query.

---

## 5. Iterative Extraction

The CLI is stateless — each `nlm notebook query` call is independent (no conversation threading). For complex solver nodes that need iterative extraction, use progressively more specific queries:

```bash
# Q1: broad context
nlm notebook query <NLM_ID> "What is the Barzilai-Borwein accelerated scheme?" --timeout 180

# Q2: drill into algorithm (standalone, includes context in the query)
nlm notebook query <NLM_ID> "Write the step-by-step Barzilai-Borwein algorithm for FFT homogenization, including the spectral step-size formula alpha_k" --timeout 180

# Q3: drill into convergence (standalone)
nlm notebook query <NLM_ID> "What is the convergence criterion for the Barzilai-Borwein scheme? Write the exact formula." --timeout 180
```

Each query must be self-contained — include enough context in the question itself since the CLI doesn't carry forward previous answers.