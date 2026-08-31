---
id: moose-output-postprocessing
title: MOOSE Output System and Postprocessing
domain: architecture
subdomain: procedural
tags:
- output
- exodus
- postprocessor
- aux-variable
- checkpoint
- restart
- VTK
- CSV
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
- to: cm-verification
  type: implements
  weight: 0.5
  note: Postprocessors and AuxKernels compute verification quantities
---

# MOOSE Output System and Postprocessing

Framework knowledge node covering 1 aspect(s) of Output System and Postprocessing.

## Output system and postprocessing architecture

MOOSE's output and postprocessing system is designed to extract and present simulation data in various formats, including scalar values, tabular data, and visualization fields . This system is built upon a hierarchy of classes that manage different output types and data processing mechanisms .

## Output Types: `Exodus`, `CSV`, `VTK`, `Console`, `Checkpoint`

MOOSE provides several output types, each handled by a specific class derived from `AdvancedOutput` . These output objects can be configured in the `[Outputs]` block of the input file .

### Classes & Methods:
*   `AdvancedOutput` : Base class for advanced output functionalities, managing various output lists and execution flags .
*   `Exodus` : Outputs simulation data to ExodusII files, a common format for finite element analysis results .
*   `CSV` : Outputs data in a comma-separated value format, often used for tabular data from Postprocessors and VectorPostprocessors .
*   `VTK` : Outputs data in VTK format for visualization in tools like ParaView .
*   `Console` : Prints output directly to the console, useful for quick checks and performance logs .
*   `Checkpoint` : Saves the complete state of the simulation for restart and recovery purposes .

## `Postprocessor` - Scalar Derived Quantities

`Postprocessor` objects compute single scalar (`Real`) values from simulation data . They are used for various aggregate calculations like integrals, averages, or sampled values .

### Classes & Methods:
*   `Postprocessor` : Base class for all scalar postprocessors .
    *   `initialize()` : Called before every execution to reset accumulated quantities .
    *   `execute()` : Defines the operation performed on a per-element, side, or node basis .
    *   `getValue()` : Returns the final scalar value of the postprocessor .
*   `GeneralPostprocessor` : `execute()` is called once per execution flag .
*   `NodalPostprocessor` : `execute()` is called for each node in the mesh .
*   `ElementalPostprocessor` : `execute()` is called for each element in the mesh .
*   `SidePostprocessor` : `execute()` is called for each side on a boundary .
*   `InternalSidePostprocessor` : `execute()` is called for each internal side .

### Execution Timing:
Postprocessors can be configured to execute at varying times during a simulation using the `execute_on` parameter, such as during initialization (`INITIAL`) or at the end of each time step (`timestep_end`) . They are also automatically restored to their previous value if a timestep is rejected .

### Pattern for Adding a New Postprocessed Quantity:
1.  Create a new C++ class inheriting from an appropriate `Postprocessor` base class (e.g., `GeneralPostprocessor`, `NodalPostprocessor`) .
2.  Override the `execute()` method to perform the calculation .
3.  Override the `getValue()` method to return the computed scalar result .
4.  Implement `initialize()` and `finalize()` for parallel communication and aggregation, if necessary .
5.  Register the new `Postprocessor` in the MOOSE input system.

## `VectorPostprocessor` - Tabular Data Output

`VectorPostprocessor` (VPP) objects compute multiple related values, outputting them as one or many vectors . They are suitable for sampling solution fields along a line or tracking values over time .

### Classes & Methods:
*   `VectorPostprocessor` : Base class for postprocessors that produce a vector of values .
    *   `declareVector(const std::string & vector_name)` : Registers a new vector to be filled and output .
    *   `getVectorNames()` : Returns the names of the vectors associated with the object .
*   `VectorPostprocessorValue` : Represents a vector of real values managed by the VPP system .

### Output:
VPP data is typically output to CSV files, with separate files for each vector and timestep unless `contains_complete_history = true` is set . VPPs are required to create their complete vectors on processor zero, using `_communicator` for reduction .

## `AuxVariable` + `AuxKernel` - Visualization Fields

`AuxVariable` and `AuxKernel` are used to compute and store auxiliary fields, often for visualization purposes like von Mises stress or plastic strain . `AuxVariables` are defined in the input file and `AuxKernels` define how these variables are computed .

### Classes & Methods:
*   `AuxiliarySystem` : Manages auxiliary variables and `AuxKernel` objects .
*   `AuxKernel` : Base class for computing scalar auxiliary values .
    *   `computeValue()` : Overridden method to define the computation of the auxiliary value .
*   `VectorAuxKernel` : For computing vector auxiliary values .
*   `ArrayAuxKernel` : For computing array auxiliary values .
*   `AuxVariable` : Represents an auxiliary variable, defined in the `[AuxVariables]` block .

`AuxKernels` can be nodal or elemental, depending on the `family` of the `AuxVariable` they operate on . Nodal `AuxKernels` compute values at each node, while elemental `AuxKernels` compute values at quadrature points within each element .

## `ElementalVariableValue` vs `NodalVariableValue` - Field Type Determination

The field type (nodal or elemental) for variables is determined by the `family` parameter of the `MooseVariable` .
*   `MooseVariableFE` : Represents a finite element variable, storing solution values, gradients, and time derivatives <

Wiki pages you might want to explore:
- [Problem Solving Architecture (idaholab/moose)](https://deepwiki.com/idaholab/moose#3)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
