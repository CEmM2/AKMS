---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/domains/fft.md
context_size: medium
domain: gpu-simulation
edges:
- note: GPU implementation of FFT-Galerkin spectral methods
  to: cm-fft-galerkin
  type: implements
  weight: 0.9
- note: FFT may bridge to cuFFT via interop
  to: tgs-ref-interop
  type: requires
  weight: 0.7
- note: FFT kernels follow standard patterns
  to: tgs-ref-kernel-patterns
  type: requires
  weight: 0.6
id: tgs-dom-fft
reading_priority: full
source: human
status: established
subdomain: taichi-fft
tags:
- FFT
- spectral-methods
- Fourier
- complex-arithmetic
- wavenumber
- dealiasing
- cuFFT
title: FFT & Spectral Methods Domain Playbook
---

# FFT & Spectral Methods Domain Playbook

## Summary

FFT spectral domain playbook: real/Fourier space field pairs, wavenumber grids, forward/inverse normalization conventions, complex number storage via ti.Vector, R2C efficiency (conjugate symmetry), dealiasing via 2/3 rule. Covers library interop (CuPy, cuFFT external), spectral derivative computation, and in-place transform memory trade-offs.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/domains/fft.md`
