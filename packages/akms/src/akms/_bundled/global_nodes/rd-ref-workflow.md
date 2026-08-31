---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/repo-documentor/references/WORKFLOW.md
context_size: large
domain: project-meta
edges:
- note: Step 2 of workflow selects repo profiles
  to: rd-ref-profiles
  type: feeds-into
  weight: 0.8
- note: Steps 6-8 use convention templates
  to: rd-ref-conventions
  type: feeds-into
  weight: 0.7
- note: Step 11 runs quality gate checks
  to: rd-ref-quality-gates
  type: feeds-into
  weight: 0.7
id: rd-ref-workflow
reading_priority: full
source: human
status: established
subdomain: documentation
tags:
- workflow
- process
- steps
- inventory
- architecture
- API-docs
- generation
title: 12-Step Documentation Generation Workflow
---

# 12-Step Documentation Generation Workflow

## Summary

Step-by-step documentation generation procedure: (0) choose output mode (Markdown/LaTeX), (1) inventory repo, (2) select 1-3 profiles, (3) two-resolution architecture (codebase + module deep dives), (4) workflows/entrypoints, (5) glossary + artifacts + conventions, (6-8) module/class/function docs with contracts, (9) validation/verification map, (10) stability policy, (11) quality gates, (12) manifest generation.

**Parent skill:** `skill-repo-documentor`
**Content:** `content/repo-documentor/references/WORKFLOW.md`
