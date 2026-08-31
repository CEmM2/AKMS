---
id: gmsh-extrusion
title: Gmsh Extrusion Operations
domain: computational-mechanics
subdomain: mesh-generation
tags:
- gmsh
- extrusion
- sweep
- layers
- prism
- recombine
status: established
confidence: 0.9
source: hybrid
edges:
- to: gmsh-geometry-api
  type: requires
  weight: 1.0
- to: gmsh-structured-meshing
  type: refines
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Gmsh Extrusion Operations

## Summary

Gmsh extrusion operations sweep 0D, 1D, and 2D geometrical entities and their meshes along translation, rotation, or combined twist paths to construct higher-dimensional entities. When extruding surface meshes, Gmsh generates 3D volumes structured in layers, producing tetrahedra by default or prisms/hexahedra/pyramids when the Recombine directive is specified.

## 1. Core Concept

Extrusion in Gmsh provides a structured sweeping mechanism to create curves from points, surfaces from curves, and volumes from surfaces. Extrude commands accept translation vectors, rotation axes, or helical twist parameters, alongside layer parameters (element counts and cumulative normalized heights). Mesh extrusion automatically generates conformal elements; triangulated base meshes yield tetrahedral elements that recombine into triangular prisms, whereas quadrangular base meshes recombine into hexahedra and pyramids.

## 2. Mathematical Formulation

**extrusion_translation**
$$
\mathbf{x}_{ext} = \mathbf{x} + \mathbf{t}
$$
_Source: Gmsh Reference Manual, Section 5.2.5, p. 104_

**extrusion_rotation**
$$
\mathbf{x}_{ext} = \mathbf{x}_0 + \mathbf{R}(\mathbf{a}, \theta)(\mathbf{x} - \mathbf{x}_0)
$$
_Source: Gmsh Reference Manual, Section 5.2.5, p. 104_

**extrusion_twist**
$$
\mathbf{x}_{ext} = \mathbf{x}_0 + \mathbf{R}(\mathbf{a}, \theta)(\mathbf{x} - \mathbf{x}_0) + \mathbf{t}
$$
_Source: Gmsh Reference Manual, Section 5.2.5, p. 104_

**extrusion_layer_height**
$$
h_i \in (0, 1], \quad 0 < h_1 < h_2 < \dots < h_k = 1
$$
_Source: Gmsh Reference Manual, Section 5.3.2, p. 109_

**Notation:**
- {'\\mathbf{x}': 'Coordinates of a point prior to extrusion transformation'}
- {'\\mathbf{x}_{ext}': 'Transformed coordinates of a point after extrusion'}
- {'\\mathbf{t}': 'Translation vector (dx, dy, dz)'}
- {'\\mathbf{x}_0': 'Pivot point on the rotation axis'}
- {'\\mathbf{a}': 'Direction vector of the rotation axis'}
- {'\\theta': 'Angle of rotation in radians'}
- {'h_i': 'Normalized cumulative height fraction for layer i'}


## 3. Algorithmic Implementation

**structured_mesh_extrusion**
$$
\begin{algorithmic}
\State $\text{Input source surface } S, \text{ layer element counts } \{N_1, \dots, N_k\}, \text{ normalized layer heights } \{h_1, \dots, h_k\}, \text{ and recombination flag } R$
\State $\text{Discretize source surface } S \text{ into 2D elements (triangles or quadrangles)}$
\For{$i \text{ from } 1 \text{ to } k$}
\State $\text{Subdivide interval } [h_{i-1}, h_i] \text{ into } N_i \text{ element subdivisions along the extrusion vector}$
\EndFor
\If{$R = \text{True}$}
\State $\text{Recombine tetrahedra generated from triangular base into prisms, or from quadrangular base into hexahedra and pyramids}$
\Else
\EndIf
\Return $\text{Extruded 3D volume mesh } V \text{ with top boundary } S_{top} \text{ and lateral surface boundaries } S_{lat}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Gmsh Reference Manual, Section 5.3.2, p. 109-110_


## 4. Known Pitfalls

- **Rotation Angle Limit in Built-in CAD Kernel**: When using the built-in geometry kernel, rotation extrusion angles must be strictly less than \pi radians. For a full 360-degree extrusion sweep using the built-in kernel, at least 3 successive rotation extrusions are required. The OpenCASCADE kernel allows angles up to 2\pi. _(Source: Gmsh Reference Manual, Section 2.3, p. 22 & Section 5.2.5, p. 104)_
- **Misconception of Triangular Prism Recombination**: Extruding a triangulated 2D surface mesh generates 3D tetrahedral elements by default. Specifying the Recombine option recombines these tetrahedra into triangular prisms (or into hexahedra/pyramids if the base surface mesh is quadrangular). Recombine does not convert triangular prisms into hexahedra. _(Source: Gmsh Reference Manual, Section 1.2, p. 9 & Section 5.3.2, p. 109)_
- **Legacy Region Tag Specification in Layers Command**: Explicit specification of region tags within Layers commands is no longer supported. Generated volume and lateral surface entity tags must be captured programmatically using the array returned by the Extrude scripting command. _(Source: Gmsh Reference Manual, Section 5.3.2, p. 109-110)_

## References

- Gmsh Reference Manual, Version 4.11.0 (development version), Christophe Geuzaine and Jean-François Remacle, 2022.
