---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/repo-documentor/assets/templates/TEMPLATES.md
context_size: medium
domain: project-meta
edges:
- note: Templates use contract block format
  to: rd-ref-contracts
  type: requires
  weight: 0.7
- note: Templates follow documentation conventions
  to: rd-ref-conventions
  type: requires
  weight: 0.6
id: rd-asset-templates-md
reading_priority: summary
source: human
status: established
subdomain: documentation
tags:
- templates
- Markdown
- index
- manifest
- module-docs
- class-docs
- function-docs
title: Markdown Template Stubs (Index, Manifest, Modules)
---

# Markdown Template Stubs (Index, Manifest, Modules)

## Summary

Five Markdown template stubs: docs/index.md (repo name, quickstart, profiles), docs/_manifest.yml (generation metadata), docs/modules/<module>.md (purpose, dependencies, public surfaces), docs/classes/<ClassName>.md (responsibility, state, lifecycle), docs/functions/<name>.md (contract, math, algorithm, safeguards). Starting skeleton for documentation generation.

**Parent skill:** `skill-repo-documentor`
**Content:** `content/repo-documentor/assets/templates/TEMPLATES.md`
