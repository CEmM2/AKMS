---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/repo-documentor/references/SECURITY_HARDWARE.md
context_size: small
domain: project-meta
edges:
- note: Security docs apply to embedded/control profiles
  to: rd-ref-profiles
  type: requires
  weight: 0.4
- note: Security items are checked by quality gates
  to: rd-ref-quality-gates
  type: feeds-into
  weight: 0.4
id: rd-ref-security-hardware
reading_priority: summary
source: human
status: established
subdomain: documentation
tags:
- security
- hardware
- safety
- interlocks
- motor-control
- embedded
- calibration
title: Security, Safety & Hardware Documentation
---

# Security, Safety & Hardware Documentation

## Summary

Documentation requirements for systems interacting with real devices (motor control, lab acquisition, experimental tooling): hardware assumptions (models, interfaces, OS), safety limits (current, speed, temperature, force), interlocks/watchdogs/emergency-stop behavior, failure modes and safe shutdown, calibration procedures/frequency, and logging/traceability artifacts.

**Parent skill:** `skill-repo-documentor`
**Content:** `content/repo-documentor/references/SECURITY_HARDWARE.md`
