---
id: solver-newmark-hht
title: 'Implicit Dynamics: Newmark-β & HHT-α'
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- implicit-dynamics
- newmark
- HHT-alpha
- generalized-alpha
- dissipation
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-explicit-dynamics
  type: contradicts
  weight: 0.0
- to: solver-imex-splitting
  type: refines
  weight: 0.7
- to: solver-pcg-algorithm
  type: requires
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Implicit Dynamics: Newmark-β & HHT-α

## Summary

Implicit dynamic time integration methods, such as the Newmark-\beta family, solve discretized transient structural equations M \ddot{d} + C \dot{d} + K d = F using predictor-corrector time stepping. Controlled by parameters \gamma and \beta, implicit Newmark schemes achieve unconditional algorithmic stability when \gamma \ge 1/2 and \beta = (\gamma + 1/2)^2 / 4, enabling large integration time steps unrestricted by Courant-Friedrichs-Lewy (CFL) limits. Setting \gamma = 1/2 yields 2nd-order temporal accuracy without numerical damping, whereas \gamma > 1/2 introduces artificial high-frequency dissipation.

## 1. Core Concept

Implicit time integration for structural dynamics solves linear or non-linear semi-discretized equations of motion M a_{n+1} + C v_{n+1} + K d_{n+1} = F_{n+1}. In the classic Newmark-\beta method, displacement and velocity vectors are updated using predictor-corrector approximations governed by integration parameters \gamma \ge 1/2 and \beta \ge (\gamma + 1/2)^2 / 4. In each time step, displacement predictors \tilde{d}_{n+1} and velocity predictors \tilde{v}_{n+1} are evaluated from previous state variables. Substituting these predictors into the semi-discretized balance equation yields an effective linear system K^* d_{n+1} = F_{n+1}^* for updated displacement vector d_{n+1}, where effective tangent stiffness operator K^* = \frac{1}{\beta \Delta t^2} M + \frac{\gamma}{\beta \Delta t} C + K combines mass, damping, and stiffness arrays. Once displacement d_{n+1} is solved, acceleration corrector a_{n+1} and velocity corrector v_{n+1} are calculated. Unconditional stability permits larger time steps \Delta t compared to explicit central difference integration, though solving effective stiffness system K^* d_{n+1} = F_{n+1}^* requires factorizing sparse matrices or executing iterative Krylov solves (such as PCG) at every time step.

## 2. Mathematical Formulation

**newmark-displacement-velocity-predictors**
$$
\tilde{d}_{n+1} = d_n + \Delta t v_n + \frac{\Delta t^2}{2} (1 - 2\beta) a_n, \quad \tilde{v}_{n+1} = v_n + \Delta t (1 - \gamma) a_n
$$
_Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 2, p. 376, Eqs. 7-8_

**newmark-effective-stiffness-and-force**
$$
K^* d_{n+1} = F_{n+1}^* \quad \text{where } K^* = \frac{1}{\beta \Delta t^2} M + \frac{\gamma}{\beta \Delta t} C + K
$$
_Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 2, p. 376, Eqs. 20-22_

**newmark-acceleration-velocity-correctors**
$$
a_{n+1} = \frac{1}{\beta \Delta t^2} (d_{n+1} - \tilde{d}_{n+1}), \quad v_{n+1} = \tilde{v}_{n+1} + \gamma \Delta t a_{n+1}
$$
_Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 2, p. 376, Eqs. 4-5_

**newmark-unconditional-stability-condition**
$$
\gamma \ge \frac{1}{2}, \quad \beta = \frac{1}{4} \left(\gamma + \frac{1}{2}\right)^2
$$
_Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 1, p. 376, Eqs. 16-17_

**Notation:**
d_n, v_n, a_n represent nodal displacement, velocity, and acceleration vectors; \tilde{d}_{n+1}, \tilde{v}_{n+1} represent predictor displacement and velocity vectors; M, C, K represent mass, damping, and stiffness matrices; K^* represents effective tangent stiffness matrix; F_{n+1}^* represents effective load vector; \Delta t represents time step size; \gamma, \beta represent Newmark time integration parameters.


## 3. Algorithmic Implementation

**newmark-implicit-transient-algorithm**
$$
\begin{algorithmic}
\State $\text{Initialize } d_0, v_0, a_0, \text{ mass matrix } M, \text{ damping } C, \text{ stiffness } K, \text{ and parameters } \gamma \ge 1/2, \beta = \frac{1}{4}(\gamma + 1/2)^2$
\State $\text{Form effective stiffness matrix } K^* = \frac{1}{\beta \Delta t^2} M + \frac{\gamma}{\beta \Delta t} C + K$
\For{$n = 0, 1, 2, \dots \text{ until } t_n \ge t_{\text{final}}$}
\State $\tilde{d}_{n+1} = d_n + \Delta t v_n + \frac{\Delta t^2}{2} (1 - 2\beta) a_n \quad \text{(displacement predictor)}$
\State $\tilde{v}_{n+1} = v_n + \Delta t (1 - \gamma) a_n \quad \text{(velocity predictor)}$
\State $F_{n+1}^* = F_{n+1} + \frac{1}{\beta \Delta t^2} M \tilde{d}_{n+1} - C \left(\tilde{v}_{n+1} - \frac{\gamma \Delta t}{\beta \Delta t^2} \tilde{d}_{n+1}\right) \quad \text{(effective load vector)}$
\State $\text{Solve linear system } K^* d_{n+1} = F_{n+1}^* \text{ for displacement } d_{n+1} \text{ via PCG or direct solver}$
\State $a_{n+1} = \frac{1}{\beta \Delta t^2} (d_{n+1} - \tilde{d}_{n+1}) \quad \text{(acceleration corrector)}$
\State $v_{n+1} = \tilde{v}_{n+1} + \gamma \Delta t a_{n+1} \quad \text{(velocity corrector)}$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 2, p. 376_


## 4. Known Pitfalls

- **newmark-numerical-dissipation-order-reduction**: In implicit Newmark time integration, setting \gamma > 1/2 introduces artificial numerical damping to suppress spurious high-frequency oscillations, but reduces scheme temporal accuracy from 2nd-order down to 1st-order. _(Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 1, p. 376)_
- **ill-conditioned-effective-stiffness-at-small-dt**: When time step size \Delta t is extremely small, effective stiffness matrix K^* = \frac{1}{\beta \Delta t^2} M + \frac{\gamma}{\beta \Delta t} C + K becomes dominated by mass scaling term \frac{1}{\beta \Delta t^2} M, causing severe linear solver ill-conditioning if mass matrix M is poorly scaled. _(Source: Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf, Section 2, p. 376; Mass_Scaling.pdf, Section 1, p. 469)_

## References

- Hughes_Liu_1978_Implicit-Explicit Finite Elements in Transient Analysis.pdf
- Mass_Scaling.pdf
- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
