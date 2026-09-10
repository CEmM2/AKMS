---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/repo-documentor/references/PROFILES.md
context_size: medium
domain: project-meta
edges:
- note: Profiles follow documentation conventions
  to: rd-ref-conventions
  type: requires
  weight: 0.6
- note: Profile sections are checked by quality gates
  to: rd-ref-quality-gates
  type: feeds-into
  weight: 0.5
id: rd-ref-profiles
reading_priority: full
source: human
status: established
subdomain: documentation
tags:
- profiles
- sci-compute
- ML
- image-processing
- data-analysis
- GUI
- embedded
- geometry
title: Repository Profiles & Domain Detection
---

# Repository Profiles & Domain Detection

## Summary

Documentation profile selection guide: scientific compute (FEM/solvers/FFT with safeguards/convergence/precision), ML/deep learning (training/inference/reproducibility), image processing (coordinates/normalization/resampling), data analysis (ETL/provenance/schema), GUI/tooling (entrypoints/workflows). Each profile adds required subsections. Repos choose 1-3 profiles.

**Parent skill:** `skill-repo-documentor`
**Content:** `content/repo-documentor/references/PROFILES.md`
