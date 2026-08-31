---
id: moose-nucleation-grain-growth
title: MOOSE Phase Field Nucleation and Grain Growth
domain: phase-field
subdomain: algorithmic
tags:
- nucleation
- grain-growth
- coarsening
- discrete-nucleation
- langevin-noise
- grain-tracker
- zener-pinning
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: medium
reading_priority: full
akms_schema: v2
edges:
- to: moose-derivative-parsed-material
  type: requires
  weight: 0.6
  note: Uses DerivativeParsedMaterial for free energy definitions
- to: moose-allen-cahn-cahn-hilliard
  type: requires
  weight: 0.7
  note: Grain growth uses Allen-Cahn evolution
- to: moose-multi-phase-component
  type: requires
  weight: 0.6
  note: Grain growth uses multi-order-parameter framework
- to: cm-phase-field-fracture
  type: implements
  weight: 0.3
  note: Nucleation and grain evolution use phase field order parameter framework
---

# MOOSE Phase Field Nucleation and Grain Growth

Framework knowledge node covering 2 aspect(s) of Phase Field Nucleation and Grain Growth.

## Nucleation models in MOOSE phase field

MOOSE handles phase field nucleation primarily through the `DiscreteNucleation` system, which artificially triggers and stabilizes nuclei formation by modifying the free energy density or directly changing an order parameter . This system involves several components, including `DiscreteNucleationInserter` for managing nucleation sites, `DiscreteNucleationMap` for creating a smooth density map of nuclei, and `DiscreteNucleation` material for applying free energy penalties .

## Classes & Methods

*   `DiscreteNucleationInserter::validParams()`: Defines the valid input parameters for the `DiscreteNucleationInserter` class .
*   `DiscreteNucleationInserter::initialize()`: Clears insertion and deletion counters and expires old nuclei from the local list .
*   `DiscreteNucleationInserter::execute()`: Checks each quadrature point for potential nucleation based on a probability density and adds new nuclei .
*   `DiscreteNucleationInserter::addNucleus()`: Adds a new nucleus to the local list with its time, center, and radius .
*   `DiscreteNucleationMap::validParams()`: Defines the valid input parameters for the `DiscreteNucleationMap` class .
*   `DiscreteNucleationMap::execute()`: Rebuilds the spatial map of nucleation sites if required, calculating the distance to the closest nucleus and applying a smooth interface function .
*   `DiscreteNucleation::validParams()`: Defines the valid input parameters for the `DiscreteNucleation` material .
*   `DiscreteNucleation::computeProperties()`: Calculates the free energy penalty based on the difference between coupled variables and their target concentrations, modified by the nucleus mask from `DiscreteNucleationMap` .
*   `DiscreteNucleationData::getValue()`: Returns diagnostic data such as the number of active nuclei, update status, total nucleation rate, or insertion/deletion counts .
*   `DiscreteNucleationTimeStep::getValue()`: Provides a time step limit to control the probability of multiple nucleation events within a single time step .

## Nucleation Algorithm

### 1. Discrete Nucleation System Overview
The `DiscreteNucleation` system in MOOSE allows for the incorporation of nucleation phenomena in phase field simulations . It addresses the lack of intrinsic nucleation due to thermal fluctuations in phase field methods by artificially triggering and stabilizing nuclei .

### 2. Nucleation Site Insertion
Nucleation sites are inserted into the phase field using the `DiscreteNucleationInserter` user object . This object manages a global list of active nucleus positions, their insertion times, centers, and radii . During each `execute()` call, it iterates through quadrature points, calculates a nucleation rate based on a material property, and uses a random number to determine if a nucleus should be added .

` ` `cpp
// From DiscreteNucleationInserter::execute()
for (unsigned int qp = 0; qp < _qrule->n_points(); ++qp)
{
  const Real rate = _probability[qp] * _JxW[qp] * _coord[qp]; // Calculate nucleation rate
  _nucleation_rate += rate;

  const Real random = getRandomReal();

  if (!_time_dep_stats) // Time-independent statistics
  {
    if (random < rate)
      addNucleus(qp);
  }
  else // Time-dependent statistics
  {
    if (random < rate * _fe_problem.dt() && random < (1.0 - std::exp(-rate * _fe_problem.dt())))
      addNucleus(qp);
  }
}
` ` `


The `addNucleus` method then creates a `NucleusLocation` object with the current time plus a `hold_time`, the quadrature point's coordinates as the center, and a local radius .

### 3. Classical Nucleation Theory (CNT) Integration: Rate-Based Nucleation
The `DiscreteNucleationInserter` integrates classical nucleation theory by using a `probability` material property, which represents the probability density for inserting a discrete nucleus . This `probability` can be a rate density for time-dependent statistics or a probability density for time-independent statistics . The total nucleation rate is integrated over the domain .

