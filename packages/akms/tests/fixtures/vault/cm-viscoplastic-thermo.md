---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/computational-mechanics/reference/constitutive-viscoplastic-thermo.md
context_size: large
domain: computational-mechanics
edges:
- note: Viscoplastic integration requires objective stress updates
  to: cm-objective-rates
  type: requires
  weight: 0.8
- note: Uses multiplicative decomposition F=FeFp
  to: cm-kinematics-tl
  type: requires
  weight: 0.7
- note: Provides framework extended by anisotropic yield models
  to: cm-anisotropic-yield
  type: feeds-into
  weight: 0.6
- note: Verified via Taylor anvil benchmark
  to: cm-verification
  type: feeds-into
  weight: 0.5
id: cm-viscoplastic-thermo
reading_priority: full
source: human
status: established
subdomain: constitutive
tags:
- viscoplasticity
- rate-dependent
- perzyna
- temperature
- adiabatic-heating
- backward-euler
- thermal-softening
title: Rate-Dependent Viscoplasticity with Thermal Coupling
---

# Rate-Dependent Viscoplasticity with Thermal Coupling

## Summary

Documents rate-dependent plasticity via Perzyna overstress formulation with finite-strain multiplicative split and temperature coupling. Covers implicit backward Euler integration for viscoplastic flow laws, thermal softening (Johnson-Cook style), and adiabatic heating via Taylor-Quinney coefficient. Establishes the default constitutive model template for the codebase.

## Related templates

- `content/computational-mechanics/templates/j2_perzyna_return_mapping.py`

**Parent skill:** `skill-computational-mechanics`
**Content:** `content/computational-mechanics/reference/constitutive-viscoplastic-thermo.md`
