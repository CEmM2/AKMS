---
id: moose-pf-grain-growth
title: MOOSE Grain growth and coarsening
domain: phase-field
subdomain: algorithmic
tags:
- grain-growth
- coarsening
- fan-chen
- grain-tracker-remap
- zener-pinning
- abnormal
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

# MOOSE Grain growth and coarsening

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
