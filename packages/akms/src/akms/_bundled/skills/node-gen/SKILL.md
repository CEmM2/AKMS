---
name: node-gen
description: "Extracts AKMS domain knowledge nodes from NotebookLM notebooks. Queries notebook sources for equations, algorithms, and pitfalls, then outputs structured YAML and converts to validated AKMS markdown. Use when generating new domain nodes from academic papers. Triggers on: 'generate nodes', 'extract knowledge graph', 'notebook to yaml', 'akms node generation', 'convert notebook to akms', 'generate akms nodes from papers', 'requery node', 'validate nodes', or any request to systematically extract structured domain knowledge from NotebookLM sources for AKMS node creation."
---

> **Provenance.** This is a published copy of the internal skill at
> `.claude/skills/node-gen/`. It is a copy rather than a move because
> Logic-Loom consumes the internal path, and relocating it would change that
> integration surface. The two are therefore expected to drift: if you change
> node-generation behaviour, update both, and treat the internal copy as the
> source of truth. Only the internal-path references differ today.


## Goal

Generate self-contained AKMS domain knowledge nodes by querying NotebookLM notebooks, outputting structured YAML, and converting to validated markdown.

**Success criterion:** a first-year PhD student can implement the node from its YAML content alone, without reading any papers.

## Required tools

This skill uses the `nlm` CLI from `notebooklm-mcp-cli` (installed via `uv tool install notebooklm-mcp-cli`).

Before starting, verify the CLI is authenticated:
```bash
nlm notebook list
```
If not authenticated, the user must run `nlm login` first.

All NLM interactions go through bash via `nlm` commands — no MCP server needed. This avoids the 35-tool context overhead of the MCP server.

**Key CLI commands used by this skill:**

| Operation | Command |
|-----------|---------|
| Query notebook AI | `nlm notebook query <NLM_ID> "question" --timeout 180` |
| Get notebook details | `nlm notebook get <NLM_ID>` |
| Get notebook summary | `nlm notebook describe <NLM_ID>` |
| Get raw source text | `nlm source content <SOURCE_ID>` |
| Get source AI summary | `nlm source describe <SOURCE_ID>` |

Use `--timeout 180` (or higher) on query commands — extraction prompts are long and the default 120s may not be enough.

File tools (Read, Write, Glob, Grep, Bash) are also required.

## Inputs

| Input | Description | Default |
|-------|-------------|---------|
| `NLM_ID` | Notebook UUID | *(required)* |
| `NODE_SELECTION` | Node id, cluster letter (A–H), or `"all"` | *(required)* |
| `PLAN_PATH` | Path to extraction plan JSON | *(required)* |
| `OUT_DIR` | Output directory for YAML + markdown | `Sources_Evals/NLM/Outputs/{plan_name}/` |
| `SCHEMA_PATH` | Path to YAML schema reference | `skills/node-gen/references/akms_node_template.md` |
| `PARALLEL` | Enable wave-based parallel dispatch | `false` |

## Bundled resources

| Resource | Path | When to read |
|----------|------|--------------|
| **Schema compliance** | `references/schema_compliance.md` | **Always read first** — frozen v2 rules from design docs 03+04 |
| YAML schema | `references/akms_node_template.md` | Before generating any YAML (always) |
| Query strategies | `references/query_strategies.md` | Before querying NLM (always) |
| YAML safety rules | `references/yaml_safety.md` | When assembling YAML or fixing parse errors |

**Read `references/schema_compliance.md`, then `references/akms_node_template.md` and `references/query_strategies.md` before doing any work.** Schema compliance is non-negotiable — nodes that violate the frozen v2 schema will be rejected by `build_graph.py`.

## Scripts

| Script | Path | Purpose |
|--------|------|---------|
| Converter | `scripts/akms_node_convert.py` | YAML → AKMS markdown |
| Validator | `scripts/akms_node_clean.py` | Clean, auto-fix, and validate markdown |

---

## Commands

### `extract` — Full pipeline (default)

The primary entry point. Queries NLM, assembles YAML, converts, and validates.

**Steps:**

