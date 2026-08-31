---
id: pf-abaqus-umat-uel
title: Phase-Field Implementation in Abaqus (UEL/UMAT)
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- abaqus
- UEL
- UMAT
- molnar-2017
- wu-huang-2020
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-fem-implementation
  type: refines
  weight: 0.7
- to: pf-staggered-scheme
  type: feeds-into
  weight: 0.5
- to: pf-monolithic-bfgs
  type: feeds-into
  weight: 0.5
- to: pf-benchmarks
  type: feeds-into
  weight: 0.5
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Phase-Field Implementation in Abaqus (UEL/UMAT)

## Summary

Comprehensive implementation framework for phase-field fracture and damage models in the commercial finite element suite Abaqus using User Element (UEL), User Material (UMAT), and thermo-mechanical analogy subroutines. The node covers three primary solution architectures: (1) UMAT-Newton-M using built-in thermal degrees of freedom and HETVAL/UMATHT subroutines for weakly coupled or modified Newton schemes, (2) UEL-Staggered using multi-layer user elements with dummy rotational degrees of freedom or global iteration counters to enforce alternate minimization, and (3) UEL-BFGS monolithic quasi-Newton implementations that combine high numerical robustness with 3x-7x computational speedups over staggered solvers. It also details multi-layer element topologies, dummy UMAT post-processing overlays for visualization in Abaqus/CAE, and elasto-plastic extensions combining von Mises or GTN damage criteria with phase-field energy degradation.

## 1. Core Concept

Implementation of non-local phase-field damage models in commercial finite element software (Abaqus) requires bridging the gap between built-in solver architectures and the coupled partial differential equations governing mechanical equilibrium and diffusive crack phase-field evolution. Because standard Newton monolithic schemes often fail due to the non-convexity of the total energy functional with respect to simultaneous displacement and damage variations, specialized implementation strategies are required. These include user-defined element (UEL) subroutines implementing the Broyden-Fletcher-Goldfarb-Shanno (BFGS) quasi-Newton algorithm with uncoupled initial block-diagonal stiffness matrices, multi-pass alternate minimization (staggered) solvers using dummy control degrees of freedom (e.g., DOF 6), and thermo-mechanical analogy routines (UMAT/HETVAL) mapping the phase-field variable to temperature and the thermodynamic driving force to internal heat generation. To overcome Abaqus UEL limitations regarding post-processing, a multi-layer element structure is used wherein fictitious Abaqus native elements with near-zero stiffness (dummy UMAT) share nodes with UELs to export solution-dependent state variables (SDVs) for visualization in Abaqus/CAE.

## 2. Mathematical Formulation

**mechanical_equilibrium_abaqus**
$$
\nabla \cdot \boldsymbol{\sigma} + \mathbf{b} = \rho \ddot{\mathbf{u}} \quad \text{with} \quad \boldsymbol{\sigma} = \omega(d) \bar{\boldsymbol{\sigma}}_d + \bar{\boldsymbol{\sigma}}_0
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method_

**phase_field_governing_equation**
$$
\frac{c_{\alpha}}{b} G_f \alpha'(d) - 2 b c_{\alpha} G_f \Delta d = -\omega'(d) \mathcal{H} + \eta \dot{d}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**history_field_definition**
$$
\mathcal{H}_{n+1} = \max\left(\mathcal{H}_n, \bar{Y}_{n+1}\right), \quad \bar{Y} = \frac{\bar{\sigma}_{eq}^2}{2 E_0} \quad \text{or} \quad \mathcal{H}_{n+1} = \max\left(\mathcal{H}_n, \psi_0^+ + \psi_0^{pl} - \psi_c\right)
$$
_Source: Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus_

**linearized_monolithic_system**
$$
\begin{bmatrix} \mathbf{K}_{uu} & \mathbf{K}_{ud} \\ \mathbf{K}_{du} & \mathbf{K}_{dd} \end{bmatrix} \begin{Bmatrix} \delta \mathbf{a} \\ \delta \bar{\mathbf{a}} \end{Bmatrix} = \begin{Bmatrix} \mathbf{r}_u \\ \mathbf{r}_d \end{Bmatrix}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**bfgs_initial_stiffness_and_update**
$$
\tilde{\mathbf{K}}^{(0)} = \begin{bmatrix} \mathbf{K}_{uu} & \mathbf{0} \\ \mathbf{0} & \mathbf{K}_{dd} \end{bmatrix}, \quad \tilde{\mathbf{K}}_{k+1}^{-1} = \left(\mathbf{I} - \frac{\delta \mathbf{z} \delta \mathbf{g}^T}{\delta \mathbf{z}^T \delta \mathbf{g}}\right) \tilde{\mathbf{K}}_k^{-1} \left(\mathbf{I} - \frac{\delta \mathbf{g} \delta \mathbf{z}^T}{\delta \mathbf{z}^T \delta \mathbf{g}}\right) + \frac{\delta \mathbf{z} \delta \mathbf{z}^T}{\delta \mathbf{z}^T \delta \mathbf{g}}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**thermal_analogy_source_term**
$$
Q(d) = \frac{c_{\alpha}}{2 b G_f} \omega'(d) \mathcal{H} + \frac{1}{c_{\alpha} b} \alpha'(d) G_f, \quad \text{with conductivity } k=1
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus_

