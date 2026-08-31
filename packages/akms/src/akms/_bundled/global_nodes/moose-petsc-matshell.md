---
id: moose-petsc-matshell
title: MOOSE Matrix-free operations and JFNK implementation details
domain: solver
subdomain: procedural
tags:
- matrix-free
- MatShell
- JFNK
- finite-difference-Jv
- SNES
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
- to: cm-solver-matrixfree
  type: implements
  weight: 0.9
  note: MatShell for matrix-free JFNK Jacobian-vector product
---

# MOOSE Matrix-free operations and JFNK implementation details

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

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
