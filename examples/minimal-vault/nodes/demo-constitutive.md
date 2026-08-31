---
akms_schema: v2
id: demo-constitutive
title: Demo Constitutive Model
domain: demo-mechanics
tags:
- demo
- constitutive
status: tentative
confidence: 0.7
source: hybrid
edges:
- to: demo-kinematics
  type: requires
  weight: 0.9
  note: Stress responds to strain, so kinematics comes first
---

A toy hyperelastic law: stress is a linear function of strain. Tentative on
purpose — the example shows how confidence and status flow through
projections.
