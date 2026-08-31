# Authoring a v2 knowledge node

The v2 schema is **frozen**. Adding or removing a required field, or changing a
field's type, is a breaking change requiring a v3 bump and a migration — not an
edit you make because a node needs somewhere to put something.

## Frontmatter fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | str | **yes** | Stable, kebab-case, unique across vault + local |
| `title` | str | **yes** | One line, human-readable |
| `domain` | str | **yes** | Broad area, e.g. `computational-mechanics` |
| `status` | enum | **yes** | `draft` \| `tentative` \| `established` \| `deprecated` |
| `source` | enum | **yes** | `human` \| `agent` \| `hybrid` \| `generated` |
| `tags` | list[str] | **yes** | At least one. The primary retrieval key. |
| `subdomain` | str \| null | no | Narrower area |
| `confidence` | float | no | `0.0`–`1.0` |
| `confidence_floor` | float \| null | no | `0.0`–`1.0`; decay will not go below it |
| `edges` | list[edge] | no | Structural edges, see below |
| `load_with` | list[str] | no | Node ids that should load alongside this one |
| `context_size` | enum \| null | no | `small` \| `medium` \| `large` |
| `reading_priority` | enum \| null | no | `full` \| `summary` \| `pitfalls-only` |
| `content_ref` | str \| null | no | Path to the content this node describes |
| `akms_schema` | str | no | Defaults to `v2`; set it explicitly anyway |

## Edges

```yaml
edges:
  - to: sparse-linear-solvers
    type: requires
    weight: 0.8
    note: assembly produces the system these solve
```

| `type` | Meaning |
|---|---|
| `requires` | This node is not usable without the target |
| `feeds-into` | Output of this node is input to the target |
| `refines` | Narrows or specialises the target |
| `contradicts` | Conflicts with the target — surfaced, not silently resolved |
| `pitfall` | Target records a trap in applying this node |
| `implements` | Concrete realisation of the target |

`weight` is `0.0`–`1.0` and drives confidence propagation.

## Status rules

- **Agent-authored nodes must enter as `tentative`.** Only human-authored nodes
  may start `established`.
- `promote` moves tentative → established. It is a judgement that the node has
  proven correct in use, not a formality to run at creation.
- `suppress` sets a node to `draft` so it stops surfacing without losing it.
- `deprecate` retires a node that is wrong or superseded.

## Body structure

The validator checks the body, not just the frontmatter:

| Section | Status | Notes |
|---|---|---|
| `## Summary` | **required** | Missing it is an **error**. This is the text shown in routing-mode loadouts. |
| `## 1. Core Concept` | recommended | Omission is INFO-level |
| `## 2. Mathematical Formulation` | recommended | Omission is INFO-level |
| `## Known Pitfalls` | recommended | Also accepted as `## 4.` / `## 5. Known Pitfalls` |

Two exact-spelling traps:

- The pitfalls heading must be **`Known Pitfalls`**. A section titled
  `## Pitfalls` is not recognised and the validator will report the section as
  missing.
- `## Summary` should run about 40–80 words. Below 15 words it warns.

Because `## Summary` is what routing mode displays, a node with a thin summary
is effectively invisible in the most common retrieval path even when the rest of
its content is excellent.

## The bar for content

> A first-year PhD student should be able to implement the node from its
> content alone, without reading the source papers.

If a reader would still have to go find the paper, the node is not finished.
Nodes that merely point at literature add retrieval cost and no knowledge.

Pitfalls are the highest-value part of most nodes — they are what an agent
cannot derive.

## Validate before committing

AKMS ships a validator. Point it at a file or a directory:

```bash
python -m akms.tools.node_validator knowledge/local-nodes/my-node.md
python -m akms.tools.node_validator knowledge/local-nodes/ --strict
```

Useful flags: `--strict` (warnings become errors, exit 1), `--json` (machine
readable), `--fix` / `--dry-run` (apply mechanical repairs), `--quiet`.

From Python, the pieces are `parse_md_file`, `validate_frontmatter`, and
`validate_body` — there is no single `validate_node` entry point:

```python
from pathlib import Path
from akms.tools.node_validator import parse_md_file, validate_frontmatter

fm, body, issues = parse_md_file(Path("knowledge/local-nodes/my-node.md"))
if fm is not None:
    model, more = validate_frontmatter(fm, body)
    issues += more
for issue in issues:
    print(issue)
```

Or scaffold a known-valid node and edit from there:

```bash
python skills/akms/scripts/new_node.py my-node --domain computational-mechanics --tags fem assembly
```
