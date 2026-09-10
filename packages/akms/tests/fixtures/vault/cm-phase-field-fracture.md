---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/computational-mechanics/reference/phase-field-fracture.md
context_size: large
domain: computational-mechanics
edges:
- note: Spectral split requires eigenvalue decomposition
  to: cm-tensor-calculus
  type: requires
  weight: 0.6
- note: Phase-field framework extended by GTN ductile coupling
  to: cm-gtn-ductile-fracture
  type: feeds-into
  weight: 0.8
- note: Verified via Sneddon Mode-I benchmark
  to: cm-verification
  type: feeds-into
  weight: 0.7
id: cm-phase-field-fracture
reading_priority: full
source: human
status: established
subdomain: fracture
tags:
- phase-field
- fracture
- brittle
- AT-2
- spectral-split
- crack-regularization
- energy-functional
title: 'Phase-Field Fracture (Brittle): AT-2 & Spectral Split'
---

# Phase-Field Fracture (Brittle): AT-2 & Spectral Split

## Summary

Comprehensive phase-field method for brittle fracture regularization. Details the energy functional combining elastic strain energy and fracture dissipation via Ambrosio-Tortorelli functional (AT-2). Covers spectral energy split to prevent compression-driven cracking, staggered vs monolithic solution algorithms, history variable for irreversibility, and mesh refinement strategies. Central to diffuse crack representation without explicit tracking.

## Related templates

- `content/computational-mechanics/templates/miehe_spectral_split.py`
- `content/computational-mechanics/templates/phasefield_staggered_solver.py`

**Parent skill:** `skill-computational-mechanics`
**Content:** `content/computational-mechanics/reference/phase-field-fracture.md`
