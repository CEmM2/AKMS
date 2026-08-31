---
akms_schema: v2
confidence: 0.95
confidence_floor: 0.7
content_ref: content/computational-mechanics/SKILL.md
context_size: medium
domain: computational-mechanics
edges:
- note: Leaf reference node
  to: cm-notation-cheatsheet
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: cm-tensor-calculus
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: cm-kinematics-tl
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: cm-objective-rates
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: cm-viscoplastic-thermo
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: cm-anisotropic-yield
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: cm-phase-field-fracture
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: cm-gtn-ductile-fracture
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: cm-fft-galerkin
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: cm-solver-matrixfree
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: cm-verification
  type: refines
  weight: 0.6
id: skill-computational-mechanics
reading_priority: summary
source: human
status: established
tags:
- fem
- plasticity
- fracture
- continuum
- tensor
- fft
- verification
title: Computational Mechanics Skill
---

# Computational Mechanics Skill

## Summary

Derives and implements nonlinear solid mechanics algorithms: tensor calculus, finite-strain kinematics
(Total Lagrangian, convected coordinates), rate- and temperature-dependent plasticity, brittle/ductile
fracture (phase-field, GTN), and FFT-Galerkin micromechanics. Use for FEM/FFT constitutive updates,
objective stress integration, solver architecture, and verification.


This is a hub node whose leaf children cover individual reference files
and domain guides.  Refer to `content_ref` for the full skill content.
