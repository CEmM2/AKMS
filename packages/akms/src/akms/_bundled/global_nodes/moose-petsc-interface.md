---
id: moose-petsc-interface
title: MOOSE PETSc Interface — Linear Operators, Matrix-Free, and GPU
domain: solver
subdomain: procedural
tags:
- PETSc
- linear-algebra
- matrix-free
- GPU
- CUDA
- Kokkos
- fieldsplit
- MUMPS
- SNES
- KSP
- preconditioner
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: large
reading_priority: full
akms_schema: v2
edges:
- to: cm-solver-matrixfree
  type: implements
  weight: 0.8
  note: Implements PETSc interface for matrix-free and GPU solvers
- to: tgs-dom-linear-solvers
  type: implements
  weight: 0.7
  note: MOOSE-PETSc interface for linear solver configuration
---

# MOOSE PETSc Interface — Linear Operators, Matrix-Free, and GPU

Framework knowledge node covering 4 aspect(s) of PETSc Interface — Linear Operators, Matrix-Free, and GPU.

## MOOSE-PETSc linear algebra interface

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


## Matrix-free operations and JFNK implementation details

MOOSE implements matrix-free Jacobian-vector products for JFNK by leveraging PETSc's `MatShell` and `MatMFFD` functionalities. It registers a custom matrix-vector product routine with PETSc, which internally calls MOOSE's residual evaluation function. For preconditioning, MOOSE can either assemble a separate matrix or operate in a fully matrix-free mode.   

## Classes & Methods
* `Moose::SlepcSupport::setOperationsForShellMat(EigenProblem & eigen_problem, Mat mat, bool eigen)`: Sets the matrix-vector product operation for a PETSc `MatShell` based on whether it's for an eigen problem or not. 
* `Moose::SlepcSupport::mooseMatMult_NonEigen(Mat mat, Vec x, Vec r)`: The callback function for `MATOP_MULT` when the `MatShell` represents the non-eigen part of the Jacobian. It evaluates the residual. 
* `NonlinearSystem::setupFiniteDifferencedPreconditioner()`: Configures the finite-differenced preconditioner, which can be either "coloring" or "standard". 
* `SNESSetJacobian()`: A PETSc function used to set the Jacobian evaluation function for the nonlinear solver. 

## Equations
The Jacobian-vector product for JFNK is approximated using a finite-difference formula:  
$$
\mathbf{J}(\mathbf{u}^{i-1}) \mathbf{y} \approx \frac{\mathbf{R}(\mathbf{u}^{i-1} + \epsilon \mathbf{y}) - \mathbf{R}(\mathbf{u}^{i-1})}{\epsilon} \quad (1)
$$
For preconditioned JFNK (PJFNK), the action of the preconditioned Jacobian is approximated as:  
$$
\mathbf{J} \mathbf{P}^{-1}\mathbf{v} \approx \frac{\mathbf{R}(\mathbf{u} + \epsilon \mathbf{P}^{-1}\mathbf{v}) - \mathbf{R}(\mathbf{u})}{\epsilon} \quad (2)
$$

## Algorithm Steps

### Matrix-Free Jv Product Setup
1. MOOSE sets up a `MatShell` for the Jacobian. 
2. The `MatShell` is configured with a custom matrix-vector product routine, `mooseMatMult_NonEigen` (or `mooseMatMult_Eigen` for eigenvalue problems). 
3. When PETSc needs to compute a Jacobian-vector product, it calls this registered routine. 
4. Inside `mooseMatMult_NonEigen`, MOOSE's residual evaluation function (`evaluateResidual`) is called with the perturbed vector `x` to compute $R(u+\epsilon v)$. 

## Parameters
* `solve_type`: Controls the nonlinear solver method.  
    * `PJFNK`: Preconditioned Jacobian-Free Newton Krylov (default). 
    * `JFNK`: Jacobian-Free Newton Krylov (no preconditioning). 
    * `NEWTON`: Full Newton solve using an assembled Jacobian. 
    * `FD`: Jacobian assembled via finite differencing. 
    * `LINEAR`: Solves a linear problem. 
* `matrix_free`: Boolean parameter to enable matrix-free operator formation. 
* `precond_matrix_free`: Boolean parameter to enable matrix-free preconditioner formation. 
* `mffd_type`: Specifies the finite differencing type for Jacobian-free solves. 
    * `wp`: Walker and Pernice (default). 
    * `ds`: Default PETSc finite difference. 

## Relationships