**Notation:**
\mathbf{u}: displacement vector; d: scalar phase-field damage variable (d \in [1]); \boldsymbol{\sigma}: Cauchy stress tensor; \boldsymbol{\epsilon}: small strain tensor; \mathbf{B}: strain-displacement interpolation matrix; \bar{\mathbf{N}}, \bar{\mathbf{B}}: shape function matrix and gradient matrix for damage field; \mathbf{a}: nodal displacement degrees of freedom; \bar{\mathbf{a}}: nodal phase-field degrees of freedom; \mathcal{H}: history variable field; G_f: critical energy release rate; b, l_c: length scale parameter; \omega(d): degradation function; \alpha(d): crack geometric function; \mathbf{r}_u, \mathbf{r}_d: mechanical and phase-field residual vectors; \mathbf{z}: unified nodal solution vector; \text{SDV}: solution-dependent state variables in Abaqus.


## 3. Algorithmic Implementation

**uel-bfgs-monolithic**
$$
\begin{algorithmic}
\State $Initialize nodal displacement vector \mathbf{a}_0, phase-field vector \bar{\mathbf{a}}_0, combined solution vector \mathbf{z}_0 = \{\mathbf{a}_0, \bar{\mathbf{a}}_0\}^T, and element history field \mathcal{H}_0 = 0.$
\For{$Loop over load/time increments n = 1, 2, \dots, N_{steps}.$}
\State $Set iteration counter k = 0, initial trial solution \mathbf{z}_{n+1}^{(0)} = \mathbf{z}_n, and compute residual vector \mathbf{g}^{(0)} = [\mathbf{r}_u(\mathbf{z}_{n+1}^{(0)})^T, \mathbf{r}_d(\mathbf{z}_{n+1}^{(0)})^T]^T.$
\State $Assemble uncoupled block-diagonal initial stiffness matrix \tilde{\mathbf{K}}^{(0)} = \text{diag}(\mathbf{K}_{uu}(\mathbf{z}_{n+1}^{(0)}), \mathbf{K}_{dd}(\mathbf{z}_{n+1}^{(0)})) in UEL subroutine.$
\While{$Residual norm \|\mathbf{g}^{(k)}\| > \text{tol} \cdot \tilde{q}_{force}.$}
\State $Compute solution correction \delta \mathbf{z} = (\tilde{\mathbf{K}}^{(k)})^{-1} \mathbf{g}^{(k)} using quasi-Newton solver.$
\State $Update solution vector \mathbf{z}^{(k+1)} = \mathbf{z}^{(k)} + \delta \mathbf{z}.$
\State $At element Gauss integration points, evaluate strain \boldsymbol{\epsilon}^{(k+1)} = \mathbf{B} \mathbf{a}^{(k+1)}, effective strain energy \bar{Y}^{(k+1)}, and update history field \mathcal{H}_{n+1} = \max(\mathcal{H}_n, \bar{Y}^{(k+1)}).$
\State $Compute updated residual vector \mathbf{g}^{(k+1)} and change in residual \delta \mathbf{g} = \mathbf{g}^{(k+1)} - \mathbf{g}^{(k)}.$
\State $Update inverse stiffness matrix \tilde{\mathbf{K}}_{k+1}^{-1} using rank-two BFGS update formula.$
\State $Increment iteration counter k \leftarrow k + 1.$
\EndWhile
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**uel-staggered-dummy-dof**
$$
\begin{algorithmic}
\State $Read global solution counter isw passed from Abaqus solver framework to UEL subroutine.$
\If{$isw == -1 (Odd iteration: displacement sub-problem).$}
\State $Evaluate element displacement stiffness matrix \mathbf{K}_{uu} = \int_{\Omega} \mathbf{B}^T \boldsymbol{\sigma}_{tan} \mathbf{B} d\Omega and displacement residual \mathbf{r}_u = \mathbf{f}_{ext} - \int_{\Omega} \mathbf{B}^T \boldsymbol{\sigma} d\Omega.$
\State $Set dummy DOF 6 residual to a large penalty value (10^3) and set damage residuals \mathbf{r}_d = \mathbf{0} to force Abaqus to perform an additional iteration while keeping damage fixed.$
\Else
\State $Update element history field \mathcal{H} = \max(\mathcal{H}_n, \bar{Y}(\boldsymbol{\epsilon})).$
\State $Evaluate element damage stiffness matrix \mathbf{K}_{dd} and damage residual vector \mathbf{r}_d.$
\State $Set displacement residuals \mathbf{r}_u = \mathbf{0} and dummy DOF 6 residual to 0 to solve damage with fixed displacement.$
\EndIf
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus_

