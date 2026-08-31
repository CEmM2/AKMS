---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/references/data-layout-and-snode.md
context_size: medium
domain: gpu-simulation
edges:
- note: Data layout choices directly affect kernel design
  to: tgs-ref-kernel-patterns
  type: feeds-into
  weight: 0.8
- note: Memory layout is primary performance determinant
  to: tgs-ref-performance
  type: feeds-into
  weight: 0.7
id: tgs-ref-data-layout
reading_priority: full
source: human
status: established
subdomain: taichi
tags:
- data-layout
- SNode
- ti.field
- ti.ndarray
- struct-of-arrays
- memory-layout
- GPU-optimization
title: 'Taichi Data Layout: Fields, SNodes & Memory'
---

# Taichi Data Layout: Fields, SNodes & Memory

## Summary

GPU-first guidelines for choosing Taichi containers (ti.field with SNodes vs ti.ndarray) and designing SNode layouts for performance. Covers field vs ndarray trade-offs, SNode tree mental models, dense/sparse layout basics, struct-of-arrays patterns, and cache-friendly tiling. Emphasizes flexibility of fields for layout optimization and thread-local storage reduction benefits.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/references/data-layout-and-snode.md`