### 4. Nucleation Seed Representation: Order Parameter Forcing and Smooth Insertion
Nucleation seeds are represented in two main ways:

*   **Free energy penalty based nucleation**: This approach modifies the local free energy density to make the nucleated state a lower energy state, driving solute diffusion or changing a non-conserved order parameter . The `DiscreteNucleation` material implements a harmonic form of this penalty . It calculates a penalty based on the difference between coupled variables (`op_names`) and their `op_values` (target concentrations), scaled by a `penalty` factor and a nucleus mask from `DiscreteNucleationMap` .

    ` ` `cpp
    // From DiscreteNucleation::computeProperties()
    const std::vector<Real> & nucleus = _map.nuclei(_current_elem); // Nucleus mask
    for (_qp = 0; _qp < _qrule->n_points(); ++_qp)
    {
      // ...
      const Real penalty = _penalty * nucleus[_qp]; // Modify penalty with nucleus mask
      Real dc = (*_args[ii])[_qp] - _op_values[i]; // Deviation from target concentration
      // ...
      if (_prop_F)
        (*_prop_F)[_qp] += dc * dc * penalty; // Build free energy correction
      // ...
    }
    ` ` `
    

*   **Direct order parameter modification**: For non-conserved order parameters, such as in polycrystalline models with `GrainTracker`, direct modification can be used . This involves applying a `DiscreteNucleationForce` and a `Reaction` kernel to a reserved order parameter .

The `DiscreteNucleationMap` user object creates a smooth density map for nuclei locations . It calculates a `value` for each quadrature point based on its distance `r` to the closest nucleus and a specified `int_width` (interface width) . This allows for smooth insertion of nuclei.

` ` `cpp
// From DiscreteNucleationMap::execute()
Real value = 0.0;
if (r <= local_radius - _int_width / 2.0) // Inside circle
{
  active_nuclei++;
  value = 1.0;
}
else if (r < local_radius + _int_width / 2.0) // Smooth interface
{
  Real int_pos = (r - local_radius + _int_width / 2.0) / _int_width;
  active_nuclei++;
  value = (1.0 + std::cos(int_pos * libMesh::pi)) / 2.0;
}
` ` `


### 5. Langevin Noise
The provided context mentions `LangevinNoise` as a separate mechanism for fluctuation-based nucleation  . However, the `DiscreteNucleation` system itself introduces nucleation artificially and does not intrinsically rely on thermal fluctuations or `LangevinNoise` .

### 6. Nucleation in Multi-Component Systems: Composition-Dependent Nucleation Barriers
The `DiscreteNucleation` material allows for coupling to multiple variables (`op_names`) and setting target values (`op_values`) for these variables . This enables the definition of composition-dependent nucleation barriers by specifying target concentrations for different components. The free energy penalty is then calculated based on the deviation from these target concentrations .

### 7. Conservation Issues
The `DiscreteNucleation` system, particularly the free energy penalty approach, "eschews directly modifying conserved concentration and non-conserved order parameter fields" . Instead, it biases the thermodynamics to drive the formation of nuclei . For conserved order parameters, a `DerivativeSumMaterial` is used to add the nucleation free energy penalty to the physical free energy contributions, which are then utilized by a Cahn-Hilliard kernel . This suggests that mass conservation is handled by integrating the nucleation penalty into the existing conservation equations (e.g., Cahn-Hilliard).

## Relationships

` ` `mermaid
classDiagram
    class DiscreteNucleationInserter {
        +addNucleus()
        -_probability
        -_hold_time
        -_local_nucleus_list
        -_nucleation_rate
        -_local_radius
        -_time_dep_stats
    }

    class DiscreteNucleationMap {
        +nuclei()
        -_inserter
        -_nucleus_list
        -_int_width
        -_nucleus_map
    }

    class DiscreteNucleation {
        +computeProperties()
        -_nvar
        -_op_index
        -_op_values
        -_penalty
        -_penalty_mode
        -_map
    }

    class DiscreteNucleationData {
        +getValue()
        -_inserter
        -_nucleus_list
        -_value_type
    }

    class DiscreteNucleationTimeStep {
        +getValue()
        -_inserter
        -_dt_nucleation
        -_changes_made
        -_rate
        -_max_lambda
    }

    DiscreteNucleationInserterBase <|-- DiscreteNucleationInserter
    ElementUserObject <|-- DiscreteNucleationMap
    DerivativeFunctionMaterialBase <|-- DiscreteNucleation
    GeneralPostprocessor <|-- DiscreteNucleationData
    GeneralPostprocessor <|-- DiscreteNucleationTimeStep

    DiscreteNucleationMap --> DiscreteNucleationInserter : uses _inserter
    DiscreteNucleation --> DiscreteNucleationMap : uses _map
    DiscreteNucleationData --> DiscreteNucleationInserterBase : uses _inserter
    DiscreteNucleationTimeStep --> DiscreteNucleationInserterBase : uses _inserter
` ` `

