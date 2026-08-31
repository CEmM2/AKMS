---
id: moose-action-system
title: MOOSE Action System — Input File to Object Graph
domain: architecture
subdomain: procedural
tags:
- action
- input-file
- tensor-mechanics-action
- object-composition
- global-params
- syntax-tree
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: medium
reading_priority: full
akms_schema: v2
edges:
- to: moose-object-factory
  type: requires
  weight: 0.6
  note: Uses MOOSE object factory and registration pattern
- to: moose-object-factory
  type: requires
  weight: 0.9
  note: Actions create objects via factory
- to: tgs-dom-fem
  type: implements
  weight: 0.5
  note: Actions auto-generate FEM kernels and strain/stress objects
---

# MOOSE Action System — Input File to Object Graph

Framework knowledge node covering 2 aspect(s) of Action System — Input File to Object Graph.

## MOOSE Action system and automatic object creation

MOOSE's Action system is a core component that translates high-level input file blocks into the low-level objects required for a simulation . This system uses `Action` classes to orchestrate the creation and configuration of various MOOSE objects like `Kernels`, `Variables`, and `Materials` based on user input . The `ActionWarehouse` manages the ordering and execution of these `Action`s, ensuring proper setup of the simulation .

## 1. What is an `Action`? How does it differ from the objects it creates?

An `Action` is a C++ class that performs setup tasks, often involving the creation of MOOSE objects  . It differs from the objects it creates in that an `Action` is a temporary construct used during the input file parsing and setup phase, whereas the objects it creates (e.g., `Kernels`, `Variables`, `Materials`) are the actual components that constitute the simulation problem and persist throughout the simulation's lifetime .

The base class for all actions is `Action` . A specialized type, `MooseObjectAction`, is used when the action's primary purpose is to create other MOOSE objects from an input file  . The `act()` method is the core of an `Action`, where the logic for creating objects or performing other setup tasks is implemented .

## 2. `TensorMechanics/Master` action (now `Physics/SolidMechanics/QuasiStatic`): what objects does it auto-generate?

The `Physics/SolidMechanics/QuasiStatic` action (formerly `TensorMechanics/Master`) is a high-level action that auto-generates a suite of low-level MOOSE objects to set up a quasi-static solid mechanics problem .

This action can generate:
*   **Stress Divergence Kernels**: For calculating stress divergence equilibrium, with options for `StressDivergenceTensors`, `WeakPlaneStress`, `StressDivergenceRZTensors`, or `StressDivergenceRSphericalTensors` in the old kernel system . For the new Lagrangian kernel system, it generates `TotalLagrangianStressDivergence` or `UpdatedLagrangianStressDivergence` .
*   **Displacement Variables**: Adds `Variables` for displacement fields  .
*   **Strain Calculators**: Depending on the `strain` parameter, it can add `ComputeFiniteStrain`, `ComputePlaneFiniteStrain`, `ComputeAxisymmetric1DFiniteStrain`, `ComputeAxisymmetricRZFiniteStrain`, `ComputeSmallStrain`, `ComputePlaneSmallStrain`, `ComputeAxisymmetric1DSmallStrain`, `ComputeAxisymmetricRZSmallStrain`, `ComputeIncrementalStrain`, `ComputePlaneIncrementalStrain`, `ComputeAxisymmetric1DIncrementalStrain`, or `ComputeAxisymmetricRZIncrementalStrain` . For the new Lagrangian system, it uses `ComputeLagrangianStrain` .
*   **AuxVariables and AuxKernels**: For outputting various tensor components and quantities, such as `RankTwoAux`, `RankTwoScalarAux`, or `RankFourAux`  .
*   **Material Properties**: Adds material properties for tensor component and quantity outputs  .
*   **Global Strain Contribution**: Can couple the `GlobalStrain` system .
*   **Homogenization Constraints**: For the new kernel system, it can add objects required to impose homogenization constraints .

The `QuasiStaticSolidMechanicsPhysics::act()` method contains the logic for creating these objects based on the current task  .

## 3. How does an Action read parameters from the input file and create multiple objects behind the scenes?

An `Action` reads parameters from the input file through its `InputParameters` object, which is populated during the parsing phase . The `MooseApp`'s `Parser` creates an abstract syntax tree from the input file, and the `Builder` then walks this tree to create `Action` objects, populating their `InputParameters` .

