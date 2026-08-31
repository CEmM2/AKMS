---
id: moose-crystal-plasticity-advanced
title: MOOSE Crystal Plasticity — Advanced Features
domain: constitutive
subdomain: algorithmic
tags:
- twinning
- phase-transformation
- polycrystal-homogenization
- voronoi
- grain-tracker
- RVE
- periodic-bc
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: medium
reading_priority: full
akms_schema: v2
edges:
- to: moose-stress-computation-chain
  type: requires
  weight: 0.7
  note: Part of the stress computation dispatch chain
- to: moose-crystal-plasticity
  type: requires
  weight: 0.9
  note: Extends base CP framework
- to: moose-nucleation-grain-growth
  type: requires
  weight: 0.5
  note: Polycrystal CP couples with grain growth
- to: cm-anisotropic-yield
  type: implements
  weight: 0.6
  note: Extends crystal plasticity with twinning and polycrystal features
---

# MOOSE Crystal Plasticity — Advanced Features

Framework knowledge node covering 2 aspect(s) of Crystal Plasticity — Advanced Features.

## Crystal plasticity twinning and phase transformation

The MOOSE crystal plasticity module supports deformation twinning through the `CrystalPlasticityTwinningKalidindiUpdate` class, which implements a Kalidindi-based twinning propagation model for FCC and HCP materials   . This module tracks the volume fraction of twinned regions and can be coupled with dislocation slip models . However, it does not explicitly support stress-induced phase transformations (TRIP implementations) or reorientation of the crystal lattice due to twinning .

## Deformation Twinning

### Classes & Methods

*   `CrystalPlasticityTwinningKalidindiUpdate` : A material model that computes plastic shear increment due to twinning based on Kalidindi's model .
    *   `CrystalPlasticityTwinningKalidindiUpdate::validParams()`: Defines the input parameters for the twinning model .
    *   `CrystalPlasticityTwinningKalidindiUpdate::initQpStatefulProperties()`: Initializes stateful material properties, including twin volume fractions and slip resistance .
    *   `CrystalPlasticityTwinningKalidindiUpdate::calculateSlipRate()`: Computes the plastic shear increment due to twinning using a power law constitutive model .
    *   `CrystalPlasticityTwinningKalidindiUpdate::calculateStateVariableEvolutionRateComponent()`: Calculates the rate of twin volume fraction on each twin system .
    *   `CrystalPlasticityTwinningKalidindiUpdate::calculateTwinVolumeFraction()`: Updates the twin volume fraction for each system and the total twin volume fraction .
    *   `CrystalPlasticityTwinningKalidindiUpdate::calculateTwinResistance()`: Calculates the twin propagation resistance based on coplanar and non-coplanar hardening coefficients .

### Twin Systems: Definition

Twin systems are defined similarly to slip systems by providing a `slip_sys_file_name` parameter, which specifies the crystallographic orientations for twinning . The `CrystalPlasticityTwinningKalidindiUpdate` class uses these definitions to calculate resolved shear stresses and plastic shear increments .

### Volume Fraction Tracking for Twinned Regions

The module tracks the volume fraction of twinned regions on each twin system and the total twin volume fraction .
The total twin volume fraction is stored in the material property `_total_twin_volume_fraction` , and individual twin system volume fractions are stored in `_twin_volume_fraction` . An upper limit for the total twin volume fraction can be set using the `upper_limit_twin_volume_fraction` parameter .

### Reorientation of the Crystal Lattice Due to Twinning

The current implementation of `CrystalPlasticityTwinningKalidindiUpdate` does not explicitly support reorientation of the crystal lattice due to twinning . The model focuses on the propagation of twins and their contribution to plastic deformation and hardening .

### Transformation Plasticity (TRIP) Implementations

The MOOSE crystal plasticity module, specifically `CrystalPlasticityTwinningKalidindiUpdate`, does not include implementations for stress-induced phase transformations (TRIP) . Its scope is limited to deformation twinning and dislocation slip .

