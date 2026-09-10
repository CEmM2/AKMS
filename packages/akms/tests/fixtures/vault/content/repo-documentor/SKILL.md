---
name: repo-documentor
description: Generate repository documentation with architecture/dataflow diagrams, workflows/entrypoints, artifacts & formats registry, units/frames conventions, module inheritance & API contracts, class/function references with math/physics descriptions, validation/verification maps, stability notes, and optional MkDocs/Sphinx/LaTeX outputs.
---

# Repo Documentation Generator Skill

This skill produces repo documentation in **Markdown** (docs tree) or **LaTeX** (article/book structure).
It is **profile-driven**: it detects the repo type(s) and includes domain-appropriate sections.

References:
- Workflow: references/WORKFLOW.md
- Profiles: references/PROFILES.md
- Conventions: references/CONVENTIONS.md
- API Contracts: references/CONTRACTS.md
- Diagrams: references/DIAGRAMS.md
- Validation: references/VALIDATION.md
- Quality Gates: references/QUALITY_GATES.md
- Security & Hardware: references/SECURITY_HARDWARE.md

Templates:
- Markdown templates: assets/templates/TEMPLATES.md
- MkDocs stub: assets/templates/mkdocs.yml
- LaTeX templates: assets/latex/*

## Output modes
When requested, choose one:
1) **Markdown mode**: emit a `docs/` tree (MkDocs-friendly by default).
2) **LaTeX mode**: emit a `tex/` tree using `main_article.tex` or `main_book.tex`.

If the user asks for a specific framework:
- MkDocs: include `mkdocs.yml`
- Sphinx/MyST: include `sphinx_myst_stub.md` and notes

## Required sections (always)
- Architecture (module deps + dataflow)
- Workflows (entry points + typical runs)
- Glossary (data types + naming + symbols)
- Artifacts & file formats registry
- Units/frames/sign conventions
- Module documentation (inheritance + API conventions)
- Class reference (methods/kernels)
- Function/kernel reference (math/physics + algorithm box when suitable)
- Validation & verification map
- Dependency surfaces and stability policy
- Manifest with generation metadata

## Domain-conditional sections (based on profiles)
- Numerical safeguards & stability notes (scientific compute / image processing / ML)
- Training/inference specifics (ML)
- Determinism/reproducibility (ML/compute)
- GUI workflows & export schemas (GUI/tooling)
- Safety/hardware/limits & calibration (control/embedded + lab tooling)
- Geometry/mesh quality metrics and IO (mesh/geometry)

## Core workflow (high-level)
Follow references/WORKFLOW.md in order:
1) Inventory and repo map
2) Select profiles (1–3)
3) Generate top-level architecture + dataflow
4) Generate workflows (entry points + typical runs)
5) Generate glossary + artifacts registry + conventions (units/frames)
6) Per-module docs (inheritance, API contracts, signatures, unused params callouts)
7) Per-class docs (state/lifecycle/call graph summary)
8) Per-function docs (math/physics, algorithm, complexity, safeguards, failure modes)
9) Validation/verification map
10) Stability policy + dependency surfaces
11) Run quality gates and fix gaps
12) Write manifest

## Non-negotiable rules
- Never invent modules/classes/functions. Diagrams must correspond to real identifiers.
- Anything inferred from names/comments must be marked **Inferred**.
- Only label “intentionally unused parameter” if verified (see references/WORKFLOW.md).
- Every equation symbol must appear in the glossary.
- Include at least 1 runnable “minimal example” per selected profile (may be pseudo-runnable if repo lacks fixtures, but must specify commands and expected artifacts).