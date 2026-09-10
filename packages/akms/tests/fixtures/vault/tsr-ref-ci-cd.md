---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-sim-reviewer/references/ci-cd-guidance.md
context_size: small
domain: project-meta
edges:
- note: CI pipeline runs the tiered test strategy
  to: tsr-ref-testing-verification
  type: requires
  weight: 0.7
- note: CI pass/fail informs review decision
  to: tsr-ref-review-checklist
  type: feeds-into
  weight: 0.5
id: tsr-ref-ci-cd
reading_priority: summary
source: human
status: established
subdomain: code-review
tags:
- CI/CD
- GitHub-Actions
- testing
- automation
- GPU-testing
- linting
- pre-commit
title: CI/CD Guidance for Taichi Projects
---

# CI/CD Guidance for Taichi Projects

## Summary

Automated testing guidance via GitHub Actions: goals (unit tests Tier A/B, integration Tier C, linting, type checking), workflow YAML template, GPU test handling, performance benchmarking in CI, and artifact retention. Emphasizes reproducibility and avoiding flaky tests through fixed seeds and deterministic operations.

**Parent skill:** `skill-taichi-sim-reviewer`
**Content:** `content/taichi-sim-reviewer/references/ci-cd-guidance.md`
