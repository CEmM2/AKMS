---
id: moose-crystal-plasticity
title: MOOSE Crystal Plasticity — Constitutive Framework
domain: constitutive
subdomain: algorithmic
tags:
- crystal-plasticity
- slip-systems
- hardening
- euler-angles
- polycrystal
- multiplicative-decomposition
- resolved-shear-stress
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: large
reading_priority: full
akms_schema: v2
edges:
- to: moose-stress-computation-chain
  type: requires
  weight: 0.7
  note: Part of the stress computation dispatch chain
- to: moose-strain-formulations
  type: requires
  weight: 0.8
  note: CP uses finite strain kinematics
- to: cm-anisotropic-yield
  type: implements
  weight: 0.8
  note: Implements crystal plasticity with slip-system-level flow rules
- to: cm-kinematics-tl
  type: implements
  weight: 0.7
  note: Uses multiplicative decomposition F=Fe·Fp in finite strain
---

# MOOSE Crystal Plasticity — Constitutive Framework

Framework knowledge node covering 3 aspect(s) of Crystal Plasticity — Constitutive Framework.

## Crystal plasticity stress update algorithm

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


## Crystal plasticity hardening laws

The MOOSE framework implements several hardening laws for crystal plasticity, primarily through the `CrystalPlasticityKalidindiUpdate` class and the `CrystalPlasticityStateVarRateComponentVoce` UserObject  . These implementations handle self and latent hardening, and store history variables like slip resistance as material properties  .

## Hardening Laws Implemented

### Kalidindi Hardening Model
The `CrystalPlasticityKalidindiUpdate` class implements the self and latent hardening crystal plasticity model developed by Kalidindi et al. (1992) .

**Equations:**
The slip rate is given by a power law relationship:
$$
\dot{\gamma}^{\alpha} = \dot{\gamma}_o \left| \frac{\tau^{\alpha}}{g^{\alpha}} \right|^{1/m} sign \left( \tau^{\alpha} \right) \quad (1)
$$ 
where $\dot{\gamma}_o$ is a reference slip rate, $\tau^{\alpha}$ is the applied shear stress, $g^{\alpha}$ is the slip system strength (resistance to slip), and $m$ is the strain rate sensitivity exponent .

The evolution of slip system strength (resistance) is given by:
$$
g^{\alpha} = g_o + \Delta \gamma^{\alpha} q^{\alpha \beta} h_o \left| 1 - \frac{g^{\alpha}}{g_{sat}} \right|^a sign \left( 1 - \frac{g^{\alpha}}{g_{sat}} \right) \quad (2)
$$ 
where $q^{\alpha \beta}$ is the hardening coefficient matrix, $h_o$ is an initial hardening term, $g_{sat}$ is the saturated hardening value, and $a$ is the hardening exponent .

The hardening coefficient matrix $q^{\alpha \beta}$ for an FCC system is defined as:
$$
q^{\alpha \beta} = \begin{Bmatrix}
                       1.0 & q   & q   & q  \\
                       q   & 1.0 & q   & q  \\
                       q   & q   & 1.0 & q  \\
                       q   & q   & q   & 1.0
                     \end{Bmatrix} \quad (3)
$$ 
where $q$ is a constant value of latent hardening among non-coplanar slip systems .

**Classes & Methods:**
*   `CrystalPlasticityKalidindiUpdate::validParams()`: Defines the input parameters for the Kalidindi hardening model .
*   `CrystalPlasticityKalidindiUpdate::initQpStatefulProperties()`: Initializes stateful properties like slip system resistances .
*   `CrystalPlasticityKalidindiUpdate::setInitialConstitutiveVariableValues()`: Sets initial values for constitutive variables .
*   `CrystalPlasticityKalidindiUpdate::calculateSlipRate()`: Calculates the slip rate for each slip system .
*   `CrystalPlasticityKalidindiUpdate::calculateStateVariableEvolutionRateComponent()`: Calculates the slip system resistance increment based on Kalidindi et al. (1992) .
*   `CrystalPlasticityKalidindiUpdate::updateStateVariables()`: Finalizes the values of state variables after convergence .

