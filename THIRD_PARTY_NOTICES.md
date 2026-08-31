# Third-party notices

AKMS vendors no third-party source code. This file records external material
and tools the project references or interoperates with.

## Runtime dependencies

Python dependencies are declared in each package's `pyproject.toml` and are
installed from PyPI under their own licenses. They are not redistributed in
this repository.

License compatibility was audited on 2026-08-18 across the full resolved
environment (137 distributions, `uv.lock`): the runtime dependency closure of
all four packages, including every optional extra (101 distributions), contains
only permissive licenses (MIT, Apache-2.0, BSD, ISC, PSF) and MPL-2.0
(file-level terms that impose no obligations on unmodified dependency use).
No GPL/AGPL-family license appears in the runtime closure; the sole flagged
entry (`docutils`, multi-licensed with optional GPL components) is reached only
through development tooling (`readme-renderer`) and is neither imported at
runtime nor redistributed. Nothing in the dependency tree constrains this
repository's outbound Apache-2.0 / CC BY 4.0 licensing.

## External tools (referenced, not bundled)

- **qmd** (https://github.com/tobi/qmd) — external Go binary used by optional
  search paths; detected at runtime and never redistributed. When absent, AKMS
  falls back to `grep`.
- **nlm** (NotebookLM CLI) — external binary used by optional node-generation
  paths; probed at runtime, never redistributed.
- Coding-agent backends (Claude Code, Codex, and OpenAI-compatible endpoints)
  are reached through their own SDKs or CLIs under their own terms.

## Bundled knowledge content

The `akms` package ships 302 knowledge nodes. They are **not uniform in
provenance**, and the `source` field on every node records which of the three
categories below it belongs to.

| `source` | Count | What it means |
|---|---|---|
| `human` | 52 | Original summaries written by the repository author. |
| `hybrid` | 180 | Author-directed summaries of published scientific literature, drafted with machine assistance and reviewed by the author. |
| `agent` | 70 | Machine-generated summaries of a third-party codebase (MOOSE), reviewed by the author. |

No third-party text or source code is reproduced anywhere in the corpus: the
nodes contain no verbatim quotation and no copied code listings. Published
scientific methods (for example anisotropic yield criteria, phase-field
fracture formulations, and FFT-Galerkin micromechanics) are cited by name and
reference only. 88 nodes carry `status: tentative`; treat those as
lower-confidence material.

Documentation and knowledge nodes are licensed under CC BY 4.0; see
`README.md` for the licensing split. That license covers **this project's
expression of these summaries**, not the underlying software or publications
they describe.

### Generation provenance

- **NotebookLM** (Google) and the **nlm** CLI — used to extract and organize
  material from published literature when drafting the `hybrid` nodes. Outputs
  were reviewed before inclusion. No NotebookLM text is reproduced verbatim.
- **DeepWiki** (https://deepwiki.com) — used to index and summarize the MOOSE
  codebase when drafting the 70 `agent` nodes. Each such node carries a
  stable attribution line pointing at the MOOSE repository and its DeepWiki
  index. No DeepWiki text is reproduced verbatim.

### Software described by the bundled knowledge content

Some nodes describe the architecture and public APIs of third-party projects.
Interface and architectural facts are not the protected expression of those
projects, and no code from them is reproduced here — but they are named and
acknowledged below. **AKMS is not affiliated with, endorsed by, or a
derivative work of any of them.**

- **MOOSE** — Multiphysics Object-Oriented Simulation Environment, Idaho
  National Laboratory. https://github.com/idaholab/moose — LGPL-2.1.
  The subject of the 70 `moose-*` nodes, which describe its kernel, action,
  material and solver architecture. All MOOSE trademarks belong to INL.
- **Gmsh** — Christophe Geuzaine and Jean-François Remacle.
  https://gmsh.info — GPL-2.0-or-later (with exceptions). The subject of the
  10 `gmsh-*` nodes, which describe its geometry, meshing and export APIs.
  AKMS neither links against nor redistributes Gmsh; describing its API does
  not make this repository a derivative work.
- **Taichi** — https://github.com/taichi-dev/taichi — Apache-2.0. The subject
  of the `tgs-*` GPU-simulation nodes.
- **Abaqus** — Dassault Systèmes. Referenced by one node describing
  UEL/UMAT user-subroutine practice. Abaqus is a registered trademark of
  Dassault Systèmes; the reference is nominative and no Abaqus material is
  included.
- **PETSc**, **libCEED**, **NumPy**, **PyTorch** and **CuPy** are mentioned in
  passing as ecosystem context, under their own respective licenses.

If you believe any content in this repository is improperly attributed or
licensed, please open an issue or use the contact in `SECURITY.md`.
