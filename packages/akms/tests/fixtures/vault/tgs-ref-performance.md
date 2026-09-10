---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/references/performance.md
context_size: medium
domain: gpu-simulation
edges:
- note: Performance tuning applies to kernel patterns
  to: tgs-ref-kernel-patterns
  type: requires
  weight: 0.8
- note: Profiling guides data layout decisions
  to: tgs-ref-data-layout
  type: requires
  weight: 0.7
id: tgs-ref-performance
reading_priority: full
source: human
status: established
subdomain: taichi
tags:
- performance
- profiling
- GPU
- memory-bandwidth
- optimization
- benchmarking
- kernel-profiler
title: 'GPU Performance: Profiling & Optimization'
---

# GPU Performance: Profiling & Optimization

## Summary

Performance best practices for GPU simulation: warm up before benchmarking (JIT overhead), kernel profiler usage, fixed-cost benchmarking methodology, GPU memory hierarchy analysis (bandwidth-bound detection), atomics/sync minimization, data layout tuning, and kernel fusion strategies. Provides a systematic profiling workflow: measure → identify hotspot → optimize → repeat.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/references/performance.md`
