---
id: moose-threaded-assembly
title: MOOSE Thread-level parallelism and assembly loop
domain: architecture
subdomain: algorithmic
tags:
- threading
- element-loop
- quadrature
- assembly
- AD-kernel
- reinit
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-assembly-loop
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-assembly-loop
- to: tgs-dom-fem
  type: implements
  weight: 0.7
  note: Threaded FEM assembly with AD support
---

# MOOSE Thread-level parallelism and assembly loop

The user is asking for a detailed explanation of MOOSE's execution architecture, focusing on the assembly process. This involves understanding the call chain from `Executioner` to `ThreadedElementLoop`, the threading model, the role of per-thread `Assembly` objects, the element loop's operations, quadrature, variable coupling, automatic differentiation, and object execution ordering.

I will address each point of your query by referencing relevant classes, methods, and concepts within the MOOSE framework.

## Execution Architecture Overview

MOOSE's execution architecture is centered around solving finite element problems. The `Executioner` class orchestrates the overall simulation, which typically involves a `NonlinearSystem` to handle the nonlinear solve, and an `FEProblem` that manages the finite element discretization and assembly process. The core of the assembly happens within `ThreadedElementLoop` and its derived classes, which parallelize the element-wise computations.

### 1. `Executioner` → `NonlinearSystem` → `FEProblem` → `ThreadedElementLoop` Call Chain

The simulation begins with an `Executioner` object, which defines the `execute()` interface for running simulations . Different types of executioners exist, such as `Steady` and `Transient`, for various simulation types .

Within the `Executioner`, the `FEProblemSolve` object encapsulates the logic for solving the `FEProblem` . The `FEProblem` then interacts with one or more `NonlinearSystem` objects to manage the solution variables and their associated equations .

The `NonlinearSystemBase` class is responsible for the assembly of residuals and Jacobians . This assembly process is parallelized using `ThreadedElementLoop` and its specialized derived classes, such as `NonlinearThread`  .

The call chain for assembly generally follows:
`Executioner::execute()` → `FEProblemSolve::solve()` → `FEProblem::computeResidual()` / `FEProblem::computeJacobian()` → `NonlinearSystemBase::assemble()` → `ThreadedElementLoop::operator()` .

### 2. Threading Model: TBB or pthreads — How are element ranges split across threads?

MOOSE leverages `libMesh` for its threading capabilities, which can utilize either TBB (Threading Building Blocks) or pthreads. The `ThreadedElementLoop` class is the base for parallelizing operations over elements .

The `operator()` method of `ThreadedElementLoop` takes a `ConstElemRange` as input, which represents a range of elements to be processed . This range is split across available threads. Each thread then iterates over its assigned subset of elements, performing computations such as `onElement()`, `onBoundary()`, and `onInternalSide()` . The `libMesh::n_threads()` function returns the number of active threads .

### 3. Per-thread `Assembly` objects: why one per thread? How do they avoid data races?

MOOSE uses per-thread `Assembly` objects to avoid data races during the element assembly process . Each thread has its own `Assembly` object, which manages local data structures like `_local_re` (local residual) and `_local_ke` (local Jacobian)  .

By having a separate `Assembly` object for each thread, computations on different elements can proceed concurrently without contention for shared memory. After each thread completes its local assembly for its assigned elements, the local contributions are accumulated into the global PETSc `Mat` (matrix) and `Vec` (vector) in a thread-safe manner  . This accumulation typically involves atomic operations or critical sections to ensure data integrity when updating the global sparse matrix and vector.

### 4. The element loop: `reinit(elem)` → compute kernels → accumulate `_local_re`/`_local_ke` → add to global PETSc Mat/Vec

The element loop, as implemented in `ThreadedElementLoop` and its derivatives like `NonlinearThread`, follows a specific sequence for each element:
1.  **`reinit(elem)`**: Before processing an element, the finite element data (shape functions, Jacobians, etc.) and material properties are reinitialized for the current element. This is handled by methods like `FEProblemBase::reinitElement()` and `FEProblemBase::reinitMaterials()` . The `MooseVariableFE` objects also reinitialize their data for the current element .
2.  **Compute Kernels**: The `computeOnElement()` method (or similar for boundaries/interfaces) is called, which iterates through the registered `Kernel` objects. Each `Kernel` then computes its contribution to the residual and Jacobian for the current element at each quadrature point . For example, `Kernel::computeResidual()` and `Kernel::computeJacobian()` are called  .
3.  **Accumulate `_local_re`/`_local_ke`**: Inside the kernel's `computeResidual()` and `computeJacobian()` methods, the contributions are added to the thread-local `_local_re` (residual vector) and `_local_ke` (Jacobian matrix)  .
4.  **Add to global PETSc Mat/Vec**: After all kernels have computed their contributions for an element, the `accumulate()` method (or similar) is called to add the thread-local `_local_re` and `_local_ke` to the global PETSc `Mat` and `Vec` . This is typically done using `add_vector()` and `add_matrix()` methods on the PETSc objects.

### 5. Quadrature: `_qp` index, `_JxW[_qp]`, `_test[_i][_qp]`, `_phi[_j][_qp]` — how are shape function values cached?

