---
id: moose-action-auto-creation
title: MOOSE MOOSE Action system and automatic object creation
domain: architecture
subdomain: procedural
tags:
- action
- tensor-mechanics-action
- action-warehouse
- syntax-association
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

# MOOSE MOOSE Action system and automatic object creation

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

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