## Parameters

### `DiscreteNucleationInserter`
*   `probability` (MaterialPropertyName, required): Probability density for inserting a discrete nucleus .
*   `hold_time` (Real, required): Duration of time each nucleus is kept active after insertion .
*   `radius` (MaterialPropertyName, default: "r_crit"): Variable radius material property name, or a constant value .
*   `time


## Grain growth and coarsening

MOOSE simulates grain growth and Ostwald ripening primarily through the phase-field method, utilizing a multi-order-parameter approach based on the Fan-Chen model. The `GrainTracker` object plays a crucial role in managing the order parameters, allowing the simulation to track more grains than the number of order parameters by remapping them as needed. Anisotropic grain boundary properties and various driving forces can be incorporated into the model.

## Multi-order-parameter grain growth: the Fan-Chen or similar model

MOOSE implements a multiphase grain growth model based on the work of Chen and Yang, and Moelans et al. . This model uses a system of Allen-Cahn equations to describe grain boundary migration . The evolution of each grain's order parameter ($\eta_i$) is governed by the equation:
$$
\frac{\partial \eta_i}{\partial t} = - L \frac{\delta F}{\delta \eta_i} \quad (1)
$$ 
where $F$ is the free energy functional and $L$ is the order parameter mobility . The free energy functional includes a local free energy density ($f_{loc}$), additional energy density sources ($f_{add}$), and a gradient term:
$$
F = \int_V f_{loc}(\eta_0, \eta_1, \ldots, \eta_N) + f_{add} (\eta_0, \eta_1, \ldots, \eta_N) + \kappa \sum^N_i |\nabla \eta_i|^2 \quad (2)
$$ 
For grain growth, the local free energy density is defined as:
$$
f_{loc} = \mu \left( \sum_i^N \left(\frac{\eta_i^4}{4} - \frac{\eta_i^2}{2} \right)  + \gamma \sum_{i=1}^N \sum_{j>i}^N \eta_i^2 \eta_j^2 + \frac{1}{4} \right) \quad (3)
$$ 
Here, $N$ is the total number of order parameters, $\mu$ is the free energy weight, and $\gamma=1.5$ for symmetric interfacial profiles .

The model parameters $L$, $\mu$, and $\kappa$ are related to the grain boundary energy ($\sigma$), diffuse grain boundary width ($w_{GB}$), and grain boundary mobility ($M_{GB}$) .

The number of order parameters typically corresponds to the number of grains being simulated. However, the `GrainTracker` allows for simulating more grains than order parameters.

## `GrainTracker` — how does it remap order parameters to track more grains than order parameters?

The `GrainTracker` is a `Postprocessor` that enables the simulation of polycrystal grain growth with a number of grains exceeding the number of order parameters . It achieves this by remapping order parameters to different grains as needed to prevent unphysical grain coalescence when grains represented by the same variable come into contact .

### Classes & Methods:
*   `GrainTracker::GrainTracker(const InputParameters & parameters)`: Constructor for the `GrainTracker` class .
*   `GrainTracker::validParams()`: Defines the input parameters for the `GrainTracker` object .
*   `GrainTracker::initialize()`: Initializes the `GrainTracker` object .
*   `GrainTracker::execute()`: Performs the grain tracking and remapping logic .
*   `GrainTracker::finalize()`: Finalizes the `GrainTracker` object .
*   `GrainTracker::assignGrains()`: Assigns a unique ID to each `FeatureData` object (grain) during the initial tracking phase .
*   `GrainTracker::trackGrains()`: Compares incoming `FeatureData` objects with previous time step information to track grains over time .
*   `GrainTracker::remapGrains()`: Remaps grains that are too close to each other to different order parameters .
*   `GrainTracker::attemptGrainRenumber(FeatureData & grain, unsigned int depth, unsigned int max_depth)`: A recursive function that attempts to remap a grain to a new index .
*   `GrainTracker::swapSolutionValues(FeatureData & grain, std::size_t new_var_index, std::vector<std::map<Node *, CacheValues>> & cache, RemapCacheMode cache_mode)`: Moves solution values from a given grain to a new variable number during remapping .
*   `FauxGrainTracker`: A lightweight replacement for `GrainTracker` when remapping is not needed, suitable when the number of grains is less than or equal to the number of order parameters .

### Algorithm Steps:
The `GrainTracker`'s remapping algorithm is executed within the `remapGrains()` method .

` ` `pseudocode
FUNCTION remapGrains()
  grains_remapped = true
  WHILE grains_remapped IS TRUE
    grains_remapped = false
    notify_ids.clear()

    FOR EACH grain1 IN _feature_sets
      // Remap grains on reserved order parameters
      IF grain1._var_index >= _reserve_op_index THEN
        IF _verbosity_level > 0 THEN
          PRINT "Grain #", grain1._id, " detected on a reserved order parameter #", grain1._var_index, ", remapping to another variable"
        END IF
        FOR max FROM 0 TO _max_remap_recursion_depth
          IF attemptGrainRenumber(grain1, 0, max) THEN
            BREAK
          END IF
        END FOR
        IF NOT attemptGrainRenumber(grain1, 0, _max_remap_recursion_depth + 1) THEN
          ERROR "Unable to find suitable order parameters for remapping for Grain #", grain1._id
        END IF
        grains_remapped = true
      END IF

      FOR EACH grain2 IN _feature_sets
        IF grain1 IS grain2 THEN CONTINUE
        IF grain1._var_index == grain2._var_index AND // Grains represented by same variable
           grain1._id != grain2._id AND               // Different grains
           grain1.boundingBoxesIntersect(grain2) AND  // Bounding boxes intersect
           grain1.halosIntersect(grain2) THEN         // Halos actually overlap
          IF _verbosity_level > 0 THEN
            PRINT "Grain #", grain1._id, " intersects Grain #", grain2._id, " (variable index: ", grain1._var_index, ")"
          END IF
          FOR max FROM 0 TO _max_remap_recursion_depth
            IF attemptGrainRenumber(grain1, 0, max) THEN
              grains_remapped = true
              BREAK
            END IF
          END FOR
          IF NOT attemptGrainRenumber(grain1, 0, _max_remap_recursion_depth + 1) AND
             NOT attemptGrainRenumber(grain2, 0, _max_remap_recursion_depth + 1) THEN
            notify_ids.insert(grain1._id)
            notify_ids.insert(grain2._id)
          END IF
        END IF
      END FOR
    END FOR

    IF notify_ids IS NOT EMPTY THEN
      IF _tolerate_failure THEN
        WARNING "Unable to find suitable order parameters for remapping for grain IDs: ", notify_ids
      ELSE
        ERROR "Unable to find suitable order parameters for remapping for grain IDs: ", notify_ids
      END IF
    END IF
  END WHILE