### Interaction Between Slip and Twin Systems — Latent Hardening Across Mechanisms

The interaction between slip and twin systems is handled by modifying the plastic velocity gradient calculation . When both twinning and dislocation slip models are included, the plastic velocity gradient ($L^P$) is calculated as a weighted sum of contributions from both mechanisms :

$$
L^P = \left(1 - {f_{total}}_{(n-1)} \right) \sum_{\alpha}^{slip} \dot{\gamma}^{\alpha} S^{\alpha}_o + \sum_{\beta}^{twin} \dot{f}^{\beta}\gamma_{tw}S^{\beta}_o \quad (1)
$$ 

Here, $f_{total}$ is the total twin volume fraction, $\dot{\gamma}^{\alpha}$ is the plastic shear rate due to dislocation slip, $S^{\alpha}_o$ is the Schmid tensor for slip systems, $\dot{f}^{\beta}$ is the rate of twin volume fraction, and $S^{\beta}_o$ is the Schmid tensor for twinning systems . The total twin volume fraction from the previous timestep, $f_{total(n-1)}$, is used to couple the models .

Latent hardening across mechanisms is implemented through the twin propagation resistance calculation, which considers different hardening coefficients for non-coplanar and coplanar twinning systems .

$$
\Delta g^{\beta} = \gamma_{tw} \left[ h_{nc}\left( f_{total} \right)^b \sum_{nc}^k \dot{f}^k + h_{cp}\left( f_{total} \right) \sum_{cp}^k \dot{f}^k \right] \quad (2)
$$ 

where $h_{nc}$ is the non-coplanar hardening coefficient, $b$ is the hardening exponent, and $h_{cp}$ is the coplanar hardening coefficient .

### Parameters

The `CrystalPlasticityTwinningKalidindiUpdate` class exposes several parameters for configuring the twinning model :

*   `initial_total_twin_volume_fraction = 0.0` (Real): Initial sum of twin volume fraction across all systems .
*   `twin_reference_strain_rate = 1.0e-3` (Real): Reference strain rate ($\gamma_o$) for the power law .
*   `twin_strain_rate_sensitivity_exponent = 0.05` (Real): Strain rate sensitivity exponent ($m$) .
*   `characteristic_twin_shear = 1.0 / std::sqrt(2.0)` (Real): Characteristic shear of the twin ($\gamma_{tw}$) .
*   `initial_twin_lattice_friction = 0.0` (Real): Initial lattice friction for twin propagation .
*   `non_coplanar_coefficient_twin_hardening = 8000.0` (Real): Hardening coefficient for non-coplanar twin systems ($h_{nc}$) .
*   `coplanar_coefficient_twin_hardening = 800.0` (Real): Hardening coefficient for coplanar twin systems ($h_{cp}$) .
*   `non_coplanar_twin_hardening_exponent = 0.05` (Real): Hardening exponent for non-coplanar twin systems ($b$) .
*   `upper_limit_twin_volume_fraction = 0.8` (Real): Maximum allowed total twin volume fraction ($f_{limit}$) .

### MOOSE Input Syntax

An example of how to configure the `CrystalPlasticityTwinningKalidindiUpdate` material model in a MOOSE input file is shown below :

` ` `ini
[Materials]
  [twin_only_xtalpl]
    type = CrystalPlasticityTwinningKalidindiUpdate
    number_slip_systems = 12
    slip_sys_file_name = 'fcc_input_twinning_systems.txt'
    initial_twin_lattice_friction = 1.5
    upper_limit_twin_volume_fraction = 1e-7
    stol = 0.01
    print_state_variable_convergence_error_messages = true
  []
[]
` ` ` 

To couple twinning with dislocation slip, the `total_twin_volume_fraction` property from the twinning model must be provided to the slip model :

` ` `ini
[Materials]
  [slip_xtalpl]
    type = CrystalPlasticityKalidindiUpdate
    number_slip_systems = 12
    slip_sys_file_name = input_slip_sys.txt
    total_twin_volume_fraction = 'twin_total_volume_fraction_twins'
  []
[]
` ` ` 

