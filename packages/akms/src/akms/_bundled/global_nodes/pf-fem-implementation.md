---
id: pf-fem-implementation
title: 'Phase-Field FEM: Weak Forms, Element Residuals, Mesh Requirements'
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- FEM
- weak-form
- element-residual
- mesh-requirement
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-at2-regularization
  type: feeds-into
  weight: 0.5
- to: pf-staggered-scheme
  type: feeds-into
  weight: 0.5
- to: fem-tl-weak-form
  type: requires
  weight: 1.0
- to: pf-abaqus-umat-uel
  type: feeds-into
  weight: 0.5
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Phase-Field FEM: Weak Forms, Element Residuals, Mesh Requirements

## Summary

Finite element method (FEM) implementation framework for coupled phase-field fracture and damage mechanics. The continuum domain is spatially discretized using multi-field finite elements with C0-continuous isoparametric shape functions approximating both displacement u and scalar phase field d. The weak forms of mechanical momentum balance and diffusive phase-field evolution yield coupled algebraic residual vectors r_u and r_d. To prevent numerical locking and ensure convergence to the true sharp crack topology as regularization length scale b or l_c approaches zero, the finite element mesh size h inside the localization band B must satisfy h <= l_c / 2 (or h <= b/5). Damage irreversibility dot(d) >= 0 is efficiently enforced using historical maximum driving force fields H, avoiding complex active-set bound optimizations in standard FE solvers.

## 1. Core Concept

Implementing regularized phase-field fracture models within the finite element method requires solving a system of non-linear coupled partial differential equations governing mechanical equilibrium and diffusive crack interface evolution. In multi-field FE formulations, identical or compatible C0-continuous shape functions (e.g., bilinear quadrilateral Q4 or linear triangular T3 elements) interpolate nodal displacements a and nodal damage degrees of freedom a_bar. Derivation of element residuals and tangent stiffness matrices via Galerkin discretization reveals two primary computational challenges: (1) non-convexity of the total energy functional with respect to simultaneous variations of displacement and damage, which causes standard monolithic Newton-Raphson solvers to diverge during crack initiation and rapid propagation, and (2) strict spatial resolution demands, where element size h inside active damage bands must not exceed half the length scale l_c (h <= l_c/2) to prevent artificial mesh-alignment bias and locking. Staggered (alternate minimization) or quasi-Newton (BFGS) solvers, combined with history variable fields H = max(Y_0, max Y_tau) for damage irreversibility dot(d) >= 0, provide robust numerical convergence across brittle and ductile failure regimes.

## 2. Mathematical Formulation

**weak_form_mechanical_equilibrium**
$$
\int_{\Omega} \mathbf{B}^T \boldsymbol{\sigma} d\Omega - \mathbf{f}_{ext} = \mathbf{0}, \quad \boldsymbol{\sigma} = \omega(d) \bar{\boldsymbol{\sigma}}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture_

**weak_form_phase_field_evolution**
$$
\int_{B} \left[ \bar{\mathbf{N}}^T \left(-\omega'(d) \mathcal{H} + \frac{G_f}{c_{\alpha} b} \alpha'(d)\right) + \frac{2b}{c_{\alpha}} G_f \bar{\mathbf{B}}^T \nabla d \right] d\Omega = \mathbf{0}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**discretized_element_residuals**
$$
\mathbf{r}_u = \mathbf{f}_{ext} - \int_{\Omega} \mathbf{B}^T \boldsymbol{\sigma} d\Omega, \quad \mathbf{r}_d = \int_{B} \left[ \bar{\mathbf{N}}^T \left( \omega'(d)\mathcal{H} + \frac{G_f}{c_{\alpha} b} \alpha'(d) \right) - \bar{\mathbf{B}}^T \mathbf{q} \right] d\Omega
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Tao et al. (2022), Phase-field modeling of 3D fracture in elasto-plastic solids_

**mesh_resolution_requirement**
$$
h \le \frac{1}{2} l_c \quad \text{or} \quad h \le \frac{1}{5} b
$$
_Source: Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Zhang et al. (2023), Phase-field modeling of coupled spall and adiabatic shear banding_

**Notation:**
\mathbf{u}: displacement vector; d: scalar phase-field damage variable (d \in); \mathbf{a}: nodal displacement degrees of freedom; \bar{\mathbf{a}}: nodal phase-field degrees of freedom; \mathbf{N}, \bar{\mathbf{N}}: shape function matrices for displacement and phase field; \mathbf{B}, \bar{\mathbf{B}}: spatial gradient matrices for displacement and phase field; \boldsymbol{\sigma}: degraded Cauchy stress tensor; \bar{\boldsymbol{\sigma}}: undamaged effective stress tensor; \omega(d): energetic degradation function; \alpha(d): geometric crack function; b, l_c: regularization length scale parameters; c_{\alpha}: geometric scaling constant; G_f: critical fracture energy density; \mathcal{H}: energy release rate history field; h: finite element mesh size; \mathbf{r}_u, \mathbf{r}_d: global residual vectors.


