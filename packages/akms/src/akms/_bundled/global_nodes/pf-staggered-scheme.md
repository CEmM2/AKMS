---
id: pf-staggered-scheme
title: Staggered (Alternate Minimization) Scheme for Phase-Field Fracture
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- staggered
- alternate-minimization
- miehe
- history-variable
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-at2-regularization
  type: feeds-into
  weight: 0.5
- to: pf-at1-regularization
  type: feeds-into
  weight: 0.5
- to: pf-monolithic-scheme
  type: contradicts
  weight: 0.0
- to: pf-spectral-split
  type: requires
  weight: 1.0
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Staggered (Alternate Minimization) Scheme for Phase-Field Fracture

## Summary

The staggered (alternate minimization / operator split) scheme is an iterative decoupling algorithm for solving the non-linear coupled equations of phase-field fracture mechanics. Developed by Bourdin et al. (2000, 2008) and adapted by Miehe et al. (2010), the scheme decouples mechanical momentum balance for displacement u and microforce balance for damage d into two separate, strictly convex sub-problems solved alternatingly within each load increment. Damage irreversibility \dot{d} \ge 0 is efficiently enforced by passing a historical maximum strain energy release rate field \mathcal{H} between sub-problems. Although the staggered scheme is highly robust against divergence and avoids the non-convex energy states that cause standard Newton monolithic schemes to fail, its first-order (Gauss-Seidel) convergence rate makes it computationally inefficient, frequently requiring over 1,000 iterations per increment during rapid crack propagation.

## 1. Core Concept

The total free energy functional in phase-field fracture is non-convex with respect to displacement u and phase-field damage d simultaneously, causing standard monolithic Newton-Raphson solvers to diverge. The staggered (alternate minimization) scheme overcomes this by exploiting the partial convexity of the free energy functional with respect to u and d individually. In each staggered iteration, the displacement sub-problem is solved for u holding d fixed, updating the strain energy field. Next, the maximum historical positive strain energy density \mathcal{H} = \max(\mathcal{H}_n, \psi_0^+) is evaluated at Gauss integration points to enforce damage irreversibility \dot{d} \ge 0 without box constraints, and the linear damage sub-problem is solved for d holding u fixed. While the staggered algorithm exhibits exceptional numerical robustness, it suffers from a first-order convergence rate. During critical steps involving rapid crack nucleation, propagation, or multi-crack branching, the staggered scheme requires hundreds or thousands of iterations, incurring a 3x to 7x CPU penalty compared to monolithic quasi-Newton (BFGS) solvers.

## 2. Mathematical Formulation

**staggered_mechanical_subproblem**
$$
\mathbf{K}_{uu}(\mathbf{a}^{(k-1)}, \bar{\mathbf{a}}^{(k-1)}) \delta \mathbf{a} = \mathbf{r}_u(\mathbf{a}^{(k-1)}, \bar{\mathbf{a}}^{(k-1)}), \quad \mathbf{a}^{(k)} = \mathbf{a}^{(k-1)} + \delta \mathbf{a}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture_

**staggered_phase_field_subproblem**
$$
\mathbf{K}_{dd}(\bar{\mathbf{a}}^{(k-1)}) \delta \bar{\mathbf{a}} = \bar{\mathbf{r}}_d(\mathbf{a}^{(k)}, \bar{\mathbf{a}}^{(k-1)}), \quad \bar{\mathbf{a}}^{(k)} = \bar{\mathbf{a}}^{(k-1)} + \delta \bar{\mathbf{a}}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Tao et al. (2022), Phase-field modeling of 3D fracture in elasto-plastic solids_

**history_variable_irreversibility_enforcement**
$$
\mathcal{H}_{n+1}(\mathbf{x}) = \max\left( \mathcal{H}_n(\mathbf{x}), \psi_0^+(\boldsymbol{\epsilon}_{n+1}(\mathbf{x})) \right)
$$
_Source: Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method_

**staggered_over_relaxation_acceleration**
$$
d^{(k)} = \omega_{rel} \tilde{d}^{(k)} + (1 - \omega_{rel}) d^{(k-1)}, \quad \omega_{rel} > 1
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Farrell and Maurini (2017), Linear and nonlinear solvers for variational phase-field models of brittle fracture_

**Notation:**
\mathbf{a}: nodal displacement degrees of freedom; \bar{\mathbf{a}}, d: nodal and scalar phase-field damage variables; \mathbf{K}_{uu}, \mathbf{K}_{dd}: mechanical and damage tangent stiffness matrices; \mathbf{r}_u, \bar{\mathbf{r}}_d: mechanical and damage residual vectors; \mathcal{H}: history variable field of maximum strain energy release rate; \psi_0^+: positive elastic strain energy density; \omega_{rel}: over-relaxation acceleration parameter; k: staggered iteration index.


## 3. Algorithmic Implementation

