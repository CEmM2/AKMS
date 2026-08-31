---
id: moose-petsc-linalg
title: MOOSE MOOSE-PETSc linear algebra interface
domain: solver
subdomain: procedural
tags:
- PETSc
- linear-algebra
- sparse-matrix
- preallocation
- libMesh-wrapper
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
- to: tgs-dom-linear-solvers
  type: implements
  weight: 0.7
  note: MOOSE-PETSc linear algebra plumbing
---

# MOOSE MOOSE-PETSc linear algebra interface

MOOSE leverages `libMesh` as an intermediary layer to interface with PETSc for linear algebra operations. `libMesh::PetscMatrix` and `libMesh::PetscVector` wrap the underlying PETSc data structures, and MOOSE's `NonlinearSystem` registers its residual and Jacobian computation routines with PETSc's SNES solver.

## MOOSE to PETSc Interface Overview

MOOSE's problem-solving architecture, centered around `FEProblemBase` and `NonlinearSystemBase`, orchestrates the definition, assembly, and solution of systems of equations . `libMesh` provides the finite element infrastructure and acts as a bridge to PETSc .

` ` `mermaid
graph TD
    subgraph "MOOSE"
        A["FEProblemBase"]
        B["NonlinearSystem"]
        C["Assembly"]
    end

    subgraph "libMesh"
        D["NonlinearImplicitSystem"]
        E["PetscMatrix"]
        F["PetscVector"]
        G["DofMap"]
    end

    subgraph "PETSc"
        H["SNES"]
        I["Mat"]
        J["Vec"]
    end

    A --> B
    B --> C
    B --> D
    D --> E
    D --> F
    D --> G
    E --> I
    F --> J
    D -- "Registers callbacks" --> H
    H -- "Calls back to" --> D
` ` `

## 1. Assembled Matrices and PETSc Mat Types

MOOSE passes assembled matrices to PETSc through `libMesh::PetscMatrix` objects . `libMesh::PetscMatrix` wraps a PETSc `Mat` object . The specific `Mat` type (e.g., `MATAIJ`, `MATBAIJ`) is typically determined by PETSc's defaults or user-specified options . MOOSE allows users to specify the matrix type via the `petsc_options_iname` and `petsc_options_value` parameters, for example, `-mat_type aij` .

## 2. `NonlinearSystem` → PETSc SNES Connection

The `NonlinearSystem` in MOOSE registers its residual and Jacobian functions with PETSc's SNES solver through `libMesh::PetscNonlinearSolver` .

### Residual Function Registration

The residual function is registered with SNES via `DMSNESSetFunction` , which points to `SNESFunction_DMMoose` . `SNESFunction_DMMoose` then calls `DMMooseFunction` , which retrieves the MOOSE `NonlinearSystemBase` and invokes its residual computation routines .

### Jacobian Function Registration

Similarly, the Jacobian function is registered using `DMSNESSetJacobian` , which points to `SNESJacobian_DMMoose` . `SNESJacobian_DMMoose` calls `DMMooseJacobian` , which in turn obtains the `NonlinearSystemBase` and calls its Jacobian computation methods . For finite-differenced preconditioners, `SNESSetJacobian` can also be used with `SNESComputeJacobianDefault`  or `MatFDColoringSetFunction` .

## 3. `libMesh::PetscMatrix` and `libMesh::PetscVector`

`libMesh::PetscMatrix` and `libMesh::PetscVector` are wrapper classes provided by `libMesh` that encapsulate PETSc's `Mat` and `Vec` data structures, respectively . They provide a `libMesh` interface while managing the underlying PETSc objects. For example, `PetscMatrix<Number>::mat()` returns the raw PETSc `Mat` pointer .

## 4. Sparse Matrix Assembly

MOOSE's element-level contributions (e.g., `_local_ke` from kernels) are assembled into the global PETSc `Mat` through `libMesh`'s assembly routines. These routines ultimately make calls to PETSc's `MatSetValues()` or similar functions to insert local matrix entries into the global sparse matrix . The `Assembly` class in MOOSE is responsible for gathering these contributions from various physics components .

## 5. Matrix Preallocation

MOOSE determines the sparsity pattern and preallocates the PETSc matrix during the setup phase. The `libMesh::DofMap` plays a crucial role in defining the global degrees of freedom and their connectivity, which is used to build the sparsity pattern . `MatCreate` and `MatSetSizes` are called, followed by `MatSetType` to specify the matrix type . For certain matrix types, `MatSetPreallocationCOO` can be used for efficient preallocation .

