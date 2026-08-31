---
id: moose-petsc-gpu
title: MOOSE GPU acceleration and PETSc GPU backends in MOOSE
domain: solver
subdomain: procedural
tags:
- GPU
- CUDA
- Kokkos
- cuSPARSE
- VecType
- MatType
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-petsc-interface
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-petsc-interface
---

# MOOSE GPU acceleration and PETSc GPU backends in MOOSE

MOOSE supports GPU-accelerated linear algebra primarily through its integration with PETSc and Kokkos. You can configure MOOSE to leverage CUDA or HIP backends for PETSc, and it also provides a Kokkos-MOOSE framework for GPU-accelerated element assembly and other operations.  

## PETSc GPU Backends
MOOSE supports PETSc with CUDA and HIP backends.   The configuration for these is done when building PETSc, by including flags like `--with-cuda` or `--with-hip`.  MOOSE also checks for `PETSC_HAVE_KOKKOS`, `PETSC_HAVE_CUDA`, and `PETSC_HAVE_HIP` during its own configuration. 

## `VecType` and `MatType` for GPU
MOOSE can utilize PETSc's GPU-specific `VecType` and `MatType` through its `libMesh` dependency.  When PETSc is built with CUDA or HIP support, `libMesh` will use the appropriate GPU-enabled vector and matrix types (e.g., `VECCUDA`, `MATAIJCUSPARSE`).  The `Moose::Kokkos::Matrix` class specifically handles `libMesh::PetscMatrix` objects and can create device-side storage for matrix values if Kokkos GPU capabilities are enabled. 

## Changes Needed in MOOSE to Run on GPU
Running MOOSE on GPU is not entirely transparent and requires specific configurations and code modifications for GPU-accelerated components. 
1.  **PETSc Configuration**: You need to build PETSc with GPU support (e.g., `--with-cuda`). 
2.  **MOOSE Configuration**: MOOSE itself needs to be configured with `--with-kokkos` to enable Kokkos-MOOSE capabilities. 
3.  **Code Modification for Kokkos-MOOSE**: For MOOSE objects to run on GPU using Kokkos, they need to be specifically written or adapted for the Kokkos-MOOSE framework.  This involves using `KOKKOS_FUNCTION` for GPU-callable functions, using `Moose::Kokkos::Array` and other Kokkos-specific data structures for device memory, and implementing static polymorphism via CRTP instead of virtual functions.   

## Matrix-Free GPU Operations
The documentation indicates that `MFEMProblem` allows problem assembly and solution on GPU architectures, which implies that matrix-free operations like the JFNK Jv product could potentially run on the GPU if the residual evaluations are implemented for the device.  However, explicit details on JFNK Jv product running on GPU are not provided in the given context.

## Element Assembly on GPU
Yes, there is active work on GPU-accelerated element assembly in MOOSE via Kokkos.  The Kokkos-MOOSE framework provides GPU versions of `Kernels`, `NodalKernels`, `BCs`, `Materials`, `AuxKernels`, and `Functions`.   These Kokkos objects are designed to resemble their CPU counterparts but require specific GPU programming practices, such as using `KOKKOS_FUNCTION` and `Moose::Kokkos::Array`. 

## libMesh's Role
`libMesh` acts as an abstraction layer for the linear algebra backend, including PETSc.  MOOSE interacts with PETSc primarily through `libMesh`.  When PETSc is configured with GPU support, `libMesh` will automatically use the GPU-enabled PETSc functionalities.  However, for element assembly and other MOOSE-specific operations to run on the GPU, MOOSE also provides its own Kokkos-based framework (`Kokkos-MOOSE`) which requires direct interaction with Kokkos programming paradigms. 

## Current Status
Currently, Kokkos-MOOSE is available for preliminary testing with NVIDIA GPUs.  It supports GPU versions of `Kernels`, `NodalKernels`, `BCs`, `Materials`, `AuxKernels`, and `Functions`.   Support for AMD and Intel GPUs is planned for the future.  Some limitations exist, such as the lack of support for coupling with scalar variables and automatic differentiation in Kokkos-MOOSE kernels, and boundary-restricted elemental `AuxKernels`.  

## Performance
The provided context does not explicitly state for what problem sizes GPU acceleration becomes beneficial in MOOSE. However, general GPU programming principles suggest that GPUs are most effective for problems with high parallelism and large data sets, where the overhead of data transfer to and from the device is amortized by the computational speedup. 

## Configuration Flags and PETSc Options
### MOOSE Configuration Flags
*   `--with-kokkos`: Enables Kokkos-MOOSE capabilities. 

### PETSc Configuration Flags
When building PETSc, you can use the following options:
*   `--with-cuda`: Enables CUDA support. 
*   `--with-hip`: Enables HIP support. 
*   `--with-cuda-arch=[arch]`: Specifies the CUDA GPU architecture (e.g., `80` for `sm_80`). 
*   `--with-hip-arch=[arch]`: Specifies the HIP GPU architecture (e.g., `gfx908`). 

## MOOSE-specific GPU Classes or Interfaces
### Classes & Methods
*   `Moose::Kokkos::Array`: A template class for multi-dimensional arrays designed for GPU access, supporting creation on host, device, or both, and explicit data synchronization. 
*   `Moose::Kokkos::JaggedArray`: A data container for jagged arrays on GPU. 
*   `Moose::Kokkos::Map`: A hash map implementation for GPU, using FNV-1a hash algorithm. 
*   `Moose::Kokkos::ReferenceWrapper`: A template class to hold a reference to a CPU variable and provide an up-to-date value on GPU, synchronizing via the copy constructor. 
*   `Moose::Kokkos::Scalar`: Derived from `Moose::Kokkos::ReferenceWrapper`, providing arithmetic operators for stored values. 
*   `Moose::Kokkos::Matrix::create(libMesh::SparseMatrix<PetscScalar> & matrix, const System & system)`: Creates a Kokkos-managed matrix from a `libMesh::PetscMatrix`, allocating device memory for values if GPU is enabled. 
*   `Moose::Kokkos::Kernel`: Base class for GPU-accelerated kernels, requiring `KOKKOS_FUNCTION` for hook methods like `computeQpResidual()`.  

### Code Snippets
**Example of `Moose::Kokkos::Array` wrapping a PETSc vector:**
` ` `cpp
PetscScalar * petsc_ptr;
PetscInt petsc_size;
VecGetArray(petsc_vector, &petsc_ptr);
VecGetLocalSize(petsc_vector, &petsc_size);

Array<PetscScalar> vector;

vector.createDevice(petsc_size);
vector.aliasHost(petsc_ptr);
vector.copyToDevice();
` ` ` 

**Example of `KOKKOS_FUNCTION` usage in a Kokkos Kernel:**
` ` `cpp
KOKKOS_FUNCTION Real
KokkosDiffusion::computeQpResidual(const unsigned int i,
                                   const unsigned int qp,
                                   AssemblyDatum & datum) const
{
  return _grad_u(datum, qp) * _grad_test(datum, i, qp);
}
` ` ` 

## Notes
The `MFEMProblem` in MOOSE also offers GPU acceleration through the MFEM library, which can leverage CUDA or HIP.  This is a separate but related path to GPU acceleration compared to the Kokkos-MOOSE framework. 

Wiki pages you might want to explore:
- [Executioner and Time Integration (idaholab/moose)](https://deepwiki.com/idaholab/moose#3.2)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
