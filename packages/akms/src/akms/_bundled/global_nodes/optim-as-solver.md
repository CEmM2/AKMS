---
id: optim-as-solver
title: Optimization-Based Nonlinear FEM Solvers
domain: computational-mechanics
subdomain: optimization
tags:
- optimization
- FEM-solver
- energy-minimization
- variational
- descent-guarantee
status: tentative
confidence: 0.85
source: hybrid
confidence_floor: 0.7
edges:
- to: optim-unconstrained-basics
  type: requires
  weight: 1.0
- to: optim-lbfgs
  type: feeds-into
  weight: 0.5
- to: optim-lbfgs-fem
  type: feeds-into
  weight: 0.5
- to: pf-monolithic-bfgs
  type: refines
  weight: 0.7
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Optimization-Based Nonlinear FEM Solvers

## Summary
Variational solid mechanics: equilibrium = minimum of total
potential energy Pi(u). Nonlinear FE solvers can target either
residual = 0 (Newton-style) or energy minimum (optimization-style).
Optimization approach gives guaranteed descent, robust handling
of softening / non-convex problems where Newton fails. L-BFGS, NCG,
trust-region all applicable. Limitation: requires conservative
constitutive law (path-independent psi); plasticity requires
incremental potential framework (Ortiz-Stainier 1999).


## 1. Core Concept
Two equivalent formulations of equilibrium:

(1) Residual form (Newton):
    F(u) = F_int(u) - F_ext = 0
- Newton iterates: u_{k+1} = u_k - J^{-1} * F(u_k)
- Quadratic local convergence
- Globalization: line search, trust region
- Issue: J indefinite at peak load / softening; Newton fails

(2) Energy form (optimization):
    Pi(u) = psi_internal(u) - W_ext(u)  (total potential energy)
    min_u Pi(u)
- Optimization iterates: u_{k+1} = u_k + alpha_k * p_k
- L-BFGS, NCG, trust region
- Guaranteed monotone decrease in Pi (with line search)

Equivalence: F = grad Pi; J = Hessian of Pi.

Why optimization?
- Robust: descent direction always available (e.g., -grad Pi)
- No tangent assembly: gradient = residual already computed
- Quasi-Newton uses gradient differences: no Hessian
- Snap-back / softening: line search prevents divergence

When applicable (conservative systems):
- Hyperelasticity (Ogden, Mooney-Rivlin, neo-Hookean)
- Brittle phase-field fracture (variational by construction)
- Variational plasticity (Ortiz-Stainier 1999, time-incremental
  potential)
- Linear elasticity (psi quadratic)

When NOT applicable:
- Path-dependent / dissipative (e.g., classical plasticity without
  incremental potential)
- Rate-dependent viscoplasticity (J2-rate flow rule)
- Coulomb friction
- Damage with hysteresis

Workaround: incremental energy (incremental potential):
    Pi^inc(u_{n+1}) = psi(F^{n+1}) + dt * D(F^{n+1}, eps^p^{n+1}, ...)
    - lambda * fy(sigma, eps^p)
Minimize this over (u, eps^p, lambda) at each time step
(Ortiz-Stainier).

L-BFGS for FE (advantages):
- Memory: m * n vectors; n = DOFs (10^4-10^7)
- No Jacobian: just element-loop residual computation
- Super-linear convergence with strong Wolfe line search
- Production: standard for variational fracture (Wu 2020)

Hybrid Newton/L-BFGS:
- Newton when J SPD (early iterations, far from peak)
- L-BFGS when J indefinite (snap-back, softening)
- Switch based on Newton convergence rate or eigenvalue check

Practical recipes:
- Initial guess: u_0 from previous time step
- Line search: strong Wolfe, c1 = 1e-4, c2 = 0.9
- Memory m = 10-20 typical
- Stopping: ||grad Pi||_max / ||F_ext|| < 1e-6

Caveats vs Newton:
- L-BFGS slower per iter but no tangent assembly
- Convergence super-linear vs Newton quadratic
- For smooth convex problems with cheap tangent, Newton wins
- For non-convex / complex tangent, L-BFGS wins


## 2. Mathematical Formulation
Variational equilibrium = stationarity of energy. Optimization
solvers leverage convexity / partial-convexity to ensure descent.


**total-potential-energy:**

$$
\Pi(\mathbf{u}) \;=\; \int_\Omega \psi(\mathbf{F}(\mathbf{u})) \, dV \;-\; \int_\Omega \mathbf{u} \cdot \mathbf{b} \, dV \;-\; \int_{\Gamma_t} \mathbf{u} \cdot \mathbf{t} \, dA
$$

where psi = strain energy density; b = body force; t = surface traction

**variational-equilibrium:**

$$
\nabla \Pi(\mathbf{u}^*) \;=\; \mathbf{F}_{int}(\mathbf{u}^*) - \mathbf{F}_{ext} \;=\; \mathbf{0}
$$