**iterative-staggered-alternate-minimization-solver**
$$
\begin{algorithmic}
\State $At load step n+1, initialize solution guesses \mathbf{a}^{(0)} = \mathbf{a}_n, \bar{\mathbf{a}}^{(0)} = \bar{\mathbf{a}}_n, and iteration counter k = 1.$
\While{$Residual/damage change norm \max(\|\mathbf{r}_u\|, \|\bar{\mathbf{r}}_d\|) > \text{tol} \text{ or } \|\bar{\mathbf{a}}^{(k)} - \bar{\mathbf{a}}^{(k-1)}\|_\infty > \text{tol}_d.$}
\State $Solve mechanical displacement sub-problem for \mathbf{a}^{(k)} with fixed damage \bar{\mathbf{a}}^{(k-1)}: \mathbf{K}_{uu}(\bar{\mathbf{a}}^{(k-1)}) \delta \mathbf{a} = \mathbf{r}_u(\mathbf{a}^{(k-1)}, \bar{\mathbf{a}}^{(k-1)}), set \mathbf{a}^{(k)} = \mathbf{a}^{(k-1)} + \delta \mathbf{a}.$
\State $At element Gauss integration points, evaluate updated strains \boldsymbol{\epsilon}^{(k)} = \mathbf{B} \mathbf{a}^{(k)} and update history variable field: \mathcal{H}_{n+1}^{(k)} = \max(\mathcal{H}_n, \psi_0^+(\boldsymbol{\epsilon}^{(k)})).$
\State $Solve damage sub-problem for \bar{\mathbf{a}}^{(k)} with fixed displacement \mathbf{a}^{(k)} and updated history \mathcal{H}_{n+1}^{(k)}: \mathbf{K}_{dd} \delta \bar{\mathbf{a}} = \bar{\mathbf{r}}_d(\mathbf{a}^{(k)}, \bar{\mathbf{a}}^{(k-1)}), set \bar{\mathbf{a}}^{(k)} = \bar{\mathbf{a}}^{(k-1)} + \delta \bar{\mathbf{a}}.$
\If{$Over-relaxation acceleration is enabled.$}
\State $Apply over-relaxation update: \bar{\mathbf{a}}^{(k)} \leftarrow \omega_{rel} \bar{\mathbf{a}}^{(k)} + (1 - \omega_{rel}) \bar{\mathbf{a}}^{(k-1)} \text{ with } \omega_{rel} > 1.$
\EndIf
\State $Increment iteration counter k \leftarrow k + 1.$
\EndWhile
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Bourdin et al. (2000, 2008)_


## 4. Known Pitfalls

- **staggered-solver-extreme-computational-inefficiency**: Because the staggered scheme decouples displacement and damage into a non-linear Gauss-Seidel iteration, convergence becomes extremely slow during unstable crack initiation and rapid propagation increments. In complex boundary value problems, the staggered algorithm frequently requires over 1,000 iterations per increment to achieve residual convergence, resulting in CPU runtimes 3x to 7x longer than monolithic quasi-Newton (BFGS) solvers. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory)_
- **one-pass-staggered-energy-error-accumulation**: Using a one-pass (non-iterative) staggered scheme where displacement and damage sub-problems are solved only once per increment without checking global convergence can lead to severe energy conservation errors and artificial delay of crack propagation unless extremely small time steps (\Delta t < 10^{-5}) are used. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method)_
- **loose-tolerance-staggered-stagnation**: Setting loose convergence tolerances in the staggered inner loop causes premature termination before displacement and damage fields reach mutual equilibrium. This introduces artificial numerical toughening, incorrect crack branching trajectories, or non-physical residual stresses across localized damage zones. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory)_

## References

- Bourdin, B., Francfort, G. A., and Marigo, J.-J. (2000). Numerical experiments in revisited brittle fracture. Journal of the Mechanics and Physics of Solids, 48(4), 797-826.
- Bourdin, B., Francfort, G. A., and Marigo, J.-J. (2008). The variational approach to fracture. Journal of Elasticity, 91(1-3), 5-148.
- Miehe, C., Hofacker, M., and Welschinger, F. (2010). Thermodynamically consistent phase-field models of fracture: Variational principles and multi-field FE implementations. International Journal for Numerical Methods in Engineering, 83(10), 1273-1311.
- Wu, J.-Y., and Huang, Y. (2020). Comprehensive implementations of phase-field damage models in Abaqus. Theoretical and Applied Fracture Mechanics, 106, 102440.
- Wu, J.-Y., Huang, Y., and Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase field damage theory. Computer Methods in Applied Mechanics and Engineering, 360, 112704.
- Molnar, G., Gravouil, A., Seghir, R., and Réthoré, J. (2020). An open-source Abaqus implementation of the phase-field method to study the effect of plasticity on the instantaneous fracture toughness in dynamic crack propagation. Computer Methods in Applied Mechanics and Engineering, 365, 113004.
- Tao, Z., Li, X., Tao, S., and Chen, Z. (2022). Phase-field modeling of 3D fracture in elasto-plastic solids based on the shear-modified GTN model and Abaqus subroutines UEL/UMAT. Engineering Fracture Mechanics, 260, 108196.
- Alessi, R., Marigo, J.-J., Maurini, C., and Vidoli, S. (2018). Coupling damage and plasticity for a phase-field regularisation of brittle, cohesive and ductile fracture: One-dimensional examples. International Journal of Mechanical Sciences, 149, 559-576.
