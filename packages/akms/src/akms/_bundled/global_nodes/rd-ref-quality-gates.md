---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/repo-documentor/references/QUALITY_GATES.md
context_size: small
domain: project-meta
edges:
- note: Quality gates verify contract completeness
  to: rd-ref-contracts
  type: requires
  weight: 0.7
- note: Quality gates verify diagram integrity
  to: rd-ref-diagrams
  type: requires
  weight: 0.5
- note: Quality gates verify validation coverage
  to: rd-ref-validation
  type: requires
  weight: 0.6
id: rd-ref-quality-gates
reading_priority: full
source: human
status: established
subdomain: documentation
tags:
- quality-gates
- documentation-audit
- completeness
- coverage
- checklist
- verification
title: Documentation Quality Gates Checklist
---

# Documentation Quality Gates Checklist

## Summary

Six mandatory quality gate categories: structural coverage (every module/class/function has a contract), glossary consistency (all symbols defined), diagram integrity (nodes match real code), inference labeling (unknowns marked), workflow completeness (entrypoints + typical runs), validation coverage (tests-to-modules mapping). Pass criteria ensures documentation is auditable.

**Parent skill:** `skill-repo-documentor`
**Content:** `content/repo-documentor/references/QUALITY_GATES.md`