` ` `mermaid
graph TD
    A[Executioner] --> B{solve_type = JFNK/PJFNK};
    B -- "Sets up SNES" --> C[PETSc SNES];
    C -- "Calls SNESSetJacobian" --> D[MOOSE's Jacobian Callback];
    D -- "If matrix-free" --> E[MatShell];
    E -- "Sets MATOP_MULT to mooseMatMult_NonEigen" --> F[mooseMatMult_NonEigen];
    F -- "Calls evaluateResidual" --> G[MOOSE Residual Assembly];
    B -- "If PJFNK" --> H[Preconditioner Matrix Assembly];
    H -- "Uses computeQpJacobian/computeQpOffDiagJacobian" --> G;
` ` `

## Code Snippets

### Setting up MatShell for Matrix-Free Jv Product
` ` `cpp
void
setOperationsForShellMat(EigenProblem & eigen_problem, Mat mat, bool eigen)
{
  LibmeshPetscCallA(eigen_problem.comm().get(), MatShellSetContext(mat, &eigen_problem));
  LibmeshPetscCallA(eigen_problem.comm().get(),
                    MatShellSetOperation(mat,
                                         MATOP_MULT,
                                         eigen ? (void (*)(void))mooseMatMult_Eigen
                                               : (void (*)(void))mooseMatMult_NonEigen));
}
` ` ` 

### `mooseMatMult_NonEigen` for Residual Evaluation
` ` `cpp
PetscErrorCode
mooseMatMult_NonEigen(Mat mat, Vec x, Vec r)
{
  PetscFunctionBegin;
  void * ctx = nullptr;
  LibmeshPetscCallQ(MatShellGetContext(mat, &ctx));

  if (!ctx)
    mooseError("No context is set for shell matrix ");

  EigenProblem * eigen_problem = static_cast<EigenProblem *>(ctx);
  NonlinearEigenSystem & eigen_nl = eigen_problem->getCurrentNonlinearEigenSystem();

  evaluateResidual(*eigen_problem, x, r, eigen_nl.nonEigenVectorTag());

  PetscFunctionReturn(PETSC_SUCCESS);
}
` ` ` 

## Detailed Answers to Questions

### 1. The matrix-free Jv product: how does MOOSE register a `MatShell` with PETSc for the Jacobian-free path?
MOOSE registers a `MatShell` with PETSc by calling `MatShellSetOperation` to associate a custom matrix-vector product function with the `MatShell` object.  For non-eigenvalue problems, this function is `mooseMatMult_NonEigen`.  The `mooseMatMult_NonEigen` function then retrieves the `EigenProblem` context and calls `evaluateResidual` to compute the residual, which is used in the finite-difference approximation of the Jacobian-vector product. 

### 2. `SNESSetJacobian` — does MOOSE provide both a matrix-free operator (shell) and a separate preconditioner matrix?
Yes, MOOSE can provide both a matrix-free operator (shell) and a separate preconditioner matrix.  When `solve_type = PJFNK`, the Jacobian used by the Krylov solver is matrix-free, while a separate preconditioner matrix is assembled.  The `mooseSlepcEigenFormJacobianA` function demonstrates this by checking if the Jacobian (`jac`) is `MATSHELL` or `MATMFFD` and if the preconditioner (`pc`) is also `MATSHELL`.  If the preconditioner is not a shell, it will be assembled. 

### 3. The finite-difference parameter ε in J·v ≈ [R(u+εv) - R(u)]/ε — how is it chosen? `MATMFFD_DS` vs `MATMFFD_WP`?
The finite-difference parameter $\epsilon$ is chosen automatically by PETSc.  The choice of the finite differencing type is controlled by the `mffd_type` parameter in MOOSE, which can be set to `wp` (Walker and Pernice, default) or `ds` (default PETSc finite difference).  The PETSc option `-mat_mffd_err` controls $\epsilon$, not `-snes_mf_err`, unless `-snes_mf_version` is set to 2. 

### 4. When `solve_type = JFNK`: the preconditioner matrix is assembled (via SMP/FDP) but the actual Jacobian used by GMRES is matrix-free — confirm this architecture?
This statement is partially correct. When `solve_type = PJFNK`, the preconditioner matrix is assembled, and the actual Jacobian used by GMRES is matrix-free.  However, when `solve_type = JFNK`, there is *no* preconditioning during the Krylov solve, and no Jacobian (or preconditioner) matrix is assembled.  The architecture for PJFNK involves a matrix-free Jacobian-vector product and an assembled preconditioner. 

### 5. Can MOOSE do fully matrix-free (no preconditioner assembly at all)? When would this be useful?
Yes, MOOSE can do fully matrix-free by setting `solve_type = JFNK`.  In this mode, no Jacobian or preconditioner matrix is assembled.  This can be useful when memory is extremely constrained, or when the Jacobian is very difficult or expensive to assemble explicitly. However, JFNK often performs poorly without preconditioning, leading to slow convergence or divergence. 

