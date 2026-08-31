---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/computational-mechanics/reference/kinematics-tl-convected.md
context_size: medium
domain: computational-mechanics
edges:
- note: TL kinematics built on tensor calculus foundations
  to: cm-tensor-calculus
  type: requires
  weight: 0.9
- note: Uses standard notation from cheatsheet
  to: cm-notation-cheatsheet
  type: requires
  weight: 0.6
- note: Kinematics feeds into objective rate formulations
  to: cm-objective-rates
  type: feeds-into
  weight: 0.8
- note: TL formulation implemented as FEM kernels on Taichi
  to: tgs-dom-fem
  type: feeds-into
  weight: 0.9
id: cm-kinematics-tl
reading_priority: full
source: human
status: established
subdomain: kinematics
tags:
- total-lagrangian
- convected-coordinates
- large-rotations
- kinematics
- metric-tensor
- green-strain
- deformation
title: Total Lagrangian Kinematics with Convected Coordinates
---

# Total Lagrangian Kinematics with Convected Coordinates

## Summary

Defines Total Lagrangian convected-coordinate kinematics for capturing large rotations without spurious stress. Specifies metric tensor construction, Green strain in convected basis, and two routes for material laws: direct evaluation in the reference frame or push-forward to the spatial frame. Critical for maintaining objectivity in large-deformation plasticity implementations.

## Related templates

- `content/computational-mechanics/templates/tl_convected_element.py`

**Parent skill:** `skill-computational-mechanics`
**Content:** `content/computational-mechanics/reference/kinematics-tl-convected.md`