## Notes

The `CrystalPlasticityTwinningKalidindiUpdate` model is based on the Kalidindi (2001) constitutive model . It does not allow for de-twinning


## Crystal plasticity polycrystal homogenization

MOOSE handles polycrystal simulations, particularly in the context of crystal plasticity and phase-field grain growth, primarily through its `phase_field` and `solid_mechanics` modules.

### 1. Full-field (each element = one orientation) vs. homogenization approaches

The provided context does not explicitly detail the distinction between full-field (each element = one orientation) and homogenization approaches for polycrystal simulations in crystal plasticity. However, the presence of `ComputePolycrystalElasticityTensor`  suggests a full-field approach where elasticity can vary per grain, which implies per element if grains are resolved at the element level. The `CrystalPlasticityStressUpdateBase`  and `FiniteStrainCrystalPlasticity`  classes in the `solid_mechanics` module indicate that crystal plasticity models are implemented at the material point level, which is consistent with a full-field approach where each quadrature point within an element can have its own crystal orientation and plastic response.

### 2. `PolycrystalElasticDrivingForce` and grain boundary energy contributions

The provided context does not contain information about a class named `PolycrystalElasticDrivingForce`. However, the `Grain Growth Model` documentation  discusses grain boundary energy contributions within the phase-field framework. The free energy functional $F$ includes a term $\kappa \sum^N_i |\nabla \eta_i|^2$ , which represents the gradient energy related to grain boundaries. The parameter $\kappa$ is defined in terms of the grain boundary energy $\sigma$ and diffuse grain boundary width $w_{GB}$ as $\kappa = \frac{3}{4} \sigma w_{GB}$ . The `GBEvolution` material  defines these model parameters.

### 3. Voronoi tessellation: `PolycrystalVoronoi` for initial grain structure generation

MOOSE uses the `PolycrystalVoronoi` UserObject to generate initial polycrystal grain structures using Voronoi tessellation . This UserObject can either generate random points as grain centroids or read them from a file .

**Classes & Methods:**
*   `PolycrystalVoronoi::validParams()`: Defines the input parameters for the `PolycrystalVoronoi` UserObject .
*   `PolycrystalVoronoi::PolycrystalVoronoi(const InputParameters & parameters)`: Constructor for the `PolycrystalVoronoi` class, which initializes parameters like the number of grains, random seed, and interface width .
*   `PolycrystalVoronoi::getGrainsBasedOnPoint(const Point & point, std::vector<unsigned int> & grains) const`: This method determines the grain(s) associated with a given spatial point . It can use a KD-tree for faster searching .
*   `PolycrystalVoronoi::precomputeGrainStructure()`: Overridden method to precompute the grain structure .
*   `PolycrystalVoronoi::buildSearchTree()`: Builds a KD-tree to speed up grain searches .

**Parameters:**
*   `grain_num`: `unsigned int`, default `0`. Number of grains to be represented by order parameters .
*   `rand_seed`: `unsigned int`, default `0`. The random seed for grain generation .
*   `columnar_3D`: `bool`, default `false`. Specifies if the 3D microstructure is columnar in the z-direction .
*   `use_kdtree`: `bool`, default `false`. Enables the use of a KD-tree for faster grain searches .
*   `point_patch_size`: `unsigned int`, default `1`. How many nearest points the KDTree should return .
*   `grain_patch_size`: `unsigned int`, default `10`. How many nearest grains the KDTree should return .
*   `file_name`: `FileName`, default `""`. Path to a file containing grain centroids .
*   `int_width`: `Real`, default `0.0`. Width of diffuse interfaces .

**MOOSE Input Syntax:**
` ` `ini
[UserObjects]
  [voronoi]
    type = PolycrystalVoronoi
    grain_num = 12 # Number of grains
    coloring_algorithm = jp
    rand_seed = 10
    # use_kdtree = true # Uncomment to enable KDTree
  []
[]

[ICs]
  [PolycrystalICs]
    [PolycrystalColoringIC]
      polycrystal_ic_uo = voronoi
    []
  []
[]
` ` ` 

