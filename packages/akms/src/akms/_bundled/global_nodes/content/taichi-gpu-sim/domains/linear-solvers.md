# Linear Solvers (GPU-friendly) — CG/PCG patterns for Taichi

This file describes how we implement iterative solvers efficiently in Taichi:
- avoid host sync
- minimize kernel launches
- structure dot products / norms as reductions

---

## 1) What you should assume
- We primarily use CG/PCG for SPD systems (common in elasticity).
- For non-SPD (contact, certain plasticity tangents), CG may fail; use a different method only if required.

---

## 2) The operator contract (matrix-free)
Define `apply_A(x, y)` as a kernel (or a small number of kernels):
- reads `x`
- writes `y = A x`
- no host reads inside iterations

Everything else (CG bookkeeping) is vector ops + reductions.

---

## 3) CG iteration structure (GPU-safe)
Per iteration:
1. `Ap = A p`
2. `alpha = (r·r) / (p·Ap)`
3. `x = x + alpha p`
4. `r = r - alpha Ap`
5. check convergence (use scalar reductions, but avoid host reads every iter if possible)
6. `beta = (r_new·r_new)/(r_old·r_old)`
7. `p = r + beta p`

### GPU hygiene
- Keep vector updates in fused kernels where sensible.
- Dot products are reductions: accumulate into 0D scalar `ti.field` to exploit field reductions.
- Reading `alpha` on host every iteration syncs; if you must, do it, but accept the cost.
  Alternative: do a fixed number of iterations per step (common in explicit-ish implicit methods).

---

## 4) PCG (Jacobi baseline)
Preconditioner `M^{-1}`:
- simplest: diagonal/Jacobi (store inverse diagonal)
- apply in kernel: `z = M^{-1} r`

PCG changes:
- use `rz = r·z` instead of `rr = r·r` in alpha/beta updates

---

## 5) Convergence criteria
Use relative residual norms:
- `||r|| / ||b|| < tol`
- also cap iterations `k_max`

Be explicit about tolerances and max iters.

---

## 6) Numerical safeguards
- if `p·Ap <= 0` (loss of SPD), bail or switch strategy
- clamp alpha/beta if NaN/Inf detected
- periodically scan vectors for NaNs in debug builds

---

## 7) Kernel launch minimization
Practical implementation tip:
- Fuse `x,r` updates if it reduces passes.
- But don’t fuse reductions into the same kernel as large vector ops unless you’ve measured it helps.