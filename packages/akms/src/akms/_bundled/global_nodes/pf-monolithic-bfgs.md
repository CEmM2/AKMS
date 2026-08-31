---
id: pf-monolithic-bfgs
title: L-BFGS Monolithic Solver for Phase-Field Fracture
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- l-bfgs
- quasi-newton
- monolithic
- wu-2020
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-monolithic-scheme
  type: refines
  weight: 0.7
- to: pf-staggered-scheme
  type: contradicts
  weight: 0.0
- to: pf-fem-implementation
  type: feeds-into
  weight: 0.5
- to: pf-abaqus-umat-uel
  type: feeds-into
  weight: 0.5
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# L-BFGS Monolithic Solver for Phase-Field Fracture

## Summary

Monolithic Broyden-Fletcher-Goldfarb-Shanno (BFGS) quasi-Newton solver framework for coupled phase-field fracture mechanics. Traditional monolithic Newton-Raphson solvers diverge during crack initiation due to the non-convexity of the total energy functional with respect to simultaneous displacement and damage variations. While alternating minimization (staggered) solvers are robust, they require hundreds to thousands of iterations per increment during rapid crack propagation. The BFGS quasi-Newton monolithic algorithm resolves this by updating the inverse stiffness matrix using rank-two secant updates starting from an uncoupled, block-diagonal symmetric positive-definite initial matrix \tilde{\mathbf{K}}^{(0)} = \text{diag}(\mathbf{K}_{uu}, \mathbf{K}_{dd}). Applied across brittle fracture (AT1, AT2) and quasi-brittle failure (PF-CZM), the BFGS algorithm achieves identical solutions to staggered solvers with 3x-7x CPU time reductions and typical iteration counts of 10-50 per increment (reaching 100-300 during critical crack propagation steps). In commercial software such as Abaqus, the solver is activated using standard built-in keywords (*SOLUTION TECHNIQUE, TYPE=QUASI-NEWTON) combined with User Element (UEL) formulations.

## 1. Core Concept

In regularized phase-field fracture modeling, the total free energy functional E(\mathbf{u}, d) is strictly convex with respect to \mathbf{u} and d individually, but non-convex with respect to both fields simultaneously. Consequently, full Newton-Raphson monolithic schemes exhibit severe convergence failures due to negative eigenvalues in the coupled tangent stiffness. The BFGS quasi-Newton monolithic approach overcomes non-convexity by maintaining a symmetric, positive-definite approximation of the inverse stiffness matrix \tilde{\mathbf{K}}^{-1}. Starting each step or reformulating after a threshold of iterations (e.g., 8-10) with an uncoupled block-diagonal initial stiffness \tilde{\mathbf{K}}^{(0)} containing mechanical stiffness \mathbf{K}_{uu} and damage stiffness \mathbf{K}_{dd}, the algorithm updates the inverse operator via rank-two matrix corrections based on residual difference vectors \delta \mathbf{g} and solution increment vectors \delta \mathbf{z}. For PF-CZM models, positive-definiteness of \mathbf{K}_{dd} is guaranteed provided the regularization length scale satisfies b \le l_{ch} / 3 (where l_{ch} = E_0 G_f / f_t^2). In finite element packages like Abaqus, the BFGS solver operates via built-in Quasi-Newton solution keywords or UEL subroutines, avoiding the need for complex inter-field coupling derivatives while drastically outperforming staggered solvers.

## 2. Mathematical Formulation

**bfgs_coupled_residual_system**
$$
\mathbf{g}(\mathbf{z}) = \begin{Bmatrix} \mathbf{r}_u(\mathbf{a}, \bar{\mathbf{a}}) \\ \mathbf{r}_d(\mathbf{a}, \bar{\mathbf{a}}) \end{Bmatrix} = \mathbf{0}, \quad \mathbf{z} = \begin{Bmatrix} \mathbf{a} \\ \bar{\mathbf{a}} \end{Bmatrix}
$$
_Source: Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus_

**bfgs_initial_uncoupled_stiffness**
$$
\tilde{\mathbf{K}}^{(0)} = \begin{bmatrix} \mathbf{K}_{uu} & \mathbf{0} \\ \mathbf{0} & \mathbf{K}_{dd} \end{bmatrix}
$$
_Source: Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus_

**bfgs_rank_two_inverse_update**
$$
\tilde{\mathbf{K}}_{k+1}^{-1} = \left(\mathbf{I} - \frac{\delta \mathbf{z} \delta \mathbf{g}^T}{\delta \mathbf{z}^T \delta \mathbf{g}}\right) \tilde{\mathbf{K}}_k^{-1} \left(\mathbf{I} - \frac{\delta \mathbf{g} \delta \mathbf{z}^T}{\delta \mathbf{z}^T \delta \mathbf{g}}\right) + \frac{\delta \mathbf{z} \delta \mathbf{z}^T}{\delta \mathbf{z}^T \delta \mathbf{g}}
$$
_Source: Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus_

**pf_czm_positive_definiteness_condition**
$$
b \le \frac{4}{\pi} \left( a_2 + p + \frac{1}{2} \right) l_{ch} \implies b \le \frac{1}{3} l_{ch} = \frac{1}{3} \frac{E_0 G_f}{f_t^2}
$$
_Source: Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus_

