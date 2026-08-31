---
id: moose-input-file-anatomy
title: MOOSE Input file structure and block composition
domain: architecture
subdomain: procedural
tags:
- input-file
- block-structure
- global-params
- parser
- type-system
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-action-system
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-action-system
---

# MOOSE Input file structure and block composition

The MOOSE input file uses a hierarchical block structure to define a simulation, with top-level blocks like `[Mesh]`, `[Variables]`, `[Kernels]`, `[BCs]`, `[Materials]`, `[Executioner]`, and `[Outputs]` each responsible for specific aspects of the simulation setup . The input file is parsed into an Action/object hierarchy, where the `Parser` creates an abstract syntax tree, the `Builder` creates `Action` objects, and the `ActionWarehouse` executes these `Action`s to construct MOOSE objects via the `Factory` .

## Top-Level Blocks and Their Responsibilities

MOOSE input files are structured into blocks, with capital-letter blocks representing system-defined syntax . The essential top-level blocks are:

*   **`[Mesh]`**: Defines the geometry of the computational domain, often using mesh generator objects like `GeneratedMesh`  .
*   **`[Variables]`**: Declares the unknown field variables that the simulation will solve for  .
*   **`[Kernels]`**: Specifies the partial differential equations (PDEs) to be solved by adding `Kernel` objects, which represent the volumetric terms of the weak form  .
*   **`[BCs]`**: Defines the boundary conditions for the problem, such as Dirichlet or Neumann conditions, applied to specific boundaries of the mesh  .
*   **`[Materials]`**: Used to define material properties, which can be constant or depend on other variables .
*   **`[Executioner]`**: Controls how the simulation progresses, including time-stepping schemes for transient problems or solver settings for steady-state problems  .
*   **`[Outputs]`**: Specifies how the simulation results are written, including format (e.g., ExodusII, CSV) and frequency  .

## Sub-blocks and the Type System

Within top-level blocks, sub-blocks are used to define individual MOOSE objects . The `type = DirichletBC` syntax inside a `[BCs]` block invokes the factory system . The `Factory` is responsible for creating physics objects (Kernels, BCs, Materials, etc.) based on the `type` parameter specified in the input file . When `type = DirichletBC` is encountered, the `Factory` looks up the registered `DirichletBC` class and instantiates an object of that type, passing the parameters defined within its sub-block .

## Block-Level Parameters vs. Object-Level Parameters

Parameters can be defined at different levels within the input file hierarchy.
*   **Block-level parameters** apply to the entire block. For example, `active` and `inactive` lists can be defined at the block level to control which sub-blocks are processed .
*   **Object-level parameters** are specific to a particular MOOSE object defined within a sub-block. These parameters configure the behavior of that individual object, such as `variable` or `boundary` for a `DirichletBC` object .

## `active`/`inactive` Lists for Toggling Objects

The `active` and `inactive` parameters allow for selective processing of sub-blocks within an input file .
*   `active`: If specified, only the sub-blocks named in this list will be visited and made active .
*   `inactive`: If specified, sub-blocks matching these identifiers will be skipped .
These parameters are processed by the `Builder` during input file parsing .

## The `[GlobalParams]` Block

The `[GlobalParams]` block is used to define parameters that can be propagated to all objects in the simulation . While not explicitly detailed in the provided snippets, the `GlobalParamsAction` is involved in handling these parameters . This mechanism allows for setting common parameters once and having them applied universally, simplifying input files for complex simulations.

## Include Files and Input File Inheritance

MOOSE supports including other input files using the `!include` syntax . This allows for modular input files and can be used in any nested context . Functionally, including a file is equivalent to inserting its text at the `!include` location . Parameters from included files do not override parent parameters by default, and explicit override syntax (`:=` or `:override=`) is needed to change previously defined values  .

## Input File Parsing into Action/Object Hierarchy