Quadrature is fundamental to numerical integration in finite element methods . MOOSE uses Gaussian quadrature to approximate integrals over elements.
-   `_qp`: This is the current quadrature point index within the element .
-   `_JxW[_qp]`: This array stores the product of the Jacobian determinant of the mapping from reference to physical element and the quadrature weight at each quadrature point . MOOSE automatically handles this term, so kernels only compute the integrand .
-   `_test[_i][_qp]`: This represents the value of the `i`-th test function at the `_qp`-th quadrature point .
-   `_phi[_j][_qp]`: This represents the value of the `j`-th trial function (shape function) at the `_qp`-th quadrature point .

Shape function values and their gradients (`_grad_test`, `_grad_phi`) are precomputed and cached by the `Assembly` object for the current element and quadrature rule . This caching avoids redundant computations within the inner loops of kernels. The `MooseVariableData` class, which is associated with each `MooseVariableFE`, holds pointers to assembly methods that retrieve these precomputed values .

### 6. Variable coupling: on-diagonal vs off-diagonal Jacobian blocks — how determined?

Variable coupling determines which entries in the Jacobian matrix are non-zero.
-   **On-diagonal Jacobian blocks**: These represent the derivative of a residual with respect to its own primary variable. For a `Kernel` operating on variable `u`, `computeQpJacobian()` calculates $\frac{\partial R_u}{\partial u}$ .
-   **Off-diagonal Jacobian blocks**: These represent the derivative of a residual with respect to a *coupled* variable. For a `Kernel` operating on variable `u` that is coupled to variable `v`, `computeQpOffDiagJacobian(jvar_num)` calculates $\frac{\partial R_u}{\partial v}$ . The `jvar_num` argument specifies the coupled variable's number.

The `FEProblem` maintains a list of coupled variables for each system. When a `Kernel` is created, it declares its dependencies on other variables. During assembly, the `NonlinearSystemBase` uses this coupling information to determine which `computeQpOffDiagJacobian()` methods need to be called . If a variable is not explicitly coupled, its off-diagonal Jacobian contribution is assumed to be zero.

### 7. AD (automatic differentiation) path: `ADKernel` and `DualNumber` types — how does AD change the assembly?

MOOSE supports Automatic Differentiation (AD) to compute Jacobians analytically, which can improve accuracy and performance compared to finite differencing.
-   `ADKernel`: This is a specialized `Kernel` class designed to work with AD .
-   `DualNumber` types: MOOSE uses `ADReal` (a `DualNumber` type) to represent values and their derivatives. When AD is enabled, variables and intermediate computations within kernels are performed using `ADReal` instead of `Real`.

When AD is used, the `computeQpResidual()` method in an `ADKernel` returns an `ADReal` value, which implicitly carries the derivative information with respect to all dependent variables . This means that the `computeQpJacobian()` and `computeQpOffDiagJacobian()` methods do not need to be explicitly overridden by the user for AD kernels, as the Jacobian contributions are extracted directly from the `ADReal` residual. The `ADFunctorInterface` provides the necessary mechanisms for this .

### 8. Object execution ordering within a thread: materials before kernels? Dependency resolution?

Within a single thread, the execution order of objects is crucial for correct dependency resolution.
1.  **Materials**: Material properties are typically computed first for an element. The `ComputeMaterialsObjectThread` is responsible for reinitializing and computing material properties for the current element, boundary, or neighbor element . This ensures that material properties are available to kernels that depend on them.
2.  **Kernels**: After materials are reinitialized, `Kernel` objects are executed. The `NonlinearThread::computeOnElement()` method iterates through the active kernels for the current element .
3.  **Dependency Resolution**: MOOSE's input file parsing and object registration system builds a dependency graph. Objects declare their dependencies (e.g., a kernel depends on a material property or another variable). The framework uses this information to ensure that objects are executed in the correct order. For example, `FEProblemBase::reinitScalars()` is called to reinitialize scalar variables, which might be dependencies for other computations .

The `MooseObjectTagWarehouse` is used to manage and retrieve objects based on tags, which can influence their execution order . The `determineObjectWarehouses()` method in `NonlinearThread` is responsible for determining which objects will be computed based on vector/matrix tag information .

## Relationships

` ` `mermaid
graph TD
    A[Executioner] --> B(FEProblemSolve)
    B --> C[FEProblem]
    C --> D[NonlinearSystemBase]
    D --> E[ThreadedElementLoop]
    E --> F[NonlinearThread]
    F --> G[Assembly]
    G --> H[Kernel]
    G --> I[ADKernel]

    subgraph Threading
        E -- "Splits element ranges" --> J[libMesh::n_threads()]
        J -- "Each thread has" --> G
    end

    subgraph Element Loop
        F -- "1. reinit(elem)" --> C
        F -- "2. computeOnElement()" --> H
        F -- "2. computeOnElement()" --> I
        H -- "3. accumulate _local_re/_local_ke" --> G

Wiki pages you might want to explore:
- [Executioner and Time Integration (idaholab/moose)](https://deepwiki.com/idaholab/moose#3.2)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