### 6. How does the `-snes_mf` vs `-snes_mf_operator` PETSc flag map to MOOSE's behavior?
The PETSc flags `-snes_mf` and `-snes_mf_operator` are related to how PETSc handles matrix-free Jacobian approximations. 
*   `-snes_mf`: This flag tells PETSc to use a matrix-free Jacobian for the nonlinear solver. It implies that the Jacobian-vector product will be approximated using finite differences.
*   `-snes_mf_operator`: This flag is used when you want to provide a matrix-free operator for the Jacobian but still use an explicitly assembled matrix for the preconditioner. This aligns with MOOSE's `PJFNK` behavior where the Jacobian is matrix-free but a preconditioner is assembled. 

MOOSE's `solve_type` parameter implicitly sets these PETSc options. For example, `PJFNK` would likely enable `-snes_mf_operator` (or similar configuration

Wiki pages you might want to explore:
- [Problem Solving Architecture (idaholab/moose)](https://deepwiki.com/idaholab/moose#3)


## GPU acceleration and PETSc GPU backends in MOOSE

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


## Custom PETSc solver configurations and fieldsplit

MOOSE extensively leverages PETSc for advanced solver configurations, particularly through its `FieldSplitPreconditioner` and `Split` objects, allowing for detailed control over block preconditioning, Schur complement methods, and custom solver types. It also provides mechanisms for PETSc monitoring and integration with external packages.

## PETScFieldSplit
MOOSE sets up PETSc's `PCFIELDSPLIT` for block preconditioning using the `FieldSplitPreconditioner` class . This preconditioner allows for custom preconditioning for each nonlinear variable in the numerical system . The `FieldSplitPreconditioner` is initialized with a `topsplit` parameter, which defines the entry point for the splitting hierarchy .

The `FieldSplitPreconditioner` constructs a `CouplingMatrix` to define how variables couple . By default, `full=true` creates a fully coupled Jacobian matrix, but users can specify `off_diag_row` and `off_diag_column` to define custom couplings . The `_nl.useFieldSplitPreconditioner(this)` call registers the preconditioner with the nonlinear system .

### MOOSE Input Syntax
An example of setting up a `FieldSplitPreconditioner` for variables 'u' and 'v' with an additive splitting type:
` ` `ini
[Preconditioning]
  [FSP]
    type = FSP
    topsplit = 'uv'
    [uv]
      splitting = 'u v'
      splitting_type = additive
    []
    [u]
      symbol_names = 'u'
      petsc_options_iname = '-pc_type -ksp_type'
      petsc_options_value = '     hypre preonly'
    []
    [v]
      symbol_names = 'v'
      petsc_options_iname = '-pc_type -ksp_type'
      petsc_options_value = '     hypre  preonly'
    []
  []
` ` ` 

## Schur Complement Preconditioners
MOOSE can use PETSc's Schur factorization for saddle-point problems. The `Split` object, which is used within `FieldSplitPreconditioner`, has parameters to control Schur complement behavior .

**Parameters:**
*   `splitting_type = schur`: Specifies that the splitting should use Schur factorization .
*   `schur_type = "diag" | "upper" | "lower" | "full"`: Controls the type of Schur complement factorization .
*   `schur_pre = "S" | "Sp" | "A11"`: Determines which preconditioning matrix to use with $S = D - CA^{-1}B$ .

The `NavierStokesProblem` specifically demonstrates the use of Schur complement preconditioning, including the Least Squares Commutator (LSC) preconditioner . It can configure the Schur complement preconditioner to be a pressure mass matrix or an LSC preconditioner .

## Custom KSP/PC Types
Users can specify nested solver configurations through the `Split` objects within the `[Preconditioning]` block . Each sub-split can have its own `petsc_options_iname` and `petsc_options_value` parameters, allowing for fine-grained control over the `KSP` and `PC` types for different blocks . For example, you can set `hypre` for `pc_type` and `preonly` for `ksp_type` for a specific variable's subsolver .

## PETSc DM Integration
MOOSE uses a custom `DMMoose` object for structured solver information, particularly in the context of `FieldSplitPreconditioner` . The `FieldSplitPreconditioner::createMooseDM` method creates and sets up this `DM` object, associating it with the nonlinear system and its `DofMap` . This `DM` object is then set on the `SNES` solver .

## Matrix-Free Preconditioners
MOOSE supports matrix-free Jacobian-vector products, especially with the `PJFNK` (Preconditioned Jacobian-Free Newton Krylov) solve type . While the documentation mentions `PCShell` in the context of custom preconditioners, the provided snippets do not explicitly show how users can provide a custom `PCShell` through MOOSE input files. However, the `PCApply_MoosePC` function in `SlepcSupport.C` suggests a mechanism for applying a MOOSE-defined preconditioner within PETSc, which could potentially be extended to a `PCShell` .

## PETSc Monitoring
PETSc monitoring options like `-ksp_monitor`, `-snes_monitor`, and `-log_view` can be enabled through MOOSE input files using the `petsc_options` parameter in the `Executioner` block or within `[Preconditioning]` blocks .

**Parameters:**
*   `petsc_options = '-ksp_monitor -snes_monitor -log_view'`: Directly sets these PETSc flags .
*   `petsc_options_iname = '-ksp_monitor'` and `petsc_options_value = ''`: Can also be used for flags .

These options are processed by `Moose::PetscSupport::storePetscOptions` , which adds them to a `PetscOptions` object  that is then used to set PETSc options .

## External Packages through PETSc
MOOSE can configure external packages like MUMPS, SuperLU, and HYPRE (ML is not explicitly mentioned in the provided context but HYPRE is) through PETSc options in the input file   .

**Parameters:**
*   `petsc_options_iname = '-pc_type -pc_hypre_type'` 
*   `petsc_options_value = 'hypre boomeramg'` 

For SuperLU, specific options like `-mat_superlu_dist_replacetinypivot` can be set . These are passed via the `petsc_options_iname` and `petsc_options_value` parameters, which are then processed by `Moose::PetscSupport::storePetscOptions` .

## Classes & Methods
*   `FieldSplitPreconditioner::validParams()`: Registers valid input parameters for the `FieldSplitPreconditioner` .
*   `FieldSplitPreconditioner::FieldSplitPreconditioner()`: Constructor that initializes the preconditioner, sets up the `CouplingMatrix`, and registers itself with the nonlinear system .
*   `FieldSplitPreconditioner::createMooseDM()`: Creates and configures the `DMMoose` object for the field split .
*   `Split::validParams()`: Registers valid input parameters for a `Split` object, including options for splitting type, Schur type, and PETSc options .
*   `Split::setup()`: Configures the PETSc options for a given split, including setting the splitting type, Schur type, and recursively setting up sub-splits .
*   `Moose::PetscSupport::storePetscOptions()`: Processes and stores PETSc options from MOOSE input parameters .
*   `NavierStokesProblem::setupLSCMatrices()`: Sets up the Least Squares Commutator (LSC) preconditioner for the Schur complement .
*   `PCApply_MoosePC()`: A PETSc callback function that applies a MOOSE-defined preconditioner .

## Parameters
*   `topsplit = 'string'`: (Type: `std::string`, Required) The name of the top-level split, which defines the entry point for the splitting hierarchy .
*   `full = true | false`: (Type: `bool`, Default: `true`) If `true`, a full coupling Jacobian matrix is constructed. If `false`, `off_diag_row` and `off_diag_column` must be specified .
*   `off_diag_row = 'vector<NonlinearVariableName>'`: (Type: `std::vector<NonlinearVariableName>`) Specifies rows for off-diagonal coupling .
*   `off_diag_column = 'vector<NonlinearVariableName>'`: (Type: `std::vector<NonlinearVariableName>`) Specifies columns for off-diagonal coupling .
*   `splitting = 'vector<string>'`: (Type: `std::vector<std::string>`) The names of the sub-splits (subsystems) in the decomposition of this split .
*   `splitting_type = "additive" | "multiplicative" | "symmetric_multiplicative" | "schur"`: (Type: `MooseEnum`, Default: `additive`) The type of split decomposition .
*   `schur_type = "diag" | "upper" | "lower" | "full"`: (Type: `MooseEnum`, Default: `full`) Type of Schur complement factorization .
*   `schur_pre = "S" | "Sp" | "A11"`: (Type: `MooseEnum`, Default: `S`) Type of Schur complement preconditioner matrix .
*   `petsc_options = 'MultiMooseEnum'`: (Type: `MultiMooseEnum`) Singleton PETSc options (flags) .
*   `petsc_options_iname = 'MultiMooseEnum'`: (Type: `MultiMooseEnum`) Names of PETSc name/value pairs .
*   `petsc_options_value = 'vector<string>'`: (Type: `std::vector<std::string>`)

Wiki pages you might want to explore:
- [Problem Solving Architecture (idaholab/moose)](https://deepwiki.com/idaholab/moose#3)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
