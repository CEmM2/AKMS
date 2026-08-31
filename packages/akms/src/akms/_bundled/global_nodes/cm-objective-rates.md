---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/computational-mechanics/reference/objective-rates-integration.md
context_size: medium
domain: computational-mechanics
edges:
- note: Uses tensor transformation rules
  to: cm-tensor-calculus
  type: requires
  weight: 0.7
- note: Builds on TL kinematics for incremental updates
  to: cm-kinematics-tl
  type: requires
  weight: 0.8
- note: Objective rates needed for viscoplastic constitutive integration
  to: cm-viscoplastic-thermo
  type: feeds-into
  weight: 0.8
- note: Theory implemented in Taichi stress update pipeline
  to: tgs-ref-stress-integration
  type: feeds-into
  weight: 0.9
id: cm-objective-rates
reading_priority: full
source: human
status: established
subdomain: kinematics
tags:
- objectivity
- corotational
- rate-integration
- jaumann
- rigid-rotation
- stress-rates
- incremental
title: Objective Stress Rates & Incremental Integration
---

# Objective Stress Rates & Incremental Integration

## Summary

Addresses spurious stress generation under rigid body rotation when integrating rate constitutive equations in the spatial frame. Recommends corotational update pattern: compute incremental rotation via polar decomposition, rotate stress into corotational frame, integrate, rotate back. Contrasts Jaumann rate approach, emphasizing robustness and objectivity verification via rigid rotation tests.

**Parent skill:** `skill-computational-mechanics`
**Content:** `content/computational-mechanics/reference/objective-rates-integration.md`
