---
id: gmsh-python-api
title: Gmsh Python API Patterns
domain: computational-mechanics
subdomain: mesh-generation
tags:
- gmsh
- python
- scripting
- parametric
- batch
status: established
confidence: 0.9
source: hybrid
edges:
- to: gmsh-geometry-api
  type: refines
  weight: 0.7
- to: gmsh-mesh-formats
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Gmsh Python API Patterns

## Summary

The Gmsh Python Application Programming Interface (API) provides a purely functional object-oriented and C-compatible interface (`gmsh.py`) to Gmsh's internal data structures, geometry kernels, meshing algorithms, post-processing modules, and option server. Python API programs follow a structured lifecycle: initializing the session with `gmsh.initialize()`, constructing geometries in kernel namespaces (`gmsh.model.geo` or `gmsh.model.occ`), synchronizing kernel data once, setting physical groups and meshing constraints, generating meshes, exporting output files, and terminating via `gmsh.finalize()`.

## 1. Core Concept

The Gmsh Python API reflects Gmsh's internal data model by organizing functional operations under specific top-level namespaces (`gmsh.model`, `gmsh.model.mesh`, `gmsh.model.geo`, `gmsh.model.occ`, `gmsh.option`, `gmsh.view`, `gmsh.plugin`, and `gmsh.onelab`). Model entities are referenced as `(dim, tag)` integer pairs. Rather than translating CAD data into an intermediate format, Gmsh queries native CAD kernel data directly. To minimize performance overhead, script developers should batch geometric definitions and minimize synchronization calls (`gmsh.model.occ.synchronize()`), as synchronization transfers native CAD data to the primary Gmsh model registry.

## 2. Mathematical Formulation

**contiguous_coordinate_array**
$$
\mathbf{X} = (x_1, y_1, z_1, x_2, y_2, z_2, \dots, x_N, y_N, z_N)^T \in \mathbb{R}^{3N}
$$
_Source: Gmsh Reference Manual, Section 6.4, p. 140-142_

**mesh_size_callback_signature**
$$
h_{target} = f(d, T, x, y, z, h_{default})
$$
_Source: Gmsh Reference Manual, Section 6.4, p. 155-156_

**Notation:**
- {'d': 'Topological entity dimension (0 for point, 1 for curve, 2 for surface, 3 for volume)'}
- {'T': 'Strictly positive integer entity tag'}
- {'\\mathbf{X}': 'Flattened 1D array of 3D nodal coordinates (x, y, z)'}
- {'h_{default}': 'Default target element size computed by Gmsh prior to callback invocation'}
- {'h_{target}': 'Custom target element size evaluated and returned by a Python size callback'}


## 3. Algorithmic Implementation

**python_api_cad_and_mesh_workflow**
$$
\begin{algorithmic}
\State $\text{Initialize API via } \text{gmsh.initialize()}, \text{ and create model } \text{gmsh.model.add}(\text{"model\_name"})$
\State $\text{Define geometry using CAD kernel functions in } \text{gmsh.model.occ} \text{ or } \text{gmsh.model.geo}$
\State $\text{Synchronize CAD kernel data once with main model via } \text{gmsh.model.occ.synchronize()}$
\State $\text{Assign physical groups using } \text{gmsh.model.addPhysicalGroup}(d, \text{tags}, k, N)$
\State $\text{Configure meshing options and size callbacks via } \text{gmsh.option.setNumber} \text{ and } \text{gmsh.model.mesh.setSizeCallback}$
\State $\text{Generate mesh of target dimension } d \text{ using } \text{gmsh.model.mesh.generate}(d)$
\State $\text{Export finite element mesh to file via } \text{gmsh.write}(\text{"output.msh"})$
\State $\text{Finalize API session and release internal memory using } \text{gmsh.finalize()}$
\Return $\text{Exported finite element mesh file}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Gmsh Reference Manual, Section 6, p. 121-124, Section 6.3, p. 126-128, & Section 6.6, p. 177_


## 4. Known Pitfalls

- **Excessive CAD Synchronization Points**: Executing synchronize() after every individual CAD definition or transformation incurs substantial computational overhead. The manual explicitly advises minimizing synchronization calls by batching CAD entity creation and executing synchronize() once before model queries, physical group assignments, or meshing. _(Source: Gmsh Reference Manual, Section 6.6, p. 177 & Section 6.8, p. 198)_
- **Uninitialized or Unfinalized API Session State**: Invoking Gmsh API functions without first executing gmsh.initialize() causes runtime exceptions. Omitting gmsh.finalize() at script completion prevents proper cleanup of allocated memory, file handles, and internal server states. _(Source: Gmsh Reference Manual, Section 6.1, p. 122-123)_
- **Querying Unsynchronized CAD Entities Outside Kernel Namespace**: Attempting to query or manipulate newly created CAD entities using top-level functions in gmsh.model or gmsh.model.mesh prior to calling synchronize() results in missing entity errors, as CAD kernel representations remain isolated within their respective kernel namespaces until explicitly synchronized. _(Source: Gmsh Reference Manual, Section 6, p. 121-122 & Section 6.6, p. 177)_

## References

- Gmsh Reference Manual, Version 4.11.0 (development version), Christophe Geuzaine and Jean-François Remacle, 2022.
