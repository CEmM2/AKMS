# Core concepts

## Knowledge node

A Markdown document whose YAML frontmatter validates as one of the frozen v2
node forms:

- **Global node:** reusable domain knowledge in the read-only global vault
- **Local node:** project-owned human or agent knowledge
- **Code-mirror node:** generated existence/provenance marker for a source file or
  definition
- **Session node:** generated from the local experiential overlay

## Structural edge

A typed relation declared in node frontmatter. Supported values are:

`requires`, `feeds-into`, `refines`, `contradicts`, `pitfall`, and `implements`.

## Experiential overlay

`knowledge/graph/local_state.yaml` stores project-local confidence overrides,
activation history, local edges, session nodes, and the replay ledger used by
explicit update operations. It does not rewrite the global vault.

## Compiled graph

`knowledge/graph/graph.json` is the generated NetworkX node-link projection of
global nodes, local nodes, code mirrors, and the experiential overlay.
Selection and ordering are deterministic for identical semantic inputs. The
ordinary serializer includes a wall-clock `generated_at` field, so do not treat
raw file bytes as a timeless content hash.

## Ranked advisory query

`query_subgraph()` starts from matching tags, traverses permitted edge types for
the selected role, filters by status/domain/confidence, ranks candidates, and
injects relevant pitfalls. It returns a ranked list for loadout construction.

## Task route index

A project-local v1 mapping from repository paths and optional symbols to node
IDs that a task must receive. Routes are separate from frozen v2 node
frontmatter.

## Selection classes

Exact task resolution distinguishes:

- **Required:** exact mirror or route-bound knowledge; uncapped and fail-closed
- **Coactivated:** nodes requested by `load_with` from an exact selection
- **Advisory:** ordinary role-aware tag/query results subject to thresholds and
  caps

## Resolution manifest

A canonical record binding task inputs, changed paths, role, graph version,
route-index hash, resolved seeds, selections, and a fingerprint. It lets a
reviewer verify which knowledge snapshot produced a loadout.

## Loadout

A Markdown artifact for an agent or reviewer. Routing mode emphasizes summaries
and paths; full mode inlines available content. Required-aware loadouts render
required, coactivated, and advisory sections separately.

## Mirror provider

A pluggable source projection boundary that writes validated code-mirror nodes.
The built-in providers are `legacy` (Python AST) and `repo2md` (external CLI).
Provider choice must not change task-route semantics after equivalent validated
mirrors are on disk.

## Failure memory

An optional package for project-owned canonical lesson registries and generated
AKMS projections. It is not an implicit part of core updates and never promotes
lessons into the global vault.

## Optional pipeline runner

A staged coordinator that can consume these surfaces, dispatch agent roles, and
checkpoint work. It is an integration, not a prerequisite or a synonym for
AKMS.
