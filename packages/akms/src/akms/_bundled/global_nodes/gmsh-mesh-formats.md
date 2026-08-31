---
id: gmsh-mesh-formats
title: Gmsh Mesh Export Formats
domain: computational-mechanics
subdomain: mesh-generation
tags:
- gmsh
- formats
- msh
- vtk
- abaqus-inp
- xdmf
status: established
confidence: 0.9
source: hybrid
edges:
- to: gmsh-physical-groups
  type: requires
  weight: 1.0
- to: gmsh-python-api
  type: requires
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Gmsh Mesh Export Formats

## Summary

Gmsh provides native export capabilities for finite element meshes across a broad spectrum of standard file formats, including MSH (versions 2.2, 4.0, and 4.1 in ASCII or binary), UNV, VTK, Abaqus INP, CGNS, MED, STL, BDF, PLY2, and SU2. Export formats can be selected automatically based on file extension, specified explicitly via the -format command-line switch or Mesh.Format option, or invoked programmatically using the API command gmsh.write().

## 1. Core Concept

Mesh export in Gmsh translates generated 1D, 2D, and 3D conformal meshes into structured or unstructured solver-ready file formats. Export operations do not rely on external conversion tools or third-party libraries. By default, when physical groups are defined, Gmsh filters output files to export only elements assigned to at least one physical group. Setting Mesh.SaveAll=1 overrides this filter to save all elements regardless of physical group assignment.

## 2. Mathematical Formulation

**physical_group_element_filtering**
$$
E_{saved} = \begin{cases} \{ e \in E \mid \exists P \in \mathcal{P}, e \in P \}, & \text{if } \text{Mesh.SaveAll} = 0 \\ E, & \text{if } \text{Mesh.SaveAll} = 1 \end{cases}
$$
_Source: Gmsh Reference Manual, Section 1.2.3, p. 11-12 & Section 7.4, p. 267_

**msh_header_specification**
$$
\text{MeshFormat} = (V, F, S), \quad V \in \{2.2, 4.0, 4.1\}, \quad F \in \{0, 1\}, \quad S = \text{sizeof(double)}
$$
_Source: Gmsh Reference Manual, Section 10.1, p. 343-344_

**Notation:**
- {'E': 'Set of all generated finite element mesh entities'}
- {'\\mathcal{P}': 'Collection of user-defined physical groups'}
- {'E_{saved}': 'Set of mesh elements written to the output file'}
- {'V': 'MSH format version number (2.2, 4.0, or 4.1)'}
- {'F': 'File mode indicator (0 for ASCII, 1 for binary)'}
- {'S': 'Floating-point data size in bytes'}


## 3. Algorithmic Implementation

**mesh_export_workflow**
$$
\begin{algorithmic}
\State $\text{Input generated mesh } E, \text{ physical groups } \mathcal{P}, \text{ target filename } \text{fn}, \text{ and format directive } \text{fmt}$
\If{$\text{fmt} = \text{"auto"}$}
\State $\text{Deduce target file format from the filename extension of } \text{fn} \text{ (e.g., } .msh, .unv, .vtk, .inp, .cgns, .med, .stl, .bdf\text{)}$
\Else
\EndIf
\If{$\text{Mesh.SaveAll} = 0 \text{ and } |\mathcal{P}| > 0$}
\State $\text{Filter mesh to } E_{saved} = \{ e \in E \mid \exists P \in \mathcal{P}, e \in P \}$
\Else
\EndIf
\State $\text{Write nodes, elements, and entity topology to } \text{fn} \text{ via API call } \text{gmsh.write(fn)} \text{ or script command } \text{Save } \text{fn}$
\Return $\text{Exported mesh file } \text{fn}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Gmsh Reference Manual, Section 1.2.3, p. 11-12, Section 4, p. 83, & Section 6.1, p. 124_


## 4. Known Pitfalls

- **Element Omission Due to Physical Group Filtering**: When physical groups are defined in a Gmsh model, mesh export functions (such as Save or gmsh.write) default to exporting only elements assigned to at least one physical group. Elements not assigned to any physical group are omitted from output unless Mesh.SaveAll=1 or command-line option -save_all is set. _(Source: Gmsh Reference Manual, Section 1.2.3, p. 11-12 & Section 7.4, p. 267)_
- **MSH Version Mismatch with Legacy Solvers**: Gmsh exports meshes in MSH 4.1 format by default. Legacy external solvers expecting MSH 2.2 syntax will fail to parse MSH 4 files unless Mesh.MshFileVersion = 2.2 is set in scripts/API or -format msh2 is specified on the command line. _(Source: Gmsh Reference Manual, Section 2.1, p. 17-18, Section 7.4, p. 261, & Section C.5, p. 377)_
- **Unsupported File Extensions**: Gmsh exports directly to native supported formats (such as MSH, UNV, VTK, INP, CGNS, MED, STL, BDF, SU2). Attempting to export to unsupported formats like XDMF (.xmf/.h5) natively in Gmsh will cause export failures, as third-party conversion packages like meshio are not integrated into Gmsh. _(Source: Gmsh Reference Manual, Section 4, p. 83 & Section 7.4, p. 255)_

## References

- Gmsh Reference Manual, Version 4.11.0 (development version), Christophe Geuzaine and Jean-François Remacle, 2022.
