---
id: moose-pf-nucleation
title: MOOSE Nucleation models in MOOSE phase field
domain: phase-field
subdomain: algorithmic
tags:
- discrete-nucleation
- classical-nucleation-theory
- langevin-noise
- nucleation-inserter
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-nucleation-grain-growth
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-nucleation-grain-growth
---

# MOOSE Nucleation models in MOOSE phase field

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

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
