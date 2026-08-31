---
name: akms-spec-check
description: Verify AKMS implementation against frozen v2 design specifications. Use when implementing or modifying AKMS components to catch spec violations.
---

> **Provenance.** Published copy of the internal asset at `.claude/skills/akms-spec-check/SKILL.md`. It is a copy
> rather than a move: consumers of this repository (Logic-Loom vendors it via git
> subtree) reference the internal path, so relocating it would change that
> integration surface. Treat the internal copy as the source of truth and update
> both when behaviour changes.

# AKMS Spec Compliance Checker

You are auditing the AKMS implementation against its frozen v2.0 design specification.

## Procedure

### 1. Load the relevant spec sections

Read the specification to understand the contracts:
- `docs/specification/AKMS_v2_specification.md` — requirement IDs (FR-*, NFR-*) and the frozen v2 schemas

### 2. Load the current implementation

Read the implementation files being checked:
- `Packages/AKMS/src/akms/schema/models.py` — Pydantic models
- `Packages/AKMS/src/akms/schema/validators.py` — parsers
- `Packages/AKMS/src/akms/graph/build_graph.py` — merge compiler
- Any other `src/akms/` files relevant to the check

### 3. Cross-reference against requirements

For each implemented component, verify these categories:

#### Schema Compliance (spec §1–§8)
- [ ] All enums match spec values exactly (NodeStatus, EdgeType, Coverage, etc.)
- [ ] All REQUIRED fields from spec are present in Pydantic models
- [ ] Field types match spec (float [0,1], string, list, enum)
- [ ] `akms_schema: v2` is required in every schema model
- [ ] `LOADABLE_STATUSES = {tentative, established}` (FR-G04)
- [ ] `EXPERIENTIAL_FIELDS` excluded from global nodes (FR-O01)
- [ ] `suppressed_edges` validated as empty list in v2 (FR-O06)
- [ ] PCD has `extract_persistent_zone()` and `extract_ephemeral_zone()` (spec §3a)
- [ ] `next_phase_warnings` has `min_length=1` (FR-M06)

#### Build Graph Compliance (spec §2.3)
- [ ] 5-step merge order: global → local → code-mirror → overlay → serialize (NFR-D06)
- [ ] Id collision: global wins, local skipped and logged (FR-O03)
- [ ] `node_origin` attribute set per node: global/local/code-mirror (NFR-I06)
- [ ] `edge_origin` attribute set per edge: global/local
- [ ] `confidence_default` preserved alongside overlay confidence
- [ ] `SchemaVersionError` raised on version mismatch (FR-G08)
- [ ] `graph.json` uses `sort_keys=True, indent=2` (NFR-I02)
- [ ] Global vault path resolves: env var > config > default (FR-O01)

#### Update Graph Compliance (spec §2.7)
- [ ] Writes ONLY to `local_state.yaml` and `local-nodes/` (FR-U08)
- [ ] Global node files never modified
- [ ] `auto_update: true` nodes skipped entirely (FR-U10)
- [ ] Confidence clamped to `[confidence_floor, max_confidence]` (FR-U07)
- [ ] Pitfall edges target session nodes, not raw file paths (FR-U05)
- [ ] Dedup check before creating tentative nodes (FR-U09)
- [ ] Session refs capped at `max_session_refs` (FR-G13)
- [ ] Mutations idempotent on same input (NFR-D03)

#### Query & Loadout Compliance (spec §2.4, §2.6)
- [ ] Role profiles loaded from `propagation_config.yaml` (FR-Q01)
- [ ] Three roles defined: implementer, code_reviewer, physics_reviewer (FR-Q02)
- [ ] physics_reviewer includes `contradicts` edges (FR-Q04)
- [ ] Loadout includes `graph_version` hash (FR-L09)
- [ ] Two modes: routing and full (FR-L10)
- [ ] `reading_priority` overrides mode (FR-L10c)
- [ ] Degraded mode when qmd unavailable (NFR-R05)
- [ ] Tag derivation uses NO LLM calls (FR-T05)

#### Safety & Reliability
- [ ] Malformed PCD rejected, not silently accepted (NFR-R01)
- [ ] Missing `content_ref` produces warning, not crash (NFR-R02)
- [ ] Graceful cold-start with empty global vault (NFR-R04)
- [ ] No file modified outside `<repo>/knowledge/` without developer action (NFR-R03)

### 4. Report findings

For each violation found, report:

```
VIOLATION: [requirement ID] — [one-line description]
  File: [path:line]
  Expected: [what the spec requires]
  Actual: [what the code does]
  Severity: CRITICAL / MAJOR / MINOR
  Fix: [specific fix suggestion]
```

Group by severity. CRITICAL = breaks a MUST requirement. MAJOR = breaks a SHOULD. MINOR = inconsistency or missing feature.

If no violations found, confirm: "All checked requirements pass."

## What to audit against

Audit against **`docs/reference/akms/conformance-invariants.md`** — the normative, checkable subset
of the frozen v2 specification. It carries the frozen vocabulary, the frozen
constants, and the graph/write/determinism/fail-closed contracts, each with a
stable ID.

Cite the ID in every finding:

> `INV-GRAPH-02` violated: `build_graph` lets a local node overwrite a global one
> on id collision; the spec requires global wins and the local node is skipped
> and logged.

A finding without an ID is not actionable, and an audit that cites no IDs has
probably not checked anything specific.

That page is kept in step with the code by
`Packages/AKMS/tests/akms/test_invariants_doc.py`, which compares its vocabulary
and constant tables against `akms.schema.models` and fails on drift — so the
values you audit against are the values the code actually enforces.

### When you need more than the invariants page

The full specification (`docs/specification/AKMS_v2_specification.md`) remains the authority and carries
the *why*. It ships with this repository; the internal design documents it was
consolidated from are not published.

If a check needs detail the invariants page does not carry and the design
documents are absent, **say so and scope the finding accordingly**. Do not report
a clean result for a contract you could not read: an audit that verified nothing
must not look like an audit that found nothing wrong.
