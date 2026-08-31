---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/computational-mechanics/reference/constitutive-anisotropic-yield.md
context_size: medium
domain: computational-mechanics
edges:
- note: Anisotropic yield extends the viscoplastic framework
  to: cm-viscoplastic-thermo
  type: requires
  weight: 0.8
- note: Requires objective rate formulation for large deformations
  to: cm-objective-rates
  type: requires
  weight: 0.6
id: cm-anisotropic-yield
reading_priority: full
source: human
status: established
subdomain: constitutive
tags:
- anisotropy
- yield-criteria
- barlat
- sheet-metal
- eigenvalues
- plasticity
- texture
title: Anisotropic Yield Criteria (Barlat 2004-18p)
---

# Anisotropic Yield Criteria (Barlat 2004-18p)

## Summary

Defines anisotropic yield criteria (Barlat 2004-18p) for materials with preferred orientations from crystallographic texture. Describes two linear stress transformations to principal values and yield function formulation using eigenvalue decomposition, with applications to sheet metal forming and textured metals. Includes both NumPy reference and Taichi GPU implementations.

## Related templates

- `content/computational-mechanics/templates/barlat_2004_numpy.py`
- `content/computational-mechanics/templates/barlat_2004_taichi.py`

**Parent skill:** `skill-computational-mechanics`
**Content:** `content/computational-mechanics/reference/constitutive-anisotropic-yield.md`
