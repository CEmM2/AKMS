# Time Integration — explicit vs implicit, and what changes in code structure

This doc defines how time stepping is structured in this repo and what kernels exist in each case.

---

## 1) Explicit stepping (common in MPM, sometimes in FEM)
Typical:
1. compute forces
2. update velocities
3. update positions/displacements
4. apply BCs

### Stability notes
- CFL-like constraints apply (mesh size, wave speed, dt).
- If plasticity/damage is stiff, you may need substepping.

---

## 2) Implicit stepping (Newton + linear solve)
Outer Newton loop:
1. assemble residual `r(u)`
2. if `||r||` small enough stop
3. build/apply tangent operator `K(u)`
4. solve `K Δu = -r` via CG/PCG (inner loop)
5. update `u ← u + Δu`
6. optional line search / damping

### Kernel structure
- residual evaluation: element loop + scatter
- operator apply: matrix-free element loop + scatter
- CG vector ops: kernels + reductions

---

## 3) Midpoint / objective integration coupling
If stress update uses midpoint kinematics (corotational), ensure `L` and `D` are computed consistently with the chosen time integration.
Do not mix “explicit velocities at n” with “midpoint stress update” unless you explicitly intend that scheme.

---

## 4) Substepping policy
Substep when:
- dt causes stress update Newton to fail (plasticity)
- damage evolution becomes unstable
- EOS stiff response requires smaller dt

Implement substepping inside a step loop but keep kernels coarse enough to avoid launch overhead.