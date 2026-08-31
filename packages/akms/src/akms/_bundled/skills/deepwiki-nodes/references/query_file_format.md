# Question File Format Specification

## Overview

The question file is a markdown document that defines what to evaluate. It contains:
- **Frontmatter** — repo config, MCP endpoint, decision thresholds
- **Topics** — conceptual areas to evaluate (e.g., "Return Mapping Algorithm")
- **Queries** — specific DeepWiki MCP tool calls within each topic
- **Ground Truth** — facts you already know, used to score DeepWiki's output
- **Scoring** — empty tables you fill after reviewing responses

The evaluation script parses this file, executes the queries, and injects responses
back into the document (or a copy of it) without disturbing the scoring sections.

---

## Frontmatter (Required)

```yaml
---
repo: idaholab/moose                        # GitHub owner/repo (required)
mcp_endpoint: https://mcp.deepwiki.com/mcp  # DeepWiki MCP URL (required)
eval_name: "MOOSE Content Quality Eval"     # Display name (required)
thresholds:                                 # Decision thresholds (required)
  proceed: 3.0                              # Average score to proceed with extraction
  supplement: 2.0                           # Below this = abandon DeepWiki
---
```

---

## Document Title

A level-1 heading after the frontmatter. Not parsed, purely for human readability.

```markdown
# MOOSE Content Quality Evaluation
```

---

## Topics

Each topic is a level-2 heading starting with `## Topic:`.

```markdown
## Topic: Return Mapping / Radial Return Algorithm
```

**Parsing rule:** The script identifies topics by the `## Topic:` prefix. Everything
after the colon (trimmed) is the topic title. Topic IDs are auto-generated as
`snake_case` of the title (e.g., `return_mapping_radial_return_algorithm`).

---

## Queries

Each query is a level-3 heading with the MCP tool name in square brackets:

```markdown
### [tool_name] Human-Readable Query Title
```

**Supported tools:**

| Tool | Parameter | Body content meaning |
|------|-----------|---------------------|
| `read_wiki_structure` | `repo_name` (from frontmatter) | Ignored (structure has no query param) |
| `read_wiki_contents` | `repo_name` + `topic` | Body text = topic search hint |
| `ask_question` | `repo_name` + `question` | Body text = the full question |

**Body text:** Everything between the query heading and the next heading (or section
boundary) is the query body. For `ask_question`, this is the literal question sent
to DeepWiki. For `read_wiki_contents`, this is the topic/search hint. Leading/trailing
whitespace is trimmed. Blank lines within the body are preserved.

### Examples

```markdown
### [read_wiki_structure] Full Topic Tree
```
↑ No body needed — just fetches the wiki structure.

```markdown
### [read_wiki_contents] Material System Documentation
Material system MaterialProperty ComputeStress history variables
```
↑ Body = topic hint sent to `read_wiki_contents`.

```markdown
### [ask_question] Return Mapping Algorithm
What is the numerical algorithm implemented in MOOSE's ComputeReturnMappingBase?
Describe step by step: (1) the trial elastic stress computation, (2) the yield
function evaluation, (3) the Newton iteration for the scalar effective inelastic
strain increment, (4) the convergence criterion, and (5) how the consistent
algorithmic tangent modulus is computed. Include the actual MOOSE variable names
used in the source code.
```
↑ Body = full question sent to `ask_question`.

---

## Ground Truth

A level-3 heading `### Ground Truth` within a topic. Contains a markdown checkbox
list of facts you know to be correct. These are never modified by the script — you
check them off manually after reviewing responses.

```markdown
### Ground Truth
- [ ] GT-1: Backward Euler discretization of flow rule, scalar equation for Δγ
- [ ] GT-2: Newton iteration: R(Δε) = Δε - Δt·f(σ_trial - C:Δε·N) = 0
- [ ] GT-3: Convergence check on |R| < tolerance (absolute and relative)
- [ ] GT-4: Mentions _effective_inelastic_strain_increment variable name
- [ ] GT-5: Consistent tangent with algorithmic correction term
```

**Numbering convention:** `GT-N:` prefix is recommended for cross-referencing in
scoring notes, but not required by the parser.

---

## Scoring

A level-3 heading `### Scoring` within a topic. Contains a markdown table with
three quality dimensions. Left empty by the question file author; filled during review.

