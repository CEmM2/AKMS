---
id: solver-imex-splitting
title: IMEX Time Integration for Coupled Problems
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- IMEX
- ARK
- time-integration
- splitting
- hughes-1978
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-explicit-dynamics
  type: refines
  weight: 0.7
- to: solver-newmark-hht
  type: refines
  weight: 0.7
- to: pf-explicit-time-integration
  type: feeds-into
  weight: 0.5
- to: solver-jfnk
  type: feeds-into
  weight: 0.5
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# IMEX Time Integration for Coupled Problems

## Summary

Implicit-explicit (IMEX) time integration schemes partition computational domains or discretized governing equations into implicit and explicit element groups. Originated by Hughes and Liu (1978) for structural dynamics and transient wave propagation, IMEX methods apply implicit Newmark integration to stiff or complex structural regions while using explicit time stepping with diagonal mass matrices on remaining domains, balancing numerical stability with computational efficiency.

## 1. Core Concept

Transient finite element analysis often involves heterogeneous mesh regions where stiff elements or complex material models require small time steps if integrated explicitly, whereas large unstructured mesh domains are efficiently solved explicitly without global linear matrix factorizations. Implicit-explicit (IMEX) formulations partition the mesh arrays into implicit (I) and explicit (E) element groups, splitting global mass, damping, stiffness, and internal force vectors into M = M^I + M^E, C = C^I + C^E, K = K^I + K^E, and F = F^I + F^E. The explicit group utilizes a diagonal mass matrix M^E and predictor-corrector time stepping, while the implicit group forms an effective stiffness matrix (K^*)^I = \frac{1}{\beta \Delta t^2} M^I + \frac{\gamma}{\beta \Delta t} C^I + K^I. Coupling implicit and explicit groups produces an effective global stiffness K^* = (K^*)^I + (K^*)^E where explicit element contributions reduce to diagonal mass scaling \frac{1}{\beta \Delta t^2} M^E, dramatically reducing global matrix profile size while restricting the Courant stability limit solely to explicit mesh elements.

## 2. Mathematical Formulation

**imex-array-partitioning**
$$
M = M^I + M^E, \quad C = C^I + C^E, \quad K = K^I + K^E, \quad F = F^I + F^E
$$
_Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 1, p. 375, Eqs. 13-15_

**imex-effective-stiffness-matrix**
$$
K^* = (K^*)^I + (K^*)^E \quad \text{where } (K^*)^I = \frac{1}{\beta \Delta t^2} M^I + \frac{\gamma}{\beta \Delta t} C^I + K^I, \quad (K^*)^E = \frac{1}{\beta \Delta t^2} M^E
$$
_Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 2, p. 376, Eqs. 21-23_

**imex-effective-force-vector**
$$
F_{n+1}^* = (F_{n+1}^*)^I + (F_{n+1}^*)^E
$$
_Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 2, p. 376, Eqs. 24-26_

**imex-explicit-group-courant-stability**
$$
\Omega = \omega \Delta t \le \frac{(\xi^2 + 2\gamma)^{1/2} - \xi}{\gamma}
$$
_Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 1, p. 376, Eq. 18_

**Notation:**
M, C, K represent global mass, damping, and stiffness matrices; M^I, C^I, K^I represent implicit element group matrices; M^E, C^E, K^E represent explicit element group matrices; d_n, v_n, a_n represent nodal displacement, velocity, and acceleration vectors; \tilde{d}_{n+1}, \tilde{v}_{n+1} represent predictor displacement and velocity vectors; \Delta t represents time step size; \gamma, \beta represent Newmark time integration parameters.


## 3. Algorithmic Implementation

**hughes-liu-imex-transient-algorithm**
$$
\begin{algorithmic}
\State $\text{Partition mesh elements into implicit group } I \text{ and explicit group } E \text{ with diagonal mass } M^E$
\State $\text{Form effective stiffness } K^* = (K^*)^I + (K^*)^E \text{ where } (K^*)^I = \frac{1}{\beta \Delta t^2} M^I + \frac{\gamma}{\beta \Delta t} C^I + K^I \text{ and } (K^*)^E = \frac{1}{\beta \Delta t^2} M^E$
\For{$n = 0, 1, 2, \dots \text{ until } t_n \ge t_{\text{final}}$}
\State $\tilde{d}_{n+1} = d_n + \Delta t v_n + \frac{\Delta t^2}{2} (1 - 2\beta) a_n \quad \text{(displacement predictor)}$
\State $\tilde{v}_{n+1} = v_n + \Delta t (1 - \gamma) a_n \quad \text{(velocity predictor)}$
\State $\text{Assemble effective force } F_{n+1}^* = (F_{n+1}^*)^I + (F_{n+1}^*)^E$
\State $\text{Solve } K^* d_{n+1} = F_{n+1}^* \text{ for displacement } d_{n+1}$
\State $a_{n+1} = \frac{1}{\beta \Delta t^2} (d_{n+1} - \tilde{d}_{n+1}) \quad \text{(acceleration corrector)}$
\State $v_{n+1} = \tilde{v}_{n+1} + \gamma \Delta t a_{n+1} \quad \text{(velocity corrector)}$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 2, p. 376_


## 4. Known Pitfalls

- **explicit-element-group-courant-instability**: In IMEX time integration, while the implicit element group is unconditionally stable, the time step size \Delta t remains conditionally bounded by the highest natural frequency \omega_{\max} of the explicit element group E according to \omega \Delta t \le ((\xi^2 + 2\gamma)^{1/2} - \xi) / \gamma. Accidental inclusion of extremely stiff or refined elements in the explicit group causes catastrophic numerical instability. _(Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 1, p. 376)_
- **nondiagonal-explicit-mass-matrix-breakdown**: The efficiency of explicit element evaluation in IMEX formulations requires the explicit mass matrix M^E to be strictly diagonal (lumped). Utilizing a consistent non-diagonal mass matrix in explicit element groups forces matrix inversions across explicit mesh domains, destroying the computational advantage of IMEX partitioning. _(Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 1, p. 375)_

## References

- Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf
- Mass_Scaling.pdf
- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
