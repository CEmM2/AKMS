---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/repo-documentor/references/CONTRACTS.md
context_size: small
domain: project-meta
edges:
- note: Contract blocks follow documentation conventions
  to: rd-ref-conventions
  type: feeds-into
  weight: 0.7
- note: Quality gates check that contracts are complete
  to: rd-ref-quality-gates
  type: feeds-into
  weight: 0.6
- note: Template stubs include contract block placeholders
  to: rd-asset-templates-md
  type: feeds-into
  weight: 0.7
id: rd-ref-contracts
reading_priority: full
source: human
status: established
subdomain: documentation
tags:
- API-contracts
- function-contract
- class-contract
- specifications
- dependency-surfaces
title: API Contract Block Specification
---

# API Contract Block Specification

## Summary

API contract block specification: function/kernel contracts include purpose, inputs (name/type/shape/units/range), outputs, side effects, errors, performance complexity, determinism. Class contracts cover responsibility, state invariants, lifecycle (init/reset/finalize), thread safety, external resources. Standard wording for dependency surfaces (public/semi-public/internal).

**Parent skill:** `skill-repo-documentor`
**Content:** `content/repo-documentor/references/CONTRACTS.md`
