# compmech-reference-pack

The computational-mechanics companion adapter for
[AKMS](https://github.com/CEmM2/AKMS). It bridges `akms-learn` Learning Source
Packet excerpts to the [MechDSL](https://github.com/CEmM2/MechDSL) executable
backend, so an algorithm described in a knowledge node can be transpiled and
compiled rather than only read.

It ships the `compmech` domain pack — the descriptor and source packs that tell
`akms-learn` which companions exist and what each can do.

## Install

```bash
pip install compmech-reference-pack
```

That gives you the domain pack and the adapter's declared capability surface,
and pulls in `akms-learn`. It does **not** pull in the MechDSL backend: every
`mechdsl` and `algo2code` import in this package is function-scoped, so it
installs and imports cleanly without them.

To enable the actual compile, transpile and verify path:

```bash
pip install "compmech-reference-pack[mechdsl]"
```

The extra exists so a downstream consumer can depend on this package without
dragging the executable backend — and transitively Taichi — into its
resolution.

## What it provides

- **`MechDSLRunner`** — the `executable_bridge` adapter. Given an LSP excerpt
  it normalises the algorithmic block, derives a safe algorithm name, and
  delegates to MechDSL's `transpile_algorithm` / `compile_from_sources`.
  Provenance is preserved from node to generated artefact.
- **`capabilities()`** — a declaration of what the package offers, kept
  deliberately import-light and Taichi-free so a caller can ask without paying
  for a backend it may not use.
- **The `compmech` domain pack** — `domain_pack.yaml` plus the source packs
  under `domain_pack/source_packs/`, addressed through
  `compmech_reference_pack.paths`.

## Companion status

| Companion | Role | Status |
|---|---|---|
| `mechdsl` | executable bridge | available |
| `constkit` | concept kit | planned |
| `symbolic_fem_workbench` | pedagogical workbench | planned |

`planned` describes the adapter, not the source: the material for both planned
companions is public, in
[SOSOVSKI/Teaching-materials](https://github.com/SOSOVSKI/Teaching-materials).

## Licence

Apache-2.0, matching AKMS.
