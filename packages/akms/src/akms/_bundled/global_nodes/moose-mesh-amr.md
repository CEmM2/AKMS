---
id: moose-mesh-amr
title: MOOSE Mesh management and adaptivity in MOOSE
domain: architecture
subdomain: procedural
tags:
- mesh-generator
- AMR
- adaptivity
- displaced-mesh
- partitioning
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-mesh-adaptivity
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-mesh-adaptivity
---

# MOOSE Mesh management and adaptivity in MOOSE

MOOSE manages meshes and mesh adaptivity through a system of `MeshGenerator` objects and an `Adaptivity` system. Mesh generation involves a pipeline of `MeshGenerator`s that can create or modify meshes, allowing for combinatorial mesh construction. Adaptive Mesh Refinement (AMR) is handled by the `Adaptivity` block, which uses various error indicators and relies on `libMesh` for refinement and coarsening operations. Parallel mesh partitioning distributes elements across processors, and named blocks, sidesets, and nodesets are used to restrict physics and boundary conditions.

## 1. Mesh Generators: `FileMeshGenerator`, `GeneratedMeshGenerator`, `MeshGeneratorMesh`

MOOSE uses a `MeshGenerator` system to construct meshes, which can involve chaining multiple generators together to build complex geometries . There are two main types of `MeshGenerator`s: those that create a mesh from scratch and those that modify an existing mesh .

### How the Generator Pipeline Works

The `MeshGenerator` pipeline works by evaluating and generating individual mesh objects in a dependency-sorted order, forming a Directed Acyclic Graph (DAG) .

**Classes & Methods:**
*   `MeshGeneratorSystem::addMeshGenerator(const std::string & type, const std::string & name, const InputParameters & params)`: Stores parameters for future construction of a `MeshGenerator` .
*   `MeshGeneratorSystem::createAddedMeshGenerators()`: Parses input parameters to build the execution tree for generators and constructs them in dependency order .
*   `MeshGenerator::generate()`: The core method overridden by child classes to create or modify the mesh .
*   `MeshGenerator::generateInternal()`: An internal method called by `MooseApp` to execute the `MeshGenerator`, handling data generation and output .

**Algorithm Steps:**
` ` `pseudocode
1. User defines MeshGenerator blocks in the input file.
2. MooseApp collects all MeshGenerator parameters.
3. MeshGeneratorSystem builds a dependency graph of MeshGenerators.
4. MeshGenerators are constructed and executed in dependency order.
5. For each MeshGenerator:
    a. If it creates a mesh (e.g., GeneratedMeshGenerator, FileMeshGenerator), it calls buildMeshBaseObject(), buildReplicatedMesh(), or buildDistributedMesh().
    b. If it modifies a mesh (e.g., TiledMeshGenerator, RefineBlockGenerator), it obtains an input mesh using getMesh() or getMeshByName().
    c. The generate() method is called to produce the output mesh.
    d. The output mesh can be used as input for subsequent MeshGenerators.
6. The final mesh is used for the simulation.
` ` `

**MOOSE Input Syntax:**
` ` `ini
[Mesh]
  [gmg]
    type = GeneratedMeshGenerator
    dim = 3
    nx = 3
    ny = 3
    nz = 3
  []

  [tmg]
    type = TiledMeshGenerator
    input = gmg # 'tmg' uses the output of 'gmg' as its input
    x_tiles = 2
    y_tiles = 1
    z_tiles = 5
  []
[]
` ` ` 

## 2. Mesh Modifiers/Generators Chaining: Combinatorial Mesh Construction

MOOSE allows for combinatorial mesh construction by chaining `MeshGenerator`s. This means the output of one generator can serve as the input for another, enabling the creation of complex meshes from simpler operations .

**Classes & Methods:**
*   `MeshGenerator::getMesh()`: Retrieves the mesh from a previous generator .
*   `MeshGenerator::getMeshByName()`: Retrieves a mesh by its name from a previous generator .
*   `CombinerGenerator`: Collects multiple meshes into a single, unconnected mesh .
*   `RefineBlockGenerator`: Refines one or more blocks within an existing mesh .

**MOOSE Input Syntax:**
An example of chaining is shown in the previous section with `GeneratedMeshGenerator` and `TiledMeshGenerator` . Another example involves combining meshes:
` ` `ini
[Mesh]
  [block_one]
    type = GeneratedMeshGenerator
    dim = 3
    nx = 4
    ny = 4
    nz = 4
    # ... other parameters ...
  []
  [block_two]
    type = GeneratedMeshGenerator
    dim = 3
    nx = 9
    ny = 9
    nz = 4
    # ... other parameters ...
  []
  [block_one_id]
    type = SubdomainIDGenerator
    input = block_one
    subdomain_id = 1
  []
  [block_two_id]
    type = SubdomainIDGenerator
    input = block_two
    subdomain_id = 2
  []
  [combine]
    type = MeshCollectionGenerator
    inputs = ' block_one_id block_two_id'
  []
[]
` ` ` 

