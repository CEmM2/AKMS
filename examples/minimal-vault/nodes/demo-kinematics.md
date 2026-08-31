---
akms_schema: v2
id: demo-kinematics
title: Demo Kinematics
domain: demo-mechanics
tags:
- demo
- kinematics
status: established
confidence: 0.85
source: human
edges:
- to: demo-tensors
  type: requires
  weight: 0.8
  note: Deformation measures are tensor-valued
---

The deformation gradient F maps reference line elements to current ones.
Strain measures derive from F; all of them are tensors, hence the dependency.
