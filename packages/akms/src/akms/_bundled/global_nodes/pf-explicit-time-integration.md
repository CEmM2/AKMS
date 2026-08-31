---
id: pf-explicit-time-integration
title: 'Explicit Phase-Field: Mass and Viscosity Scaling'
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- explicit
- mass-scaling
- viscosity
- GPU
- CFL
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-at2-regularization
  type: feeds-into
  weight: 0.5
- to: pf-staggered-scheme
  type: contradicts
  weight: 0.0
- to: pf-dynamic-brittle
  type: feeds-into
  weight: 0.5
- to: pf-fem-implementation
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Explicit Phase-Field: Mass and Viscosity Scaling

## Summary

Formulation and implementation of explicit time integration schemes for coupled elastodynamics and diffusive phase-field fracture mechanics. Explicit phase-field frameworks decouple the mechanical displacement field u and phase-field damage variable d using staggered central-difference (for displacement) and forward-difference (for phase field) updates. By employing lumped diagonal mass M and artificial damping/capacity C matrices (constructed via row-sum techniques), explicit algorithms eliminate the need to solve large non-linear algebraic systems or re-assemble global tangent matrices at every increment. Artificial viscosity parameter \varpi = \omega l_c / g_f regularizes local phase-field evolution and prevents high-frequency spatial instabilities. To ensure stability, the time step size \Delta t is strictly bounded by the Courant-Friedrichs-Lewy (CFL) limit \Delta t \le h / c_p, where h is element size and c_p is dilatational wave speed. Furthermore, modern GPU-accelerated array programming frameworks (such as JAX-PF) leverage element-wise vectorization via jax.vmap to deliver 5x+ speedups over CPU-MPI solvers.

## 1. Core Concept

Explicit time integration for phase-field fracture provides a computationally decoupled, matrix-free solution architecture ideal for high-rate dynamic fracture, wave propagation, impact failure, and massive GPU parallelization. Unlike implicit monolithic or staggered schemes that require solving global stiffness systems with Newton-Raphson or quasi-Newton iterations, explicit schemes update solution states at time t_{n+1} directly from known state variables at time t_n. The mechanical sub-problem is integrated using the explicit central-difference method driven by lumped diagonal mass matrices M, while the phase-field evolution equation is integrated using the explicit forward-difference method governed by lumped capacity matrices C. To stabilize the forward-difference phase-field update and prevent numerical oscillations without violating thermodynamic irreversibility \dot{d} \ge 0, an artificial viscosity parameter \omega or viscous power term P_{vis} = \int \frac{\omega}{2} \dot{d}^2 d\Omega is introduced. Numerical stability requires satisfying the CFL condition \Delta t \le h / c_p; because resolving the regularized localization band requires fine spatial discretization (h \le l_c/2), explicit time steps are very small (\Delta t \sim 10^{-8} \text{ s} - 10^{-9} \text{ s}). GPU architectures exploit this element-wise decoupling using array vectorization to achieve extreme computational throughput.

## 2. Mathematical Formulation

**explicit_phase_field_governing_pde**
$$
\varpi \dot{d} = (1-d)\mathcal{H} - (d - l_c^2 \Delta d), \quad \varpi = \frac{\omega l_c}{g_f}
$$
_Source: Li et al. (2025), Phase field fracture in elastoplastic solids; Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration_

**forward_difference_phase_field_update**
$$
\mathbf{C} \dot{\mathbf{d}}_n = \mathbf{Y}_n \implies \dot{\mathbf{d}}_n = \mathbf{C}^{-1} \mathbf{Y}_n, \quad \mathbf{d}_{n+1} = \mathbf{d}_n + \Delta t_{n+1} \dot{\mathbf{d}}_n
$$
_Source: Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration; Li et al. (2025), Phase field fracture in elastoplastic solids; Zhang et al. (2023), Phase-field modeling of coupled spall and adiabatic shear banding_

