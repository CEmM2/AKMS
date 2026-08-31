---
id: solver-explicit-dynamics
title: 'Explicit Dynamics: Central Difference & CFL'
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- explicit-dynamics
- central-difference
- CFL
- lumped-mass
- mass-scaling
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-newmark-hht
  type: contradicts
  weight: 0.0
- to: solver-imex-splitting
  type: feeds-into
  weight: 0.5
- to: solver-gpu-data-layout
  type: requires
  weight: 1.0
- to: pf-dynamic-brittle
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Explicit Dynamics: Central Difference & CFL

## Summary

Explicit time integration schemes, such as the central difference method, solve transient elastodynamic equations without assembling or factorizing global stiffness matrices. By pairing explicit time stepping with diagonal lumped mass matrices, explicit dynamics computes nodal accelerations and displacements via element-local vector updates. Numerical stability is conditionally governed by the Courant-Friedrichs-Lewy (CFL) condition, which bounds the time step size by the maximum eigenfrequency of the system. Mass scaling techniques selectively modify the mass operator to artificially depress high-frequency modes and enlarge critical time steps.

## 1. Core Concept

Explicit time integration for structural dynamics solves the discretized system of ordinary differential equations M \ddot{u} + C \dot{u} + K u = f^{\text{ext}}. By utilizing a diagonal lumped mass matrix M, the acceleration vector \ddot{u}_n = M^{-1} (f_n^{\text{ext}} - f_n^{\text{int}}) is computed directly via element-wise vector scaling without matrix inversions or tangent stiffness linearizations. In the explicit central difference scheme, displacement iterates u_{n+1} and velocity updates \dot{u}_{n+1/2} are updated via short time step increments \Delta t. The method is conditionally stable, requiring step sizes to satisfy the Courant-Friedrichs-Lewy (CFL) limit \Delta t \le \Delta t_{\text{crit}} = 2 / \omega_{\max}, where \omega_{\max} is the highest natural frequency of the element assembly. To overcome severe CFL time step constraints in fine-mesh regions, mass scaling strategies add semi-definite mass terms E_e = \beta m_e (I - u u^T) to local element mass matrices, depressing high-frequency eigenvalues while preserving linear momentum and rigid-body translations.

## 2. Mathematical Formulation

**central-difference-acceleration-update**
$$
\ddot{u}_n = M^{-1} (f_n^{\text{ext}} - f_n^{\text{int}})
$$
_Source: Mass_Scaling.pdf, Section 1, p. 469_

**cfl-critical-time-step-condition**
$$
\Delta t \le \Delta t_{\text{crit}} = \frac{2}{\omega_{\max}}
$$
_Source: Mass_Scaling.pdf, Section 1, p. 470_

**selective-mass-scaling-element-matrix**
$$
\bar{M}_e = M_e + E_e, \quad E_e = \beta m_e (I_8 - u u^T)
$$
_Source: Mass_Scaling.pdf, Section 2.2.1, p. 476_

**Notation:**
u represents nodal displacement vector; \dot{u}, \ddot{u} represent nodal velocity and acceleration vectors; M represents diagonal lumped mass matrix; K represents stiffness matrix; f^{\text{ext}}, f^{\text{int}} represent external and internal force vectors; \Delta t represents time step size; \omega_{\max} represents maximum system eigenfrequency; E_e represents mass scaling operator matrix.


## 3. Algorithmic Implementation

**central-difference-explicit-dynamics-loop**
$$
\begin{algorithmic}
\State $\text{Initialize } u_0, \dot{u}_0, \text{ diagonal lumped mass matrix } M, \text{ and critical step } \Delta t \le 2 / \omega_{\max}$
\State $\ddot{u}_0 = M^{-1} (f_0^{\text{ext}} - f^{\text{int}}(u_0))$
\For{$n = 0, 1, 2, \dots \text{ until } t_n \ge t_{\text{final}}$}
\State $\dot{u}_{n+1/2} = \dot{u}_{n-1/2} + \Delta t \, \ddot{u}_n$
\State $u_{n+1} = u_n + \Delta t \, \dot{u}_{n+1/2}$
\State $f_{n+1}^{\text{int}} = \text{EvaluateInternalForces}(u_{n+1}) \quad \text{(element-level matrix-free evaluation)}$
\State $\ddot{u}_{n+1} = M^{-1} (f_{n+1}^{\text{ext}} - f_{n+1}^{\text{int}}) \quad \text{(direct element-wise division)}$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Mass_Scaling.pdf, Section 1, pp. 469-470; Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 2, p. 59_


## 4. Known Pitfalls

- **cfl-time-step-instability**: Exceeding the critical CFL time step \Delta t > 2 / \omega_{\max} causes unbounded numerical energy growth and immediate instability in explicit central difference time integration. _(Source: Mass_Scaling.pdf, Section 1, p. 470)_
- **excessive-mass-scaling-frequency-distortion**: Applying overly aggressive mass scaling parameter \beta \to \infty artificially depresses physical natural frequencies, altering transient wave speeds and dynamic structural response. _(Source: Mass_Scaling.pdf, Section 2.2.1, p. 476; Section 2.2.3, p. 487)_

## References

- Mass_Scaling.pdf
- Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf
- Shen et al. - 2024 - Preconditioned Nonlinear Conjugate Gradient Method for Real-time Interior-point Hyperelasticity.pdf
