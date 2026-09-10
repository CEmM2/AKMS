---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/references/style-and-architecture.md
context_size: small
domain: gpu-simulation
edges:
- note: Style guide assumes kernel pattern knowledge
  to: tgs-ref-kernel-patterns
  type: requires
  weight: 0.5
- note: Naming follows convention quick-reference
  to: tgs-ref-conventions-quickref
  type: requires
  weight: 0.6
id: tgs-ref-style-architecture
reading_priority: summary
source: human
status: established
subdomain: taichi
tags:
- style-guide
- naming-conventions
- code-organization
- architecture
- maintainability
title: Codebase Style Guide & Module Architecture
---

# Codebase Style Guide & Module Architecture

## Summary

House style and naming conventions for a coherent Taichi codebase: tensor variable names (F, C, b, L, D, W, R_delta), stress/damage naming (sigma_v, sigma_hat_v, p, m, vm, ws, wt), file organization (reference/ cross-domain, domains/ recipes), and module structure (kinematics.py, constitutive.py, fem_ops.py). Ensures generated code matches repository patterns.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/references/style-and-architecture.md`