END FUNCTION
` ` ` 

### Parameters:
*   `remap = true/false`: Boolean parameter to enable or disable grain remapping .
*   `_reserve_op_index`: The index above which order parameters are considered reserved and trigger remapping if a grain is found on them .
*   `_max_remap_recursion_depth`: The maximum recursion depth for the `attemptGrainRenumber` method .
*   `_tolerate_failure`: If `true`, the simulation will issue a warning instead of an error if remapping fails .

### Relationships:
` ` `mermaid
classDiagram
    class FeatureFloodCount {
        +execute()
        #_feature_sets
    }
    class GrainTracker {
        +remapGrains()
        #_feature_sets_old
        #_remap
        #_tolerate_failure
        #_reserve_op_index
        #_max_remap_recursion_depth
        #attemptGrainRenumber()
        #swapSolutionValues()
    }
    class GrainTrackerInterface {
        <<interface>>
        +getFeatureVar()
        +getGrainCentroid()
    }
    class PolycrystalUserObjectBase {
        #prepopulateState()
    }

    GrainTracker --|> FeatureFloodCount : extends
    GrainTracker --|> GrainTrackerInterface : implements
    GrainTracker "1" -- "1" PolycrystalUserObjectBase : uses > _poly_ic_uo
    FeatureFloodCount "1" *-- "many" FeatureData : contains
    GrainTracker "1" *-- "many" FeatureData : _feature_sets_old
` ` `         

## Grain boundary energy: how is anisotropic GB energy specified?

While the basic grain growth model assumes isotropic grain boundary properties , MOOSE provides the `GBAnisotropy` material to define parameters $L$, $\mu$, and $\kappa$ considering misorientation dependence for the GB energy . This allows for specifying anisotropic grain boundary energy.

## Grain boundary mobility: isotropic vs anisotropic, temperature-dependent

### Isotropic Mobility
For isotropic grain boundary mobility, the model parameters $L$, $\mu$, and $\kappa$ are defined in terms of the grain boundary energy ($\sigma$), diffuse grain boundary width ($w_{GB}$), and grain boundary mobility ($M_{GB}$) . The `GBEvolution` material defines these parameters assuming isotropic properties .

### Anisotropic Mobility
Anisotropic mobilities can be specified using the `anisotropic` parameter in actions like `GrandPotentialKernelAction` . The `GBAnisotropy` material also allows for misorientation-dependent grain boundary properties

Wiki pages you might want to explore:
- [Physics Modules (idaholab/moose)](https://deepwiki.com/idaholab/moose#5)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
