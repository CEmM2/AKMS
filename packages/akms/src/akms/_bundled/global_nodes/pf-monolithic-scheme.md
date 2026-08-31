---
id: pf-monolithic-scheme
title: Monolithic Coupled Newton Solver for Phase-Field Fracture
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- monolithic
- newton
- coupled-solver
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-staggered-scheme
  type: contradicts
  weight: 0.0
- to: pf-at2-regularization
  type: feeds-into
  weight: 0.5
- to: pf-monolithic-bfgs
  type: refines
  weight: 0.7
- to: pf-spectral-split
  type: requires
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Monolithic Coupled Newton Solver for Phase-Field Fracture

## Summary

Monolithic coupled Newton-Raphson solver framework for solving the non-linear simultaneous system of equations in phase-field fracture mechanics. In the monolithic formulation, mechanical equilibrium for displacement u and microforce balance for crack phase-field d are solved simultaneously in a single coupled algebraic system K \delta z = g. While monolithic Newton solvers achieve quadratic convergence when initial guesses lie within the convergence basin, standard Newton-Raphson schemes suffer from severe convergence difficulties and divergence during crack initiation and rapid crack growth due to the non-convexity of the total energy functional with respect to (u,d) jointly. Specialized globalization techniques such as non-conventional line searches (Gerasimov & De Lorenzis, 2016), modified Newton matrices (Wick, 2017), or primal-dual active set methods (Heister et al., 2015) are employed to stabilize monolithic Newton iterations, while full inter-field coupling tangents K_ud and K_du must be constructed.

## 1. Core Concept

The monolithic coupled solver approach formulates phase-field fracture as a unified initial boundary value problem where displacement degrees of freedom a and phase-field degrees of freedom \bar{a} are updated simultaneously using a fully coupled Jacobian matrix K. Owning to the variational formulation of rate-independent brittle fracture (Miehe et al., 2010), the monolithic tangent matrix is symmetric when derived from pure energy minimization. However, in hybrid formulations employing a historical energy field \mathcal{H} = \max(\mathcal{H}_n, \psi_0^+) to enforce damage irreversibility \dot{d} \ge 0, the off-diagonal coupling blocks K_ud and K_du become unsymmetric (K_ud \neq K_du^T). Although monolithic schemes possess full inter-field coupling and potential quadratic local convergence, their primary limitation is numerical instability: because the underlying free energy functional E(u,d) is non-convex with respect to displacement and damage fields simultaneously, standard Newton-Raphson solvers frequently fail to converge during crack initiation or abrupt crack propagation increments. In contrast to staggered solvers that often require over 1,000 iterations per increment in critical crack-propagation steps, monolithic Newton solvers require line-search stabilization or adaptive step-size controls to navigate non-convex energy landscapes.

## 2. Mathematical Formulation

**monolithic_coupled_residual**
$$
\mathbf{g}(\mathbf{z}) = \begin{Bmatrix} \mathbf{r}_u(\mathbf{a}, \bar{\mathbf{a}}) \\ \mathbf{r}_d(\mathbf{a}, \bar{\mathbf{a}}) \end{Bmatrix} = \mathbf{0}, \quad \mathbf{z} = \begin{Bmatrix} \mathbf{a} \\ \bar{\mathbf{a}} \end{Bmatrix}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**monolithic_newton_linearized_system**
$$
\begin{bmatrix} \mathbf{K}_{uu} & \mathbf{K}_{ud} \\ \mathbf{K}_{du} & \mathbf{K}_{dd} \end{bmatrix} \begin{Bmatrix} \delta \mathbf{a} \\ \delta \bar{\mathbf{a}} \end{Bmatrix} = \begin{Bmatrix} \mathbf{r}_u \\ \mathbf{r}_d \end{Bmatrix}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**monolithic_symmetric_tangent_variational**
$$
\mathbf{K} = \int_{\Omega} \mathbf{B}^T \frac{\partial^2 \psi(\boldsymbol{\epsilon}, d)}{\partial \mathbf{z} \partial \mathbf{z}} \mathbf{B} d\Omega
$$
_Source: Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture_

**Notation:**
\mathbf{z}: combined nodal solution vector \{\mathbf{a}, \bar{\mathbf{a}}\}^T; \mathbf{a}: nodal displacement vector; \bar{\mathbf{a}}: nodal phase-field damage vector; \mathbf{r}_u, \mathbf{r}_d: mechanical and damage residual vectors; \mathbf{g}: monolithic global residual vector; \mathbf{K}_{uu}, \mathbf{K}_{dd}: mechanical and damage tangent stiffness blocks; \mathbf{K}_{ud}, \mathbf{K}_{du}: inter-field coupling tangent blocks; \boldsymbol{\sigma}: Cauchy stress tensor; \boldsymbol{\epsilon}: strain tensor; d: phase-field damage variable; \mathcal{H}: historical maximum energy release rate field.


## 3. Algorithmic Implementation