where gradient of Pi = residual; equilibrium = stationarity

**hessian-tangent-stiffness:**

$$
\nabla^2 \Pi(\mathbf{u}) \;=\; \mathbf{K}_T(\mathbf{u}) \;=\; \frac{\partial \mathbf{F}_{int}}{\partial \mathbf{u}}
$$

where Hessian of Pi = tangent stiffness; SPD for stable equilibrium

**incremental-potential:**

$$
\Pi^{inc}(\mathbf{u}_{n+1}, \boldsymbol{\xi}_{n+1}) \;=\; \psi(\mathbf{F}_{n+1}, \boldsymbol{\xi}_{n+1}) - \boldsymbol{\xi}_{n+1}^T \mathbf{Y}_n + \Delta D(\boldsymbol{\xi}_{n+1}, \boldsymbol{\xi}_n)
$$

where Ortiz-Stainier 1999; xi = internal variables; Delta D = dissipation pseudo-potential; minimize over (u, xi)

**descent-guarantee:**

$$
\Pi(\mathbf{u}_{k+1}) \;<\; \Pi(\mathbf{u}_k) \quad \forall k \;\;\text{(with Armijo line search)}
$$

where monotone decrease in energy; not guaranteed with Newton + indefinite J

**convergence-comparison:**

$$
T_{Newton} \sim k_{Newton} \cdot T_{tangent-assembly + linear-solve}
$$

where Newton: few iter but expensive each; L-BFGS: more iter but cheap each

**lbfgs-fem-cost:**

$$
T_{L-BFGS} \sim k_{L-BFGS} \cdot (T_{residual-assembly} + T_{line-search})
$$

where no Jacobian assembly; gradient = residual already needed

**Notation:**

- $Pi(u)$ — total potential energy
- $psi(F)$ — strain energy density
- $F_int, F_ext$ — internal, external forces
- $K_T$ — tangent stiffness (Hessian of Pi)
- $xi$ — internal variables (plastic strain, hardening, ...)
- $D$ — dissipation pseudo-potential


## 3. Algorithmic Implementation
**Algorithm: lbfgs-as-fem-solver**

$$
\begin{algorithmic}
\State $$
\State $$
\State $$
\State $$
\State $$
\State $$
\State $$
\State $$
\State $$
\end{algorithmic}
$$

**Taichi Mapping:**
ti.kernel for F_int assembly (element loop). Pi evaluation
via element loop summing strain energies. L-BFGS state via
ti.field.


**Algorithm: hybrid-newton-lbfgs**

$$
\begin{algorithmic}
\State $$
\State $$
\State $$
\State $$
\end{algorithmic}
$$

**Taichi Mapping:**
Switch logic in Python; same kernels for Newton (Krylov +
tangent assembly) and L-BFGS (residual + line search).


**Algorithm: variational-plasticity-step**

$$
\begin{algorithmic}
\State $$
\State $$
\State $$
\State $$
\end{algorithmic}
$$

**Taichi Mapping:**
Two-phase loop: outer L-BFGS for u (cheap), inner return
mapping for eps_p (per-GP). Same data layout as standard FE.



## 4. Known Pitfalls
**not-conservative-system:** Plasticity / damage with hysteresis: not derivable from a
potential. Energy minimization not applicable. Use Newton on
residual or incremental potential framework (Ortiz-Stainier).


**rate-dependent-flow:** Viscoplasticity with rate-dependent yield: standard variational
structure breaks. Incremental potential exists but more complex.


**line-search-too-loose:** Backtracking-only without curvature: L-BFGS loses super-linear
rate. Always use strong Wolfe.


**m-too-small-history:** m = 1-3: behaves like steepest descent + small memory. Default
m = 10 robust; larger m for tight problems.


**residual-vs-energy-stopping:** ||F||_inf < tol_F: standard FE convergence. Pi-based stopping
(|Pi_k - Pi_{k-1}| < tol_Pi) less robust for tight tolerances.


**ill-scaled-energy:** psi values vary wildly across mesh (e.g., concentrated stresses):
L-BFGS history dominated by hot-spot updates. Use diagonal
preconditioner H_0.


## 5. References
- Wu, J.-Y., Huang, Y., Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase-field damage theory. CMAME 360:112704.
- Ortiz, M., Stainier, L. (1999). The variational formulation of viscoplastic constitutive updates. CMAME 171:419-444.
- Mielke, A., Roubíček, T. (2015). Rate-Independent Systems: Theory and Application. Springer.
- Stainier, L., Ortiz, M. (2010). Study and validation of a variational theory of thermo-mechanical coupling in finite visco-plasticity. IJSS 47:705-715.
- Kelley, C. T. (1999). Iterative Methods for Optimization. SIAM.
- Bourdin, B., Francfort, G. A., Marigo, J.-J. (2008). The variational approach to fracture. Springer.
