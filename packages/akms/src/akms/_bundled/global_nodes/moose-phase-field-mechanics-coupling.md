---
id: moose-phase-field-mechanics-coupling
title: MOOSE Phase Field — Solid Mechanics Two-Way Coupling
domain: phase-field
subdomain: algorithmic
tags:
- elastic-energy
- eigenstrain
- two-way-coupling
- microstructural-evolution
- composite-elasticity-tensor
- switching-function
- vegards-law
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
- to: moose-strain-formulations
  type: requires
  weight: 0.7
  note: Two-way coupling requires mechanics
- to: moose-allen-cahn-cahn-hilliard
  type: requires
  weight: 0.6
  note: Elastic energy enters AC driving force
- to: cm-kinematics-tl
  type: implements
  weight: 0.5
  note: Phase-dependent eigenstrains affect mechanical deformation
---

# MOOSE Phase Field — Solid Mechanics Two-Way Coupling

Framework knowledge node covering 2 aspect(s) of Phase Field — Solid Mechanics Two-Way Coupling.

## Elastic energy coupling with phase field

The MOOSE framework couples elastic strain energy with phase field evolution primarily through the `ElasticEnergyMaterial` class, which calculates the elastic free energy and its derivatives, and the `ACGrGrElasticDrivingForce` kernel, which incorporates these elastic energy derivatives into the Allen-Cahn equation. Phase-dependent eigenstrains are handled by classes like `ComputeVariableEigenstrain`, which allows the eigenstrain to be a function of order parameters. This creates a two-way coupling where the phase field influences the elastic strain, and the resulting elastic energy feeds back into the phase field evolution.

## Elastic Energy Contribution to Total Free Energy
The elastic energy contribution, $f_{elastic} = \frac{1}{2} \epsilon^e : C : \epsilon^e$, is added to the total free energy through the `ElasticEnergyMaterial` class . This material computes the elastic free energy density and its derivatives with respect to coupled variables, which can include phase field order parameters . The `computeF()` method within `ElasticEnergyMaterial` calculates this elastic free energy density .

## Eigenstrain from Phase Transformation
MOOSE defines phase-dependent eigenstrains using material classes derived from `ComputeEigenstrainBase` . Specifically, `ComputeVariableEigenstrain` is designed to make the eigenstrain a function of multiple variables, such as order parameters .

## `ComputeVariableEigenstrain` and Order Parameter Dependence
The `ComputeVariableEigenstrain` class makes the eigenstrain a function of the order parameter $\eta$ by taking a `prefactor` material property that depends on the coupled variables (`args`) . The `computeQpEigenstrain()` method calculates the eigenstrain as the product of a base tensor and this prefactor . The derivatives of the eigenstrain with respect to the coupled variables are also computed, which are crucial for the two-way coupling .

## Two-Way Coupling
The two-way coupling is achieved as follows:
1.  **Order parameter affects eigenstrain**: The phase field order parameter ($\eta$) influences the eigenstrain through `ComputeVariableEigenstrain` by acting as one of the `args` for the `prefactor` .
2.  **Eigenstrain changes stress**: The eigenstrain contributes to the total strain, which in turn affects the stress and elastic energy calculated by the solid mechanics module.
3.  **Elastic energy feeds back to PF driving force**: The `ACGrGrElasticDrivingForce` kernel calculates the portion of the Allen-Cahn equation that results from the deformation energy . This kernel requires the elastic strain and the derivative of the elasticity tensor as material properties . The `computeDFDOP()` method in `ACGrGrElasticDrivingForce` computes this driving force .

## `ElasticEnergyMaterial` and $\partial f_{elastic}/\partial \eta$
Yes, `ElasticEnergyMaterial` computes $\partial f_{elastic}/\partial \eta$ for the Allen-Cahn equation. It is a `DerivativeFunctionMaterialBase`  and its `computeDF()` method calculates the first derivative of the elastic free energy with respect to a coupled variable (e.g., an order parameter $\eta$) . This derivative is then used by kernels like `ACGrGrElasticDrivingForce` to formulate the Allen-Cahn equation.

## Khachaturyan's Model (Concentration-dependent or Phase-dependent Lattice Mismatch)
MOOSE implements concentration-dependent or phase-dependent lattice mismatch by allowing the eigenstrain to be a function of other variables, such as concentration or order parameters. This is achieved through classes like `ComputeVariableEigenstrain`  or `ComputeVariableBaseEigenStrain` . These materials take a `prefactor` that can be defined as a function of concentration or phase field variables, effectively making the eigenstrain (representing lattice mismatch) dependent on these quantities.

