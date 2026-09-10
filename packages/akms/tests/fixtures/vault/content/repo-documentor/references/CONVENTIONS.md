# Documentation conventions

## Markdown output structure
Default tree (can be adjusted to repo needs):

docs/
- index.md
- repo-map.md
- _profiles.md
- _manifest.yml
- architecture/
  - overview.md
  - module-deps.md
  - dataflow.md
  - dependency-surfaces.md
- workflows/
  - entrypoints.md
  - typical-runs.md
- glossary/
  - data-types-and-symbols.md
  - artifacts.md
- conventions/
  - units-and-frames.md
  - naming.md
- api/
  - public-api.md
  - stability.md
- modules/
  - <module_name>.md
- classes/
  - <ClassName>.md
- functions/
  - <function_or_kernel>.md
- validation/
  - verification-map.md
  - tests-to-modules.md
  - benchmarks.md
- stability/
  - numerical-safeguards.md
  - determinism.md
- security/
  - hardware-and-safety.md  (only when applicable)

## Admonitions (Markdown)
Use GitHub-style callouts:

> [!IMPORTANT]
> Intentionally-unused parameter: `dt` is accepted to preserve a standardized signature across integrators.

> [!NOTE]
> **Inferred**: symbol `$\\sigma$` is used for stress based on naming/comments.

> [!WARNING]
> Side effect: mutates global cache / persistent buffers.

## LaTeX structure
Use `assets/latex/main_article.tex` or `assets/latex/main_book.tex`.
Sections live in `assets/latex/sections/`.

## Style rules
- Do not invent identifiers. Cite exact names from code.
- Mark inferred items explicitly.
- Every math symbol used in equations must appear in the glossary.
- Prefer Mermaid for Markdown diagrams; TikZ or included PDFs for LaTeX.