**monolithic-coupled-newton-solver**
$$
\begin{algorithmic}
\State $At load step n+1, initialize solution vector \mathbf{z}^{(0)} = \{\mathbf{a}_n, \bar{\mathbf{a}}_n\}^T and iteration index k = 0.$
\For{$Loop over Newton-Raphson iterations k = 0, 1, 2, \dots, k_{max}.$}
\State $Evaluate element strain \boldsymbol{\epsilon}^{(k)} = \mathbf{B} \mathbf{a}^{(k)} and damage d^{(k)} = \bar{\mathbf{N}} \bar{\mathbf{a}}^{(k)} at integration points.$
\State $Update energy driving force \bar{Y}^{(k)} and damage history field \mathcal{H}_{n+1} = \max(\mathcal{H}_n, \bar{Y}^{(k)}).$
\State $Assemble monolithic residual vector \mathbf{g}^{(k)} = [\mathbf{r}_u(\mathbf{z}^{(k)})^T, \mathbf{r}_d(\mathbf{z}^{(k)})^T]^T.$
\If{$Residual norm \|\mathbf{g}^{(k)}\| \le \text{tol} \cdot \tilde{q}_{force} (Convergence criterion met).$}
\State $Accept step solution: \mathbf{z}_{n+1} = \mathbf{z}^{(k)}, \mathcal{H}_{n+1} = \max(\mathcal{H}_n, \bar{Y}^{(k)}), and exit iteration.$
\EndIf
\State $Assemble monolithic tangent stiffness matrix \mathbf{K}^{(k)} containing blocks \mathbf{K}_{uu}, \mathbf{K}_{ud}, \mathbf{K}_{du}, \mathbf{K}_{dd}.$
\State $Solve fully coupled linear system for Newton update: \mathbf{K}^{(k)} \delta \mathbf{z} = \mathbf{g}^{(k)}.$
\State $Perform line-search damping if required: \mathbf{z}^{(k+1)} = \mathbf{z}^{(k)} - s \cdot \delta \mathbf{z} with step length s \in (0, 1].$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture; Gerasimov and De Lorenzis (2016), A line search assisted monolithic approach for phase-field computing_


## 4. Known Pitfalls

- **monolithic-newton-divergence-from-nonconvexity**: The total free energy functional E(u,d) in phase-field fracture is non-convex with respect to simultaneous variations of displacement u and damage d. Consequently, standard monolithic Newton-Raphson algorithms frequently fail or diverge during crack initiation and rapid propagation increments unless line-search or quasi-Newton globalization techniques are used. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method)_
- **interfield-tangent-matrix-asymmetry-in-hybrid-formulations**: In hybrid phase-field formulations that use a history variable field \mathcal{H} to enforce damage irreversibility \dot{d} \ge 0, the off-diagonal inter-field coupling blocks are unsymmetric (\mathbf{K}_{ud} \neq \mathbf{K}_{du}^T). Applying symmetric linear solvers (e.g., standard CG) directly to the monolithic system causes numerical breakdown. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory)_
- **problem-dependent-composite-solver-switching**: Attempting to build composite solvers that alternate between staggered iterations and monolithic Newton iterations (e.g. Farrell & Maurini, 2017) introduces problem-dependent transition heuristics. If the switch threshold is miscalibrated, the solver reverts to divergent Newton steps during critical crack initiation stages. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Farrell and Maurini (2017), Linear and nonlinear solvers for variational phase-field models of brittle fracture)_

## References

- Wu, J.-Y., and Huang, Y. (2020). Comprehensive implementations of phase-field damage models in Abaqus. Theoretical and Applied Fracture Mechanics, 106, 102440.
- Wu, J.-Y., Huang, Y., and Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase field damage theory. Computer Methods in Applied Mechanics and Engineering, 360, 112704.
- Miehe, C., Hofacker, M., and Welschinger, F. (2010). Thermodynamically consistent phase-field models of fracture: Variational principles and multi-field FE implementations. International Journal for Numerical Methods in Engineering, 83(10), 1273-1311.
- Molnar, G., Gravouil, A., Seghir, R., and Réthoré, J. (2020). An open-source Abaqus implementation of the phase-field method to study the effect of plasticity on the instantaneous fracture toughness in dynamic crack propagation. Computer Methods in Applied Mechanics and Engineering, 365, 113004.
- Gerasimov, T., and De Lorenzis, L. (2016). A line search assisted monolithic approach for phase-field computing of brittle fracture. Computer Methods in Applied Mechanics and Engineering, 312, 276-303.
- Farrell, P., and Maurini, C. (2017). Linear and nonlinear solvers for variational phase-field models of brittle fracture. International Journal for Numerical Methods in Engineering, 109(5), 648-667.
- Wick, T. (2017). Modified Newton methods for solving fully monolithic phase-field quasi-static brittle fracture propagation. Computer Methods in Applied Mechanics and Engineering, 325, 577-611.
- Heister, T., Wheeler, M. F., and Wick, T. (2015). A primal-dual active set method and predictor-corrector mesh adaptivity for computing fracture propagation using a phase-field approach. Computer Methods in Applied Mechanics and Engineering, 290, 466-495.