**Notation:**
\mathbf{z}: unified nodal solution vector; \mathbf{a}: nodal displacement degrees of freedom; \bar{\mathbf{a}}: nodal damage degrees of freedom; \mathbf{r}_u, \mathbf{r}_d: displacement and damage residual vectors; \mathbf{g}: coupled global residual vector; \tilde{\mathbf{K}}^{(0)}: uncoupled initial block-diagonal stiffness matrix; \mathbf{K}_{uu}, \mathbf{K}_{dd}: mechanical and damage element tangent matrices; \delta \mathbf{z}: solution correction vector; \delta \mathbf{g}: residual change vector; b: regularization length scale parameter; l_{ch}: Irwin characteristic length.


## 3. Algorithmic Implementation

**bfgs-monolithic-phase-field-solver**
$$
\begin{algorithmic}
\State $At time step n+1, initialize iteration counter k = 0, solution guess \mathbf{z}^{(0)} = \mathbf{z}_n, and calculate initial coupled residual \mathbf{g}^{(0)} = [\mathbf{r}_u(\mathbf{z}^{(0)})^T, \mathbf{r}_d(\mathbf{z}^{(0)})^T]^T.$
\State $Evaluate uncoupled block-diagonal initial stiffness matrix \tilde{\mathbf{K}}^{(0)} = \text{diag}(\mathbf{K}_{uu}(\mathbf{z}^{(0)}), \mathbf{K}_{dd}(\mathbf{z}^{(0)})) and invert to obtain \tilde{\mathbf{K}}^{(0)-1}.$
\While{$Residual norm \|\mathbf{g}^{(k)}\| > \text{tol} \cdot \tilde{q}_{force}.$}
\State $Compute search direction step: \delta \mathbf{z} = \tilde{\mathbf{K}}^{(k)-1} \mathbf{g}^{(k)}.$
\State $Perform line search with step length parameter s \in (0, 1] to satisfy residual reduction: \mathbf{z}^{(k+1)} = \mathbf{z}^{(k)} + s \delta \mathbf{z}.$
\State $Update integration point strain energy \bar{Y} and history variable field: \mathcal{H}_{n+1} = \max(\mathcal{H}_n, \bar{Y}).$
\State $Evaluate updated global residual vector \mathbf{g}^{(k+1)} and residual increment \delta \mathbf{g} = \mathbf{g}^{(k+1)} - \mathbf{g}^{(k)}.$
\If{$Iteration counter k \text{ mod } N_{reform} == 0 (e.g., N_{reform} = 8).$}
\State $Re-evaluate and invert uncoupled block-diagonal matrix: \tilde{\mathbf{K}}^{(k+1)-1} = \text{diag}(\mathbf{K}_{uu}^{-1}, \mathbf{K}_{dd}^{-1}).$
\Else
\EndIf
\State $Increment iteration counter k \leftarrow k + 1.$
\EndWhile
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus_


## 4. Known Pitfalls

- **bfgs-matrix-indefiniteness-from-excessive-length-scale**: For cohesive phase-field models (PF-CZM), if the regularization length scale b exceeds Irwin's characteristic material bound b > l_ch / 3, the damage tangent stiffness matrix \mathbf{K}_{dd} loses positive-definiteness upon damage initiation (-\partial Q / \partial d < 0). This causes the BFGS inverse stiffness approximation \tilde{\mathbf{K}}^{-1} to become indefinite, leading to convergence failures. _(Source: Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus)_
- **misjudging-bfgs-iteration-counts-during-rapid-crack-propagation**: Assuming BFGS monolithic solvers converge in 5-15 iterations across all steps leads to improper time step controls. While BFGS requires only 10-50 iterations per increment during elastic loading and steady crack growth, critical increments with rapid crack propagation or multi-crack branching can require 100-300 iterations per increment. Setting Abaqus default iteration cutoffs too low causes unnecessary step cutbacks. _(Source: Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus)_
- **unneeded-interfield-coupling-derivatives-in-uel**: Attempting to manually derive and assemble off-diagonal coupled stiffness terms \mathbf{K}_{ud} and \mathbf{K}_{du} in UEL subroutines is unnecessary and error-prone. The BFGS monolithic scheme starts with uncoupled diagonal blocks \mathbf{K}_{uu} and \mathbf{K}_{dd} and automatically builds inter-field coupling via rank-two secant updates \delta \mathbf{z} and \delta \mathbf{g}. _(Source: Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus)_

## References

- Wu, J.-Y., Huang, Y., and Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase field damage theory. Computer Methods in Applied Mechanics and Engineering, 360, 112704.
- Wu, J.-Y., and Huang, Y. (2020). Comprehensive implementations of phase-field damage models in Abaqus. Theoretical and Applied Fracture Mechanics, 106, 102440.
- Miehe, C., Hofacker, M., and Welschinger, F. (2010). Thermodynamically consistent phase-field models of fracture: Variational principles and multi-field FE implementations. International Journal for Numerical Methods in Engineering, 83(10), 1273-1311.
- Zhang, H., Pei, X.-Y., Peng, H., and Wu, J.-Y. (2021). Phase-field modeling of spontaneous shear bands in collapsing thick-walled cylinders. Engineering Fracture Mechanics, 249, 107706.
