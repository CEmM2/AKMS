# Quickstart

This walks through a small throwaway repository: build a wiki, query it, and
write an AKMS code mirror. It assumes `akms` is installed
([Installation](../../../getting-started/akms/installation.md)) so that
`repo-wiki` is on your `PATH`.

## Create a sample repository

```bash
mkdir demo && cd demo
git init -q
mkdir -p src/shapes
cat > src/shapes/area.py <<'PY'
"""Area helpers."""

import math


def circle_area(radius: float) -> float:
    """Return the area of a circle."""
    return math.pi * radius**2


class Square:
    """A square."""

    def __init__(self, side: float) -> None:
        self.side = side

    def area(self) -> float:
        return self.side**2
PY
```

## Initialize

```bash
repo-wiki init
```

```text
Initialized repo wiki at <path>/demo/.repo_wiki
created: .repo_wiki/overlays
created: .repo_wiki/config.yaml
created: .repo_wiki/SPEC.md
```

`init` writes the default [configuration](configuration.md) and an empty
`overlays/` directory for notes you write by hand. It never overwrites an
existing `config.yaml` or `SPEC.md`.

## Scan

```bash
repo-wiki scan
```

```text
Eligible files: 3
Skipped files: 2
.repo_wiki/SPEC.md
.repo_wiki/config.yaml
src/shapes/area.py
```

`scan` shows what the next steps will read, before anything is written. The
`.repo_wiki/` files are eligible but are not parsed: only Python has an
extractor enabled by default. Add `--json` for the full list with a reason for every
skipped file (`excluded`, `not_included`, `too_large`, `binary`, `symlink`).

## Build

```bash
repo-wiki build
repo-wiki stats
```

```text
--- build summary ---
processed: 1
skipped:   2
errored:   0
--- end summary ---
Repo: demo
Initialized: True
Tracked files: 1
Generated docs: 10
```

`build` parses each source file and writes module pages, symbol pages, local
summaries, a repo map and a symbol graph under `.repo_wiki/generated/`. Unless
you pass `--no-index`, it also builds the search index. After editing sources,
`repo-wiki build --changed-only` reprocesses only what changed, and `--force`
reprocesses everything. `build` exits 1 if any file failed to parse; the
failures are listed in `.repo_wiki/build_errors.json`.

## Query

```bash
repo-wiki query circle_area
repo-wiki query --no-answer --top-k 3 "how is the area of a circle computed"
```

`query` searches the index and prints the ranked results, then an "Answer"
block. The answer is a list of citations (`path:Lstart-end`) into the
retrieved context; no language model writes it, and the source file stays
the authority. With `--no-answer` it prints the results and their surrounding
context instead (parents, children, callers and callees). Add `--json` for
machine-readable output.

If you changed the generated pages by hand, or skipped the index during
`build`, refresh the index with `repo-wiki index`. To search without the
question wrapper, `repo-wiki index --query circle_area` prints matching index
entries as JSON.

## View the symbol graph

```bash
repo-wiki graph
```

Serves `.repo_wiki/generated/symbol_graph.json` at `http://127.0.0.1:8765/` and
opens a browser. Use `--no-browser` to skip that, and `--host` and `--port` to
change the address. Stop it with Ctrl-C.

## Write an AKMS code mirror

```bash
SOURCE_DATE_EPOCH=1767225600 repo-wiki export-akms --output . --phase 1
```

```text
written: .knowledge/code-mirror/src/shapes/area.md
skipped (unsupported_language): .repo_wiki/SPEC.md
skipped (unsupported_language): .repo_wiki/config.yaml
```

This projects each supported source file into one Markdown document with AKMS
v2 code-mirror frontmatter, under `<output>/.knowledge/code-mirror/`.
`export-akms` does not read the wall clock, so you must give it a timestamp,
here through `SOURCE_DATE_EPOCH`; `--generated-at` is the alternative. It does
not require `build` to have run first.

Running the same command with `--changed-only` rewrites only mirrors whose
content differs:

```bash
SOURCE_DATE_EPOCH=1767225600 repo-wiki export-akms --output . --phase 1 --changed-only
```

```text
skipped (unsupported_language): .repo_wiki/SPEC.md
skipped (unsupported_language): .repo_wiki/config.yaml
skipped (unchanged): src/shapes/area.py
```

To export only what changed since a git ref, use `--git-base`:

```bash
git add src
git -c user.name=demo -c user.email=demo@example.com commit -qm "Add demo"
echo "# touched" >> src/shapes/area.py
SOURCE_DATE_EPOCH=1767225600 repo-wiki export-akms --output . --phase 1 --git-base HEAD
```

See [AKMS export](akms-export.md) for all flags. In an AKMS project you
normally do not run `export-akms` yourself: `akms generate-mirror` runs it
through the `builtin` provider, which also chooses the right `--knowledge-dir`.