The input file parsing process involves several key components:
1.  **Parser**: The `Parser` class uses the HIT (Hierarchical Input Text) parser to read the input file and create an abstract syntax tree (AST) . The `MooseApp` orchestrates this by calling `Parser::parse()` .
2.  **Builder**: The `Builder` class then walks this AST and creates `Action` objects . The `MooseApp` calls `Builder::build()` .
3.  **ActionWarehouse**: The created `Action` objects are stored in the `ActionWarehouse` . The `ActionWarehouse` manages and executes these `Action`s in dependency order .
4.  **Factory**: As `Action`s are executed, they interact with the `Factory` to dynamically create MOOSE objects (e.g., Kernels, BCs, Materials) based on the `type` parameter specified in the input file .

This pipeline transforms the declarative input file into a fully configured simulation object hierarchy within the `MooseApp` .

## Relationships

` ` `mermaid
graph LR
    InputFile["Input File<br/>(.i file)"]
    Parser["Parser"]
    HitTree["hit::Node<br/>(AST)"]
    Builder["Builder"]
    Actions["Action Objects"]
    ActionWarehouse["ActionWarehouse"]
    Factory["Factory"]
    MooseObjects["MOOSE Objects<br/>(Kernels, BCs, etc.)"]
    
    InputFile --> Parser
    Parser --> HitTree
    HitTree --> Builder
    Builder --> Actions
    Actions --> ActionWarehouse
    ActionWarehouse --> |"executeActions"| Factory
    Factory --> MooseObjects
` ` `


## Complete Minimal Input File for a Mechanics Problem

Here is a minimal MOOSE input file for a mechanics problem, annotated with the purpose of each block. This example sets up a simple diffusion problem, which is analogous to a basic mechanics problem in terms of input file structure.

` ` `ini
# This is a minimal MOOSE input file for a mechanics-like problem (diffusion)

[Mesh] # Defines the geometry of the simulation domain.
  type = GeneratedMesh # Uses a built-in mesh generator.
  dim = 2 # Specifies a 2-dimensional mesh.
  nx = 10 # Number of elements in the x-direction.
  ny = 10 # Number of elements in the y-direction.
[]

[Variables] # Declares the primary unknown variables to be solved.
  [u] # Defines a variable named 'u'.
    family = LAGRANGE # Uses Lagrange finite elements.
    order = FIRST # Specifies first-order interpolation.
  []
[]

[Kernels] # Defines the terms of the partial differential equations.
  [diff] # A sub-block for a specific kernel.
    type = Diffusion # Specifies the Diffusion kernel, representing -∇²u.
    variable = u # Applies this kernel to the variable 'u'.
  []
[]

[BCs] # Defines the boundary conditions for the problem.
  [left_bc] # A sub-block for a boundary condition on the 'left' boundary.
    type = DirichletBC # Specifies a Dirichlet boundary condition (fixed value).
    variable = u # Applies to variable 'u'.
    boundary = left # Applies to the boundary named 'left'.
    value = 1.0 # Sets the value of 'u' to 1.0 on the 'left' boundary.
  []
  [right_bc] # A sub-block for a boundary condition on the 'right' boundary.
    type = DirichletBC
    variable = u
    boundary = right
    value = 0.0
  []
[]

[Executioner] # Controls the simulation process (e.g., steady-state, transient).
  type = Steady # Specifies a steady-state solver.
  solve_type = NEWTON # Uses Newton's method for solving the nonlinear system.
[]

[Outputs] # Specifies how and what results are saved.
  exodus = true # Enables output in ExodusII format.
[]
` ` `







## Notes

The provided context primarily focuses on the core MOOSE framework and its input file processing. While the prompt asks for a mechanics problem, the fundamental structure of the input file and the roles of the top-level blocks remain consistent across different physics applications. The example provided uses a diffusion problem as it directly relates to the available snippets illustrating basic input file structure. The `[GlobalParams]` block is mentioned in the `Builder.C` file as `GlobalParamsAction` , indicating its role in parameter propagation,

Wiki pages you might want to explore:
- [Core Application Architecture (idaholab/moose)](https://deepwiki.com/idaholab/moose#2)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
