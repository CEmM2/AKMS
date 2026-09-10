---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-sim-reviewer/references/interface-compatibility.md
context_size: small
domain: project-meta
edges:
- note: Interface checks are part of the review checklist
  to: tsr-ref-review-checklist
  type: feeds-into
  weight: 0.6
id: tsr-ref-interface-compatibility
reading_priority: summary
source: human
status: established
subdomain: code-review
tags:
- API-compatibility
- breaking-changes
- deprecation
- versioning
- stability
- Hyrum's-Law
title: Interface Compatibility & API Stability
---

# Interface Compatibility & API Stability

## Summary

API stability guidance: defines breaking changes (renaming, removing, adding required args, changing return type, altering field layout, changing unit/sign conventions). Review strategies for signatures, data structures, and behavior. Deprecation patterns with warnings, semantic versioning, and migration guides. Hyrum's Law reminder: fix 'bugs' users may depend on carefully.

**Parent skill:** `skill-taichi-sim-reviewer`
**Content:** `content/taichi-sim-reviewer/references/interface-compatibility.md`