**Parameters:**
The `CrystalPlasticityKalidindiUpdate` class uses the following parameters :
*   `r`: Latent hardening coefficient (default: 1.0) 
*   `h`: Hardening constant (default: 541.5) 
*   `t_sat`: Saturated slip system strength (default: 109.8) 
*   `gss_a`: Coefficient for hardening (default: 2.5) 
*   `ao`: Slip rate coefficient (default: 0.001) 
*   `xm`: Exponent for slip rate (default: 0.1) 
*   `gss_initial`: Initial lattice friction strength (default: 60.8) 
*   `total_twin_volume_fraction`: Name of the material property for total twin volume fraction, if twinning is considered .

### Voce Hardening Model
The `CrystalPlasticityStateVarRateComponentVoce` UserObject implements a phenomenological Voce constitutive model for state variable evolution .

**Equations:**
The hardening rate `hb(i)` for a slip system `i` is calculated as:
$$
hb(i) = h_0 \left| 1 - \frac{g^{\alpha} - \tau_0}{\tau_{sat} - \tau_0} \right|^{hardening\_exponent} \text{sign}\left(1 - \frac{g^{\alpha} - \tau_0}{\tau_{sat} - \tau_0}\right) \quad (4)
$$ 
where $h_0$ is an initial hardening constant, $\tau_0$ is the initial critical resolved shear stress, $\tau_{sat}$ is the saturation resolved shear stress, and $hardening\_exponent$ is the hardening exponent .
The evolution rate of the state variable `val[i]` is then calculated by summing contributions from all slip systems `j`, considering self and latent hardening coefficients `q_ab`:
$$
val[i] += |\dot{\gamma}_{j}| \cdot q_{ab} \cdot hb(j) \quad (5)
$$ 

**Classes & Methods:**
*   `CrystalPlasticityStateVarRateComponentVoce::validParams()`: Defines input parameters for the Voce hardening model .
*   `CrystalPlasticityStateVarRateComponentVoce::calcStateVariableEvolutionRateComponent()`: Computes the slip system hardening rate .
*   `CrystalPlasticityStateVarRateComponentVoce::getHardeningCoefficient()`: Retrieves the appropriate self/latent hardening coefficient .

**Parameters:**
The `CrystalPlasticityStateVarRateComponentVoce` class uses the following parameters :
*   `uo_slip_rate_name`: Name of the slip rate property.
*   `uo_state_var_name`: Name of the state variable property.
*   `crystal_lattice_type`: Type of crystal lattice structure (e.g., "FCC", "BCC").
*   `groups`: Defines slip system groups (e.g., '0 12 24 48').
*   `h0_group_values`: `h0` hardening constant for each group.
*   `tau0_group_values`: Initial critical resolved shear stress for each group.
*   `tauSat_group_values`: Saturation resolved shear stress for each group.
*   `hardeningExponent_group_values`: Hardening exponent for each group.
*   `selfHardening_group_values`: Self-hardening coefficient `q_aa` for each group.
*   `coplanarHardening_group_values`: Coplanar latent hardening coefficient `q_ab` for each group.
*   `GroupGroup_Hardening_group_values`: Group-to-group latent hardening coefficient `q_ab` (N x N matrix).

**MOOSE Input Syntax Example:**
` ` `ini
[UserObjects]
  [./state_var_evol_rate_comp_voce]
    type = CrystalPlasticityStateVarRateComponentVoce
    variable_size = 48
    crystal_lattice_type = 'BCC'
    groups = '0 12 24 48'
    h0_group_values = '1 2 3'
    tau0_group_values = '50 51 52'
    tauSat_group_values = '70 81 92'
    hardeningExponent_group_values = '1 2 3'
    selfHardening_group_values ='4 5 6'
    coplanarHardening_group_values='7 8 9'
    GroupGroup_Hardening_group_values = '10 20 30
                                         40 50 60
                                         70 80 90'
    uo_slip_rate_name = slip_rate_gss
    uo_state_var_name = state_var_gss
  [../]
[]
` ` ` 

### Beyerlein Hardening Model (HCP)
The `CrystalPlasticityHCPDislocationSlipBeyerleinUpdate` class implements a constitutive model for the glide and evolution of forest dislocations within an HCP crystal lattice . This model considers contributions from initial lattice friction, Hall-Petch type hardening, forest dislocations, and substructure density .

