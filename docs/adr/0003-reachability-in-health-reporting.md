# ADR 0003 — Reachability in health reporting

**Status**: accepted (2026-11-03)

## Context

The health report (specification §5.7) lists "orphaned nodes (no edges)". The
rule assumes every node is meant to be reached by walking the graph, so a node
with no edge in or out is either a mistake or a forgotten leftover.

That assumption does not hold for nodes reached on purpose by other means:

- **`load_with` hints (FR-G10).** A node that names others in `load_with`, or
  that another node names there, is loaded by coactivation. `load_with` is not
  a graph edge, so these nodes have no edges.
- **Exact routes.** A task route index (`by_path` / `by_symbol`) maps
  repository paths and symbols straight to node ids. Task resolution and
  reviewer required-knowledge load those nodes without traversing the graph.
- **Generated lesson packs.** Tools such as `akms-failure-memory` generate one
  node per lesson, with no edges, and reach each lesson through `load_with`
  links to related lessons and through the route index they write next to the
  nodes.

In an adopter's failure-memory project, `akms status` reported all 348
generated lesson nodes as orphaned. None of them was unreachable. The section
was all noise, which hid the nodes that really were isolated.

Two smaller gaps made it worse. `akms status` never looked for a route index at
all. And the orchestrator's reviewer route discovery listed
`failure-routes.json`, but not `generated/failure_routes.json`, the default
`paths.routes` that `akms-failure-memory` writes, so a project using that
default got tag-based reviewer loadouts instead of its exact routes.

## Decision

A node is reported as orphaned only when **all** of the following hold:

1. it has no edges, in or out;
2. it is not linked by `load_with` in either direction: it names no other node
   in `load_with`, and no other node names it. A `load_with` that names only
   the node itself does not count;
3. it is not a target in the task route index that `akms status` discovered,
   or in the route indexes it was given.

Session nodes and code-mirror nodes stay exempt, as before.

Any well-formed task route index counts. No tool, node-id prefix or domain is
special-cased: a route index written by hand, by `akms-failure-memory` or by
another generator is treated the same.

Route-index discovery moves to `akms.task_context.routes`
(`TASK_ROUTE_INDEX_CANDIDATES`, `find_task_route_index`), which is part of the
projection surface of [ADR 0001](0001-projection-and-evidence-contract-surface.md).
The health report and the orchestrator's reviewer use the same function, and
the health report does not import the embedded runtime. The earlier locations
keep their order; `.knowledge/generated/failure_routes.json` and
`knowledge/generated/failure_routes.json` are appended after them, so a
repository that resolved to one file before still resolves to the same file.

`akms status --routes PATH` (repeatable) names the route indexes to use instead
of discovering one. A route index that cannot be read or parsed is skipped and
reported as a warning; it never stops the report.

This changes health-report behaviour only. There is no schema change and no new
required field. The rule is recorded normatively in
[Addendum 0001](../specification/addenda/0001-health-reporting-reachability.md).

## Consequences

- The **Orphaned Nodes** heading reads "no edges, load_with or route", and the
  section names the route index used, or says there was none. The structured
  report (as returned by `graph_status` and the `akms_graph_status` MCP tool)
  adds `route_index` (the first index used, or `null`), `route_indexes` (all
  indexes used) and `route_index_warnings`. No existing key is renamed or
  removed.
- An unusable route index appears under **Route Index Warnings** and counts
  toward the report's issue total.
- Reviewer required-knowledge now finds `generated/failure_routes.json` under
  `.knowledge/` or `knowledge/`, so projects on the `akms-failure-memory`
  default get exact reviewer routes without configuration.
- What is still reported: nodes with no edges, no `load_with` link and no
  route, other than session and code-mirror nodes. Those are the nodes nothing
  loads. In the adopter project above, a lesson is listed only if it has no
  related lesson and no route, which is the set worth looking at.
- A route target that does not exist in the graph is not reported here. Task
  resolution already fails closed on such a route, since it validates the route
  index against the graph.
- `graph_status(route_index=[])` turns discovery off, for callers that want the
  rule without routes.
