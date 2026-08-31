---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/repo-documentor/references/DIAGRAMS.md
context_size: small
domain: project-meta
edges:
- note: Diagrams follow documentation structure conventions
  to: rd-ref-conventions
  type: requires
  weight: 0.5
- note: Diagram integrity is a quality gate check
  to: rd-ref-quality-gates
  type: feeds-into
  weight: 0.5
id: rd-ref-diagrams
reading_priority: full
source: human
status: established
subdomain: documentation
tags:
- diagrams
- Mermaid
- Graphviz
- TikZ
- architecture
- dataflow
- class-relationships
title: Architecture & Dataflow Diagram Recipes
---

# Architecture & Dataflow Diagram Recipes

## Summary

Six Mermaid diagram recipes: module dependency DAGs, dataflow diagrams, lifecycle/state machines, data provenance graphs, class relationships, and call graphs. Graphviz DOT fallback for complex layouts. TikZ for small diagrams in LaTeX output. Diagrams must correspond to real modules/classes in codebase (quality gate requirement).

**Parent skill:** `skill-repo-documentor`
**Content:** `content/repo-documentor/references/DIAGRAMS.md`