**Equations:**
The total slip resistance $g^{\alpha}$ is the sum of four terms:
$$
g^{\alpha} = g^{\alpha}_o + g^{\alpha}_{HP} + g^{\alpha}_{forest} + g^{\alpha}_{sub} \quad (6)
$$ 
where $g^{\alpha}_o$ is initial lattice friction, $g^{\alpha}_{HP}$ is Hall-Petch hardening, $g^{\alpha}_{forest}$ is forest dislocation hardening, and $g^{\alpha}_{sub}$ is substructure hardening .

Hall-Petch hardening:
$$
g^{\alpha}_{HP} = HP^{\alpha}\mu^{\alpha} \sqrt{\frac{b^{\alpha}}{d_g}} \quad (7)
$$


## Crystal plasticity slip systems and orientation

MOOSE handles crystallographic orientations and slip systems primarily within the `solid_mechanics` module, particularly for crystal plasticity models . It supports defining slip systems from files, reading Euler angles (Bunge convention), applying crystal-to-sample rotations, and integrating with EBSD data for polycrystal orientations   .

## Slip System Definition Files

Slip systems are defined in external text files, which are then read by MOOSE . The `CrystalPlasticityStressUpdateBase` class handles reading these files .

### Format for Specifying {hkl}<uvw> Systems

The slip system files typically contain the slip plane normal and slip direction vectors . For HCP crystals, a 4-index Miller-Bravais notation can be transformed into a 3-index Cartesian representation .

**Parameters:**
*   `slip_sys_file_name` = "path/to/file.txt" (type: `FileName`, required): Name of the file containing slip systems, with the slip plane normal given before the slip plane direction .
*   `number_slip_systems` (type: `unsigned int`, required): The total number of possible active slip systems .
*   `crystal_lattice_type` (type: `MooseEnum`, default: "FCC"): Specifies the crystal lattice type (BCC, FCC, HCP) .
*   `unit_cell_dimension` (type: `std::vector<Real>`, default: `{1.0, 1.0, 1.0}`): Dimensions of the unit cell, used for computing slip systems .

**Code Snippets:**
The `getSlipSystems()` method in `CrystalPlasticityStressUpdateBase` reads and normalizes the slip system vectors . For HCP crystals, `transformHexagonalMillerBravaisSlipSystems()` performs the coordinate transformation .

` ` `cpp
void
CrystalPlasticityStressUpdateBase::getSlipSystems()
{
  bool orthonormal_error = false;

  // read in the slip system data from auxiliary text file
  MooseUtils::DelimitedFileReader _reader(_slip_sys_file_name);
  _reader.setFormatFlag(MooseUtils::DelimitedFileReader::FormatFlag::ROWS);
  _reader.read();

  // check the size of the input
  if (_reader.getData().size() != _number_slip_systems)
    paramError(
        "number_slip_systems",
        "The number of rows in the slip system file should match the number of slip system.");

  for (const auto i : make_range(_number_slip_systems))
  {
    // initialize to zero
    _slip_direction[i].zero();
    _slip_plane_normal[i].zero();
  }

  if (_crystal_lattice_type == CrystalLatticeType::HCP)
    transformHexagonalMillerBravaisSlipSystems(_reader);
  else if (_crystal_lattice_type == CrystalLatticeType::BCC ||
           _crystal_lattice_type == CrystalLatticeType::FCC)
  {
    for (const auto i : make_range(_number_slip_systems))
    {
      // directly grab the raw data and scale it by the unit cell dimension
      for (const auto j : index_range(_reader.getData(i)))
      {
        if (j < LIBMESH_DIM)
          _slip_plane_normal[i](j) = _reader.getData(i)[j] / _unit_cell_dimension[j];
        else
          _slip_direction[i](j - LIBMESH_DIM) =
              _reader.getData(i)[j] * _unit_cell_dimension[j - LIBMESH_DIM];
      }
    }
  }

  for (const auto i : make_range(_number_slip_systems))
  {
    // normalize
    _slip_plane_normal[i] /= _slip_plane_normal[i].norm();
    _slip_direction[i] /= _slip_direction[i].norm();

    if (_crystal_lattice_type != CrystalLatticeType::HCP)
    {
      const auto magnitude = _slip_plane_normal[i] * _slip_direction[i];
      if (std::abs(magnitude) > libMesh::TOLERANCE)
      {
        orthonormal_error = true;
        break;
      }
    }
  }

  if (orthonormal_error)
    mooseError("CrystalPlasticityStressUpdateBase Error: The slip system file contains a slip "
               "direction and plane normal pair that are not orthonormal in the Cartesian "
               "coordinate system.");
}
` ` ` 