1. **Load plan.** Read `PLAN_PATH`. Parse clusters and filter to `NODE_SELECTION`:
   - Single id → one node
   - Cluster letter → all nodes in that cluster
   - `"all"` → every node. If `PARALLEL` is false, process sequentially (A → B → ... → H). If `PARALLEL` is true, use wave-based dispatch (see Batching Rules below).

2. **Read schema + compliance.** Load `references/schema_compliance.md` first (frozen v2 rules), then `references/akms_node_template.md` (YAML structure). The compliance doc is authoritative — if the template and compliance doc disagree, compliance wins.

3. **Check for existing outputs.** For each node, check if `{OUT_DIR}/{id}.yaml` already exists. If it does and its corresponding `.md` passes validation, skip it and log `SKIP: {id} — already valid`. To force regeneration, the user must delete the existing file.

4. **Query NLM.** For each node, determine the query strategy from `references/query_strategies.md` based on the node's characteristics. Run queries in sequence. See the Query Strategy section below for the adaptive approach.

5. **Assemble YAML.** Synthesize query results into a YAML document matching the schema. Write to `{OUT_DIR}/{id}.yaml`.

6. **Convert.** Run: `uv run python scripts/akms_node_convert.py {OUT_DIR}/{id}.yaml -v`

7. **Validate.** Run: `uv run python scripts/akms_node_clean.py {OUT_DIR}/{id}.md --validate-only -v`

8. **Fix loop.** If the validator reports errors, enter the requery loop (max 2 cycles per node):
   - **Equation-number reference** → requery NLM for the specific equation by name
   - **Vague algorithm step** → requery: "Write the step-by-step algorithm for [title] with actual formulas, not descriptions"
   - **YAML parse error** → fix in the `.yaml` file directly (read `references/yaml_safety.md`)
   - **Missing section** → requery for the missing content
   - After fixes, re-convert and re-validate
   - If still failing after 2 cycles, log `MANUAL: {id}` and move on

9. **Report.** After all nodes: print a summary table with status (OK / MANUAL / SKIP) per node.

---

### `convert` — YAML to markdown only

Use when YAML files already exist (e.g., after manual edits) and you only need to regenerate markdown.

**Steps:**

1. Glob `{OUT_DIR}/*.yaml` (or a specific file if given).
2. For each: `uv run python scripts/akms_node_convert.py {file} -v`
3. Report results.

---

### `validate` — Check existing markdown

Use to audit node quality without regenerating anything.

**Steps:**

1. Glob `{OUT_DIR}/*.md` (or a specific file if given).
2. For each: `uv run python scripts/akms_node_clean.py {file} --validate-only -v`
3. Report summary: errors vs. warnings per file.

---

### `requery` — Fix insufficient fields

Use when a node has `[INSUFFICIENT SOURCE]` markers or specific fields need richer content.

**Inputs:** A node id + the field(s) to fix (e.g., `requery fft-green-operator math_formulation algorithms`).

**Steps:**

1. Read the existing `{OUT_DIR}/{id}.yaml`.
2. Identify fields marked `[INSUFFICIENT SOURCE]` or specified by the user.
3. Run targeted NLM queries for those specific fields (see Query Strategies).
4. Update the YAML in-place — only the targeted fields, leave everything else untouched.
5. Re-convert and re-validate.

---

### `review` — Cross-node quality audit (Opus-tier, separate session)

Run after `extract` completes all clusters. This is a post-extraction pass that catches issues no single-node validator can see — notation drift across clusters, edge incoherence, redundant definitions, and holistic implementability gaps.

**Intended model tier:** Opus. The review requires holding the full node set in context and making judgment calls about cross-node consistency. Run this in a separate session from extraction.

**Inputs:**

| Input | Description | Default |
|-------|-------------|---------|
| `OUT_DIR` | Directory containing generated `.yaml` files | *(required)* |
| `PLAN_PATH` | Path to extraction plan JSON | *(required)* |
| `REPORT_PATH` | Where to write the review report | `{OUT_DIR}/review_report.md` |

**Steps:**

