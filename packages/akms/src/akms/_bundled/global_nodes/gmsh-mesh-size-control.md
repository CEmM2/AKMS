---
id: gmsh-mesh-size-control
title: Gmsh Mesh Size Control & Size Fields
domain: computational-mechanics
subdomain: mesh-generation
tags:
- gmsh
- mesh-size
- size-field
- attractor
- distance
- threshold
status: established
confidence: 0.9
source: hybrid
edges:
- to: gmsh-meshing-algorithms
  type: requires
  weight: 1.0
- to: gmsh-geometry-api
  type: requires
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Gmsh Mesh Size Control & Size Fields

## Summary

Gmsh controls mesh element sizes using point-based size specifications, curvature-adapted sizing, structured grid constraints, and general mesh size fields (such as Distance, Threshold, Box, MathEval, and PostView). To determine the local target element size at any spatial location, Gmsh computes the minimum of all active constraints, clamps the result within user-defined bounds [Mesh.MeshSizeMin, Mesh.MeshSizeMax], and scales it by Mesh.MeshSizeFactor.

## 1. Core Concept

Mesh size control in Gmsh prescribes local spatial resolution during bottom-up 1D, 2D, and 3D discretization. Target element sizes can be specified directly at CAD points, calculated automatically from local entity curvature, or defined dynamically using background size fields. Fields like Distance measure distance to geometric entities, Threshold maps distance to a range [SizeMin, SizeMax], Box imposes rectangular size step-changes, MathEval applies spatial mathematical functions, and Min combines multiple field outputs. When size fields drive discretization, disabling point-based and boundary-extended sizing prevents unwanted over-refinement.

## 2. Mathematical Formulation

**threshold_field_mapping**
$$
h_{thresh}(d) = \begin{cases} h_{min}, & d \le d_{min} \\ h_{min} + \frac{d - d_{min}}{d_{max} - d_{min}}(h_{max} - h_{min}), & d_{min} < d < d_{max} \\ h_{max}, & d \ge d_{max} \end{cases}
$$
_Source: Gmsh Reference Manual, Section 2.10, p. 38-39 & Section 8, p. 312_

**curvature_based_size**
$$
h_{curv} = \frac{2\pi R}{N_{2\pi}}
$$
_Source: Gmsh Reference Manual, Section 1.2.2, p. 10 & Section 7.4, p. 259_

**global_size_clamping**
$$
h_{final} = \text{MeshSizeFactor} \cdot \max\left( h_{min\_bound}, \min\left( \min_i(h_i), h_{max\_bound} \right) \right)
$$
_Source: Gmsh Reference Manual, Section 1.2.2, p. 11 & Section 2.10, p. 40_

**Notation:**
- {'d': 'Spatial distance to a specified point, curve, or surface entity'}
- {'d_{min}, d_{max}': 'Distance threshold bounds (DistMin, DistMax) for size field mapping'}
- {'h_{min}, h_{max}': 'Target element size bounds (SizeMin, SizeMax) within a Threshold field'}
- {'R': 'Local geometric radius of curvature'}
- {'N_{2\\pi}': 'Target element count per 2\\pi radians specified by Mesh.MeshSizeFromCurvature'}
- {'h_{final}': 'Final evaluated target element size at a given spatial coordinate'}


## 3. Algorithmic Implementation

**mesh_size_evaluation_pipeline**
$$
\begin{algorithmic}
\State $\text{Input coordinate } \mathbf{x}, \text{ geometry model entities, active fields } F_1, \dots, F_m, \text{ and global size options}$
\If{$\text{Mesh.MeshSizeFromPoints} = 1$}
\State $\text{Interpolate size } h_{point}(\mathbf{x}) \text{ from prescribed point size values}$
\EndIf
\If{$\text{Mesh.MeshSizeFromCurvature} > 0$}
\State $\text{Compute curvature size } h_{curv}(\mathbf{x}) = \frac{2\pi R(\mathbf{x})}{\text{Mesh.MeshSizeFromCurvature}}$
\EndIf
\If{$\text{Background Field } F_{bg} \text{ is assigned}$}
\State $\text{Evaluate field size } h_{field}(\mathbf{x}) = F_{bg}(\mathbf{x})$
\EndIf
\State $\text{Compute candidate minimum } h_{raw} = \min(h_{bbox}, h_{point}, h_{curv}, h_{field}, h_{bnd})$
\State $\text{Clamp size: } h_{clamped} = \max(\text{Mesh.MeshSizeMin}, \min(h_{raw}, \text{Mesh.MeshSizeMax}))$
\State $\text{Scale size: } h_{final} = h_{clamped} \cdot \text{Mesh.MeshSizeFactor}$
\Return $\text{Local target mesh size } h_{final}(\mathbf{x})$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Gmsh Reference Manual, Section 1.2.2, p. 10-11 & Section 2.10, p. 39-40_


## 4. Known Pitfalls

- **Over-Refinement from Unset Global Size Options**: When mesh element size is intended to be governed entirely by a background size field, leaving Mesh.MeshSizeFromPoints=1, Mesh.MeshSizeFromCurvature>0, or Mesh.MeshSizeExtendFromBoundary=1 active can cause unintended over-refinement near geometry boundaries. These options should be explicitly set to 0 when using size fields. _(Source: Gmsh Reference Manual, Section 1.2.2, p. 11 & Section 2.10, p. 40)_
- **Attractor Field Deprecation**: In Gmsh 4, the legacy Attractor field is a deprecated synonym for the Distance field. Size fields should be constructed using Distance fields combined with Threshold, MathEval, or Box fields. _(Source: Gmsh Reference Manual, Appendix D, p. 381 & Chapter 8, p. 297, 303)_
- **Algorithm Sensitivity to Steep Size Gradients**: When using size fields with steep element size gradients, Frontal-Delaunay (Mesh.Algorithm = 6) can struggle or produce poor quality elements; switching to the standard 2D Delaunay algorithm (Mesh.Algorithm = 5) handles steep gradients more robustly. _(Source: Gmsh Reference Manual, Section 2.10, p. 40)_

## References

- Gmsh Reference Manual, Version 4.11.0 (development version), Christophe Geuzaine and Jean-François Remacle, 2022.