## Euler Angle Input and Rotation Tensors

MOOSE uses Euler angles to define crystallographic orientations, primarily following the Bunge convention .

### Euler Angle Input: Bunge Convention

The `ComputeElasticityTensorCP` class accepts Bunge Euler angles as input . These can be provided directly in the input file, read from a `PropertyReadFile` user object, or coupled from other variables .

**Parameters:**
*   `euler_angle_1`, `euler_angle_2`, `euler_angle_3` (type: `Real`): Individual Euler angles .
*   `read_prop_user_object` (type: `UserObjectName`): A `PropertyReadFile` user object to read Euler angles per element .
*   `euler_angle_variables` (type: `std::vector<VariableName>`): Coupled variables providing Euler angles .

### Rotation Tensors: Crystal-to-Sample Rotation

The `RotationTensor` class is used to manage and apply rotations . The `ComputeElasticityTensorCP` material generates a "passive" rotation matrix from the Euler angles or a user-supplied rotation matrix . This matrix rotates the crystal slip system direction and plane normals into the user-specified orientation .

**Equations:**
The rotation matrix $R$ can be directly provided or constructed from Euler angles. The documentation provides an example of a rotation matrix :
$$
R = \begin{bmatrix}
        \frac{\sqrt{2}}{2} & \frac{\sqrt{6}}{6} & \frac{\sqrt{3}}{3}  \\
       -\frac{\sqrt{2}}{2} & \frac{\sqrt{6}}{6} & \frac{\sqrt{3}}{3}  \\
        0                  & -\frac{\sqrt{6}}{3} & \frac{\sqrt{3}}{3}
    \end{bmatrix}
$$ 

This matrix is used for a "passive" rotation, converting directions from the sample frame to the crystal frame .

**Classes & Methods:**
*   `ComputeElasticityTensorCP::assignEulerAngles()`: Assigns Euler angles from various sources (input file, `PropertyReadFile`, coupled variables) to a material property .
*   `ComputeElasticityTensorCP::computeQpElasticityTensor()`: Computes the elasticity tensor, applying the crystal rotation matrix .
*   `CrystalPlasticityStressUpdateBase::calculateSchmidTensor()`: Rotates slip system plane normal and direction vectors into the local crystal lattice orientation using the crystal rotation tensor .

## GrainTracker and Polycrystal

The `phase_field` module provides tools for managing polycrystal structures and assigning orientations to grains .

### Assigning Orientations to Grains in a Polycrystal

The `PolycrystalUserObjectBase` class serves as a base for creating polycrystal initial conditions and discovering grain structures . Derived classes like `PolycrystalEBSD` can reconstruct grain structures from EBSD data .

**Classes & Methods:**
*   `PolycrystalUserObjectBase::getGrainsBasedOnPoint()`: Retrieves active grain IDs based on a point in the mesh .
*   `PolycrystalUserObjectBase::getNumGrains()`: Returns the number of grains in the polycrystal structure .
*   `PolycrystalEBSD`: A user object for setting up a polycrystal structure from an EBSD Datafile . It uses an `EBSDReader` to get data for specific points .

## EBSD Data Integration

MOOSE can integrate experimental orientation maps through the `EBSDReader` and `PolycrystalEBSD` classes  .

### Reading Experimental Orientation Maps

The `EBSDReader` user object is responsible for reading EBSD data . The `PolycrystalEBSD` class then uses this reader to assign grain IDs and phase information based on spatial points .

**MOOSE Input Syntax:**
` ` `ini
[UserObjects]
  [ebsd_reader]
    type = EBSDReader
  []
  [ebsd]
    type = PolycrystalEBSD
    coloring_algorithm = bt
    ebsd_reader = ebsd_reader
    enable_var_coloring = true
  []
[]
` ` ` 

This input block defines an `EBSDReader` named `ebsd_reader` and a `PolycrystalEBSD` object named `ebsd` that uses the reader to set up the polycrystal structure .

## Texture Evolution

MOOSE can track orientation changes during deformation, particularly through the `EulerAngleUpdater` class

Wiki pages you might want to explore:
- [Physics Modules (idaholab/moose)](https://deepwiki.com/idaholab/moose#5)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
