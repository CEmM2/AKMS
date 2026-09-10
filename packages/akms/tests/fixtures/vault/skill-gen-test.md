---
akms_schema: v2
confidence: 0.95
confidence_floor: 0.7
content_ref: content/gen-test/SKILL.md
context_size: medium
domain: project-meta
edges:
- note: Tier B tests require Taichi kernel knowledge
  to: skill-taichi-gpu-sim
  type: requires
  weight: 0.7
- note: Tier C tests need mechanics for benchmark validation
  to: skill-computational-mechanics
  type: requires
  weight: 0.6
- note: Test generation uses verification benchmark definitions
  to: cm-verification
  type: requires
  weight: 0.7
- note: Test conventions align with reviewer testing practices
  to: tsr-ref-testing-verification
  type: requires
  weight: 0.6
id: skill-gen-test
reading_priority: full
source: human
status: established
subdomain: testing
tags:
- testing
- taichi-fem
- tiers
- pytest
- gpu
- tolerance
title: Test Generation Conventions for Taichi FEM Projects
---

# Test Generation Conventions for Taichi FEM Projects

## Summary

Generate tests for a Taichi FEM module following the tiered testing conventions (Tier A/B/C) with proper tolerances and GPU backend handling.

**Content:** `content/gen-test/SKILL.md`