### 4. Coupling with phase field grain growth: how do CP and grain evolution interact?

The `phase_field` module provides capabilities for microstructure evolution, including grain tracking and phase transformations . The `Grain Growth Model` documentation  describes the Allen-Cahn equation used for grain evolution.

Coupling between crystal plasticity and grain evolution can occur through:
*   **Material properties**: The `ComputePolycrystalElasticityTensor`  material in the `phase_field` module computes an evolving elasticity tensor coupled to a grain growth phase field model. This implies that the elastic properties used in crystal plasticity calculations can be influenced by the evolving grain structure.
*   **UserObjects**: `PolycrystalUserObjectBase`  and its derivatives like `PolycrystalVoronoi`  provide information about the grain structure (e.g., grain IDs, centroids) that can be used by other modules.
*   **Order Parameters**: The phase field model uses order parameters ($\eta_i$) to represent different grains . These order parameters can influence material properties, which in turn affect the crystal plasticity response.

### 5. RVE (Representative Volume Element) computations: periodic BCs, volume averaging of stress/strain

The use of periodic boundary conditions (BCs) is mentioned in the context of `PolycrystalVoronoiIC_periodic.i`  and `PolycrystalHex` , indicating support for RVE computations. For example, `PolycrystalHex` explicitly checks for periodic BCs . The `PolycrystalUserObjectBase` also checks for consistent periodicity across coupled variables .

The provided context does not explicitly detail volume averaging of stress/strain for RVE computations, but it is a common post-processing step in such simulations.

### 6. Performance: how does MOOSE parallelize polycrystal CP simulations?

MOOSE is designed for parallel execution, and this extends to polycrystal simulations. The `Physics Modules` wiki page  mentions that module objects requiring parallel communication should use libMesh/PETSc communicator patterns .

Specifically for `PolycrystalVoronoi`, the `use_kdtree` parameter  is available to speed up grain searches, especially for a large number of grains . The `KDTree` is built a-priori to optimize the search time for nearest points and neighboring grains .

The `distributed_poly_ic.i` test input file  explicitly sets `parallel_type = distributed` for the mesh, indicating that polycrystal initial condition generation can be run in parallel.

## Classes & Methods:

*   `PolycrystalVoronoi::validParams()`: Defines input parameters for Voronoi tessellation .
*   `PolycrystalVoronoi::getGrainsBasedOnPoint()`: Determines grain(s) associated with a spatial point .
*   `PolycrystalVoronoi::buildSearchTree()`: Constructs a KD-tree for efficient grain searching .
*   `PolycrystalColoringIC::value()`: Returns the order parameter value for a given point based on the polycrystal user object .
*   `PolycrystalUserObjectBase::initialSetup()`: Checks for consistent periodicity across coupled variables .
*   `ComputePolycrystalElasticityTensor::computeQpElasticityTensor()`: Computes the elasticity tensor at a quadrature point, coupled to grain growth .
*   `CrystalPlasticityStressUpdateBase::getSlipSystems()`: Reads and normalizes slip system vectors from a file .
*   `FiniteStrainUObasedCP`: Material class for user-object-based finite strain crystal plasticity .

## Equations:

The grain growth model uses the Allen-Cahn equation for the evolution of each grain's order parameter:
$$
\frac{\partial \eta_i}{\partial t} = - L \frac{\delta F}{\delta \eta_i} \quad (1)
$$ 
where $F$ is the free energy functional, $L$ is the order parameter mobility, and $\delta$ represents a variational derivative. The free energy functional is given by:
$$
F = \int_V f_{loc}(\eta_0, \eta_1, \ldots, \eta_N) + f_{add} (\eta_0, \eta_1, \ldots, \eta_N) + \kappa \sum^N_i |\nabla \eta_i|^2 \quad (2)
$$

Wiki pages you might want to explore:
- [Physics Modules (idaholab/moose)](https://deepwiki.com/idaholab/moose#5)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