## 6. Block Structure for Multi-Variable Problems

For multi-variable problems, MOOSE primarily uses a monolithic matrix approach where all variables are part of a single system . However, it can leverage PETSc's block preconditioning capabilities, such as field-split preconditioners, to improve convergence . The `PetscDMMoose` utility provides functions like `DMMooseSetSplitNames` and `DMMooseSetSplitVars` to define these field splits for PETSc's `DM` objects .

## 7. Exposing PETSc Options to the User

MOOSE exposes PETSc options to the user through input file parameters: `petsc_options`, `petsc_options_iname`, and `petsc_options_value` .

*   `petsc_options`: Used for single-flag PETSc options (e.g., `-snes_mf`) .
*   `petsc_options_iname`: Specifies the names of PETSc key-value pairs (e.g., `-pc_type`) .
*   `petsc_options_value`: Provides the corresponding values for the `petsc_options_iname` parameters (e.g., `hypre`) .

These parameters allow for raw PETSc command-line pass-through, enabling users to fine-tune PETSc's solvers and preconditioners . The `PetscSupport::addPetscFlagsToPetscOptions` and `PetscSupport::addPetscPairsToPetscOptions` functions process these input parameters and set the options within PETSc .

## Classes & Methods

*   `NonlinearSystem::compute_jacobian()`: A static function called by `libMesh` to compute the Jacobian matrix .
*   `NonlinearSystem::setupColoringFiniteDifferencedPreconditioner()`: Configures PETSc for finite-differenced Jacobian computation using coloring .
*   `DMMooseFunction()`: A static PETSc callback function that computes the residual for a `DM` object .
*   `SNESFunction_DMMoose()`: The PETSc SNES callback for residual computation, which calls `DMMooseFunction` .
*   `DMMooseJacobian()`: A static PETSc callback function that computes the Jacobian matrix for a `DM` object .
*   `SNESJacobian_DMMoose()`: The PETSc SNES callback for Jacobian computation, which calls `DMMooseJacobian` .
*   `DMCreateMoose()`: Creates a MOOSE-specific PETSc `DM` object .
*   `DMCreateMatrix_Moose()`: Creates a PETSc `Mat` object associated with a MOOSE `DM` .
*   `PetscSupport::petscSetOptions()`: Sets PETSc options from MOOSE's `PetscOptions` object .
*   `PetscSupport::addPetscFlagsToPetscOptions()`: Populates `PetscOptions` with single-flag PETSc options from input parameters .
*   `PetscSupport::addPetscPairsToPetscOptions()`: Populates `PetscOptions` with key-value pair PETSc options from input parameters .

## Parameters

*   `solve_type = PJFNK | JFNK | NEWTON | FD | LINEAR`: Controls the nonlinear solver method .
*   `mffd_type = wp | ds`: Specifies the finite differencing type for Jacobian-free solves .
*   `petsc_options = <flags>`: Singleton PETSc options (e.g., `-snes_ksp_ew`) .
*   `petsc_options_iname = <names>`: Names of PETSc name/value pairs (e.g., `-pc_type`) .
*   `petsc_options_value = <values>`: Values corresponding to `petsc_options_iname` (e.g., `hypre`) .

## MOOSE Input Syntax

` ` `ini
[Executioner]
  type = Steady
  solve_type = PJFNK
  petsc_options_iname = '-pc_type -pc_hypre_type'
  petsc_options_value = 'hypre    boomeramg'
[]
` ` `


## Notes

The interaction between MOOSE and PETSc is primarily mediated by `libMesh`. `libMesh` provides the `PetscMatrix` and `PetscVector` wrappers, and its `NonlinearImplicitSystem` registers the necessary callbacks with PETSc's SNES solver. The `PetscDMMoose` utility plays a significant role in setting up the PETSc `DM` object and connecting it to MOOSE's `NonlinearSystemBase` for residual and Jacobian evaluations. Users have extensive control over PETSc's behavior through input file parameters, allowing for flexible solver and preconditioner configurations.

Wiki pages you might want to explore:
- [Problem Solving Architecture (idaholab/moose)](https://deepwiki.com/idaholab/moose#3)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
