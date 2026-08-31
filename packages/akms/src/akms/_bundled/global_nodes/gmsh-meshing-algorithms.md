---
id: gmsh-meshing-algorithms
title: Gmsh Meshing Algorithms & Selection
domain: computational-mechanics
subdomain: mesh-generation
tags:
- gmsh
- meshing
- delaunay
- frontal
- HXT
- MeshAdapt
status: established
confidence: 0.9
source: hybrid
edges:
- to: gmsh-mesh-size-control
  type: feeds-into
  weight: 0.5
- to: gmsh-structured-meshing
  type: refines
  weight: 0.7
- to: gmsh-mesh-quality
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Gmsh Meshing Algorithms & Selection

## Summary

Gmsh provides a range of 2D and 3D unstructured finite element meshing algorithms. In 2D, surface triangulation algorithms include Frontal-Delaunay (the default, Mesh.Algorithm=6), Delaunay, MeshAdapt, BAMG, and Frontal-Delaunay for Quads. In 3D, tetrahedral algorithms include 3D Delaunay (Mesh.Algorithm3D=1), Netgen Frontal (Mesh.Algorithm3D=4), MMG3D, and HXT (a fast, parallel reimplementation of the 3D Delaunay algorithm).

## 1. Core Concept

Algorithm selection in Gmsh governs the unstructured spatial discretization of 2D surfaces and 3D volumes. Unstructured meshing follows a strict bottom-up sequence: 1D boundary curves are meshed first, followed by 2D surface meshing, and finally 3D volume meshing. For 2D surface meshes, Frontal-Delaunay offers high element quality, standard Delaunay is optimal for large planar domains, and MeshAdapt provides robustness on complex curved geometries. For 3D volume meshes, standard 3D Delaunay supports pyramid creation, embedded entities, and size fields, while HXT provides fine-grained OpenMP parallel speedup.

## 2. Mathematical Formulation

**delaunay_circumcircle_criterion**
$$
\|\mathbf{x} - \mathbf{c}_i\| < R_i
$$
_Source: Gmsh Reference Manual, Section 1.2.1, p. 9_

**adimensional_circumradius_insertion**
$$
\alpha_K = \frac{R_K}{h(\mathbf{c}_K)}
$$
_Source: Gmsh Reference Manual, Section 1.2.1, p. 9_

**delaunay_time_complexity**
$$
T(n) = \mathcal{O}(n \log n)
$$
_Source: Gmsh Reference Manual, Section 1.2.1, p. 9_

**Notation:**
- {'\\mathbf{x}': 'Spatial coordinates of an inserted interior mesh node'}
- {'\\mathbf{c}_K': 'Circumcenter of finite element K'}
- {'R_K': 'Circumradius of finite element K'}
- {'h(\\mathbf{x})': 'Local target mesh element size evaluated at position \\mathbf{x}'}
- {'\\alpha_K': 'Adimensional circumradius ratio governing sequential point insertion'}


## 3. Algorithmic Implementation

**unstructured_2d_and_3d_mesh_generation**
$$
\begin{algorithmic}
\State $\text{Input model geometry, 1D boundary discretization, 2D algorithm option } A_{2D}, \text{ and 3D algorithm option } A_{3D}$
\State $\text{Construct initial 2D Delaunay triangulation of 1D boundary nodes via divide-and-conquer}$
\State $\text{Recover missing boundary curve edges using topological edge swaps}$
\If{$A_{2D} = 6 \quad (\text{Frontal-Delaunay, Default})$}
\State $\text{Insert interior surface nodes along advancing fronts guided by local size } h(\mathbf{x})$
\ElsIf{$A_{2D} = 5 \quad (\text{Delaunay})$}
\State $\text{Insert interior nodes sequentially at circumcenters of elements with maximum } \alpha_K$
\ElsIf{$A_{2D} = 1 \quad (\text{MeshAdapt})$}
\State $\text{Apply local edge splits, collapses, and swaps to refine surface triangulation}$
\EndIf
\If{$\text{Dimension} = 3$}
\If{$A_{3D} = 1 \quad (\text{Delaunay})$}
\State $\text{Build 3D bounding mesh, recover surface boundaries via TetGen/BR, and insert interior volume nodes}$
\ElsIf{$A_{3D} = 10 \quad (\text{HXT})$}
\State $\text{Execute fine-grained parallel 3D Delaunay tetrahedralization across OpenMP threads}$
\ElsIf{$A_{3D} = 4 \quad (\text{Frontal})$}
\State $\text{Generate 3D tetrahedral elements using Netgen advancing-front algorithm}$
\EndIf
\EndIf
\Return $\text{Generated 2D surface or 3D volume finite element mesh}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Gmsh Reference Manual, Section 1.2.1, p. 9-10 & Section 7.4, p. 253_


## 4. Known Pitfalls

- **Misidentification of HXT Algorithm Target Element Type**: HXT is not a hexahedral generator using cube transformations; it is a fast, parallel multithreaded reimplementation of the 3D Delaunay algorithm designed specifically for tetrahedral mesh generation. _(Source: Gmsh Reference Manual, Section 1.2.1, p. 10 & Section 7.4, p. 253)_
- **Misinterpreting Default 2D Meshing Algorithm**: MeshAdapt is not the default 2D meshing algorithm in Gmsh. The default 2D algorithm is Frontal-Delaunay (Mesh.Algorithm = 6). MeshAdapt (Mesh.Algorithm = 1) is automatically triggered as a fallback if Delaunay or Frontal-Delaunay fails. _(Source: Gmsh Reference Manual, Section 1.2.1, p. 10 & Section 7.4, p. 253)_
- **Distinction Between 2D Frontal-Delaunay and 3D Frontal Algorithms**: Frontal is not a standalone 2D algorithm name in Gmsh. In 2D, the advancing-front algorithm is designated Frontal-Delaunay (Mesh.Algorithm = 6), whereas Frontal (Mesh.Algorithm3D = 4) specifically refers to Netgen's 3D advancing-front tetrahedral meshing algorithm. _(Source: Gmsh Reference Manual, Section 1.2.1, p. 9-10 & Section 7.4, p. 253)_

## References

- Gmsh Reference Manual, Version 4.11.0 (development version), Christophe Geuzaine and Jean-François Remacle, 2022.
