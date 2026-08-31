# Glossary

**Advisory knowledge**  
Role-aware tag/query context subject to ordinary thresholds and caps.

**AKMSAgent**  
Base class used by the optional pipeline runtime adapters.

**Code mirror**  
Generated v2 marker that binds a graph node to a repository source path or
definition.

**Coactivated knowledge**  
Knowledge selected through a required/exact node's `load_with` hints.

**Experiential overlay**  
Project-local `knowledge/graph/local_state.yaml` containing confidence,
activation, local-edge, session, and replay state.

**Failure-memory registry**  
Project-owned append-only canonical lesson history managed by the optional
`akms-failure-memory` package.

**Global vault**  
Read-only shared domain node collection, defaulting to
`~/.claude/akms/nodes/`.

**Learning Source Packet (LSP)**  
Validated learning artifact compiled by `akms-learn` from a graph slice and
learning request.

**Loadout**  
Task/phase/role-specific Markdown knowledge artifact.

**Mirror provider**  
Source projector that emits validated code-mirror nodes; currently `legacy` or
`repo2md`.

**PCD**  
Phase completion document containing task outcomes and a persistent knowledge
zone suitable for explicit graph update.

**Required knowledge**  
Exact route- or mirror-selected nodes that bypass advisory caps and fail closed
when unavailable.

**Resolution manifest**  
Canonical fingerprinted record of task inputs, graph/routes, role, and selected
knowledge.

**Route index**  
Project-local v1 mapping from source paths/symbols to required node IDs.

**Semantic determinism**  
Identical validated inputs produce the same graph/selection meaning and ordering,
even when generated artifact metadata includes a timestamp.
