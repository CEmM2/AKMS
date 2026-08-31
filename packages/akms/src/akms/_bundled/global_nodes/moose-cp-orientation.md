---
id: moose-cp-orientation
title: MOOSE Crystal plasticity slip systems and orientation
domain: constitutive
subdomain: algorithmic
tags:
- slip-systems
- euler-angles
- bunge-convention
- EBSD
- grain-tracker
- texture
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
---

# MOOSE Crystal plasticity slip systems and orientation

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