## Implementation: MultiApp or Single-App
The coupling described is typically implemented within a single MOOSE application using coupled variables. The phase field variables and mechanical variables (displacements) are solved simultaneously within the same application. This is evident from the way material properties and their derivatives are fetched and coupled across different modules (e.g., `PhaseFieldApp` and `SolidMechanicsApp`) within the same input file structure  .

## Coupled PDE System

The general form of the Allen-Cahn equation for an order parameter $\eta_j$ is given by:
$$
\frac{\partial \eta_j}{\partial t} = - L_j \frac{\delta F}{\delta \eta_j} \label{eq:AC} \quad (1)
$$ 
where $F$ is the total free energy functional. When elastic energy is included, $F$ contains an elastic energy term $E_d$ (or $f_{elastic}$) . The functional derivative $\frac{\delta F}{\delta \eta_j}$ will then include $\frac{\partial E_d}{\partial \eta_j}$ .

The elastic energy density is $f_{elastic} = \frac{1}{2} \epsilon^e : C : \epsilon^e$, where $\epsilon^e = \epsilon - \epsilon^*$ is the elastic strain, $\epsilon$ is the total strain, and $\epsilon^*$ is the eigenstrain. The total strain $\epsilon$ is derived from the displacement field $u$. The eigenstrain $\epsilon^*$ is a function of the order parameter $\eta$.

The coupled system involves:
1.  **Mechanical Equilibrium Equation**:
    $$
    \nabla \cdot \sigma = 0 \quad (2)
    $$
    where $\sigma = C : \epsilon^e$ is the stress tensor.
2.  **Allen-Cahn Equation for Phase Field Evolution**:
    $$
    \frac{\partial \eta}{\partial t} = -L \left( \frac{\partial f_{loc}}{\partial \eta} + \frac{\partial f_{elastic}}{\partial \eta} - \nabla \cdot (\kappa \nabla \eta) \right) \quad (3)
    $$ 
    The term $\frac{\partial f_{elastic}}{\partial \eta}$ is the elastic driving force for phase evolution.

## Classes & Methods

*   `ElasticEnergyMaterial::computeF()`: Computes the elastic free energy density $f_{elastic} = \frac{1}{2} \sigma : \epsilon^e$. 
*   `ElasticEnergyMaterial::computeDF(unsigned int i_var)`: Computes the first derivative of the elastic free energy density with respect to a coupled variable (e.g., an order parameter $\eta$). 
*   `ACGrGrElasticDrivingForce::computeDFDOP(PFFunctionType type)`: Calculates the elastic driving force term $\frac{\partial f_{elastic}}{\partial \eta}$ for the Allen-Cahn equation. 
*   `ComputeVariableEigenstrain::computeQpEigenstrain()`: Calculates the eigenstrain at each quadrature point, making it a function of coupled variables (e.g., order parameters). 
*   `ComputeVariableEigenstrain::ComputeVariableEigenstrain()`: Fetches derivatives of the prefactor and builds elastic strain derivatives with respect to coupled variables. 

## Parameters

*   `ElasticEnergyMaterial`:
    *   `base_name`: `string`, "Material property base name" 
    *   `coupled_variables`: `vector<string>`, "Vector of variable arguments of the free energy function" 
    *   `displacement_gradients`: `vector<string>`, "Vector of displacement gradient variables" 
*   `ComputeVariableEigenstrain`:
    *   `args`: `vector<string>`, "variable dependencies for the prefactor" (required) 
*   `ACGrGrElasticDrivingForce`:
    *   Inherits parameters from `ACBulk`.

## Relationships

` ` `mermaid
classDiagram
    direction LR
    class Material {
        +computeQpProperties()
    }
    class DerivativeMaterialInterface {
    }
    class ComputeEigenstrainBase {
        +computeQpEigenstrain()
    }
    class ComputeVariableEigenstrain {
        -_num_args
        -_dprefactor
        -_d2prefactor
        -_delastic_strain
        -_d2elastic_strain
    }
    class ElasticEnergyMaterial {
        -_stress
        -_elasticity_tensor
        -_strain
        +computeF()
        +computeDF()
    }
    class ACBulk {
        +computeDFDOP()
    }
    class ACGrGrElasticDrivingForce {
        -_D_elastic_tensor
        -_elastic_strain
    }
    class AllenCahn {
        -_dFdEta
        -_d2FdEta2
        -_d2FdEtadarg
    }

    Material <|-- ComputeEigenstrainBase
    DerivativeMaterialInterface <|-- ComputeVariableEigenstrain
    ComputeEigenstrainBase <|-- ComputeVariableEigenstrain
    DerivativeFunctionMaterialBase <|-- ElasticEnergyMaterial
    ACBulk <|-- ACGrGrElasticDrivingForce
    ACBulk <|-- AllenCahn

    ComputeVariableEigenstrain ..> MaterialProperty : "sets _eigenstrain"
    ElasticEnergyMaterial ..> MaterialProperty : "gets _stress, _elasticity_tensor, _strain"
    ACGrGrElasticDrivingForce ..> MaterialProperty : "gets _D_elastic_tensor, _elastic_strain"

    ElasticEnergyMaterial --|> "calculates ∂f_elastic/∂η" ACGrGrElasticDrivingForce
    ComputeVariableEigenstrain --|> "defines ε*(η)" ElasticEnergyMaterial
` ` `

