---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/references/interop.md
context_size: small
domain: gpu-simulation
edges:
- note: Interop requires understanding of Taichi field layout
  to: tgs-ref-data-layout
  type: requires
  weight: 0.6
- note: FFT domain bridges to cuFFT via interop
  to: tgs-dom-fft
  type: feeds-into
  weight: 0.7
id: tgs-ref-interop
reading_priority: summary
source: human
status: established
subdomain: taichi
tags:
- interop
- NumPy
- PyTorch
- zero-copy
- kernel-arguments
- GPU-memory
- cuFFT
title: Taichi ↔ NumPy/PyTorch/CuPy Interoperability
---

# Taichi ↔ NumPy/PyTorch/CuPy Interoperability

## Summary

Data interchange between Taichi and NumPy/PyTorch/CuPy: copy-based interop (from_numpy, to_torch) vs reference/zero-copy interop via ti.types.ndarray kernel arguments. Covers contiguity requirements, device matching, external array support, field/array conversions, and integration with cuFFT. Critical for avoiding accidental GPU↔CPU copies in hot paths.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/references/interop.md`