**central_difference_displacement_explicit_step**
$$
\mathbf{M} \ddot{\mathbf{u}}_n = \mathbf{F}_{ext, n} - \mathbf{F}_{int, n}, \quad \dot{\mathbf{u}}_{n+1/2} = \dot{\mathbf{u}}_{n-1/2} + \frac{\Delta t_{n+1} + \Delta t_n}{2} \ddot{\mathbf{u}}_n, \quad \mathbf{u}_{n+1} = \mathbf{u}_n + \Delta t_{n+1} \dot{\mathbf{u}}_{n+1/2}
$$
_Source: Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration; Li et al. (2025), Phase field fracture in elastoplastic solids_

**cfl_explicit_stability_bound**
$$
\Delta t \le \Delta t_{crit} = \frac{h}{c_p}, \quad c_p = \sqrt{\frac{\lambda + 2\mu}{\rho}}
$$
_Source: Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration; Li et al. (2025), Phase field fracture in elastoplastic solids; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus_

**Notation:**
d: scalar phase-field damage variable (d \in); \varpi: modified viscosity parameter (\varpi = \omega l_c / g_f); \omega: artificial viscosity parameter; l_c: regularization length scale parameter; g_f: critical fracture energy; \mathcal{H}: history variable field; \mathbf{d}: nodal phase-field vector; \mathbf{u}, \dot{\mathbf{u}}, \ddot{\mathbf{u}}: nodal displacement, velocity, and acceleration vectors; \mathbf{M}: lumped diagonal mass matrix; \mathbf{C}: lumped diagonal capacity/damping matrix; \mathbf{Y}: phase-field residual vector; \mathbf{F}_{int}, \mathbf{F}_{ext}: internal and external force vectors; \Delta t: explicit time step size; h: element mesh size; c_p: dilatational wave speed.


## 3. Algorithmic Implementation

**explicit-staggered-phase-field-time-integration**
$$
\begin{algorithmic}
\State $Initialize nodal displacement \mathbf{u}_0, velocity \dot{\mathbf{u}}_0, phase field \mathbf{d}_0 = \mathbf{0}, history field \mathcal{H}_0 = 0, and form lumped diagonal mass matrix \mathbf{M} and capacity matrix \mathbf{C} using row-sum lumping.$
\For{$Loop over explicit time increments n = 0, 1, 2, \dots, N_{steps} with time step \Delta t_{n+1} \le h / c_p.$}
\State $At element Gauss integration points, evaluate strain \boldsymbol{\epsilon}_n = \mathbf{B}_u \mathbf{u}_n, positive strain energy \psi_0^+(\boldsymbol{\epsilon}_n), and update damage history field: \mathcal{H}_n = \max(\mathcal{H}_{n-1}, \psi_0^+(\boldsymbol{\epsilon}_n)).$
\State $Compute phase-field residual vector \mathbf{Y}_n = -\mathbf{A}_{e=1}^{N_e} \int_{\Omega_e} \{ [d_n - 2(1-d_n)\mathcal{H}_n] \mathbf{N}_d^T + l_c^2 \mathbf{B}_d^T \nabla d_n \} d\Omega.$
\State $Compute nodal phase-field rate \dot{\mathbf{d}}_n = \mathbf{C}^{-1} \mathbf{Y}_n and update phase field explicitly: \mathbf{d}_{n+1} = \mathbf{d}_n + \Delta t_{n+1} \dot{\mathbf{d}}_n.$
\State $Evaluate degraded Cauchy stress \boldsymbol{\sigma}_n = [(1-d_n)^2 + k] \boldsymbol{\sigma}_0^+ + \boldsymbol{\sigma}_0^- and assemble internal force vector \mathbf{F}_{int, n} = \mathbf{A}_{e=1}^{N_e} \int_{\Omega_e} \mathbf{B}_u^T \boldsymbol{\sigma}_n d\Omega.$
\State $Compute accelerations \ddot{\mathbf{u}}_n = \mathbf{M}^{-1} (\mathbf{F}_{ext, n} - \mathbf{F}_{int, n}), advance mid-step velocity \dot{\mathbf{u}}_{n+1/2} = \dot{\mathbf{u}}_{n-1/2} + \frac{\Delta t_{n+1} + \Delta t_n}{2} \ddot{\mathbf{u}}_n, and update displacement \mathbf{u}_{n+1} = \mathbf{u}_n + \Delta t_{n+1} \dot{\mathbf{u}}_{n+1/2}.$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration; Li et al. (2025), Phase field fracture in elastoplastic solids_