## MOOSE Input Syntax

` ` `ini
[Materials]
  [./elastic_tensor]
    type = ComputeIsotropicElasticityTensor
    block = 0
    youngs_modulus = 100e9
    poissons_ratio = 0.3
  [../]
  [./eigenstrain_prefactor]
    type = GenericFunctionMaterial
    prop_names = 'prefactor'
    f_name = 'eta' # Assuming 'eta' is the order parameter variable
    block = 0
  [../]
  [./eigenstrain]
    type = ComputeVariableEigenstrain
    block = 0
    eigen_base_tensor = '1 0 0 0 1 0 0 0 1' # Isotropic eigenstrain
    prefactor = eigenstrain_prefactor/prefactor
    args = eta # Coupled to the order parameter 'eta'
  [../]
  [./elastic_energy]
    type = ElasticEnergyMaterial
    block = 0
    coupled_variables = eta # Coupled to the order parameter 'eta'
    displacement_gradients = 'disp_x_grad_x disp_x_grad_y disp_x_grad_z disp_y_grad_x disp_y_grad_y disp_y_grad_z disp_z_grad_x disp_z_grad_y disp_z_grad_z'
    elasticity_tensor = elastic_tensor/elasticity_tensor
    elastic_strain = total_elastic_strain # This is the elastic strain (total - eigen)
  [../]
[]

[Kernels]
  [./ac_elastic_driving_force]
    type = ACGrGrElasticDrivingForce
    variable = eta
    block = 0
    elastic_tensor_derivative = elastic_energy/delasticity_tensor_d_eta # Derivative of C w.r.t. eta
    elastic_strain = elastic_energy/elastic_strain # Elastic strain
  [../]
  [./ac_bulk]
    type = AllenCahn
    variable = eta
    block = 0
    f_name = free_energy_material/f_local # Local free energy contribution
  [../]
[]

[Functions]
  [./free_energy_function]
    type = ParsedFunction
    value = 'f_local(eta)' # Define your local free energy function
  [../]
[]

[Problem]
  type = Reference
  coord_type = XYZ
  [./Executioner]
    type = Transient
    solve_type = 'NEWTON'
  [../]
[]

[Variables]
  [./disp_x]
    type = Displacement
    order = FIRST
    family = LAGRANGE
  [../]
  [./disp_y]
    type = Displacement
    order = FIRST
    family = LAGRANGE
  [../]
  [./disp_z]
    type = Displacement
    order = FIRST
    family = LAGRANGE
  [../]
  [./eta]
    type = OrderParameter
    order = FIRST



## Phase field parameters in constitutive models

MOOSE integrates phase field variables into solid mechanics constitutive models primarily through material classes that allow for phase-dependent material properties and stress calculations.

## Phase-dependent elastic moduli: $C(\eta) = h(\eta) \cdot C_{phase1} + (1-h(\eta)) \cdot C_{phase2}$

The `ComputeConcentrationDependentElasticityTensor` class is used to define an elasticity tensor that depends on a concentration field, which can represent a phase field variable . This class interpolates between two elasticity tensors, `_Cijkl0` and `_Cijkl1`, based on the value of a coupled concentration variable `_c` .

### Classes & Methods:
*   `ComputeConcentrationDependentElasticityTensor::validParams()`: Defines the input parameters for the concentration-dependent elasticity tensor, including two stiffness tensors (`C0_ijkl`, `C1_ijkl`) and a coupled concentration variable (`c`) .
*   `ComputeConcentrationDependentElasticityTensor::computeQpElasticityTensor()`: Computes the elasticity tensor at a given quadrature point using a linear interpolation formula .

### Equations:
The elasticity tensor $C$ is computed as:
$$
C = C_{ijkl0} + (C_{ijkl1} - C_{ijkl0}) \cdot c \quad (1)
$$ 
where $C_{ijkl0}$ is the stiffness tensor for zero concentration, $C_{ijkl1}$ is the stiffness tensor for concentration 1.0, and $c$ is the concentration variable .

## `CompositeElasticityTensor` — how does it interpolate tensors between phases?

The `CompositeElasticityTensor` class is used to combine multiple elasticity tensors with corresponding weights . While the provided snippets do not show its C++ implementation, an example input file demonstrates its usage where `tensors` are combined with `weights` . This allows for interpolation of elasticity tensors based on material properties that can be derived from phase field variables.

## Creep/plasticity parameters that depend on phase

MOOSE supports phase-dependent creep and plasticity parameters. The test suite for `CompositePowerLawCreepStressUpdate` indicates that the system provides phase-dependent power law creep that can handle different material properties for different phases . This includes scenarios with multiple plasticity rules for different phases . The input parameters for such creep models, like activation energy, coefficient, and n-exponent, are expected to have lengths equal to the number of switching functions (phases) .

## Swelling eigenstrains: coupling species concentration c to volumetric strain

The `ElasticEnergyMaterial` class is designed to handle elastic energy contributions and can fetch stress and elasticity tensor derivatives with respect to coupled variables . This framework allows for coupling species concentration `c` to volumetric strain by defining the elastic strain and elasticity tensor as functions of `c` and their derivatives.

## Thermal expansion differences between phases: phase-dependent CTE

While not explicitly shown in the provided snippets, the general approach for phase-dependent material properties in MOOSE, as demonstrated with elasticity tensors and creep parameters, would extend to thermal expansion coefficients. A material class similar to `ComputeConcentrationDependentElasticityTensor` could be implemented to interpolate CTE values based on a phase field variable.

## How to ensure thermodynamic consistency when mixing phase field and mechanics?

Thermodynamic consistency in coupled phase field and mechanics problems is ensured by defining a global free energy functional that includes contributions from both the local free energy density ($f_{loc}$), gradient energy density ($f_{gr}$), and additional energy sources like deformation energy ($E_d$) . The evolution equations for phase field variables (conserved and non-conserved) are derived from the functional derivatives of this global free energy .

For two-phase models, the `DerivativeTwoPhaseMaterial` combines phase free energies into a global free energy using a switching function $h(\eta)$ .
$$
F = (1-h(\eta)) F_a + h(\eta)F_b + Wg(\eta) \quad (2)
$$ 
where $F_a$ and $F_b$ are the free energies of phase A and B, respectively, and $\eta$ is the order parameter. The `TwoPhaseStressMaterial` and `MultiPhaseStressMaterial` classes calculate global stress and its derivative with respect to strain by interpolating between phase-specific stresses and stiffnesses using a switching function `_h_eta` . This approach ensures that the mechanical response is consistent with the phase distribution.

### Classes & Methods:
*   `TwoPhaseStressMaterial::computeQpProperties()`: Computes the global stress and its Jacobian by linearly interpolating between the stresses and Jacobians of two phases using a switching function `_h_eta` .
*   `ElasticEnergyMaterial`: A free energy material for elastic energy contributions, which can be coupled with other variables like concentration .

### MOOSE Input Syntax:
For phase-dependent elastic moduli using `ComputeConcentrationDependentElasticityTensor`:
` ` `ini
[Materials]
  [./elasticity_tensor]
    type = ComputeConcentrationDependentElasticityTensor
    block = '1'
    C0_ijkl = '...' # Stiffness tensor for zero concentration phase
    C1_ijkl = '...' # Stiffness tensor for concentration 1.0 phase
    c = concentration_variable # Coupled concentration variable
  [../]
