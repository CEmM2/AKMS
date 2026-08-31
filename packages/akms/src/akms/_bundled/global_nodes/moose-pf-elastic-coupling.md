---
id: moose-pf-elastic-coupling
title: MOOSE Elastic energy coupling with phase field
domain: phase-field
subdomain: algorithmic
tags:
- elastic-energy
- variable-eigenstrain
- two-way-coupling
- khachaturyan
- driving-force
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-phase-field-mechanics-coupling
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-phase-field-mechanics-coupling
- to: cm-kinematics-tl
  type: implements
  weight: 0.5
  note: Elastic energy feedback into phase field driving force
---

# MOOSE Elastic energy coupling with phase field

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

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