## 3. Algorithmic Implementation

**fe-spatial-discretization-and-residual-assembly**
$$
\begin{algorithmic}
\State $Define multi-field finite element mesh \mathcal{T}_h subdividing domain \Omega into elements e \in \mathcal{E} with nodal displacement DOFs \mathbf{a} and phase-field DOFs \bar{\mathbf{a}}.$
\For{$Loop over finite elements e = 1, 2, \dots, N_e.$}
\State $At Gauss integration points, evaluate shape function matrices \mathbf{N}, \bar{\mathbf{N}} and gradient matrices \mathbf{B}, \bar{\mathbf{B}}.$
\State $Interpolate strain \boldsymbol{\epsilon}^h = \mathbf{B} \mathbf{a}^e, phase field d^h = \bar{\mathbf{N}} \bar{\mathbf{a}}^e, and phase-field gradient \nabla d^h = \bar{\mathbf{B}} \bar{\mathbf{a}}^e.$
\State $Compute effective energy release rate \bar{Y} = \frac{\bar{\sigma}_{eq}^2}{2 E_0} and update history field \mathcal{H} = \max(\mathcal{H}_n, \bar{Y}).$
\State $Evaluate degraded Cauchy stress \boldsymbol{\sigma} = \omega(d^h) \bar{\boldsymbol{\sigma}} and damage microforce flux \mathbf{q} = \frac{2b}{c_\alpha} G_f \nabla d^h.$
\State $Assemble element displacement residual \mathbf{r}_u^e = \mathbf{f}_{ext}^e - \int_{\Omega_e} \mathbf{B}^T \boldsymbol{\sigma} d\Omega and element phase-field residual \mathbf{r}_d^e = \int_{B_e} \left[ \bar{\mathbf{N}}^T Q(d^h) - \bar{\mathbf{B}}^T \mathbf{q} \right] d\Omega.$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture; Tao et al. (2022), Phase-field modeling of 3D fracture in elasto-plastic solids_


## 4. Known Pitfalls

- **insufficient-mesh-resolution-locking-and-bias**: If the element size h in the expected crack localization zone exceeds l_c/2 or b/5, the spatial discretization fails to resolve the continuous phase-field gradient \nabla d. This results in severe mesh-bias, artificial overestimation of peak structural strength, and numerical locking. _(Source: Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Zhang et al. (2023), Phase-field modeling of coupled spall and adiabatic shear banding)_
- **monolithic-newton-divergence-from-non-convexity**: Standard monolithic Newton-Raphson solvers frequently fail to converge during crack initiation and rapid propagation increments. This instability stems from the non-convexity of the coupled energy functional with respect to u and d simultaneously. Solvers must utilize staggered alternate minimization, line search, or quasi-Newton (BFGS) algorithms. _(Source: Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture)_
- **tangent-matrix-asymmetry-in-hybrid-formulations**: In hybrid phase-field formulations where the history variable field \mathcal{H} replaces the instantaneous strain energy in the damage sub-problem to enforce damage irreversibility \dot{d} \ge 0, the inter-field coupling stiffness matrices K_{ud} and K_{du} are unsymmetric (K_{ud} \neq K_{du}^T). Solving monolithic systems with standard symmetric linear solvers causes non-convergence. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory)_

## References

- Wu, J.-Y., and Huang, Y. (2020). Comprehensive implementations of phase-field damage models in Abaqus. Theoretical and Applied Fracture Mechanics, 106, 102440.
- Wu, J.-Y., Huang, Y., and Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase field damage theory. Computer Methods in Applied Mechanics and Engineering, 360, 112704.
- Miehe, C., Hofacker, M., and Welschinger, F. (2010). Thermodynamically consistent phase-field models of fracture: Variational principles and multi-field FE implementations. International Journal for Numerical Methods in Engineering, 83(10), 1273-1311.
- Tao, Z., Li, X., Tao, S., and Chen, Z. (2022). Phase-field modeling of 3D fracture in elasto-plastic solids based on the modified GTN theory and Abaqus subroutines UEL/UMAT. Engineering Fracture Mechanics, 260, 108196.
- Wang, T., Ye, X., Liu, Z., Liu, X., Chu, D., and Zhuang, Z. (2020). A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration. Computational Mechanics, 65(5), 1305-1321.
- Zhang, H., Peng, H., Pei, X.-Y., Wu, J.-Y., Li, P., Tang, T.-G., Cai, L.-C., Li, Y., and Liu, H. (2023). Phase-field modeling of coupled spall and adiabatic shear banding and simulation of complex cracks in ductile metals. Journal of the Mechanics and Physics of Solids, 172, 105186.