**multi-layer-postprocessing-overlay**
$$
\begin{algorithmic}
\State $Define Layer 1 elements (e.g., U1 or CPS4/C3D8) contributing stiffness to displacement DOFs (1, 2, 3).$
\State $Define Layer 2 elements (e.g., U2 or phase UEL) sharing identical nodes contributing stiffness to phase-field DOF (11).$
\State $Define Layer 3 overlaid elements sharing the same node connectivity using standard Abaqus solid elements (CPS4/C3D8) governed by a dummy UMAT with negligible stiffness E_{dummy} = 10^{-10} \text{ MPa}.$
\State $In Layer 1/Layer 2 subroutines, write integration point state variables (phase field d, equivalent plastic strain \varepsilon_{eq}^{pl}, stresses \boldsymbol{\sigma}, strain energy \psi^+) into a shared COMMON block or solution-dependent state variable array STATEV.$
\State $In Layer 3 UMAT subroutine, read shared SDV values and assign them to output SDV array for contour plotting in Abaqus/CAE Viewer.$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Tao et al. (2022), Phase-field modeling of 3D fracture in elasto-plastic solids based on the shear-modified GTN model_


## 4. Known Pitfalls

- **monolithic-newton-nonconvexity-divergence**: Standard Newton-Raphson monolithic algorithms in Abaqus frequently fail or diverge during crack initiation and propagation. This occurs because the total energy functional is non-convex with respect to displacement and damage fields simultaneously, causing negative eigenvalues in the coupled tangent matrix and numerical jumps. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method)_
- **staggered-solver-computational-inefficiency**: While the alternate minimization (staggered) scheme is robust, it converges extremely slowly in critical crack-propagation increments, often requiring over 1,000 iterations per increment and leading to prohibitive CPU runtimes (up to 7x slower than BFGS quasi-Newton monolithic solvers). _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory)_
- **fictitious-stiffness-volumetric-locking-under-compression**: Applying degraded elastic strain energy or improper strain energy splits under heavy hydrostatic compression can cause non-physical damage evolution or artificial volumetric locking. In compressive/shear fracture, energy splits must preserve compressive stiffness (e.g., spectral or deviatoric/volumetric splits) and use numerical stability parameters k \approx 10^{-8} to avoid zero-stiffness singularities at d=1. _(Source: Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture)_
- **postprocessing-visualization-limitation-in-uel**: User-defined elements (UEL) in Abaqus do not automatically export internal integration point state variables to Abaqus/CAE visualization databases (.odb). Bypassing this requires adding an overlaid layer of standard dummy elements with near-zero stiffness (dummy UMAT) or using post-processing scripts (e.g., Abaqus2Matlab) to transfer SDVs to nodal fields. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Tao et al. (2022), Phase-field modeling of 3D fracture in elasto-plastic solids)_

## References

- Wu, J.-Y., and Huang, Y. (2020). Comprehensive implementations of phase-field damage models in Abaqus. Theoretical and Applied Fracture Mechanics, 106, 102440.
- Molnar, G., Gravouil, A., Seghir, R., and Réthoré, J. (2020). An open-source Abaqus implementation of the phase-field method to study the effect of plasticity on the instantaneous fracture toughness in dynamic crack propagation. Computer Methods in Applied Mechanics and Engineering, 365, 113004.
- Tao, Z., et al. (2022). Phase-field modeling of 3D fracture in elasto-plastic solids based on the shear-modified GTN model and Abaqus subroutines UEL/UMAT. Engineering Fracture Mechanics, 260, 108196.
- Wu, J.-Y., Huang, Y., and Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase field damage theory. Computer Methods in Applied Mechanics and Engineering, 360, 112704.
- Wang, T., Ye, X., Liu, Z., Liu, X., Chu, D., and Zhuang, Z. (2020). A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration. Computational Mechanics, 65(5), 1305-1321.
- Miehe, C., Welschinger, F., and Hofacker, M. (2010). Thermodynamically consistent phase-field models of fracture: Variational principles and multi-field FE implementations. International Journal for Numerical Methods in Engineering, 83(10), 1273-1311.
