# Documentation workflow (detailed)

## Step 0: Decide output mode
- Markdown: `docs/` tree
- LaTeX: `tex/` tree (article for small repos, book for large systems)

## Step 1: Inventory the repository
Collect:
- Language(s), build system, package/module roots
- Entrypoints (CLI, scripts, main(), notebooks, GUI launcher)
- Major subsystems (core compute, IO, configs, viz, tools)
- External deps that define interfaces (frameworks, file formats)

Deliverable:
- `docs/repo-map.md` (or `sections/architecture.tex` intro)
- A short list of "public surfaces" (APIs, CLIs, file formats)

## Step 2: Select profiles (1–3)
Use `references/PROFILES.md`.
Deliverable:
- `docs/_profiles.md` listing chosen profiles and why

## Step 3: Architecture at two resolutions
### 3A) Codebase-level
Deliver:
- Module/package dependency diagram
- Runtime dataflow diagram
- Dependency surfaces: public vs internal vs tooling

### 3B) Module-level deep dives (only when triggered)
Trigger a finer diagram if ANY:
- >3 significant classes in module
- >15 public functions
- tightly coupled internal call cluster
- module implements a pipeline (parse → preprocess → compute → postprocess)

Deliver:
- per-module internal dataflow or call graph (when valuable)

## Step 4: Workflows and entry points (required)
Deliver:
- `docs/workflows/entrypoints.md`
- `docs/workflows/typical-runs.md`

Include per workflow:
- invocation (CLI or script call)
- configs used and where they come from
- inputs/outputs and artifact paths
- what “success” looks like
- common failure modes

## Step 5: Glossary + Artifacts registry + Conventions (required)
### Glossary
Create:
- `docs/glossary/data-types-and-symbols.md`

Fields:
- English name
- Code identifiers
- Type/dtype
- shape (arrays/tensors)
- units
- math symbol (if explicit, else inferred)
- Notes (Explicit vs Inferred)

### Artifacts registry
Create:
- `docs/glossary/artifacts.md`

Fields:
- artifact name
- path pattern
- format (HDF5/NIfTI/CSV/JSON/mesh/etc.)
- schema/keys
- units, coordinate frame, versioning

### Units/frames/sign conventions
Create:
- `docs/conventions/units-and-frames.md`
Include:
- coordinate frames
- unit system
- sign conventions
- indexing conventions
- time stepping conventions

## Step 6: Module docs (required)
For each module:
- purpose
- dependencies
- public surfaces
- inheritance map (bases and derived)
- standardized API contracts (see references/CONTRACTS.md)
- signature conventions

### Intentionally-unused parameters (strict rule)
Only label as “intentionally unused” if verified:
- present in signature and unused in body, AND
- peers share signature OR documentation explains it

When verified, add a prominent admonition.

## Step 7: Class docs (required)
For each class:
- responsibility
- key state
- lifecycle (init/reset/update/finalize)
- methods/kernels list
- side effects and invariants
- call relationships (summary + optional diagram)

## Step 8: Function/kernel docs (required for public + critical internals)
For each:
- contract block
- math/physics description + equations
- algorithm box when suitable
- numerical safeguards
- complexity/memory
- failure modes

## Step 9: Validation & verification map (required)
See references/VALIDATION.md.
Deliver:
- tests → modules mapping
- numerical regression tolerances
- benchmark notes
- datasets/fixtures provenance + hashes if available
- sanity plots expectations

## Step 10: Stability policy + dependency surfaces (required)
Deliver:
- `docs/api/stability.md` describing: Public / Semi-public / Internal

## Step 11: Quality gates (required)
Run checks in references/QUALITY_GATES.md and fix gaps.

## Step 12: Write manifest (required)
Create:
- `docs/_manifest.yml`

Include:
- generation date
- repo revision/commit if available
- chosen profiles
- included/excluded scope
- unknowns/inferred list
- diagram types emitted