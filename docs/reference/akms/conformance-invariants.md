# AKMS conformance invariants

**Normative.** This is the checkable subset of the frozen v2 specification: the
contracts an implementation can be audited against mechanically.

It exists so that a conformance audit has one mechanically checkable target.
The full public specification ships alongside it at
[`specification/AKMS_v2_specification.md`](../../specification/AKMS_v2_specification.md);
the internal design documents it was consolidated from are not published.
Auditing against this page, rather than against documents an implementer may
not hold, is the difference between a real check and one that silently
verified nothing.

The full specification remains authoritative where the two disagree;
requirement IDs below (`FR-*`, `NFR-*`) point back into it. This page is
deliberately narrow: it records what is frozen, not why.

!!! note "Kept honest by a test"

    The vocabulary and constant tables below are asserted against
    `akms.schema.models` by `tests/akms/test_invariants_doc.py`. If the code and
    this page disagree, that test fails. Nothing here is maintained by hand alone.

---

## 1. Frozen vocabulary — `INV-VOCAB`

Enum values are frozen at v2. Adding, removing, or renaming a value is a breaking
change requiring a v3 bump and a migration.

| Enum | Frozen values |
|---|---|
| `NodeStatus` | `draft` · `tentative` · `established` · `deprecated` |
| `NodeSource` | `human` · `agent` · `hybrid` · `generated` |
| `EdgeType` | `requires` · `feeds-into` · `refines` · `contradicts` · `pitfall` · `implements` |
| `ContextSize` | `small` · `medium` · `large` |
| `ReadingPriority` | `full` · `summary` · `pitfalls-only` |
| `AgentRole` | `implementer` · `code_reviewer` · `physics_reviewer` |
| `LoadoutMode` | `routing` · `full` |
| `Coverage` | `sufficient` · `missing-detail` · `outdated` |
| `Priority` | `high` · `medium` · `low` |
| `Severity` | `high` · `medium` · `low` |
| `TaskStatus` | `complete` · `partial` · `failed` · `deferred` |
| `SessionOutcome` | `success` · `partial` · `failed` |
| `ImpactOnNextPhase` | `none` · `low` · `blocking` |
| `TitleMatch` | `whole_word` · `substring` |

## 2. Frozen constants — `INV-CONST`

| Constant | Value | Meaning |
|---|---|---|
| `AKMS_SCHEMA_VERSION` | `v2` | Every schema-bearing file must carry `akms_schema: v2` |
| `LOADABLE_STATUSES` | `established` · `tentative` | Only these statuses may enter a loadout (FR-G04) |
| `EXPERIENTIAL_FIELDS` | `activated_by_tasks` · `activations` · `auto_update` · `last_activated` · `session_refs` | Must never appear on a global vault node (FR-O01) |

`draft` and `deprecated` are therefore never loadable. A retrieval path that
returns them is non-conformant.

## 3. Node identity — `INV-NODE`

- **`INV-NODE-01`** — Required frontmatter: `id` · `title` · `domain` · `status` · `source`, plus
  `tags` with **at least one** entry.
- **`INV-NODE-02`** — `confidence` and `confidence_floor`, when present, lie in
  `[0.0, 1.0]`.
- **`INV-NODE-03`** — Global node frontmatter rejects unknown fields
  (`extra = "forbid"`); an unexpected field is an error, not a warning.
- **`INV-NODE-04`** — An agent-authored node enters as `tentative`. Only a
  human-authored node may enter as `established`. Promotion is a separate,
  deliberate act (FR-O08).
- **`INV-NODE-05`** — Node bodies require a `## Summary` section: it is the text
  routing-mode loadouts render, so a node without one is effectively invisible in
  the most common retrieval path.

## 4. Write targets — `INV-WRITE`

- **`INV-WRITE-01`** — The global vault is **read-only** to every automated
  process. Resolution order: `$AKMS_GLOBAL_VAULT` → config `global_vault` →
  `~/.claude/akms/nodes` (FR-O01, NFR-R03).
- **`INV-WRITE-02`** — `update_graph` writes only to `local_state.yaml` and
  `local-nodes/`. Never to a global node file (FR-U08).
- **`INV-WRITE-03`** — Loadout artifacts are written through one module only
  (`generate_loadout`), the single-writer boundary.
- **`INV-WRITE-04`** — A read-only operation creates nothing. A path that only
  reads must not create directories, lock parents, or output roots as a side
  effect.

## 5. Graph compilation — `INV-GRAPH`

- **`INV-GRAPH-01`** — Merge order is fixed: global → local → code-mirror →
  overlay → serialize (NFR-D06).
- **`INV-GRAPH-02`** — On an id collision the global node wins; the local node is
  skipped and the collision logged (FR-O03).
- **`INV-GRAPH-03`** — Every node carries `node_origin`
  (`global` / `local` / `code-mirror`) and every edge carries `edge_origin`
  (NFR-I06).
- **`INV-GRAPH-04`** — Local edges are append-only over global edges.
- **`INV-GRAPH-05`** — `graph.json` is serialized with `sort_keys=True, indent=2`
  (NFR-I02).
- **`INV-GRAPH-06`** — A schema-version mismatch raises `SchemaVersionError`
  rather than degrading (FR-G08).

## 6. Determinism — `INV-DET`

- **`INV-DET-01`** — Identical inputs produce byte-identical outputs.
- **`INV-DET-02`** — Graph mutations are idempotent for repeated inputs
  (NFR-D01–D06).
- **`INV-DET-03`** — No wall-clock time, absolute host path, or iteration-order
  accident may reach a published artifact. Timestamps are explicit arguments, not
  defaults.
- **`INV-DET-04`** — Retrieval results are sorted deterministically before use.

## 7. Fail-closed retrieval — `INV-FAIL`

- **`INV-FAIL-01`** — A tag query is a **ranking** signal. It never establishes
  that required knowledge exists.
- **`INV-FAIL-02`** — Exact task resolution fails closed: when a required node is
  unavailable it raises with a structured error code and emits **no** partial
  loadout.
- **`INV-FAIL-03`** — A resolution manifest records what was selected and why, so
  coverage can be checked rather than trusted.
- **`INV-FAIL-04`** — A capability that cannot verify its precondition reports
  that it could not, rather than reporting success. Absence of evidence is never
  rendered as evidence of absence.

## 8. No LLM in graph operations — `INV-PURE`

- **`INV-PURE-01`** — Tag derivation is pure string matching (FR-T05).
- **`INV-PURE-02`** — Subgraph queries, dedup, and confidence propagation are
  deterministic algorithmic paths with no model call.
- **`INV-PURE-03`** — Optional LLM use is confined to mirror docstring-drift
  checks and never affects graph structure.

---

## Auditing against this page

`skills/akms-spec-check/` and `agents/akms-spec-reviewer.md` audit an
implementation against these IDs. Cite the ID in a finding
(`INV-GRAPH-02 violated: local node silently overwrote global`) so the finding is
traceable without the design documents.

Where a check needs detail this page does not carry, the design documents are the
authority — and if they are absent, say so rather than passing the check.
