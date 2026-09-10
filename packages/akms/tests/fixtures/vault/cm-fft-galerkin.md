---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/computational-mechanics/reference/fft-galerkin-micromechanics.md
context_size: large
domain: computational-mechanics
edges:
- note: FFT operates on tensor fields in Fourier space
  to: cm-tensor-calculus
  type: requires
  weight: 0.7
- note: Uses standard notation for polarization fields
  to: cm-notation-cheatsheet
  type: requires
  weight: 0.5
- note: FFT solver uses matrix-free Newton-Krylov architecture
  to: cm-solver-matrixfree
  type: feeds-into
  weight: 0.8
- note: Theory implemented via Taichi FFT kernels
  to: tgs-dom-fft
  type: feeds-into
  weight: 0.9
id: cm-fft-galerkin
reading_priority: full
source: human
status: established
subdomain: spectral
tags:
- FFT
- Galerkin
- micromechanics
- RVE
- lippmann-schwinger
- homogenization
- periodic-boundary-conditions
- contrast
title: FFT-Galerkin Micromechanics & Homogenization
---

# FFT-Galerkin Micromechanics & Homogenization

## Summary

FFT-based Galerkin solvers for periodic heterogeneous materials (RVE homogenization). Introduces the Lippmann-Schwinger equation for polarization stress, Green's function projection in Fourier space, and contrast handling strategies. Covers strain-controlled and stress-controlled boundary conditions, accelerated schemes (Eyre-Milton, augmented Lagrangian), and Newton-Krylov convergence for computational homogenization of composites and polycrystals.

## Related templates

- `content/computational-mechanics/templates/fft_lippmann_schwinger.py`

**Parent skill:** `skill-computational-mechanics`
**Content:** `content/computational-mechanics/reference/fft-galerkin-micromechanics.md`
