---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/references/kernel-patterns.md
context_size: large
domain: gpu-simulation
edges:
- note: Kernel patterns depend on SNode/field data layout choices
  to: tgs-ref-data-layout
  type: requires
  weight: 0.8
- note: Kernel patterns inform known-pitfall awareness
  to: tgs-ref-gotchas
  type: feeds-into
  weight: 0.7
- note: Patterns are the primary lever for performance tuning
  to: tgs-ref-performance
  type: feeds-into
  weight: 0.7
id: tgs-ref-kernel-patterns
reading_priority: full
source: human
status: established
subdomain: taichi
tags:
- kernel-design
- GPU
- ti.static
- ti.ndrange
- block-dim
- warp-divergence
- loop-forms
title: Taichi Kernel Patterns for GPU Simulation
---

# Taichi Kernel Patterns for GPU Simulation

## Summary

House style for writing fast Taichi kernels: one-responsibility-per-kernel pattern (map/reduce/scatter), interior-fast-path + boundary-kernel split to avoid warp divergence, ti.static for tiny fixed loops, ti.ndrange and ti.grouped for structured iteration, block_dim tuning for hotspots. Encodes performance best practices without sacrificing readability.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/references/kernel-patterns.md`