To create multiple objects, an `Action`'s `act()` method uses the `_factory` (an instance of `Factory`) to get valid parameters for the objects it intends to create, and then calls methods on the `_problem` (an instance of `FEProblemBase`) or `_action_factory` to add these objects to the simulation .

For example, in `QuasiStaticSolidMechanicsPhysics::act()`, when the `_current_task` is "add_variable", it retrieves valid parameters for a `MooseVariable` using `_factory.getValidParams("MooseVariable")` and then adds the variable to the problem using `_problem->addVariable("MooseVariable", disp, params)` .

## 4. The Action warehouse: how are Actions ordered and executed?

The `ActionWarehouse` is responsible for storing, ordering, and executing `Action` instances .

**Ordering:**
Actions are ordered based on tasks and their registered dependencies . The `Syntax` class manages these tasks and their dependencies . The `ActionWarehouse::build()` method sorts the tasks using `_syntax.getSortedTask()` and then builds actions for each task .

**Execution:**
The `MooseApp::run()` method orchestrates the execution flow, which includes `ActionWarehouse::executeAllActions()` . During execution, `Actions` can dynamically add other `Actions` to the warehouse (meta-Actions), which will then be executed if their associated task has not already passed  .

The execution order can be debugged using the `show_actions` and `show_action_dependencies` parameters in the `[Debug]` block of the input file  .

## 5. Syntax association: how does `[Modules/TensorMechanics/Master]` in the input file map to the `TensorMechanicsAction` class?

The mapping from input file syntax like `[Modules/TensorMechanics/Master]` to a specific `Action` class (e.g., `QuasiStaticSolidMechanicsPhysics` which replaced `TensorMechanicsAction`) is handled by the `Syntax` system and `ActionFactory`  .

1.  **Registration**: `Action` classes are registered with the `ActionFactory` and `Syntax` system. This involves associating an `Action` class with one or more tasks and defining the input file syntax that triggers its creation  . For example, `registerSyntax("SetupMeshCompleteAction", "Mesh")` associates the `SetupMeshCompleteAction` with the `Mesh` block in the input file .
2.  **Parsing**: The `Parser` reads the input file and creates an abstract syntax tree (`hit::Node` tree) .
3.  **Building Actions**: The `Builder` walks this syntax tree. When it encounters a block that matches a registered syntax, it instructs the `ActionFactory` to create an instance of the associated `Action` class  . The `ActionFactory::create()` method is responsible for instantiating the `Action` and populating its `InputParameters` .

For the specific case of `[Modules/TensorMechanics/Master]`, it was deprecated and replaced by `[Physics/SolidMechanics/QuasiStatic]` . The `SolidMechanicsApp::registerAll` method includes calls to `registerDeprecatedSyntax` to handle the old syntax and map it to the new `QuasiStaticSolidMechanicsPhysics` action .

## 6. Custom Actions: how to write a new Action that auto-generates a set of objects?

To write a new `Action` that auto-generates a set of objects, you need to:

1.  **Derive from `Action` or `MooseObjectAction`**: If your action will create MOOSE objects from input file syntax, derive from `MooseObjectAction`. Otherwise, derive from `Action` .
    ` ` `cpp
    #include "MooseObjectAction.h" // Or "Action.h"

    class MyCustomAction : public MooseObjectAction
    {
    public:
      static InputParameters validParams();
      MyCustomAction(const InputParameters & params);
      virtual void act() override;
    };
    ` ` `
2.  **Define `validParams()`**: Implement a static `validParams()` method to register the parameters your `Action` will accept from the input file .
    ` ` `cpp
    InputParameters
    MyCustomAction::validParams()
    {
      InputParameters params = MooseObjectAction::validParams();
      params.addRequiredParam<std::string>("my_object_name", "Name for the object to be created.");
      params.addParam<Real>("some_value", 1.0, "A value for the object.");
      return params;
    }
    ` ` `
3.  **Implement the Constructor**: The constructor will receive the `InputParameters` for your action .
    ` ` `cpp
    MyCustomAction::MyCustomAction(const InputParameters & params)
      : MooseObjectAction(params)
    {
    }
    ` ` `
4.  **Implement `act()`**: This is where you define the logic for creating objects. You will typically use `_factory.getValidParams()` to get default parameters for the objects you want to create, modify them with values from your action's parameters, and then use methods like `_problem->addVariable()`, `_problem->addKernel()`, etc., to add the objects to the simulation

Wiki pages you might want to explore:
- [Core Application Architecture (idaholab/moose)](https://deepwiki.com/idaholab/moose#2)


## Input file structure and block composition

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
