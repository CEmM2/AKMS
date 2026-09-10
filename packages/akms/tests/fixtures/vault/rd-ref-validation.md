---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/repo-documentor/references/VALIDATION.md
context_size: small
domain: project-meta
edges:
- note: Validation coverage is checked by quality gates
  to: rd-ref-quality-gates
  type: feeds-into
  weight: 0.6
id: rd-ref-validation
reading_priority: full
source: human
status: established
subdomain: documentation
tags:
- validation
- verification
- testing
- benchmarks
- golden-outputs
- SymPy
- data-provenance
title: Validation & Verification Documentation
---

# Validation & Verification Documentation

## Summary

Validation documentation structure: verification-map.md (unit test coverage, numerical regression with tolerances/seeds, benchmarks with hardware specs), tests-to-modules.md (coverage matrix), benchmarks.md (inputs/expected). SymPy or analytic verification recommended for tensor ops. Includes data provenance, versioning, checksums, and sanity expectations.

**Parent skill:** `skill-repo-documentor`
**Content:** `content/repo-documentor/references/VALIDATION.md`
