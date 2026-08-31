# Development setup

## Prerequisites

- Git
- uv
- Python 3.12 for all-workspace development
- A sibling `../MechDSL` checkout only when developing the optional executable
  adapter with all extras

## Core development

```bash
git clone <repository-url>
cd AKMS
uv sync --project Packages/AKMS --all-extras --all-groups
uv run --project Packages/AKMS pytest Packages/AKMS/tests/akms -q
```

## Whole workspace

```bash
uv sync --all-packages --all-extras --all-groups
```

Use package-scoped commands when you do not need the sibling MechDSL sources.

## Documentation

```bash
uv sync --group docs
python tools/check_docs_contract.py
uv run --group docs mkdocs build --strict
uv run --group docs mkdocs serve
```

## Repository layout

```text
Packages/
  AKMS/                    core distribution
  AKMS_nodes_gen/          node-generation distribution
  FailureMemory/           optional failure-memory distribution
  Nodes_Vault/             knowledge content, not a Python package
packages/
  AKMS_learn/              learning-packet compiler
  compmech_reference_pack/ executable companion adapter
docs/                      unified MkDocs site
dev/                       design, plans, reviews, and task records
```

Read the package-local `CLAUDE.md` and frozen design documents before changing
schema or public-contract code. Do not copy their transient test totals into
public docs.
