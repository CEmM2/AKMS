---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/computational-mechanics/reference/tensor-calculus.md
context_size: medium
domain: computational-mechanics
edges:
- note: Tensor calculus uses notation defined in cheatsheet
  to: cm-notation-cheatsheet
  type: requires
  weight: 0.8
- note: Tensor calculus is the language of kinematics
  to: cm-kinematics-tl
  type: feeds-into
  weight: 0.8
- note: Objective rates require tensor transformation rules
  to: cm-objective-rates
  type: feeds-into
  weight: 0.7
id: cm-tensor-calculus
reading_priority: full
source: human
status: established
subdomain: tensors
tags:
- tensor-calculus
- curvilinear
- push-forward
- pull-back
- objectivity
- metric-tensor
- covariant
title: Tensor Calculus for Continuum Mechanics
---

# Tensor Calculus for Continuum Mechanics

## Summary

Mathematical foundations for tensor operations in continuum mechanics code: curvilinear and convected coordinate systems, covariant/contravariant bases, metric tensor construction. Covers material vs spatial gradients, push-forward/pull-back transformations for 2nd and 4th-order tensors, objectivity requirements, and verification tests (symmetry, positive Jacobian, rigid rotation invariance).

## Related templates

- `content/computational-mechanics/templates/tensor_ops.py`

**Parent skill:** `skill-computational-mechanics`
**Content:** `content/computational-mechanics/reference/tensor-calculus.md`
