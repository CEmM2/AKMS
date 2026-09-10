---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/computational-mechanics/reference/ductile-fracture-gtn-phasefield.md
context_size: large
domain: computational-mechanics
edges:
- note: GTN-phase-field coupling builds on brittle phase-field framework
  to: cm-phase-field-fracture
  type: requires
  weight: 0.9
- note: GTN is coupled to the viscoplastic constitutive model
  to: cm-viscoplastic-thermo
  type: requires
  weight: 0.7
- note: Verified via spallation and cup-cone benchmarks
  to: cm-verification
  type: feeds-into
  weight: 0.5
id: cm-gtn-ductile-fracture
reading_priority: full
source: human
status: established
subdomain: fracture
tags:
- GTN
- porous-plasticity
- void-growth
- ductile-fracture
- phase-field-coupling
- damage
- coalescence
title: Gurson-Tvergaard-Needleman (GTN) Porous Ductile Fracture
---

# Gurson-Tvergaard-Needleman (GTN) Porous Ductile Fracture

## Summary

Describes the Gurson-Tvergaard-Needleman porous plasticity model with void growth, nucleation, and coalescence mechanisms. Includes phase-field coupling strategy linking plastic dissipation and porosity evolution to crack driving fields, stabilizing the transition from ductile damage to macroscopic fracture. Return mapping on the GTN yield surface with Tvergaard q-parameters.

**Parent skill:** `skill-computational-mechanics`
**Content:** `content/computational-mechanics/reference/ductile-fracture-gtn-phasefield.md`