**gpu-vectorized-explicit-array-update**
$$
\begin{algorithmic}
\State $Define global solution vectors for displacement \mathbf{U} and phase field \mathbf{D} mapped over structured FE grid.$
\State $In GPU environment (JAX-PF framework), vectorize quadrature point strain and history field evaluations across all finite element cells simultaneously using array operations (e.g. jax.vmap).$
\For{$Loop over explicit time steps n = 0, 1, 2, \dots, N_{steps}.$}
\State $Compute element-wise residual arrays \mathbf{r}(\mathbf{U}_n, \mathbf{D}_n) in parallel without constructing global tangent stiffness matrices.$
\State $Apply diagonal mass and damping inverses \mathbf{M}^{-1} and \mathbf{C}^{-1} directly via element-wise array multiplication.$
\State $Advance solution state \{\mathbf{U}_{n+1}, \mathbf{D}_{n+1}\} in a single vectorized GPU execution pass.$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Hu et al. (2025), Efficient GPU-computing simulation platform JAX-PF for differentiable phase field model_


## 4. Known Pitfalls

- **cfl-time-step-restriction-from-fine-mesh-resolution**: Phase-field fracture modeling requires fine element sizes h \le l_c/2 (or h \le b/5) inside localization zones to resolve sharp damage gradients. In explicit time integration, this fine spatial resolution drastically reduces the CFL stability limit (\Delta t \le h / c_p \sim 10^{-8} \text{ s} - 10^{-9} \text{ s}), demanding millions of time increments for long physical durations. _(Source: Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Zhang et al. (2023), Phase-field modeling of coupled spall and adiabatic shear banding)_
- **spurious-viscous-lag-from-excessive-artificial-damping**: If the artificial viscosity or damping parameter \varpi = \omega l_c / g_f is chosen too large, phase-field evolution lags significantly behind the mechanical stress state. This causes non-physical delay in crack initiation, artificially elevates peak load capacity, and distorts dynamic crack branching angles. _(Source: Li et al. (2025), Phase field fracture in elastoplastic solids; Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration)_
- **spurious-oscillations-from-undamped-explicit-phase-field**: Omitting viscous damping (\varpi = 0) in explicit forward-difference phase-field updates makes the local damage rate \dot{d} prone to numerical high-frequency oscillations and spatial instability across element boundaries, requiring artificial viscosity \omega > 0 or viscous power terms P_{vis} to smooth spatial phase-field rates. _(Source: Li et al. (2025), Phase field fracture in elastoplastic solids; Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration; Zhang et al. (2022), Assessment of four strain energy decomposition methods)_

## References

- Wang, T., Ye, X., Liu, Z., Liu, X., Chu, D., and Zhuang, Z. (2020). A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration. Computational Mechanics, 65(5), 1305-1321.
- Li, C., Liu, J., Dong, L., Wu, C., Steven, G., Li, Q., and Fang, J. (2025). Phase field fracture in elastoplastic solids: a stress-state, strain-rate, and orientation dependent model in explicit dynamics and its applications to additively manufactured metals. Journal of the Mechanics and Physics of Solids, 197, 105978.
- Hu, F., Guo, J., Niezgoda, S., Liu, W. K., and Cao, J. (2025). Efficient GPU-computing simulation platform JAX-PF for differentiable phase field model. arXiv pre-print.
- Zhang, H., Peng, H., Pei, X.-Y., Wu, J.-Y., Li, P., Tang, T.-G., Cai, L.-C., Li, Y., and Liu, H. (2023). Phase-field modeling of coupled spall and adiabatic shear banding and simulation of complex cracks in ductile metals. Journal of the Mechanics and Physics of Solids, 172, 105186.
- Wu, J.-Y., and Huang, Y. (2020). Comprehensive implementations of phase-field damage models in Abaqus. Theoretical and Applied Fracture Mechanics, 106, 102440.
- Wu, J.-Y., Huang, Y., and Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase field damage theory. Computer Methods in Applied Mechanics and Engineering, 360, 112704.