1. **Load all nodes.** Read every `.yaml` file in `OUT_DIR`. Load the extraction plan for cluster/dependency context.

2. **Notation consistency.** Scan all `math_formulation.notation` maps across the full node set. Flag:
   - Same physical quantity with different LaTeX (e.g., `\hat{\varepsilon}` vs `\hat{\boldsymbol{\varepsilon}}` for the strain field)
   - Same LaTeX symbol defined differently across nodes

3. **Edge coherence.** For every `edges[].to` target that points to another node in the plan:
   - Verify the target node exists in `OUT_DIR`
   - Check bidirectional sense: if A `requires` B, does B `feeds-into` A? (Not mandatory, but flag missing reciprocals as warnings)
   - Flag dangling edges (target doesn't exist in plan or inventory)
   - Flag orphan nodes (no incoming or outgoing edges)

4. **Redundancy detection.** Compare `math_formulation.equations` across all nodes:
   - Flag equations that appear in multiple nodes with identical or near-identical LaTeX
   - Suggest which node should own the equation and which should reference via `requires` edge instead

5. **Implementability audit.** For each node, apply the PhD-student test holistically:
   - Can a reader implement this node using ONLY its content plus the content of its `requires` edges (which are also in the set)?
   - Flag nodes where the algorithm references concepts defined in a different node but lacks the `requires` edge
   - Flag algorithms where step N uses a symbol defined only in another node's notation map

6. **Schema compliance spot-check.** Re-verify all nodes against `references/schema_compliance.md`:
   - Correct `status: tentative`, `source: hybrid`, `akms_schema: v2`
   - Domain values match taxonomy (FFT nodes should be `fft-galerkin`, not `computational-mechanics`)
   - Tags from canonical vocabulary
   - No experiential fields

7. **Write report.** Write to `REPORT_PATH` using the exact structure below.

8. **Apply fixes (optional).** If the user approves, apply the suggested YAML patches from the report:
   - Update notation maps to use canonical forms
   - Add missing `requires` edges
   - Fix schema violations
   - Re-convert and re-validate all modified nodes

**Report structure — use this exact template:**

```markdown
# Node-Gen Review Report

> Plan: {plan name from extraction plan}
> Nodes reviewed: {count}
> Date: {ISO date}
> Reviewer: Opus

## 1. Summary

| Metric | Count |
|--------|-------|
| Nodes reviewed | {n} |
| PASS | {n} |
| NEEDS-FIX | {n} |
| CRITICAL | {n} |
| Notation conflicts | {n} |
| Edge issues | {n} |
| Redundant equations | {n} |
| Implementability gaps | {n} |
| Schema violations | {n} |

## 2. Per-Node Verdicts

| Node ID | Cluster | Verdict | Issues |
|---------|---------|---------|--------|
| {id} | {letter} | PASS / NEEDS-FIX / CRITICAL | {one-line summary or "—"} |
| ... | ... | ... | ... |

Verdict criteria:
- **PASS** — no errors, at most minor warnings
- **NEEDS-FIX** — fixable issues (notation drift, missing edges, minor schema)
- **CRITICAL** — implementability failure or structural error requiring requery

## 3. Notation Conflicts

### 3.1 Symbol collisions (same symbol, different meaning)

| Symbol | Node A | Definition A | Node B | Definition B |
|--------|--------|-------------|--------|-------------|
| {latex} | {id} | {def} | {id} | {def} |

### 3.2 Representation drift (same quantity, different LaTeX)

| Quantity | Canonical form | Nodes using canonical | Nodes using variant | Variant |
|----------|---------------|----------------------|--------------------| --------|
| {name} | {latex} | {ids} | {ids} | {latex} |

### 3.3 Suggested canonical notation

{Table of recommended canonical symbol → definition mappings for the full node set.}

## 4. Edge Coherence

### 4.1 Dangling edges (target not found)

| Source node | Edge target | Edge type | Resolution |
|-------------|------------|-----------|------------|
| {id} | {target_id} | {type} | REMOVE / ADD TARGET TO INVENTORY |

### 4.2 Orphan nodes (no edges in or out)

| Node ID | Suggested edges |
|---------|----------------|
| {id} | requires: {id}, feeds-into: {id} |

### 4.3 Missing reciprocals (warnings only)

| Node A | Edge A→B | Node B | Missing B→A |
|--------|----------|--------|-------------|
| {id} | requires | {id} | feeds-into |

## 5. Redundant Equations

| Equation label | Defined in | Also in | Recommended owner | Action for duplicate |
|---------------|-----------|---------|-------------------|---------------------|
| {label} | {id} | {id} | {id} | Remove, add `requires` edge |

## 6. Implementability Gaps

### 6.1 Missing dependency edges

| Node | Algorithm step | Uses symbol/concept | Defined in | Missing edge |
|------|---------------|--------------------| -----------|-------------|
| {id} | Step {n} | {symbol} | {other_id} | requires |

### 6.2 Undefined symbols

| Node | Field | Symbol | Not in notation map, not in `where`, not in `requires` chain |
|------|-------|--------|-------------------------------------------------------------|
| {id} | {field_path} | {latex} | {suggestion} |

## 7. Schema Violations

| Node | Field | Expected | Actual | Fix |
|------|-------|----------|--------|-----|
| {id} | {field} | {value} | {value} | {corrected value} |

## 8. Suggested Fixes

YAML patches that can be applied directly. Grouped by fix type.

### 8.1 Notation fixes
```yaml
# {id}.yaml — normalize symbol
math_formulation.notation:
  '\hat{\boldsymbol{\varepsilon}}': "microscopic strain field (Fourier space)"
  # was: '\hat{\varepsilon}'
```

### 8.2 Edge fixes
```yaml
# {id}.yaml — add missing requires edge
edges:
  - to: {target_id}
    type: requires
    weight: {weight}
```

### 8.3 Schema fixes
```yaml
# {id}.yaml — fix domain
domain: fft-galerkin
# was: computational-mechanics
```
```

---

## Query Strategy (summary)

Read `references/query_strategies.md` for the full approach. The key idea: **don't run the same 5 queries for every node.** Adapt based on node type.

| Node type | How to identify | Core queries |
|-----------|----------------|--------------|
| **Concept** | Title is a definition/theory (e.g., "Periodic Cell Problem") | Definition, Equations, Pitfalls |
| **Solver** | Title contains "solver", "scheme", "method" | All 5 queries + convergence criteria |
| **Discretization** | Title contains "discretization", "grid", "finite" | Equations, Algorithm, Discretization-specific |
| **Operator** | Title contains "operator", "Green's", "Γ" | Definition, Full equations with all symbols, Pitfalls |

Always run a targeted query (Query 5) when the extraction plan's `source` field contains `Eq.` or `§` references — those point to specific content worth extracting directly.

## Schema Compliance (from frozen design docs 03 + 04)

Read `references/schema_compliance.md` for full details. These are the hard constraints:

**Every generated node MUST have these exact values:**
```yaml
status: tentative       # never established — developer promotes during review
source: hybrid          # NLM-extracted content
confidence: 0.90
content_ref: null
akms_schema: v2         # NEVER v1
```

**Domain taxonomy:** For FFT-related nodes use `domain: fft-galerkin`, not `computational-mechanics`. See compliance doc §3 for the full taxonomy from doc 04.

**Edge types (frozen in FR-G05):** `requires`, `feeds-into`, `refines`, `contradicts`, `pitfall`, `implements`. For domain nodes, primarily use the first three. Do NOT use `implements` (reserved for code-mirror).

**Edge targets:** Use exact ids from the inventory in `references/akms_node_template.md` §6. Log any invented ids.

**Forbidden fields:** Never include experiential state in node frontmatter: `activations`, `last_activated`, `activated_by_tasks`, `session_refs`. These belong in `local_state.yaml` only.

**Tags:** Prefer the canonical tag vocabulary from doc 04 (listed in compliance doc §4).

## Self-Containedness Rules

These are non-negotiable. Every node must be implementable from its content alone.

1. **NEVER** output equation-number references from papers ("Eq. 2.47"). Write the full equation in `math_formulation.equations`.

2. **NEVER** use vague algorithm steps. Every step must contain executable math.
   - WRONG: `{cmd: State, math: 'evaluate symmetrized gradient'}`
   - RIGHT: `{cmd: State, math: '\hat{\varepsilon}_{ij} \gets \frac{1}{2}(\eta_i u_j + \eta_j u_i)'}`

3. **EVERY** symbol in an equation must be defined in `notation` or inline in `where`.

4. **NEVER** say "apply the formula from §X" or "as described in [source]". Extract and write the actual formula.

5. **Grounding:** All domain content MUST come from the NotebookLM notebook. Do not supplement with training data for formulas or algorithms. If the notebook lacks content for a field, set its value to `"[INSUFFICIENT SOURCE]"` and log a warning.

## NLM Failure Handling

If `nlm notebook query` returns an error, empty response, or times out:

1. **Retry once** with a reformulated query using more specific terms from the extraction plan's `source` field. Consider increasing `--timeout`.
2. **Fall back** to `nlm source content <SOURCE_ID>` to read raw paper text and extract manually.
3. **If still insufficient**, set the field to `"[INSUFFICIENT SOURCE]"` and log a warning — never fill gaps from training data.
4. **At end of batch**, report all `[INSUFFICIENT SOURCE]` fields so the user knows what needs manual attention.

## Output Structure

```
{OUT_DIR}/
  {id}.yaml          ← source of truth
  {id}.md            ← derived (regenerable via `convert`)
```

## Batching Rules

### Sequential mode (default)

- **Single node:** generate, convert, validate, report.
- **Cluster:** iterate all nodes. Convert and validate after each. Report cluster summary at end.
- **All:** process one cluster at a time (A → B → ... → H). Validate each cluster before starting the next. Report full summary at end.

### Parallel mode (`PARALLEL=true`)

When `NODE_SELECTION` is `"all"` and `PARALLEL` is true, dispatch subagents in waves. This gives ~3× speedup without tripping NLM rate limits (~50 queries/day free tier, auth sessions last ~20 min).

**Wave assignment algorithm:**

1. Sort clusters by node count (descending).
2. Assign clusters to waves of **2–3 agents each**, balancing total node count per wave.
3. Each wave must complete before the next starts.

**Example for the FFT plan (30 nodes, 8 clusters):**

```
Wave 1:  B (7 nodes)  |  A (4 nodes)  |  C (4 nodes)     ← 15 nodes, 3 agents
Wave 2:  F (3 nodes)  |  D (2 nodes)  |  E (2 nodes)     ←  7 nodes, 3 agents
Wave 3:  G (4 nodes)  |  H (4 nodes)                      ←  8 nodes, 2 agents
```

**Subagent dispatch:**

Each subagent receives a self-contained task. The orchestrating agent spawns them via `Task`:

```
Task for each subagent:
  "Use the node-gen skill (skills/node-gen/SKILL.md) with the extract command.
   Read all bundled references (schema_compliance, akms_node_template, query_strategies) first.

   NLM_ID: {NLM_ID}
   NODE_SELECTION: {cluster_letter}
   PLAN_PATH: {PLAN_PATH}
   OUT_DIR: {OUT_DIR}

   Process only cluster {cluster_letter}. Convert and validate each node.
   Report summary at end."
```

**Wave completion gate:**

After all agents in a wave finish, the orchestrator:
1. Collects each agent's summary (OK / MANUAL / SKIP per node).
2. Runs a batch validation pass: `uv run python scripts/akms_node_clean.py {OUT_DIR}/ -v`
3. Only proceeds to the next wave if no unresolved errors remain.
4. After all waves, prints the final combined report.

**Rate limit safety:**

- Maximum 3 agents per wave (limits concurrent NLM queries to ~15 simultaneous).
- If any agent reports NLM rate-limit errors or auth failures, pause and re-authenticate (`nlm login`) before continuing.
- Subagents should add a 2-second delay between NLM queries to avoid bursts.