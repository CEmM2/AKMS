---
akms_schema: v2
confidence: 0.95
confidence_floor: 0.7
content_ref: content/taichi-gpu-sim/SKILL.md
context_size: medium
domain: gpu-simulation
edges:
- note: Leaf reference node
  to: tgs-ref-kernel-patterns
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-ref-data-layout
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-ref-performance
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-ref-gotchas
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-ref-continuum-tensors
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-ref-conventions-quickref
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-ref-stress-integration
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-ref-numerical-safeguards
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-ref-interop
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-ref-style-architecture
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-ref-testing-validation
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-dom-fem
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-dom-fd
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-dom-fft
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-dom-mpm
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-dom-linear-solvers
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: tgs-dom-time-integration
  type: refines
  weight: 0.6
id: skill-taichi-gpu-sim
reading_priority: summary
source: human
status: established
tags:
- taichi
- gpu
- kernel
- snode
- fem
- fft
- mpm
- fd
title: Taichi GPU Simulation Skill
---

# Taichi GPU Simulation Skill

## Summary

Writes optimized Taichi (taichi-lang) code for GPU numerical simulation, focusing on performant kernels, data layout/SNode design, and solver patterns for FEM, finite differences (FD), FFT-like spectral methods, and MPM. Use when implementing or optimizing Taichi kernels, choosing fields/SNodes, reducing atomics, tuning block dimensions, or debugging GPU performance/correctness.

This is a hub node whose leaf children cover individual reference files
and domain guides.  Refer to `content_ref` for the full skill content.
