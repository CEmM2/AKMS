---
id: gmsh-geometry-api
title: Gmsh Geometry Definition (OCC & Built-in Kernels)
domain: computational-mechanics
subdomain: mesh-generation
tags:
- gmsh
- geometry
- OCC
- built-in
- boolean-ops
- CAD
status: established
confidence: 0.9
source: hybrid
edges:
- to: gmsh-physical-groups
  type: feeds-into
  weight: 0.5
- to: gmsh-meshing-algorithms
  type: feeds-into
  weight: 0.5
- to: gmsh-python-api
  type: requires
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Gmsh Geometry Definition (OCC & Built-in Kernels)

## Summary

Gmsh defines geometric models using Boundary Representation (BRep) and constructive solid geometry (CSG) supported by two primary CAD engines: the built-in kernel and the OpenCASCADE (OCC) kernel. Elementary entities (points, curves, surfaces, volumes) are uniquely identified by a dimension-tag integer pair. Built-in geometries follow a strict bottom-up construction flow, whereas the OpenCASCADE kernel additionally supports top-down primitive creation (such as Rectangle, Sphere, and Box) and 3D boolean operations.

## 1. Core Concept

Geometry definition in Gmsh establishes the topological and geometric foundation for finite element meshing using Boundary Representation (BRep). Topological entities are categorized into four dimensions: 0D (points), 1D (curves), 2D (surfaces), and 3D (volumes), each identified by an entity tag pair (dim, tag) where tag is a positive integer. Gmsh interfaces two distinct CAD kernels: the native built-in kernel (`geo`) requiring explicit bottom-up topology assembly (points to curves to curve loops to surfaces), and the OpenCASCADE kernel (`occ`) enabling solid primitives, STEP/IGES import, and constructive solid geometry via boolean operations (union, intersection, difference, fragments). Kernel actions remain isolated until synchronized with the internal model.

## 2. Mathematical Formulation

**entity_identification**
$$
e_i = (d_i, T_i), \quad d_i \in \{0, 1, 2, 3\}, \quad T_i \in \mathbb{Z}^+
$$
_Source: Gmsh Reference Manual, Section 1.1, p. 7-8_

**curve_parametrization**
$$
\mathbf{x}(u) = (x(u), y(u), z(u)), \quad u \in [u_{min}, u_{max}]
$$
_Source: Gmsh Reference Manual, Section 6.3, p. 133_

**surface_parametrization**
$$
\mathbf{x}(u, v) = (x(u, v), y(u, v), z(u, v)), \quad (u, v) \in \Omega \subset \mathbb{R}^2
$$
_Source: Gmsh Reference Manual, Section 6.3, p. 133_

**occ_rectangle_primitive**
$$
\mathbf{x}_{rect}(u, v) = \mathbf{x}_0 + u \cdot dx \, \mathbf{e}_x + v \cdot dy \, \mathbf{e}_y, \quad u, v \in [1]
$$
_Source: Gmsh Reference Manual, Section 5.2.3, p. 102 & Section 6.8, p. 183_

**Notation:**
- {'d': 'Topological dimension (0 for point, 1 for curve, 2 for surface, 3 for volume)'}
- {'T': 'Strictly positive integer tag unique per dimension'}
- {'u, v, w': 'Parametric coordinates within the reference space of a model entity'}
- {'\\mathbf{x}': 'Coordinates (x, y, z) in 3D Euclidean space'}
- {'\\Omega': 'Parametric domain of a surface entity'}


## 3. Algorithmic Implementation

**built_in_versus_occ_surface_creation**
$$
\begin{algorithmic}
\State $\text{Define corner coordinates } (x_0, y_0, z_0), \text{ width } dx, \text{ height } dy, \text{ and characteristic length } l_c$
\If{$\text{Kernel} = \text{Built-in}$}
\State $p_1 = \text{Point}(1) = \{x_0, y_0, z_0, l_c\}, \; p_2 = \text{Point}(2) = \{x_0+dx, y_0, z_0, l_c\}$
\State $p_3 = \text{Point}(3) = \{x_0+dx, y_0+dy, z_0, l_c\}, \; p_4 = \text{Point}(4) = \{x_0, y_0+dy, z_0, l_c\}$
\State $c_1 = \text{Line}(1) = \{p_1, p_2\}, \; c_2 = \text{Line}(2) = \{p_2, p_3\}, \; c_3 = \text{Line}(3) = \{p_3, p_4\}, \; c_4 = \text{Line}(4) = \{p_4, p_1\}$
\State $L_1 = \text{Curve Loop}(1) = \{c_1, c_2, c_3, c_4\}$
\State $S_1 = \text{Plane Surface}(1) = \{L_1\}$
\ElsIf{$\text{Kernel} = \text{OpenCASCADE}$}
\State $\text{SetFactory}("OpenCASCADE")$
\State $S_1 = \text{Rectangle}(1) = \{x_0, y_0, z_0, dx, dy\}$
\EndIf
\State $\text{Synchronize CAD kernel data with internal Gmsh model structure}$
\Return $\text{Surface entity } (2, S_1) \text{ ready for physical group assignment or meshing}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Gmsh Reference Manual, Section 2.1, p. 15-18 & Section 5.2.3, p. 102_


## 4. Known Pitfalls

- **Primitive Rectangle Unavailability in Built-in Kernel**: Attempting to create a rectangle primitive directly using the Rectangle command under the built-in geometry kernel causes a syntax error. Built-in surface creation requires a bottom-up construction sequence defining 4 corner points, 4 bounding lines, 1 curve loop, and 1 plane surface. Direct primitive commands such as Rectangle, Box, Sphere, and Cylinder are exclusive to the OpenCASCADE kernel. _(Source: Gmsh Reference Manual, Section 2.1, p. 18 & Section 5.2.3, p. 102)_
- **Unsynchronized Kernel Model State**: Geometrical entities added or transformed via scripting or API calls in either the built-in (geo) or OpenCASCADE (occ) kernels are not visible to meshing algorithms or top-level model queries until a synchronization operation (e.g., SyncModel, gmsh.model.geo.synchronize(), or gmsh.model.occ.synchronize()) is executed. _(Source: Gmsh Reference Manual, Section 5.1.9, p. 99 & Section 6.6, p. 177)_
- **Inability to Cross-Translate Geometry Formats**: Gmsh does not convert native geometry definitions between CAD kernels. Geometries created using the built-in kernel cannot be exported as OpenCASCADE BREP or STEP files, and OpenCASCADE models cannot be exported as Unrolled GEO files. _(Source: Gmsh Reference Manual, Section 2.2, p. 21 & Section C.4, p. 375)_

## References

- Gmsh Reference Manual, Version 4.11.0 (development version), Christophe Geuzaine and Jean-François Remacle, 2022.
