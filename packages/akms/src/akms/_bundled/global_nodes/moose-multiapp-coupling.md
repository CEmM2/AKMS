---
id: moose-multiapp-coupling
title: MOOSE MultiApp system for multi-physics coupling
domain: architecture
subdomain: procedural
tags:
- multi-app
- transfer
- picard-iteration
- sub-cycling
- multi-physics
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-multiapp-transfers
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-multiapp-transfers
---

# MOOSE MultiApp system for multi-physics coupling

MOOSE's MultiApp system enables hierarchical coupling of multiple physics simulations, allowing a parent application to launch and control child applications, manage data transfer, and coordinate execution strategies . This system supports various coupling schemes, including loose coupling, Picard iteration, and sub-cycling, with flexible control over execution timing and parallel distribution   .

## Parent-Child App Hierarchy
A parent app launches and controls child apps by defining `MultiApp` objects in its input file . Each `MultiApp` object can represent multiple sub-applications, which are instances of `MooseApp` or derived applications . The parent app passes parameters and input files to the child apps  . The hierarchy can be arbitrarily deep, with sub-apps themselves containing `MultiApps` .

**Parameters:**
* `app_type`: `string` - The name of the `MooseApp` derived application to be executed .
* `input_files`: `string` - Specifies the input file(s) for the sub-app(s) . If one file is provided, it's used for all sub-apps in the `MultiApp` .
* `positions`: `vector<Real>` - A list of 3D coordinate vectors defining the offset of each sub-app relative to the parent app's coordinate system .
* `positions_file`: `string` - A file containing position vectors for sub-apps .
* `positions_objects`: `vector<string>` - A list of names of `Positions` objects to specify sub-app locations .
* `clone_parent_mesh`: `bool` - Allows re-using the main application mesh in the sub-app to avoid mesh creation operations .

**MOOSE Input Syntax:**
` ` `ini
[MultiApps]
  [sub_app_name]
    type = TransientMultiApp
    app_type = MyChildApp
    input_files = 'child.i'
    positions = '0 0 0'
    execute_on = 'timestep_end'
  []
[]
` ` ` 

## `TransientMultiApp` and `FullSolveMultiApp` Execution Strategies

MOOSE provides different `MultiApp` types to manage how child applications execute.

### `TransientMultiApp`
The `TransientMultiApp` is designed for sub-applications that progress in time with the main application . It requires sub-apps to use an `Executioner` derived from `Transient` . By default, the time step size for both parent and child apps is the minimum of all requested time steps . It supports sub-cycling, where child apps can take multiple smaller time steps per parent time step .

**Classes & Methods:**
* `TransientMultiApp::solveStep(Real dt, Real target_time, bool auto_advance = true)`: Solves the sub-app for a given time step `dt` up to `target_time` .
* `TransientMultiApp::incrementTStep(Real target_time)`: Advances the multi-app's time step .
* `TransientMultiApp::finishStep(bool recurse_through_multiapp_levels = false)`: Calls the sub-app's executioner's `endStep` and `postStep` methods .

**Parameters:**
* `sub_cycling`: `bool`, default: `false` - Allows the `MultiApp` to take smaller timesteps than the rest of the simulation .
* `interpolate_transfers`: `bool`, default: `false` - When `sub_cycling` is enabled, allows transferred values to be interpolated over the time frame the `MultiApp` is executing .
* `detect_steady_state`: `bool`, default: `false` - If true and sub-cycling, a steady-state check is performed for each child app, allowing them to skip to the end of the parent time step if steady conditions are detected .
* `output_sub_cycles`: `bool`, default: `false` - If true, every sub-cycle will be output .

### `FullSolveMultiApp`
The `FullSolveMultiApp` performs a complete simulation during each execution . This is often used for steady-state fixed-point iterations .

**Parameters:**
* `ignore_solve_not_converge`: `bool`, default: `false` - If true, the main app continues even if a sub-app's solve does not converge .

## Data Transfer: `MultiAppTransfer` Base Class
Transfers are used to move information between applications in the MultiApp hierarchy . The `MultiAppTransfer` is the base class for these operations. Data can be transferred to and from `AuxiliaryVariable` fields, `Postprocessor` values, and `UserObject`s .

**Classes & Methods:**
* `MultiAppTransfer`: Base class for all MultiApp transfer objects .

**Transfer Types:**
*   `MultiAppGeneralFieldShapeEvaluationTransfer`: Interpolates a field (solution or auxiliary) from one domain to another, populating an `AuxiliaryVariable` field in the receiving app . This is a more general and efficient implementation of field interpolation .
    *   **Parameters:** `from_multi_app`, `to_multi_app`, `source_variable`, `variable` .
*   `MultiAppGeneralFieldNearestLocationTransfer`: Moves field data by matching nodes/centroids .
*   `MultiAppGeneralFieldUserObjectTransfer`: Evaluates a "spatial" `UserObject` in one app at the other app's nodes/centroids and deposits the information into an `AuxiliaryVariable` field .
*   `MultiAppPostprocessorTransfer`: Moves `Postprocessor` data from one app to another .

**MOOSE Input Syntax (Example `MultiAppPostprocessorTransfer`):**
` ` `ini
[Transfers]
  [pressure_drop_transfer]
    type = MultiAppPostprocessorTransfer
    from_multi_app = subchannel
    from_postprocessor = total_pressure_drop_SC
    to_postprocessor = core_delta_p_tgt
    reduction_type = average
    execute_on = 'timestep_end'
  []
[]
` ` ` 

## Execution Timing: `execute_on`
The `execute_on` parameter, inherited from `SetupInterface`, dictates when an object, including `MultiApp`s and `Transfers`, is executed during the simulation  . This parameter controls the coupling scheme (explicit vs. implicit).

**Parameters:**
*   `execute_on`: `enum` - Controls when the `MultiApp` or `Transfer` is executed.
    *   `TIMESTEP_BEGIN`: Executed prior to the solve for each time step .
    *   `TIMESTEP_END`: Executed after the solve for each time step .
    *   `NONLINEAR`: Executed prior to each Jacobian evaluation .
    *   `MULTIAPP_FIXED_POINT_BEGIN`: Executed at the beginning of each fixed-point solve loop .
    *   `MULTIAPP_FIXED_POINT_END`: Executed at the end of each fixed-point solve loop .
    *   Other flags exist for various execution points .

**Coupling Scheme Control:**
*   **Explicit (Loose) Coupling:** If `MultiApp`s and `Transfers` are executed only once per time step (e.g., `TIMESTEP_END`), data is exchanged once, and the simulation proceeds .
*   **Implicit (Tight) Coupling / Picard Iteration:** By setting `fixed_point_max_its` in the parent app's `Executioner` block to a value greater than 1, MOOSE performs Picard iterations, where data is exchanged and physics re-solved until convergence within a time step .

## Picard Iteration
MOOSE performs fixed-point (Picard) iteration between parent and child apps to achieve tight coupling . This involves iterating back

Wiki pages you might want to explore:
- [MOOSE Framework Overview (idaholab/moose)](https://deepwiki.com/idaholab/moose#1)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
