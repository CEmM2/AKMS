# FEM (Taichi GPU) — Assembly + Solve Playbook (TL-focused, corotational stress update)

This domain guide describes how we structure FEM in this repo, with emphasis on:
- Total Lagrangian (TL) formulations
- Corotational/objective stress updates using `Stress_Update6`
- Efficient GPU kernel structure for element loops and solver loops

Authoritative conventions:
- Tensorial Voigt order `[xx, yy, zz, xy, xz, yz]` (no shear scaling)
- Objective corotational update (Hughes–Winget / Cayley) with midpoint kinematics
- PK2 conversion: `S = J F^{-1} σ F^{-T}` when TL assembly needs material measures

(See `references/continuum-tensors.md` and `references/stress-integration.md`.)

---

## 1) FEM data model (what lives where)

### Mesh/topology
Store mesh connectivity and geometry in dense arrays:
- `x0[node]`: reference coordinates
- `x[node]`: current coordinates (or `u[node]` displacement)
- `elem_conn[e, a]`: node indices for element `e`, local node `a`

Connectivity is read-only in the hot path, so keep it contiguous.

### Quadrature state (typical TL)
Per element × quadrature point, store:
- stress in **spatial Cauchy** (tensorial-Voigt): `sigma[e, q, 6]`
- internal scalars: `peeq[e,q]`, `T[e,q]`, etc.
- PF damage scalars (if used): `ds[e,q]`, `dt[e,q]`
- optional: deformation gradient `F[e,q]` if you explicitly store it

If memory is tight, store only what you need for restart and history.

---

## 2) Kernel structure (GPU-friendly pass boundaries)

### Recommended per-step passes
1. **Element kinematics + stress update** (per elem, per quad)
2. **Internal force assembly** (per elem, scatter to nodes)
3. **External forces / BCs** (separate pass)
4. **Solver step** (explicit update or implicit iterations)

Keep boundary condition work out of the main interior kernels when possible.

---

## 3) TL element kinematics (what to compute per quadrature point)

At each quad point:
- build deformation gradient `F` (from reference shape grads and current displacements)
- build velocity gradient `L` (from nodal velocities, midpoint evaluation if required)
- compute `D = sym(L)` and objective rotation `R_delta` (Hughes–Winget / Cayley)

Then:
- rotate stress and `D` to corotational frame
- call `Stress_Update6` in that frame
- rotate stress back to spatial

---

## 4) Internal forces (TL concept)

In TL, internal force uses reference gradients and a material stress measure (often PK2 `S`) or PK1 `P`.

A common pattern:
- compute spatial Cauchy `σ`
- convert to PK2: `S = J F^{-1} σ F^{-T}`
- compute 1st Piola: `P = F S`
- assemble nodal forces via reference shape gradients

### GPU performance notes
- Element-local math stays in registers (small matrices/vectors)
- Scatter to nodal force requires atomics unless you restructure (coloring / staging)
- Try to accumulate per-element node contributions in local variables, then atomic once per node component

---

## 5) Tangents and stiffness (implicit FEM)

### If you do Newton (implicit)
You need:
- residual `r(u) = f_int(u) - f_ext`
- linear operator application `y = K(u) x` (matrix-free) or assembled K

### Recommended: matrix-free operator application
Avoid assembling global sparse matrices on GPU unless you have a compelling reason.

Matrix-free:
- element loop computes `δP` or `δσ` from `dF` (virtual gradient)
- scatter element contributions to `y` (still atomics, but avoids huge matrix storage)

If you do tangent rotations and PK transformations, follow the conventions in `references/continuum-tensors.md`.

---

## 6) Boundary conditions (BCs)
Apply BCs in separate kernels to avoid divergence:
- Dirichlet: mask DOFs and overwrite/update velocity/displacement
- Neumann/tractions: add to external force vector

(See also `references/gotchas.md` §13 for GPU-specific BC pitfalls.)

---

## 7) Solver integration
- Explicit: update `v, u` directly from forces and mass
- Implicit: CG/PCG inner loop for linear solve, with outer Newton

(See `domains/linear-solvers.md` and `domains/time-integration.md`.)

---

## 8) Validation (FEM sanity)
Minimum tests:
- patch test (constant strain)
- rigid body motion (no spurious stress)
- symmetry checks where appropriate
- residual decrease for implicit solves