[]
` ` ` 

For combining stresses from multiple phases using `TwoPhaseStressMaterial`:
` ` `ini
[Materials]
  [./phase_A_stress]
    type = SomeElasticStressMaterial
    block = '1'
    # ... parameters for phase A stress
  [../]
  [./phase_B_stress]
    type = SomeElasticStressMaterial
    block = '1'
    # ... parameters for phase B stress
  [../]
  [./switching_function]
    type = SwitchingFunctionMaterial
    block = '1'
    # ... parameters for h(eta)
  [../]
  [./global_stress]
    type = TwoPhaseStressMaterial
    block = '1'
    h = switching_function # Material property providing h(eta)
    base_A = phase_A_stress # Base name for Phase A strain/stress
    base_B = phase_B_stress # Base name for Phase B strain/stress
  [../]
[]
` ` ` 

## Notes
The provided context primarily focuses on elastic properties and general free energy formulations. Specific implementations for phase-dependent thermal expansion coefficients (CTE) were not directly found, but the framework suggests that similar material classes could be developed. The `ComputePolycrystalElasticityTensor` class also deals with evolving elasticity tensors coupled to grain growth phase field models, which is a related concept but not directly addressing the user's specific question about $C(\eta) = h(\eta) \cdot C_{phase1} + (1-h(\eta)) \cdot C_{phase2}$ .

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
