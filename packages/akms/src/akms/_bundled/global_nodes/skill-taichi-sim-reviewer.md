---
akms_schema: v2
confidence: 0.95
confidence_floor: 0.7
content_ref: content/taichi-sim-reviewer/SKILL.md
context_size: medium
domain: gpu-simulation
edges:
- note: Leaf reference node
  to: tsr-ref-review-checklist
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tsr-ref-testing-verification
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tsr-ref-documentation-standards
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tsr-ref-interface-compatibility
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tsr-ref-ci-cd
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tsr-ex-bad-kernel-review
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tsr-ex-pr-template
  type: refines
  weight: 0.6
id: skill-taichi-sim-reviewer
reading_priority: summary
source: human
status: established
subdomain: code-review
tags:
- review
- taichi
- checklist
- testing
- ci-cd
- documentation
title: Taichi Simulation Code Review Skill
---

# Taichi Simulation Code Review Skill

## Summary

Reviews Taichi (taichi-lang) simulation code, PRs, and modifications for correctness, performance, interface compliance, documentation quality, and test coverage. Enforces the patterns and best practices defined in `taichi-gpu-sim`.

This is a hub node whose leaf children cover individual reference files
and domain guides.  Refer to `content_ref` for the full skill content.