```markdown
### Scoring
| Dimension | Score (1-5) | Notes |
|-----------|:-----------:|-------|
| D1 — Algorithmic Accuracy | | |
| D2 — Implementation Detail | | |
| D3 — Coverage Depth | | |
```

The script preserves this table exactly as-is. You fill it in after reviewing the
DeepWiki responses.

---

## Response Injection

When the script runs, it injects an `#### Response` block directly below each query
heading and body. The response is wrapped in a fenced code block to prevent markdown
rendering issues with DeepWiki's output.

**Before running:**
```markdown
### [ask_question] Return Mapping Algorithm
What is the numerical algorithm in ComputeReturnMappingBase?...
```

**After running:**
```markdown
### [ask_question] Return Mapping Algorithm
What is the numerical algorithm in ComputeReturnMappingBase?...

#### Response
<!-- deepwiki_query: tool=ask_question, status=success, tokens=1847, elapsed=4.2s -->
​```
The ComputeReturnMappingBase class implements a Newton-Raphson iteration...
​```
```

The HTML comment contains machine-readable metadata (tool, status, token estimate,
elapsed time). The code block contains the raw DeepWiki response text.

**Idempotency:** If the script detects an existing `#### Response` block under a
query, it replaces it rather than appending a duplicate. This lets you re-run the
eval to refresh stale responses.

---

## Summary Section

The script appends a `## Evaluation Summary` section at the bottom of the output
file containing:

```markdown
## Evaluation Summary

| Topic | Queries | Succeeded | Failed | Avg Response Length |
|-------|:-------:|:---------:|:------:|:-------------------:|
| Return Mapping | 3 | 3 | 0 | 1,247 chars |
| Material System | 3 | 2 | 1 | 983 chars |
| ... | | | | |

**Run metadata:**
- Timestamp: 2026-03-22T15:30:00Z
- Repo: idaholab/moose
- MCP endpoint: https://mcp.deepwiki.com/mcp
- Total queries: 12
- Total elapsed: 47.3s
- Decision thresholds: proceed=3.0, supplement=2.0

### Summary Scorecard
| Topic | D1 | D2 | D3 | Avg |
|-------|:--:|:--:|:--:|:---:|
| Return Mapping | | | | |
| Material System | | | | |
| ... | | | | |
| **Average** | | | | **Overall:** |

### Decision
- [ ] ≥ 3.0 → Proceed with extraction pipeline
- [ ] 2.0–3.0 → Proceed with heavy supplementation
- [ ] < 2.0 → Abandon as primary source
```

---

## Complete Example

See `references/question_template.md` for a blank template ready to fill in.

Below is a minimal two-topic example:

```markdown
---
repo: idaholab/moose
mcp_endpoint: https://mcp.deepwiki.com/mcp
eval_name: "MOOSE Eval — Minimal Example"
thresholds:
  proceed: 3.0
  supplement: 2.0
---

# MOOSE Eval — Minimal Example

## Topic: Return Mapping

### [ask_question] Radial Return Algorithm
What is the numerical algorithm in ComputeReturnMappingBase? Show the
Newton iteration, convergence criterion, and MOOSE variable names.

### [ask_question] Creating a New Model
How do I create a new radial return material model? What base class,
what methods to override, how to declare history variables?

### Ground Truth
- [ ] GT-1: Backward Euler flow rule discretization
- [ ] GT-2: returnMappingSolve() entry point
- [ ] GT-3: computeStressInitialize/Finalize hooks

### Scoring
| Dimension | Score (1-5) | Notes |
|-----------|:-----------:|-------|
| D1 — Algorithmic Accuracy | | |
| D2 — Implementation Detail | | |
| D3 — Coverage Depth | | |

## Topic: Material System

### [read_wiki_contents] Material Property Mechanics
Material system MaterialProperty stateful properties

### [ask_question] Stress Computation Chain
Walk through the stress computation chain in Tensor Mechanics from
ComputeStressBase through to a specific material model.

### Ground Truth
- [ ] GT-1: MaterialProperty<T> is per-qp vector
- [ ] GT-2: Old/older swapped by pointer, not copied
- [ ] GT-3: computeQpStress() override point

### Scoring
| Dimension | Score (1-5) | Notes |
|-----------|:-----------:|-------|
| D1 — Algorithmic Accuracy | | |
| D2 — Implementation Detail | | |
| D3 — Coverage Depth | | |
```
