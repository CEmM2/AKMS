# Addendum 0001 — Health reporting reachability

**Status**: accepted (2026-11-03)
**Amends**: [§5.7 Health Reporting](../AKMS_v2_specification.md#57-health-reporting),
the "Orphaned nodes" item.
**Decision record**: [ADR 0003](../../adr/0003-reachability-in-health-reporting.md)

This addendum refines one item of the frozen v2 specification. It changes the
health report's behaviour only. It changes no field of the frozen `akms/v2`
schema (§4), no compiled-graph field (§4.9) and no external-consumer contract
(§6), and it adds no required field anywhere. Requirement language follows the
specification's RFC-2119 conventions.

## Normative text

In §5.7, the item "Orphaned nodes (no edges)" is to be read as follows.

The health reporter **MUST** report a node as orphaned only when all of these
hold:

1. the node has no edges, incoming or outgoing, in the compiled graph;
2. the node is not linked by `load_with` (§4.1) in either direction: its own
   `load_with` names no node other than itself, and no other node names it in
   `load_with`;
3. the node is not the target (`node_id`) of any `by_path` or `by_symbol`
   record in a task route index in use for the report.

Session nodes and code-mirror nodes **MUST NOT** be reported as orphaned.

A task route index is in use when the caller names it explicitly, or, when the
caller names none, when the reporter discovers it at a conventional location in
the repository. Explicitly named route indexes **MUST** replace discovery. The
reporter **SHOULD** search conventional locations in a fixed order and use the
first file found, and **MUST NOT** reorder locations it already searched when
it adds new ones.

The reporter **MUST NOT** treat any route index, node id prefix, domain or
generating tool specially: every well-formed task route index counts the same.

A route index that cannot be read or does not parse as a task route index
**MUST NOT** stop the report. The reporter **MUST** report it as a warning and
**MUST** then evaluate orphans as if that index were not in use.

The structured report **SHOULD** say which route index was used, and **MUST**
keep every report key it already had.

Stale-node reporting, the other half of the same §5.7 item, is unchanged.

## Rationale

"No edges" was meant to find nodes nothing reaches. Nodes reached on purpose
without edges, through `load_with` coactivation or exact routes in a task route
index, matched it anyway. Generated lesson packs are built that way, and an
adopter's project saw every one of its 348 generated lessons reported as
orphaned. With this refinement the report lists the nodes nothing loads. The
full reasoning and its consequences are in
[ADR 0003](../../adr/0003-reachability-in-health-reporting.md).
