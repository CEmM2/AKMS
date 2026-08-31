# AKMS v2 — Public Specification

> **Adaptive Knowledge Management System** — a knowledge infrastructure layer that gives
> coding agents persistent, structured, domain-aware memory via a directed knowledge graph.
>
> **Schema version:** `akms/v2` (frozen).
> This document is the public contract for AKMS v2. It consolidates the frozen v2 design
> documents into a single reference. Requirement language follows RFC-2119 conventions:
> **MUST** (non-negotiable), **SHOULD** (strong preference), **MAY** (optional).

---

## Table of Contents

1. [What AKMS Is](#1-what-akms-is)
2. [Concepts and Terminology](#2-concepts-and-terminology)
3. [Core Invariants and Guarantees](#3-core-invariants-and-guarantees)
4. [The Frozen v2 Schema](#4-the-frozen-v2-schema)
5. [Architecture and Algorithms](#5-architecture-and-algorithms)
6. [Contracts for External Consumers](#6-contracts-for-external-consumers)
7. [Performance Targets](#7-performance-targets)
8. [Schema Versioning and Compatibility Policy](#8-schema-versioning-and-compatibility-policy)

---

## 1. What AKMS Is

Coding agents start every session cold: hard-won domain knowledge, prior task outcomes,
and discovered pitfalls are invisible to future runs. AKMS solves this by connecting
plain-text knowledge assets into a **living directed knowledge graph** that is compiled
deterministically, queried algorithmically, and updated through a human-reviewed
feedback loop.

### 1.1 The Model

AKMS represents knowledge as **nodes** — Markdown files with YAML frontmatter — connected
by **typed, weighted, directed edges**. The graph is split across two layers:

- **Global layer** (the *global vault*, default `~/.claude/akms/nodes/`): domain knowledge
  nodes shared across every repository on a machine — the single source of truth for
  concepts, derivations, and patterns. Read-only to all automated processes.
- **Local layer** (`<repo>/knowledge/`): repository-specific state — experiential
  confidence scores, activation history, repo-local nodes, session records, pitfall
  edges, generated code mirrors, and generated loadouts. Zero cross-contamination
  between repositories.

A compiler merges both layers into a single **compiled graph** (`graph.json`), so each
repository sees the universal domain knowledge through the lens of its own experiential
state. The same global node can carry different confidence scores in different
repositories, with no manual synchronization, and the global file is never modified.

The graph feeds agents through **loadouts**: generated, ephemeral, inspectable Markdown
files containing the task-specific knowledge slice — relevant nodes, pitfall warnings
with session references, relevant session history, and a suggested reading order.
Agents write back **AgentMemory** files (per task) and **Phase Completion Documents**
(per phase); a deterministic update step folds that evidence into the local overlay.
Agent-drafted knowledge always enters as reviewable drafts — a human decides what
becomes trusted.

### 1.2 The Global–Local Split (Overlay Architecture)

```
GLOBAL VAULT (~/.claude/akms/)            REPO-LOCAL (<repo>/knowledge/)
┌──────────────────────────┐              ┌──────────────────────────────┐
│  nodes/                  │──────────────│  graph/                      │
│    *.md                  │  build_graph │    graph.json  (compiled)    │
│    (read-only            │  merges both │    local_state.yaml          │
│     from repos)          │──────────────│    propagation_config.yaml   │
└──────────────────────────┘              │  local-nodes/  (repo nodes)  │
                                          │  sessions/     (memories)    │
Global: intrinsic content + structure     │  loadouts/     (generated)   │
                                          │  code-mirror/  (generated)   │
                                          └──────────────────────────────┘
                                          Local: experiential state +
                                            repo-specific knowledge
```

**Confidence separation.** A global node carries an intrinsic `confidence` (the author's
quality assessment). Each repository tracks its own experiential confidence in
`local_state.yaml`. The compiler uses the local override when present, otherwise the
global value as seed/default.

**Promotion path.** Agent-drafted nodes land in `<repo>/knowledge/local-nodes/` with
`status: tentative`. If a node proves universally useful, a human manually moves it to
the global vault and marks it `established`. The system MUST NOT automate this promotion.

### 1.3 Non-Goals

AKMS v2 is explicitly **not**:

- A general-purpose RAG or document-retrieval system.
- An autonomous, self-modifying knowledge base — every promotion passes a human review gate.
- A GUI or visualization product.
- A real-time graph updater — graph mutations happen between work phases, never during
  agent execution.
- A per-repository edge suppressor — `suppressed_edges` is a reserved hook only (§4.2).

### 1.4 Design Constraints

- **Language:** Python for all orchestration and graph tooling.
- **Graph engine:** NetworkX; the compiled graph serializes to NetworkX node-link JSON.
- **Search:** the `qmd` search tool (literal + semantic search over Markdown), used as
  a content-retrieval layer scoped to node sets the graph has already selected. AKMS
  operates in a documented degraded mode when qmd is absent (§3.6).
- **Storage:** filesystem only — no database, no external service.
- **Source of truth:** node `.md` frontmatter is authoritative for content and structural
  edges; `local_state.yaml` is authoritative for experiential state; `graph.json` is a
  derived artifact, always rebuildable from the sources.

### 1.5 Usability Requirements

These are first-class requirements of the design, not afterthoughts:

| ID | Requirement |
|---|---|
| UR-01 | The system MUST be useful from the first session without any pre-written knowledge nodes (cold-start tolerance). |
| UR-02 | Incomplete nodes (`draft`, `tentative`) MUST be valid graph citizens — there is no "complete before use" gate. |
| UR-03 | The review step MUST require no more than reading plus one CLI command per node. |
| UR-04 | All tunable parameters MUST live in a single `propagation_config.yaml` file per repository. |
| UR-05 | Agent-written content MUST be clearly marked as agent-authored at all times (provenance always visible). |
| UR-06 | The review report MUST be scannable quickly — no walls of text. |
| UR-07 | Writing a new knowledge node by hand MUST require only adding YAML frontmatter to an existing `.md` file. |
| UR-08 | Confidence scores and node statuses MUST be visible in the review report without opening node files or `local_state.yaml`. |

---

## 2. Concepts and Terminology

| Term | Meaning |
|---|---|
| **Node** | A unit of knowledge: a `.md` file with YAML frontmatter (identity, status, edges) and a free-form Markdown body. The body is never parsed by graph tooling — only searched by qmd. |
| **Global vault** | The shared, machine-level node directory (default `~/.claude/akms/nodes/`, overridable via the `AKMS_GLOBAL_VAULT` environment variable or the `global_vault` config field). Read-only to automation. |
| **Local node** | A repository-specific node in `<repo>/knowledge/local-nodes/`, either agent-drafted (`tentative`) or human-written for that repo. |
| **Local overlay** | `<repo>/knowledge/graph/local_state.yaml` — the repository's experiential state: per-node confidence overrides, activation history, repo-local edges, session-node registry. |
| **Compiled graph** | `<repo>/knowledge/graph/graph.json` — the deterministic merge of global nodes, local nodes, code-mirror nodes, and the local overlay, in NetworkX node-link format. |
| **Edge** | A typed, weighted, directed relationship between two nodes (§4.1.3). |
| **Loadout** | A generated `.md` file delivering a task-specific knowledge slice to an agent. Ephemeral, cacheable, never hand-edited. |
| **AgentMemory** | A per-task structured record written by a task agent at completion (§4.3). |
| **Phase Completion Document (PCD)** | A per-phase record aggregating all task AgentMemories, plus phase-level context (§4.4). |
| **Session node** | A graph node with `domain: session` representing a session artifact file. Session nodes are the valid targets of `pitfall` edges — raw file paths are not. |
| **Code mirror** | A generated search index in `<repo>/knowledge/code-mirror/`: one `.md` per source file, containing each function's docstring (semantic search layer) and full source (literal search layer). Mirror nodes are existence markers, not graph participants (§4.7). |
| **Activation** | One recorded use of a node by a task; per-repository counts live in the overlay. |
| **Confidence** | A float in [0, 1] expressing trust in a node — intrinsic (global frontmatter, author-assessed) or experiential (local overlay, usage-driven). |
| **Query profile / agent role** | A named configuration (`implementer`, `code_reviewer`, `physics_reviewer`) selecting which edge types, ranking formula, and domain filters a subgraph query uses (§5.3). |

---

## 3. Core Invariants and Guarantees

These invariants define what an external user can trust about the system's behavior.

### 3.1 The Global Vault Is Read-Only

- No automated process may modify global node files — ever. Repo-level tooling MUST
  treat the global vault as strictly read-only (FR-O01, NFR-R03).
- All write-back from agent evidence goes exclusively to `local_state.yaml` and
  `<repo>/knowledge/local-nodes/`.
- Agent-drafted nodes MUST be created under `local-nodes/`, never in the global vault
  (FR-O07).
- Promotion of a local node to global MUST be a manual human action (file move plus
  status change); the system MUST NOT automate it (FR-O08).
- The system MUST NOT modify any file outside `<repo>/knowledge/` without explicit
  developer action.

### 3.2 No LLM in Graph Operations

All graph operations are pure algorithmic paths. Given the same inputs, they produce
the same outputs, with no model call anywhere in the chain:

- **Tag derivation** (from task descriptions and file scopes) MUST NOT use LLM calls —
  pure string matching only (FR-T05; algorithm in §4.5).
- **Subgraph queries** are deterministic graph algorithms (seed matching, ego-graph
  expansion, filtering, ranking) over the compiled graph.
- **Deduplication** of newly drafted knowledge is deterministic threshold-based lexical
  scoring (token Jaccard, with exact-id treated as score 1.0) — no LLM calls.
- **Confidence propagation** is closed-form arithmetic (§5.5.2).

The only place a model call MAY appear anywhere in the toolchain is the optional
*semantic* docstring-drift check during code-mirror generation (§5.6) — an auxiliary
quality signal, not a graph operation. The deterministic drift path never invokes a model.

### 3.3 Determinism and Reproducibility

- Given the same graph state (global + local) and task description, a subgraph query
  MUST return the same node set (NFR-D01).
- Loadout generation MUST be reproducible — same inputs, same loadout (NFR-D02).
- The compiled-graph merge order MUST be deterministic and executed in a fixed
  five-step sequence (§5.2); serialization uses stable key ordering
  (`sort_keys=True, indent=2`) so `graph.json` is human-diffable (NFR-D06, NFR-I02).
- qmd search results MUST be sorted deterministically by `(file_path, line_number)`
  after retrieval, regardless of qmd's internal ranking, and MUST be cached per
  `(graph_version, query_hash)` so identical inputs yield identical outputs
  (NFR-D04, NFR-D05). The qmd version MUST be pinned in project dependencies.

### 3.4 Idempotence

Graph mutations MUST be idempotent: applying the same Phase Completion Document twice
yields the same final state as applying it once (NFR-D03). Rebuilding the graph from
scratch from its sources yields a graph identical to the incrementally maintained one.

### 3.5 Inspectability

- Every node, edge, confidence score, and loadout MUST be readable as plain text
  (NFR-I01).
- Every loadout MUST include its generation timestamp and a `graph_version` hash so
  staleness is detectable (NFR-I03, FR-L09).
- The provenance of every node (`source: human | agent | hybrid | generated`) MUST be
  recorded and visible (NFR-I04).
- The compiled graph MUST record a `node_origin` attribute per node
  (`global | local | code-mirror`) and an `edge_origin` per edge (`global | local`)
  (NFR-I06).
- `local_state.yaml` MUST be human-readable and git-diffable (NFR-I05).

### 3.6 Reliability and Graceful Degradation

- A malformed Phase Completion Document MUST NOT corrupt the graph — it is rejected
  with a clear error (NFR-R01). Malformed inputs are rejected, never silently ignored.
- A missing or unresolvable `content_ref` MUST produce a warning, not a crash (NFR-R02).
- If the global vault is missing or empty, the system MUST operate using only local
  sources — graceful cold start (NFR-R04).
- If qmd is not installed, loadout generation MUST operate in a documented degraded
  mode: the loadout contains the node table with file paths and confidence scores, but
  no inline content or extracted summaries, and the loadout header records
  `qmd_available: false`. All other components (graph build, update, query, mirror
  generation, status reporting) MUST work fully without qmd (NFR-R05).

### 3.7 The Human Review Gate

- All agent-written node drafts MUST be created with `status: tentative` and
  `source: agent` (FR-M04).
- The system MUST NOT auto-promote any node from `tentative` to `established` (FR-M05).
- Nodes with status `draft` or `deprecated` MUST NOT be loaded into any agent loadout
  (FR-G04).
- After each phase, a review report MUST be generated listing: new tentative nodes,
  dedup events, nodes with degraded confidence, new pitfalls, blocked downstream tasks,
  and id collisions between global and local nodes (FR-R01, FR-R02).
- A human MUST be able to promote a node with a single CLI command, and to mark a node
  `draft` to suppress it from loadouts without deleting it (FR-R03, FR-R04).

---

## 4. The Frozen v2 Schema

> The schemas in this section are **frozen**. Any change requires a schema version bump
> and a migration script (§8). Every file that participates in the schema MUST carry
> `akms_schema: v2`, and the graph compiler validates the version on every source it
> reads — a mismatch is a hard error (`SchemaVersionError`), not a warning.

This section is written so that a reader can author a valid node — and validate any
AKMS artifact — from this document alone.

### 4.1 Knowledge Node Frontmatter (Global and Local)

Every knowledge node is a `.md` file whose YAML frontmatter carries the machine-readable
contract. The content below the closing `---` is free-form Markdown, never parsed by
graph tooling (only searched by qmd).

Global nodes carry **intrinsic** properties only — content quality, structural
relationships, authorship. They MUST NOT carry experiential state: the fields
`activations`, `last_activated`, `activated_by_tasks`, `session_refs`, and
`auto_update` are invalid in global node frontmatter (they live in `local_state.yaml`;
`auto_update` appears only in generated code-mirror node frontmatter). A validator
rejects a global node containing them.

#### 4.1.1 Annotated Example

```yaml
---
# ── Identity ──────────────────────────────────────────────────────────
id: lippmann-schwinger                  # REQUIRED. Unique, stable, lower-case identifier
title: "Lippmann-Schwinger Equation & Green's Operator"  # REQUIRED. Human-readable
domain: fft-galerkin                    # REQUIRED. Top-level domain bucket
subdomain: spectral-operators           # OPTIONAL. Finer grain within domain
tags:                                   # REQUIRED. At least one. Used for seed matching.
  - green-operator
  - micromechanics
  - spectral

# ── Graph Status ──────────────────────────────────────────────────────
status: established     # REQUIRED. draft | tentative | established | deprecated
confidence: 0.90        # REQUIRED. Float [0.0, 1.0]. Intrinsic quality assessment;
                        #   serves as default/seed — overridden per-repo by the overlay.
source: human           # REQUIRED. human | agent | hybrid | generated
confidence_floor: 0.70  # OPTIONAL. Float [0.0, 1.0]. Per-node minimum confidence,
                        #   respected by all repositories during propagation.

# ── Structural Edges ─────────────────────────────────────────────────
edges:
  - to: fft-galerkin-basics             # REQUIRED. Target node id
    type: requires                      # REQUIRED. See edge-type table below
    weight: 1.0                         # REQUIRED. Float [0.0, 1.0]
    note: ""                            # OPTIONAL. Human-readable annotation

# ── Loadout Hints ─────────────────────────────────────────────────────
load_with:                              # OPTIONAL. Node ids almost always co-loaded
  - fft-galerkin-basics
context_size: medium                    # OPTIONAL. small | medium | large
reading_priority: full                  # OPTIONAL. full | summary | pitfalls-only
content_ref: null                       # OPTIONAL. Relative path if content lives elsewhere

# ── Schema Version ────────────────────────────────────────────────────
akms_schema: v2                         # REQUIRED. Must match current schema version
---

# Lippmann-Schwinger Equation & Green's Operator

Free-form Markdown content below here. Never parsed by graph tooling.
qmd searches this section for content-level retrieval.
```

#### 4.1.2 Field Reference

| Field | Type | Required | Allowed values / constraints | Semantics |
|---|---|---|---|---|
| `id` | string | ✓ | Unique across the compiled graph; stable across renames; lower-case identifier | Primary key. Nodes are `id`-keyed in the compiled graph. |
| `title` | string | ✓ | — | Human-readable title; matched (whole-word) during tag derivation. |
| `domain` | string | ✓ | Open vocabulary; `session` and `code-mirror` are system-reserved | Top-level conceptual bucket. Drives role-profile domain filters. |
| `subdomain` | string | | Open vocabulary | Finer grain within a domain. |
| `tags` | list[string] | ✓ (≥ 1) | Open vocabulary | Seed matching for subgraph queries and tag derivation. |
| `status` | enum | ✓ | `draft` \| `tentative` \| `established` \| `deprecated` | Lifecycle state; see status semantics below. |
| `confidence` | float | ✓ | [0.0, 1.0] | Intrinsic quality seed; overridden per-repo by the overlay. |
| `source` | enum | ✓ | `human` \| `agent` \| `hybrid` \| `generated` | Provenance. `generated` is reserved for code-mirror nodes. |
| `confidence_floor` | float | | [0.0, 1.0] | Per-node minimum; overrides the configured `min_confidence` in all repositories. Foundational nodes SHOULD set this to prevent confidence collapse. |
| `edges` | list | | See §4.1.3 | Outgoing structural edges. |
| `edges[].to` | string | ✓ per edge | Existing node id | Edge target. |
| `edges[].type` | enum | ✓ per edge | `requires` \| `feeds-into` \| `refines` \| `contradicts` \| `pitfall` \| `implements` | Edge semantics; see §4.1.3. |
| `edges[].weight` | float | ✓ per edge | [0.0, 1.0] | Propagation weight. |
| `edges[].note` | string | | — | Human-readable annotation. |
| `load_with` | list[string] | | Node ids | Co-activation pragmatics — a loading hint, distinct from semantic edges. |
| `context_size` | enum | | `small` \| `medium` \| `large` | Token-budget hint for full-mode loadouts (default allocations: 500 / 1500 / 3000 tokens). |
| `reading_priority` | enum | | `full` \| `summary` \| `pitfalls-only` | Per-node override of the loadout mode; see §5.4. |
| `content_ref` | path | | Relative path | Indirection to external content; see §4.1.5. |
| `akms_schema` | string | ✓ | `v2` | Schema version stamp. |

**Status semantics:**

| Status | Loadable? | Meaning |
|---|---|---|
| `draft` | No — never | Suppressed from all loadouts; a parking state (also used to hide a node without deleting it). |
| `tentative` | Yes (flagged) | Valid graph citizen, awaiting human review; all agent-drafted nodes start here. |
| `established` | Yes | Trusted, human-reviewed knowledge. |
| `deprecated` | No — never | Retired; retained for history and edge integrity. |

#### 4.1.3 Edge Types

Edges are directed (`from` the declaring node `to` the target), typed, and weighted.
The edge type controls both query traversal (which roles follow which edges, §5.3) and
confidence propagation (§5.5.2).

| Edge type | Meaning | Default propagation multiplier |
|---|---|---|
| `requires` | Target is a foundational prerequisite of this node | 1.0 (full propagation) |
| `refines` | This node refines/specializes the target | 0.7 |
| `feeds-into` | Looser dependency; this node's output informs the target | 0.5 |
| `contradicts` | The two nodes describe conflicting formulations (surfaced to reviewer roles) | 0.0 (no propagation — the contradiction is already explicit) |
| `pitfall` | Links a domain node to a **session node** recording a discovered pitfall | 0.0 (no propagation — pitfalls are explicit warnings) |
| `implements` | Links to code that implements the concept | 0.0 (no propagation — code mirrors reality, not the other way around) |

`pitfall` edges MUST target session nodes (`domain: session`); edges to raw file paths
are not permitted (FR-G11, FR-U05).

#### 4.1.4 Local Node Constraints

Local nodes in `<repo>/knowledge/local-nodes/` use the **same frontmatter schema** as
global nodes, with these additional constraints:

- `source` MUST be `agent` (if agent-written) or `human` (if developer-written for this
  repository specifically). `source: generated` is reserved for code-mirror nodes and
  is invalid in `local-nodes/`.
- `status` MUST be `tentative` when agent-written; a human may promote it to
  `established` locally.
- Agent-drafted nodes MUST include a `content_draft` section in the Markdown body,
  clearly marking the content as agent-authored.
- Local nodes MAY carry experiential fields during promotion (unlike global nodes,
  the validator does not reject them there).
- After compilation, local nodes participate in the graph identically to global nodes.
  The only differences are provenance and promotion path.

On an `id` collision between a global node and a local node, the global node takes
precedence: the local node is skipped and the collision is flagged in the review report
(FR-O03).

#### 4.1.5 `content_ref` Semantics

`content_ref` is an OPTIONAL relative path pointing to where a node's substantive
content lives when it is not inline in the node body. Its contract:

- When set, the node file acts as a **wrapper**: the frontmatter carries identity,
  status, and edges, while the referenced file carries the content. This is the
  standard low-effort path for turning an existing Markdown document into a node —
  add a wrapper with frontmatter, point `content_ref` at the document.
- The path is relative (to the vault or repository root of the node's own layer, per
  deployment layout). A missing or unresolvable `content_ref` MUST produce a warning,
  not a crash (NFR-R02).
- `content_ref` participates in **scope-based tag derivation**: when a task's `scope`
  file paths match a node's `content_ref` (or a mirror node's `source_file`), that
  node's tags are collected as derived tags for the task (§4.5).
- In generated code-mirror node frontmatter, `content_ref` points to the mirror `.md`
  file; in session-node registry entries, `content_ref` points to the session file.

#### 4.1.6 Authoring a Minimal Valid Node

The smallest valid node is an existing Markdown file with this frontmatter added:

```yaml
---
id: my-concept
title: "My Concept"
domain: my-domain
tags: [my-tag]
status: tentative
confidence: 0.7
source: human
akms_schema: v2
---
```

All other fields are optional. Edges, hints, and floors can be added incrementally —
incomplete nodes are valid graph citizens by design (UR-02, UR-07).

### 4.2 Local State Overlay (`local_state.yaml`)

Stored at `<repo>/knowledge/graph/local_state.yaml`. This is the repository's
experiential state — the source of truth for per-repo confidence, activation history,
repo-local edges, and the session-node registry. It is written exclusively by the
graph-update step, never by hand.

```yaml
akms_schema: v2
repo_id: example-repo                     # Informational — for display in reports

# ── Per-Node State Overrides ──────────────────────────────────────────
nodes:
  lippmann-schwinger:
    confidence: 0.85                      # Overrides the global default for this repo
    activations: 7
    last_activated: 2025-06-01
    activated_by_tasks:
      - phase1-task14
    session_refs:
      - sessions/phase1-task14.md

# ── Repo-Local Edges ──────────────────────────────────────────────────
local_edges:
  - from: lippmann-schwinger
    to: session-phase2-task3
    type: pitfall
    weight: 0.8
    note: "Near-zero frequency → division by zero. Add epsilon regularization."

# ── Session Node Registry ─────────────────────────────────────────────
session_nodes:
  session-phase2-task3:
    title: "Session: phase2-task3"
    tags: [fft-galerkin]
    outcome: success
    content_ref: sessions/phase2-task3.md
    phase: 2

# ── Reserved (v2 — not processed) ────────────────────────────────────
suppressed_edges: []                      # RESERVED. MUST be an empty list in v2.
```

#### Field Reference

| Section | Field | Type | Required | Notes |
|---|---|---|---|---|
| top level | `akms_schema` | string | ✓ | `v2` |
| top level | `repo_id` | string | | Informational, for display in reports |
| `nodes.<id>` | `confidence` | float [0,1] | | Overrides the global default for this repository |
| `nodes.<id>` | `activations` | int | | Repo-local activation count |
| `nodes.<id>` | `last_activated` | ISO date | | |
| `nodes.<id>` | `activated_by_tasks` | list[string] | | Task ids that used this node |
| `nodes.<id>` | `session_refs` | list[path] | | Capped at `max_session_refs` (default 10), most recent retained; pruned during graph update (FR-G13) |
| `local_edges[]` | `from` | string (node id) | ✓ | |
| `local_edges[]` | `to` | string (node id) | ✓ | For `pitfall` edges, MUST be a session node |
| `local_edges[]` | `type` | enum | ✓ | Same edge-type enum as §4.1.3 |
| `local_edges[]` | `weight` | float [0,1] | ✓ | |
| `local_edges[]` | `note` | string | | |
| `session_nodes.<id>` | `title` | string | ✓ | |
| `session_nodes.<id>` | `tags` | list[string] | | |
| `session_nodes.<id>` | `outcome` | enum | ✓ | Task/phase outcome |
| `session_nodes.<id>` | `content_ref` | path | ✓ | Path to the session file |
| `session_nodes.<id>` | `phase` | int | ✓ | |
| top level | `suppressed_edges` | list | | RESERVED for future per-repo suppression of global edges. MUST be `[]` in v2; v2 tooling MUST NOT process it (FR-O06), and a validator rejects a non-empty value. |

Overlay entries referring to nodes that no longer exist in any source are **orphaned
overlay entries**: they are logged as warnings during compilation and surfaced in
health reports, never silently dropped or fatal.

### 4.3 AgentMemory Schema (Per-Task)

Written by each task agent at completion — one file per task, at
`<repo>/knowledge/sessions/{task_id}.md`. AgentMemory is the leaf-level evidence
artifact. Its frontmatter MUST be valid parseable YAML (FR-M03).

```yaml
---
# ── Task Identity ─────────────────────────────────────────────────────
task_id: TASK-101                       # REQUIRED. Matches the task's id
task_description: "Fix strain-rate formula"
phase_id: 1                             # REQUIRED. Int
timestamp: 2026-03-04T10:32:00          # REQUIRED. ISO 8601
agent_model: <model-identifier>         # REQUIRED
loadout_used: loadouts/phase1-loadout.md  # REQUIRED. Relative path

# ── Outcome ───────────────────────────────────────────────────────────
status: complete    # REQUIRED. complete | partial | failed | deferred
commit: abc1234     # OPTIONAL. null if branch-only
tests_passed: 7     # REQUIRED. Int
tests_total: 7      # REQUIRED. Int
completion_notes: "…"

# ── Node Feedback ─────────────────────────────────────────────────────
nodes_used:
  - id: some-node-id                    # REQUIRED. Must resolve to a known node
    useful: true                        # REQUIRED. Bool
    coverage: sufficient                # REQUIRED. sufficient | missing-detail | outdated
    note: "…"

nodes_missing:
  - description: "Knowledge that would have helped but did not exist"
    suggested_id: suggested-node-id
    domain: some-domain
    tags: [tag-a, tag-b]
    priority: medium

# ── Lessons Learned ───────────────────────────────────────────────────
lessons:
  worked:
    - "Approach that worked"
  failed:
    - what: "Approach that failed"
      why: "Why it failed"
      fix: "What fixed it"

# ── Pitfalls Discovered ───────────────────────────────────────────────
pitfalls_discovered:
  - node_ref: some-node-id              # null = pitfall with no existing node
    description: "…"
    severity: medium                    # high | medium | low

# ── New Knowledge ─────────────────────────────────────────────────────
new_knowledge: []   # Empty if no new concepts discovered

# ── Schema Version ────────────────────────────────────────────────────
akms_schema: v2
---

## Task Notes

Free-form section: observations, dead ends, context not captured above.
```

#### Field Reference

| Field | Type | Required | Notes |
|---|---|---|---|
| `task_id` | string | ✓ | Matches the task record |
| `task_description` | string | ✓ | |
| `phase_id` | int | ✓ | |
| `timestamp` | ISO 8601 | ✓ | |
| `agent_model` | string | ✓ | |
| `loadout_used` | path | ✓ | |
| `status` | enum | ✓ | `complete` \| `partial` \| `failed` \| `deferred` |
| `commit` | string | | null if branch-only |
| `tests_passed` / `tests_total` | int | ✓ | |
| `completion_notes` | string | | |
| `nodes_used[].id` | string | ✓ | Must resolve to an existing node |
| `nodes_used[].useful` | bool | ✓ | Drives confidence boost |
| `nodes_used[].coverage` | enum | ✓ | `sufficient` \| `missing-detail` \| `outdated` — the latter two drive confidence decay |
| `nodes_used[].note` | string | | |
| `nodes_missing[].description` | string | ✓ | |
| `nodes_missing[].suggested_id` | string | ✓ | |
| `nodes_missing[].domain` | string | ✓ | |
| `nodes_missing[].priority` | enum | ✓ | |
| `lessons.worked` | list[string] | | |
| `lessons.failed[].what/why/fix` | string | ✓ if entry | |
| `pitfalls_discovered[].node_ref` | string \| null | ✓ | null = pitfall not tied to an existing node |
| `pitfalls_discovered[].description` | string | ✓ | |
| `pitfalls_discovered[].severity` | enum | ✓ | `high` \| `medium` \| `low` |
| `new_knowledge[].suggested_id` | string | ✓ | |
| `new_knowledge[].content_draft` | string | ✓ | |
| `new_knowledge[].status` | string | ✓ | Always `tentative` |
| `new_knowledge[].source` | string | ✓ | Always `agent` |
| `akms_schema` | string | ✓ | `v2` |

### 4.4 Phase Completion Document (PCD) Schema

Written by the phase-level agent at phase completion, at
`<repo>/knowledge/sessions/handoff_phase_{N}.md`. The PCD aggregates all per-task
AgentMemories and adds phase-level context that only the phase agent can see. Its
frontmatter MUST be valid parseable YAML.

The PCD has two zones:

- **Ephemeral zone** — for the orchestrator and the next phase's agent: per-task
  completion summary, architecture state (files created/modified/deleted, interfaces
  added), assumptions, known issues, and a forward briefing.
- **Persistent zone** — for graph updates: aggregated node feedback, lessons, pitfalls,
  and new knowledge. **The persistent-zone fields are identical to the corresponding
  AgentMemory fields** (FR-M08); the update step consumes either input type through the
  same validator.

The PCD serves three consumers:

1. The next phase's agent → ephemeral zone (codebase state, assumptions, warnings).
2. The graph-update step → persistent zone.
3. Code-mirror generation → the `files_modified` list.

#### Field Reference

**Phase identity (all REQUIRED):**

| Field | Type | Notes |
|---|---|---|
| `phase_id` | int | |
| `plan_file` | path | Path to the plan document |
| `branch` | string | Phase branch name |
| `date` | ISO date | |
| `loadout_used` | path | Loadout consumed by this phase |

**Ephemeral zone — completion:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `tasks[].task_id` | string | ✓ | |
| `tasks[].title` | string | ✓ | |
| `tasks[].commit` | string | | null if branch-only |
| `tasks[].tests_passed` / `tests_total` | int | ✓ | |
| `tasks[].status` | enum | ✓ | `complete` \| `partial` \| `failed` \| `deferred` |
| `tasks[].agent_model` | string | ✓ | |
| `tasks[].review_score` | int | | 0 = not reviewed yet |
| `tasks[].review_breakdown` | object | | `minor` / `medium` / `high` / `critical` counts |
| `overall_test_status` | object | ✓ | Aggregate pass/total/skipped/fixed counts |

**Ephemeral zone — architecture state:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `files_created[].path` / `.description` | string | ✓ | |
| `files_modified[].path` / `.changes` | string | ✓ | `files_modified` is also consumed by code-mirror generation (FR-M07) |
| `files_deleted[].path` / `.reason` | string | ✓ | |
| `interfaces_added[].name` / `.description` | string | ✓ | |
| `taichi_fields_added[].name` / `.spec` / `.purpose` | string | | Optional; for projects using the Taichi GPU framework |

**Ephemeral zone — risk and forward briefing:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `assumptions[].claim` / `.where` / `.rationale` / `.risk_if_wrong` | string | ✓ if entry | |
| `known_issues.failing_tests[]` | object | | `tests`, `reason`, `impact_on_next_phase` (`none` \| `low` \| `blocking`) |
| `known_issues.bugs` | list[string] | | |
| `known_issues.coverage_gaps` | list[string] | | |
| `next_phase_warnings` | list[string] | ✓ | MUST contain at least one entry, even if "No warnings" (FR-M06) |
| `recommended_start` | string | | Task id to begin the next phase |

**Persistent zone:** identical fields to AgentMemory's `nodes_used`, `nodes_missing`,
`lessons`, `pitfalls_discovered`, and `new_knowledge` (§4.3), but aggregated across all
of the phase's tasks. Plus `akms_schema: v2`.

### 4.5 Task Record AKMS Fields and Tag Derivation

AKMS adds three fields to each task's JSON record; all pre-existing task fields are
unchanged.

```json
{
    "task_id": "TASK-302",
    "scope": ["src/solvers/fft/green.py"],

    "akms_tags": ["fft-galerkin", "spectral"],
    "loadout_path": "knowledge/loadouts/phase3-TASK-302-loadout.md",
    "akms_schema": "v2"
}
```

| Field | Type | Required | Managed by |
|---|---|---|---|
| `akms_tags` | list[string] | ✓ (may be empty) | Task author; derived fallback fills it if empty |
| `loadout_path` | string | | Filled by the orchestrator after loadout generation, before the task agent is dispatched |
| `akms_schema` | string | ✓ | Set on creation |

**Tag derivation fallback** (when `akms_tags` is empty) — deterministic, no LLM:

1. **Scope-based:** each file path in `task.scope` is matched against every code-mirror
   node's `source_file` and every node's `content_ref`; the matched nodes' `tags` are
   collected. Code-mirror nodes carry no `tags` (§4.7) and therefore never contribute
   tags themselves — their `source_file` serves only as a scope-match anchor for
   locating associated concept nodes.
2. **Text-based:** the task's title, objective, and implementation steps are
   concatenated and matched against all node titles (whole-word, case-insensitive)
   and all node tags (substring, minimum length configurable, default 2 characters).
3. **Union + dedup** of both sets.
4. **Write-back + log:** derived tags are written back to the task's `akms_tags` field
   and logged with their derivation source for auditability; a human can inspect and
   correct them before execution (FR-T04).

### 4.6 Loadout File Schema

Loadouts are generated artifacts — never hand-edited. The structure is fixed and part
of the frozen contract:

```markdown
---
task_id: phase2-task3
phase: 2
generated_at: 2025-06-01T13:55:00
graph_version: a3f2c1d8
seed_tags: [fft-galerkin, green-operator]
agent_role: implementer          # implementer | code_reviewer | physics_reviewer
node_count: 4
loadout_mode: routing            # routing | full
available_context: 45000         # Estimated tokens available when mode was chosen
qmd_available: true              # false = degraded mode (no inline content/summaries)
akms_schema: v2
---

# Loadout: <task>

## Domain Knowledge
| Node | Origin | Confidence | Priority | Path | Read |
|---|---|---|---|---|---|
| …    | global/local | 0.85 | 1 | <node file path> | full/summary/pitfalls-only |

### Summaries        (routing mode)  — or full inline content (full mode)

## Known Pitfalls    (always included, regardless of mode)

## Relevant Session History

## Suggested Reading Order   (derived from `requires` edge topology)
```

Contract points:

- One loadout file per task (FR-L01).
- The header MUST record the generation timestamp, `graph_version` hash, loadout mode,
  agent role, and estimated available context (FR-L09, FR-L10d).
- **`routing` mode:** each node entry contains a 3–5-sentence summary (from the node's
  `## Summary` section), the file path, confidence, and reading priority — roughly 200
  tokens per node; the agent reads full content on demand via the path (FR-L10a).
- **`full` mode:** node content is embedded inline; each node is allocated tokens
  proportional to its `context_size` hint, and the total MUST NOT exceed
  `max_loadout_tokens`; lowest-ranked nodes are trimmed first (FR-L10b).
- Per-node `reading_priority` overrides the mode in both directions
  (`full` forces inline content even in routing mode; `summary` forces summary-only
  even in full mode; `pitfalls-only` includes only pitfall warnings) (FR-L10c).
  A node with `reading_priority: summary` but no `## Summary` section falls back to
  `full`. Authors MUST include a `## Summary` section in nodes with
  `context_size: large` (FR-L11).
- Pitfall warnings are always included regardless of mode.
- Loadouts SHOULD be cached and reused while the graph is unchanged (FR-L08); the
  `graph_version` hash makes staleness detectable.

### 4.7 Code-Mirror Node Schema

The code mirror is a **search index**, not a knowledge store: it exists so that
literal and semantic code search work over Markdown. Mirror node frontmatter is
generated — never written by hand:

```yaml
---
id: mirror-solvers-fft-green
title: "Code Mirror: src/solvers/fft/green.py"
domain: code-mirror              # Always code-mirror — excluded from loadout queries
status: established              # Always established
confidence: 1.0                  # Always 1.0 — marker only
source: generated                # Always generated
auto_update: true                # Skipped by all confidence propagation
content_ref: code-mirror/solvers/fft/green.md
source_file: src/solvers/fft/green.py
generated_at: 2025-06-01T14:32:00
generated_by_phase: 2
akms_schema: v2
---
```

**Invariants (all MUST):**

- No `tags` field — mirror nodes are never seed-matched and never contribute tags to
  tag derivation.
- No `edges` field — mirror nodes have no graph relationships.
- `confidence` is always `1.0` and is never mutated.
- `auto_update: true` nodes are skipped entirely by all confidence propagation —
  no hit, boost, or neighbor effect (FR-U10).
- `domain: code-mirror` excludes them from all domain loadout queries.
- Functions without docstrings produce mirror entries with code only — literal search
  works, semantic search does not.

The mirror file itself contains, per function/class in the source file, the docstring
rendered as plain Markdown followed by the full source in a fenced code block (FR-C02).

### 4.8 Configuration (`propagation_config.yaml`)

All tunable parameters live in one repo-local file. **Changing parameter values is
tuning, not a schema change** — it never requires a version bump. Defaults:

```yaml
akms_schema: v2
global_vault: ~/.claude/akms/nodes      # Overridable via AKMS_GLOBAL_VAULT env var

confidence:
  local_decay: 0.85            # Multiplicative decay on a negative signal
  propagation_factor: 0.30     # Neighbor-propagation strength
  activation_boost: 0.02       # Additive boost on confirmed-useful
  min_confidence: 0.10         # Global floor (overridden by per-node confidence_floor)
  max_confidence: 0.99
  hop_limit: 1                 # Propagation depth

edge_type_propagation:
  requires: 1.0
  refines: 0.7
  feeds-into: 0.5
  contradicts: 0.0
  pitfall: 0.0
  implements: 0.0

loadout:
  max_nodes_per_loadout: 8
  max_pitfall_nodes: 4
  min_confidence_threshold: 0.30
  max_loadout_tokens: 12000
  context_size_tokens: {small: 500, medium: 1500, large: 3000}
  routing_tokens_per_node: 200
  mode_selection:
    budget_fraction: 0.15      # Max share of available context for loadout content
    low_threshold: 8000        # Below this available budget → always routing mode
    safety_margin: 4000        # Reserved headroom tokens
    default_mode: routing

graph:
  stale_node_days: 90
  orphan_warning: true
  max_session_refs: 10
  dedup_threshold: 0.75

query_roles:
  implementer:
    edge_types: [requires, feeds-into, pitfall]
    rank_formula: "confidence * activations"
    prefer_domains: []
    exclude_domains: []
  code_reviewer:
    edge_types: [requires, feeds-into, pitfall]
    rank_formula: "confidence * activations"
    prefer_domains: []
    exclude_domains: []
  physics_reviewer:
    edge_types: [requires, contradicts]
    rank_formula: "confidence"
    prefer_domains: []            # e.g. list the domains this reviewer should favor
    exclude_domains: [code-mirror]

tag_derivation:
  min_tag_length: 2
  title_match: whole_word         # whole_word | substring
  log_derived_tags: true

orchestrator:
  plan_name: ""                   # Used for phase-branch naming
  base_branch: main               # Phase 1 branches from here
```

Role profiles MUST be configurable here without code changes (FR-Q06). An OPTIONAL
`model_routing` section MAY configure which provider/model serves the optional
semantic docstring-drift check; because it is an optional field that does not affect
node, overlay, or PCD schemas, its presence or absence is non-breaking.

### 4.9 Compiled Graph (`graph.json`)

NetworkX node-link format, pretty-printed with stable key ordering:

```json
{
  "directed": true,
  "multigraph": false,
  "graph": {
    "akms_schema": "v2",
    "generated_at": "2025-06-01T13:00:00",
    "node_count": 42,
    "edge_count": 87,
    "global_vault": "~/.claude/akms/nodes",
    "repo_id": "example-repo"
  },
  "nodes": [
    {
      "id": "lippmann-schwinger",
      "title": "Lippmann-Schwinger Equation & Green's Operator",
      "domain": "fft-galerkin",
      "tags": ["green-operator", "micromechanics", "spectral"],
      "status": "established",
      "confidence": 0.85,
      "confidence_default": 0.90,
      "source": "human",
      "node_origin": "global",
      "activations": 7,
      "last_activated": "2025-06-01",
      "akms_schema": "v2"
    }
  ],
  "links": [
    {
      "source": "lippmann-schwinger",
      "target": "fft-galerkin-basics",
      "type": "requires",
      "weight": 1.0,
      "edge_origin": "global"
    }
  ]
}
```

Guaranteed attributes: `node_origin` (`global` | `local` | `code-mirror`) on every node,
`edge_origin` (`global` | `local`) on every edge, and `confidence_default` (the global
seed value, exposed alongside any local override for inspectability). All node
frontmatter fields become node attributes.

---

## 5. Architecture and Algorithms

### 5.1 Component Overview

| Component | Responsibility |
|---|---|
| Graph compiler (`build_graph`) | Deterministic merge of all sources into `graph.json` |
| Subgraph query (`query_subgraph`) | Planning-time extraction of a ranked, role-filtered subgraph |
| Loadout generator (`generate_loadout`) | Assembles the loadout `.md` from the subgraph result and retrieved content — the single authoritative loadout writer |
| Graph updater (`update_graph`) | Applies AgentMemory/PCD persistent zones to the local overlay — the only write-back path |
| Mirror generator (`generate_mirror`) | Post-phase code-mirror generation plus docstring-drift check |
| Health reporter (`graph_status`) | On-demand and per-phase graph health reporting |
| Loadout re-evaluator (`re_evaluate`) | Regenerates loadouts after the graph changes |
| qmd cache | Caches search output per `(graph_version, query_hash)` |
| Orchestrator | Stage pipeline, checkpoints, tag derivation, wave dispatch (§5.8) |

The compiled graph is the interface boundary: query, loadout, and update logic operate
on `graph.json` and are unaware of the global/local split. Only the compiler and updater
know about the two layers.

### 5.2 Graph Compilation — The Deterministic Five-Step Merge

The compiler rebuilds `graph.json` from scratch, in this exact order (NFR-D06):

```
1. LOAD GLOBAL NODES
   Parse all *.md in the global vault (default ~/.claude/akms/nodes/,
   or $AKMS_GLOBAL_VAULT). Validate schema version on each.
   Add to graph with node_origin: "global".

2. LOAD LOCAL NODES
   Parse all *.md in <repo>/knowledge/local-nodes/, sorted by id.
   Validate schema version on each.
   On id collision with a global node → SKIP the local node, log a
   collision warning (global wins).
   Else add with node_origin: "local".

3. LOAD CODE-MIRROR NODES
   Parse all *.md in <repo>/knowledge/code-mirror/ (a distinct step,
   never grouped with the overlay).
   Add with node_origin: "code-mirror", source: generated, auto_update: true.

4. APPLY LOCAL OVERLAY (local_state.yaml)
   For each entry in nodes: override confidence, activations,
     last_activated, activated_by_tasks, session_refs
     (orphaned entries → warning, not error).
   For each entry in local_edges: append the edge (global edges are
     never removed or modified — the merge is append-only, FR-O05).
   For each entry in session_nodes: materialize a session node
     (domain: session, auto_update: true).

5. SERIALIZE
   Write graph.json with sort_keys=True, indent=2.
```

If any source carries a schema version other than the current one, compilation halts
with `SchemaVersionError` (FR-G08). Global node `confidence` is stored as
`confidence_default`; the overlay value, when present, becomes the effective
`confidence`. Building twice from the same sources produces byte-identical output.

### 5.3 Subgraph Query and Role Profiles

Given a task description, seed tags, and an agent role, the query step extracts a
ranked subgraph:

1. Load the query profile for the `agent_role` from configuration.
2. Find seed nodes matching any of the task's tags.
3. Compute the ego graph of radius `max_depth` around each seed; union them.
4. Filter to loadable statuses (`tentative`, `established`).
5. Keep all seeds; traverse only along the profile's `edge_types`
   (strict seed-anchored filtering).
6. Boost nodes in `prefer_domains` (rank × 1.5); remove nodes in `exclude_domains`.
7. Exclude nodes below `confidence_floor` / `min_confidence_threshold`.
8. Rank by the profile's `rank_formula`; cap at `max_nodes_per_loadout`.
9. **Pitfall injection:** pitfall-connected nodes are always included regardless of
   rank, up to `max_pitfall_nodes`.

At least three roles MUST be defined (FR-Q02):

| Role | Edge types | Rank formula | Notes |
|---|---|---|---|
| `implementer` (default) | `requires`, `feeds-into`, `pitfall` | `confidence × activations` | |
| `code_reviewer` | `requires`, `feeds-into`, `pitfall` | `confidence × activations` | Same graph query as implementer; operationally also receives diffs and searches the code mirror directly to trace code back to concepts (a search operation, not a graph operation) |
| `physics_reviewer` | `requires`, `contradicts` | `confidence` | The only role that follows `contradicts` edges (FR-Q04) — enabling detection of formulation inconsistencies; excludes `code-mirror` |

### 5.4 Loadout Generation — The Projection Contract

The orchestrator selects a loadout mode per task based on available context:

```
available = model_context_limit − system_prompt_tokens − task_tokens − safety_margin
if available < low_threshold:                          mode = routing
elif full_cost > available × budget_fraction:          mode = routing
else:                                                  mode = full
```

Nodes with `reading_priority: full` receive full content regardless of mode, letting a
human force-include critical material even under a routing-mode budget.

Content retrieval within the selected node set uses qmd — always with a **pre-scoped
file set**: the graph decides which nodes are structurally relevant; search happens
only within them. There is no open-ended corpus search in the loadout path. Retrieved
passages are sorted by `(file_path, line_number)` and cached per
`(graph_version, query_hash)`, guaranteeing identical loadouts for identical inputs.

If qmd is unavailable, the degraded-mode contract of §3.6 applies, and the loadout still
delivers the node table, paths, confidence scores, pitfall warnings, and reading order.

### 5.5 Graph Update — The Evidence Contract

The update step is the **only** path through which experience enters the graph. It
consumes AgentMemory files and/or PCD persistent zones (identical field contract),
mutates `local_state.yaml` deterministically, creates tentative node files in
`local-nodes/`, then recompiles `graph.json`. It never touches global node files.

#### 5.5.1 Mutation Rules

| Evidence | Effect |
|---|---|
| `nodes_used[i].useful == true` | Confidence boost by `activation_boost`; activation count incremented; `last_activated` updated |
| `nodes_used[i].coverage == missing-detail` or `outdated` | Confidence decay by `local_decay`; node flagged in the review report |
| `pitfalls_discovered[i]` | A `pitfall` edge added to `local_edges`, from the domain node to the **session node** representing the memory/PCD file |
| `new_knowledge[i]` | Dedup check (§5.5.3), then a new tentative node file in `local-nodes/`, or content appended to an existing tentative node |
| Any node with `auto_update: true` | Skipped entirely — no confidence change of any kind |

For each processed document, a session node is registered in
`local_state.yaml.session_nodes` (one per phase for PCDs, one per task for
AgentMemories), making the session file a valid `pitfall` edge target.

After all mutations: updated confidence/activations/`session_refs` and new edges are
persisted to `local_state.yaml` (with `session_refs` pruned to `max_session_refs`),
and the graph is recompiled.

#### 5.5.2 Confidence Propagation Mathematics

All confidence arithmetic operates on the compiled graph and writes results to the
local overlay only.

**Direct hit** (negative signal):

$$c_i \leftarrow \max\left(c_i \cdot \alpha,\ c_{\min,i}\right)$$

where α = `local_decay` (default 0.85) and c_min,i is the node's `confidence_floor`
if set, otherwise the configured `min_confidence`.

**Neighbor propagation** — each direct hit propagates to predecessor nodes (nodes with
edges pointing *to* the hit node), up to `hop_limit` hops:

$$c_j \leftarrow \max\left(c_j - \delta_i \cdot \lambda \cdot \mu_e \cdot w_{ji},\ c_{\min,j}\right)$$

where δᵢ is the magnitude of the hit (confidence before − after), λ = `propagation_factor`
(default 0.30), μₑ is the edge-type multiplier (§4.1.3), and w is the edge weight.
Multiple hits in the same update cycle compound multiplicatively.

**Recovery** (positive signal):

$$c_i \leftarrow \min\left(c_i + \beta,\ c_{\max}\right)$$

where β = `activation_boost` (default 0.02). Recovery is **asymmetric by design**: one
hit at default parameters (−15%) takes roughly eight successful activations to recover
from. Fast decay on failure, slow recovery on success.

Confidence is always clamped to `[confidence_floor or min_confidence, max_confidence]`
(FR-U07); a foundational node never falls below its declared floor regardless of hit
severity.

#### 5.5.3 Deduplication Algorithm

Before creating a new tentative node, the updater checks for near-duplicates —
deterministically, with no LLM (FR-U09):

```
Given: new_knowledge entry K with domain D
1. Fetch all existing tentative nodes N with N.domain == D
   (from both local-nodes/ and the global vault)
2. score(N) = lexical_similarity(K.title + K.content_draft,
                                 N.title + N.content_draft)
   — deterministic token-Jaccard; exact id match scores 1.0
3. If max(score) > dedup_threshold (default 0.75):
     if best match is local  → append K.content_draft to it (with separator)
     if best match is global → create a new local node
                               (global files cannot be modified)
     log the dedup event; flag it in the review report
4. Else → create a new tentative node file in local-nodes/
```

### 5.6 Code Mirror Generation and Docstring Drift

After each phase, the mirror generator processes only the source files modified in that
phase (determined by the version-control diff against the phase's parent branch,
NFR-B02) and writes one mirror `.md` per source file:

1. Parse the source with the AST module.
2. For each function/class: extract the docstring (rendered as Markdown — the semantic
   search layer) and the full source (fenced code block — the literal search layer).
3. Write the mirror file and its marker frontmatter (§4.7).

**Docstring drift check:** each mirror entry's docstring is checked against the
function's actual AST signature (parameter names, return annotation). The default
check is structural and deterministic. A deeper semantic check MAY be enabled, in
which case it uses a single model call per function; this optional path is the one
exception noted in §3.2 and never runs in the deterministic mirror-refresh path. On a
detected mismatch, the mirror node is set to `status: draft` and the drift is flagged
in the review report (FR-C03). This catches the dangerous case — a docstring that
actively contradicts the code — not incomplete docstrings. Functions without
docstrings pass (they are simply literal-search-only).

### 5.7 Health Reporting

The health reporter runs on demand or as part of the review cycle and reports:

- Nodes with degraded confidence (showing both the global default and local override)
- Nodes flagged `missing-detail` or `outdated`
- Tentative nodes awaiting promotion, with their location (global vs `local-nodes/`)
- Dedup events from the current phase
- Docstring drift warnings
- Id collisions between global and local nodes
- Orphaned nodes (no edges) and stale nodes (`last_activated` older than
  `stale_node_days`)
- Blocked downstream tasks awaiting tentative-node promotion
- Orphaned overlay entries (overlay state for nodes no longer in any source)

### 5.8 Orchestration Reference Workflow

AKMS ships a reference orchestration pipeline — a plain Python state machine with
human gates — that exercises the full feedback loop. The graph, schema, and loadout
contracts above stand on their own; the pipeline is how they compose in practice.

```
INIT → PLAN → TASK BREAKDOWN → SCAFFOLD → EXECUTE (per phase) → REVIEW (per phase) → FINALIZE
         [gate]      [gate]        [gate]      [gate]              [gate]              [gate]
```

Contract points (FR-S, NFR-B, NFR-C):

- Every stage transition except Init is gated by a human checkpoint presenting the
  stage output, AKMS status (node changes, pitfalls), an action menu, and warnings.
  Checkpoint actions: approve, reject with reason, edit artifacts, or abort with full
  state preservation for resumption.
- **Pre-phase:** the orchestrator derives tags per task (hybrid: explicit `akms_tags`
  or the derivation fallback), queries the subgraph per role, generates loadouts, and
  fills each task's `loadout_path` before dispatch.
- **Execution:** tasks run in dependency-ordered waves. Tasks within a wave MUST have
  non-overlapping `scope` file sets (validated before dispatch); two tasks touching the
  same file MUST be in different waves with an explicit dependency. Each task agent
  writes its AgentMemory to a unique path, so concurrent writes are safe. Pitfalls
  discovered by multiple agents for the same node are recorded as separate additive
  edges — never merged.
- **Serialization point:** the graph updater is NEVER called during task execution.
  All graph mutations are serialized through the phase agent: task agents →
  AgentMemories → phase agent → PCD → update (serial).
- **Post-phase:** update the graph from the PCD persistent zone, regenerate the code
  mirror from `files_modified`, produce the health report, present the review
  checkpoint. The full PCD (including the forward briefing) is passed to the next
  phase's agent alongside its loadout.
- **Review:** code-reviewer and physics-reviewer agents run with role-specific
  loadouts; their AgentMemories feed back into the graph (e.g., a reviewer flagging a
  node `outdated` causes a confidence hit).
- **Branching:** each phase runs on its own branch, named
  `<plan_name>_phase-<N>`, branching from its predecessor (phase 1 from the configured
  `base_branch`); merging at finalization proceeds in reverse phase order. `plan_name`
  and `base_branch` are configured in `propagation_config.yaml`.

---

## 6. Contracts for External Consumers

An external consumer — a tool, agent framework, or human — can rely on the following.

### 6.1 Projection Contract (Reading From AKMS)

- **`graph.json` is a derived artifact** in NetworkX node-link format (§4.9): always
  rebuildable from its sources, byte-stable for identical inputs, human-diffable, and
  carrying provenance (`node_origin`, `edge_origin`, `source`, `confidence_default`)
  on every element. Consumers MAY read it directly; they MUST NOT treat it as a source
  of truth to write to.
- **Loadouts are the delivery format** for task context (§4.6): fixed structure,
  versioned via `graph_version`, self-describing header (mode, role, qmd availability,
  context estimate). A consumer holding a loadout can detect staleness by comparing
  its `graph_version` against a hash of the current `graph.json`.
- **Node files are plain Markdown + YAML** and can be authored, read, and reviewed with
  any text tooling. The frontmatter contract of §4.1 is sufficient to author a valid
  node.

### 6.2 Evidence Contract (Writing Into AKMS)

- The **only** write-back channels are AgentMemory (§4.3) and the PCD persistent zone
  (§4.4). Their persistent-zone fields are identical, and the updater accepts both.
- All evidence is schema-validated before any mutation; malformed evidence is rejected
  with a clear error and the graph is left untouched.
- Write-back effects are confined to `local_state.yaml` and `local-nodes/` — never the
  global vault, never files outside `<repo>/knowledge/`.
- Every mutation is deterministic and idempotent, so evidence can be safely replayed.

### 6.3 Multi-Repository Guarantee

Multiple repositories sharing one global vault are fully isolated from each other:

- Repository A boosting a node's confidence and repository B decaying the same node's
  confidence both leave the global node file byte-identical.
- A pitfall recorded in one repository never appears in another repository's graph or
  loadouts.
- The same task tags can produce different loadouts in different repositories,
  reflecting each repository's experiential state — with zero manual synchronization.

---

## 7. Performance Targets

| ID | Target | Priority |
|---|---|---|
| NFR-P01 | Subgraph query for a single task completes in under 2 seconds | MUST |
| NFR-P02 | Full graph rebuild (merge + compile) completes in under 10 seconds for up to 500 nodes | SHOULD |
| NFR-P03 | Loadout generation for a full phase (up to 10 tasks) completes in under 30 seconds | SHOULD |

---

## 8. Schema Versioning and Compatibility Policy

- **Current version:** `akms/v2`.
- Every file participating in the schema MUST include `akms_schema: v2`.
- The graph compiler validates the schema version on every node and overlay it reads;
  a mismatch is a hard error (`SchemaVersionError`) and compilation halts.
- The node frontmatter, local overlay, AgentMemory, PCD, task-record, loadout, and
  code-mirror schemas are **frozen at v2**.

### 8.1 What Constitutes a Breaking Change (Requires v3)

Any of the following requires a version bump to `akms/v3`, a migration script
(`knowledge/graph/migrations/v2_to_v3.py`), and an update to this specification:

- Adding a REQUIRED field to any schema (node, overlay, AgentMemory, PCD).
- Removing or renaming any existing field.
- Changing the type or valid values of any field.
- Changing the loadout file structure.
- Adding a new node domain type that affects query-filtering logic.
- Changing the `local_state.yaml` structure.
- Activating `suppressed_edges` processing (currently reserved).

### 8.2 What Does NOT Constitute a Breaking Change

- Adding a new OPTIONAL field to node frontmatter.
- Adding new values to `tags` (open vocabulary).
- Changing `propagation_config.yaml` parameter values (tuning, not schema).
- Adding new optional fields to `local_state.yaml` node overrides.

### 8.3 Migration Expectations

A schema version bump ships with a migration script that transforms all participating
artifacts in place and re-stamps their `akms_schema` field, after which a full graph
rebuild validates the migrated state. (The v1 → v2 migration, which introduced the
overlay architecture by extracting experiential fields from node frontmatter into
`local_state.yaml`, followed exactly this pattern.)

### 8.4 Reserved Extension Points

The following are declared in v2 but deliberately inert; relying on them is
unsupported until a future version activates them:

- `suppressed_edges` in `local_state.yaml` — reserved for per-repository suppression
  of global structural edges. MUST remain an empty list; v2 tooling MUST NOT process it.

---

*AKMS v2 — Public Specification · Consolidated from the frozen v2 design documents.*
