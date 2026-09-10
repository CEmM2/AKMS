---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-sim-reviewer/references/documentation-standards.md
context_size: small
domain: project-meta
edges:
- note: Doc standards are checked during review
  to: tsr-ref-review-checklist
  type: feeds-into
  weight: 0.7
- note: Documentation enables interface stability
  to: tsr-ref-interface-compatibility
  type: feeds-into
  weight: 0.5
id: tsr-ref-documentation-standards
reading_priority: summary
source: human
status: established
subdomain: code-review
tags:
- documentation
- docstrings
- comments
- Google-style
- naming
- magic-numbers
title: Documentation Standards for Simulation Code
---

# Documentation Standards for Simulation Code

## Summary

Documentation standards for Taichi simulation code: docstring format (Google style), essential info (purpose, args, returns, invariants, tuning), inline comments explain 'why' not syntax, code examples with assumptions, README guidance, and magic number justification. Emphasis on sufficient detail without bloat.

**Parent skill:** `skill-taichi-sim-reviewer`
**Content:** `content/taichi-sim-reviewer/references/documentation-standards.md`
