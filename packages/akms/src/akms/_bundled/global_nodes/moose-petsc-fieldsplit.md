---
id: moose-petsc-fieldsplit
title: MOOSE Custom PETSc solver configurations and fieldsplit
domain: solver
subdomain: procedural
tags:
- fieldsplit
- schur-complement
- MUMPS
- SuperLU
- nested-solvers
- block-preconditioning
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

# MOOSE Custom PETSc solver configurations and fieldsplit

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
