---
akms_schema: v2
confidence: 0.95
confidence_floor: 0.7
content_ref: content/repo-documentor/SKILL.md
context_size: medium
domain: documentation
edges:
- note: Leaf reference node
  to: rd-ref-workflow
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: rd-ref-profiles
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: rd-ref-contracts
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: rd-ref-conventions
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: rd-ref-diagrams
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: rd-ref-quality-gates
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: rd-ref-validation
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: rd-ref-security-hardware
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: rd-asset-templates-md
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: rd-asset-mkdocs
  type: refines
  weight: 0.6
- note: Leaf reference node
  to: rd-asset-latex
  type: refines
  weight: 0.6
id: skill-repo-documentor
reading_priority: summary
source: human
status: established
tags:
- docs
- mkdocs
- sphinx
- latex
- diagrams
- api-contracts
title: Repository Documentation Generator Skill
---

# Repository Documentation Generator Skill

## Summary

Generate repository documentation with architecture/dataflow diagrams, workflows/entrypoints, artifacts & formats registry, units/frames conventions, module inheritance & API contracts, class/function references with math/physics descriptions, validation/verification maps, stability notes, and optional MkDocs/Sphinx/LaTeX outputs.

This is a hub node whose leaf children cover individual reference files
and domain guides.  Refer to `content_ref` for the full skill content.