## 3. Adaptive Mesh Refinement (AMR): `Adaptivity` block

The `Adaptivity` system in MOOSE handles Adaptive Mesh Refinement (AMR) . It allows for dynamic refinement and coarsening of the mesh based on error indicators.

**Classes & Methods:**
*   `Adaptivity`: The main class responsible for managing mesh adaptivity . It initializes and controls the adaptivity cycles .
*   `Adaptivity::setErrorEstimator(const MooseEnum & error_estimator_name)`: Sets the error estimator to be used for adaptivity .

**Parameters:**
*   `Adaptivity/initial_steps`: Number of adaptivity cycles to perform before the simulation starts .
*   `Adaptivity/steps`: Number of adaptivity cycles to run during a steady solve .
*   `Adaptivity/p_refinement`: Indicates whether the refinement will be p-refinement or h-refinement .

**Error Indicators Available:**
MOOSE leverages `libMesh` for error estimation. The `Adaptivity::setErrorEstimator` method indicates support for:
*   `Laplacian` 
*   `Kelly` (e.g., `libmesh::KellyErrorEstimator`) 
*   `PatchRecovery` (e.g., `libmesh::PatchRecoveryErrorEstimator`) 
*   `Fourth` (e.g., `libmesh::FourthErrorEstimators`) 

**MOOSE Input Syntax:**
` ` `ini
[Adaptivity]
  # ... configuration for adaptivity ...
[]
` ` ` 

## 4. How Refinement/Coarsening Works: `libMesh` Classes

MOOSE utilizes `libMesh` for the underlying mesh data structures and refinement/coarsening algorithms . The `Adaptivity` class interacts with `libMesh::MeshRefinement` to perform these operations.

**Classes & Methods:**
*   `libMesh::MeshRefinement`: A `libMesh` class that handles the actual mesh refinement and coarsening operations .
*   `libMesh::ErrorEstimator`: Base class for error estimators in `libMesh` .
*   `libMesh::SystemNorm`: Used to define the error norm for adaptivity .

## 5. Mesh Partitioning for Parallel

MOOSE supports parallel computation by partitioning the mesh across multiple processors.

**Classes & Methods:**
*   `MooseMesh::determineUseDistributedMesh()`: Determines whether to use a distributed mesh .
*   `MooseMesh::partitioning()`: Returns MOOSE Mesh partitioning options .

**Parameters:**
*   `Mesh/parallel_type = DEFAULT | REPLICATED | DISTRIBUTED`: Controls how the mesh is distributed.
    *   `DEFAULT`: Uses `libMesh::ReplicatedMesh` unless `--distributed-mesh` is specified .
    *   `REPLICATED`: Always uses `libMesh::ReplicatedMesh` .
    *   `DISTRIBUTED`: Always uses `libMesh::DistributedMesh` .
*   `Mesh/partitioner = ...`: Specifies a mesh partitioner to use when splitting the mesh for parallel computation . Available partitioners include `linear_partitioner`, `centroid_partitioner`, `parmetis_partitioner`, `hilbert_sfc_partitioner`, and `morton_sfc_partitioner` .
*   `Mesh/centroid_partitioner_direction = x | y | z | radial`: Specifies the sort direction if using the centroid partitioner .

## 6. Displaced Mesh: `use_displaced_mesh`

MOOSE handles geometric nonlinearity through the concept of a displaced mesh. This is typically managed by a `DisplacedProblem` which uses a `MooseMesh` that can be cloned and modified to represent the deformed geometry.

**Classes & Methods:**
*   `DisplacedProblem`: A specialized problem type that handles displaced meshes .
*   `MooseMesh::clone()`: Creates a copy of the mesh, which can then be displaced .
*   `MooseMesh::safeClone()`: A safer version of `clone()` that returns a `std::unique_ptr` .

## 7. Named Blocks (Subdomains), Sidesets, Nodesets

Named blocks (subdomains), sidesets, and nodesets are crucial for defining regions where specific kernels, boundary conditions (BCs), and materials apply.

**Classes & Methods:**
*   `MooseMesh`: Stores the underlying `libMesh` mesh, which contains information about subdomains, sidesets, and nodesets .
*   `MooseMesh::construct_node_list_from_side_list`: A parameter that controls whether nodesets are automatically constructed from sidesets .
*   `MooseMesh::displace_node_list_by_side_list`: Controls renumbering of existing nodesets when constructing nodesets from sidesets .

**Usage for Restricting Kernels/BCs:**
*   **Subdomains (Blocks):** Elements are grouped into subdomains, allowing kernels, materials, and initial conditions to be applied only to specific regions of the mesh .
*   **Sidesets:** Collections of $dim-1$ dimensional elements (faces in 3D, edges in 2D) typically on boundaries. These are used to apply boundary conditions or other boundary-related objects .
*   **Nodesets:** Collections of nodes, typically on a boundary

Wiki pages you might want to explore:
- [MOOSE Framework Overview (idaholab/moose)](https://deepwiki.com/idaholab/moose#1)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
