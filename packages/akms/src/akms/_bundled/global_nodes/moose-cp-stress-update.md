---
id: moose-cp-stress-update
title: MOOSE Crystal plasticity stress update algorithm
domain: constitutive
subdomain: algorithmic
tags:
- crystal-plasticity
- multiplicative-decomposition
- resolved-shear-stress
- plastic-velocity-gradient
- exponential-map
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-crystal-plasticity
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-crystal-plasticity
- to: cm-anisotropic-yield
  type: implements
  weight: 0.8
  note: CP stress update with slip system flow rules
---

# MOOSE Crystal plasticity stress update algorithm

The MOOSE framework implements crystal plasticity primarily through the `CrystalPlasticityStressUpdateBase` class and its derived classes, such as `CrystalPlasticityKalidindiUpdate` and `ComputeMultipleCrystalPlasticityStress`   . The implementation uses a multiplicative decomposition of the deformation gradient and an iterative Newton-Raphson approach to update the stress state and internal variables  .

## Multiplicative Decomposition $F = F^e \cdot F^p$

The crystal plasticity models in MOOSE utilize the multiplicative decomposition of the total deformation gradient $F$ into an elastic component $F^e$ and a plastic component $F^p$ . This decomposition is fundamental to the stress update algorithm, where the plastic deformation gradient `_plastic_deformation_gradient` is a stateful material property that is evolved over time .

## `CrystalPlasticityStressUpdateBase` — Stress Update Algorithm

The `CrystalPlasticityStressUpdateBase` class provides the foundational structure for crystal plasticity stress updates . Derived classes implement the specific constitutive laws. The stress update involves an iterative process to converge the stress state and internal variables .

### Algorithm Steps

The overall stress update is handled by `ComputeMultipleCrystalPlasticityStress::computeQpStress()` , which calls `solveQp()`  to perform the iterative solution.

#### a. Trial Elastic Deformation Gradient: $F^e_{trial} = F \cdot (F^p_{old})^{-1}$

The trial elastic deformation gradient is implicitly calculated within the stress update. The `_plastic_deformation_gradient_old` and `_deformation_gradient` (current total deformation gradient) are used to compute the elastic response  .

#### b. Resolved Shear Stress on each Slip System: $\tau^\alpha = \Sigma_{ij} (S^e_{ij} \cdot s^\alpha_i \cdot m^\alpha_j)$

The resolved shear stress $\tau^\alpha$ on each slip system is calculated by the `CrystalPlasticityStressUpdateBase::calculateShearStress()` method . This method takes the PK2 stress and other deformation gradient components to compute `_tau`, which stores the applied shear stress for each slip system . The Schmid tensor, which involves the slip direction `_slip_direction` and slip plane normal `_slip_plane_normal`, is computed by `calculateSchmidTensor()` .

#### c. Flow Rule: $\dot{\gamma}^\alpha = \dot{\gamma}_0 \cdot |\tau^\alpha/g^\alpha|^n \cdot \text{sign}(\tau^\alpha)$ (power law)

A common power law flow rule is used in several crystal plasticity models, such as `CrystalPlasticityKalidindiUpdate`  and `FiniteStrainCrystalPlasticity` . The parameters involved are:
*   $\dot{\gamma}_0$: Reference slip rate .
*   $\tau^\alpha$: Applied shear stress on slip system $\alpha$ .
*   $g^\alpha$: Slip system strength or resistance to slip .
*   $n$ (or $1/m$): Strain rate sensitivity exponent .

The `calculateSlipRate()` virtual method in `CrystalPlasticityStressUpdateBase` is responsible for computing the slip increment based on the constitutive model defined in child classes .

#### d. Plastic Velocity Gradient: $L^p = \Sigma^\alpha \dot{\gamma}^\alpha \cdot s^\alpha \otimes m^\alpha$

The plastic velocity gradient is constructed from the sum of contributions from each slip system. The `_flow_direction` property, which is a `std::vector<RankTwoTensor>`, stores the Schmid tensors ($s^\alpha \otimes m^\alpha$) for each slip system . The slip rates `_slip_increment` are calculated and used in conjunction with `_flow_direction` to update the plastic deformation .

#### e. Update $F^p$ via exponential map or forward Euler

The update of $F^p$ is handled internally within the stress update routines. While the prompt mentions exponential map or forward Euler, the documentation for `ComputeMultipleCrystalPlasticityStress` states that "Backward Euler integration rule is used for the rate equations" .

#### f. Newton Iteration to converge the stress state

The stress state is converged using a Newton-Raphson iteration. The `ComputeMultipleCrystalPlasticityStress` class explicitly mentions solving the "PK2 stress residual equation using Newton - Raphson" . The `calculateResidualAndJacobian()` method is called to compute the residual `_residual_tensor` and Jacobian `_jacobian`   . The `solveStress()` method performs the actual stress update .

## Convergence Criterion for the Crystal Plasticity Inner Loop

The convergence of the crystal plasticity inner loop, which involves the stress state and internal variables, is controlled by several tolerances:
*   `_rtol`: Stress residual equation relative tolerance .
*   `_abs_tol`: Stress residual equation absolute tolerance .
*   `_rel_state_var_tol` (`stol`): Constitutive internal state variable relative change tolerance .
*   `_slip_incr_tol`: Maximum allowable slip in an increment for each individual constitutive model .
*   `_resistance_tol`: Constitutive slip system resistance relative residual tolerance .
*   `_zero_tol`: Tolerance for residual check when variable value is zero .

The `areConstitutiveStateVariablesConverged()` virtual method in `CrystalPlasticityStressUpdateBase` is used to determine if all state variables have converged .

## Slip System Geometries (FCC, BCC, HCP)

Slip system geometries are defined by reading data from a file specified by `slip_sys_file_name` . The `CrystalPlasticityStressUpdateBase::getSlipSystems()` method handles reading and processing this data .

*   **Crystal Lattice Type**: The `crystal_lattice_type` parameter, an `MooseEnum`, specifies the lattice type (BCC, FCC, HCP) .
*   **Miller Indices / Miller-Bravais**: For BCC and FCC crystals, slip plane normals and directions are read directly from the file and scaled by `_unit_cell_dimension` . For HCP crystals, a transformation from Miller-Bravais 4-index notation to a 3-index Cartesian representation is performed by `transformHexagonalMillerBravaisSlipSystems()` . This transformation also includes checks to ensure that the Miller-Bravais indices for the basal plane sum to zero .
*   **Unit Cell Dimensions**: The `unit_cell_dimension` parameter allows specifying the dimensions of the unit cell, which are used in scaling the slip system vectors .

### Classes & Methods

*   `CrystalPlasticityStressUpdateBase::validParams()`: Defines input parameters common to all crystal plasticity stress update materials .
*   `CrystalPlasticityStressUpdateBase::getSlipSystems()`: Reads slip system data from a file and normalizes vectors .
*   `CrystalPlasticityStressUpdateBase::transformHexagonalMillerBravaisSlipSystems()`: Transforms HCP Miller-Bravais indices to Cartesian coordinates .
*   `CrystalPlasticityStressUpdateBase::calculateShearStress()`: Computes the resolved shear stress for each slip system .
*   `CrystalPlasticityStressUpdateBase::calculateSlipRate()`: Virtual method to calculate the slip increment based on the constitutive model .
*   `CrystalPlasticityStressUpdateBase::areConstitutiveStateVariablesConver

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
