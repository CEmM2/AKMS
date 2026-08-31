---
id: pf-cohesive-zone
title: Cohesive Phase-Field Model (PF-CZM, Wu Unified Theory)
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- cohesive
- PF-CZM
- wu
- length-insensitive
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-variational-griffith
  type: refines
  weight: 0.7
- to: pf-at1-regularization
  type: refines
  weight: 0.7
- to: pf-at2-regularization
  type: refines
  weight: 0.7
- to: pf-staggered-scheme
  type: feeds-into
  weight: 0.5
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Cohesive Phase-Field Model (PF-CZM, Wu Unified Theory)

## Summary

The phase-field regularized cohesive zone model (PF-CZM), developed within Wu's unified phase-field damage theory, bridges gradient-damage mechanics and classical cohesive zone models (CZM) for quasi-brittle and cohesive fracture. PF-CZM employs a specific geometric crack function \alpha(d) = 2d - d^2 (with scaling constant c_{\alpha} = \pi) and a rational energetic degradation function \omega(d) = (1-d)^p / [(1-d)^p + a_1 d P(d)] to strictly satisfy physical traction-separation laws (such as linear, exponential, or Cornelissen softening). A hallmark feature of PF-CZM is that the global load-displacement response and peak structural load capacity are length-scale insensitive with respect to the regularization parameter b, provided b \le l_{ch}/3 (where l_{ch} = E_0 G_f / f_t^2 is Irwin's characteristic length). Furthermore, PF-CZM naturally recovers Barenblatt-type cohesive fracture profiles without requiring pre-defined crack paths or mesh-alignment constraints.

## 1. Core Concept

Classical phase-field brittle fracture models (such as AT1 and AT2) exhibit strong dependence of structural peak load on the internal length scale parameter b, which acts purely as a numerical regularization parameter or artificial strength governor. Wu's unified phase-field damage theory resolves this limitation by constructing a phase-field regularized cohesive zone model (PF-CZM) where material tensile strength f_t, fracture energy G_f, Young's modulus E_0, and cohesive traction-separation laws are independently and consistently prescribed. By adopting a parabolic geometric crack function \alpha(d) = 2d - d^2 and a parameterized rational energetic degradation function \omega(d), the damage driving force is calibrated against Irwin's characteristic length l_{ch} = E_0 G_f / f_t^2 via scaling parameter a_1 = (4/\pi)(l_{ch}/b). As a result, the macroscopic structural response becomes insensitive to length scale b (for b \le l_{ch}/3), eliminating artificial mesh-bias and permitting coarse-mesh approximations outside the localization band. Within a variational and coupled continuum framework, PF-CZM rigorously reproduces classical Barenblatt and Dugdale cohesive crack profiles across arbitrary 2D and 3D geometries.

## 2. Mathematical Formulation

**pf_czm_geometric_crack_function**
$$
\alpha(d) = 2d - d^2, \quad c_{\alpha} = 4 \int_0^1 \sqrt{\alpha(\beta)} d\beta = \pi
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**pf_czm_energetic_degradation_function**
$$
\omega(d) = \frac{(1-d)^p}{(1-d)^p + a_1 d P(d)}, \quad P(d) = 1 + a_2 d + a_3 d^2
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**pf_czm_softening_parameter_calibration**
$$
\text{Linear: } p=2, a_2=-\frac{1}{2}, a_3=0; \quad \text{Exponential: } p=2.5, a_2=2^{5/3}-3, a_3=0; \quad \text{Cornelissen: } p=2, a_2=1.3868, a_3=0.9106
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**pf_czm_governing_microforce_balance**
$$
\nabla \cdot \mathbf{q} + Q(d) \le 0, \quad \mathbf{q} = \frac{2b}{\pi} G_f \nabla d, \quad Q(d) = -\omega'(d) \mathcal{H} - \frac{G_f}{\pi b} \alpha'(d)
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**pf_czm_length_scale_insensitivity_bound**
$$
b \le \frac{1}{3} l_{ch} = \frac{1}{3} \frac{E_0 G_f}{f_t^2}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**Notation:**
d: scalar damage variable (d \in); \omega(d): rational energetic degradation function; \alpha(d): parabolic geometric crack function (\alpha(d)=2d-d^2); b: regularization length scale parameter; l_{ch}: Irwin's characteristic material length (l_{ch} = E_0 G_f / f_t^2); f_t: uniaxial tensile strength; G_f: critical fracture energy; E_0: Young's modulus; \mathcal{H}: history field of maximum effective strain energy release rate; \mathbf{q}: microforce flux vector; Q(d): thermodynamic damage driving force source.


## 3. Algorithmic Implementation

**pf-czm-bfgs-monolithic-solver**
$$
\begin{algorithmic}
\State $Initialize displacement degrees of freedom \mathbf{a}_0, damage degrees of freedom \bar{\mathbf{a}}_0, combined solution vector \mathbf{z}_0 = \{\mathbf{a}_0, \bar{\mathbf{a}}_0\}^T, and initial history field \mathcal{H}_0 = \frac{f_t^2}{2 E_0}.$
\For{$Loop over load/displacement increments n = 1, 2, \dots, N_{steps}.$}
\State $Set iteration index k = 0, initial solution guess \mathbf{z}_{n+1}^{(0)} = \mathbf{z}_n, and compute residual vector \mathbf{g}^{(0)} = [\mathbf{r}_u(\mathbf{z}_{n+1}^{(0)})^T, \mathbf{r}_d(\mathbf{z}_{n+1}^{(0)})^T]^T.$
\State $Set uncoupled initial block-diagonal inverse stiffness matrix \tilde{\mathbf{K}}^{(0)-1} = \text{diag}(\mathbf{K}_{uu}^{-1}, \mathbf{K}_{dd}^{-1}).$
\While{$Residual norm \|\mathbf{g}^{(k)}\| > \text{tol}.$}
\State $Compute solution update step: \delta \mathbf{z} = \tilde{\mathbf{K}}^{(k)-1} \mathbf{g}^{(k)}.$
\State $Update solution vector: \mathbf{z}^{(k+1)} = \mathbf{z}^{(k)} + \delta \mathbf{z}.$
\State $At Gauss integration points, evaluate effective equivalent stress \bar{\sigma}_{eq}^{(k+1)} and update history variable field: \mathcal{H}_{n+1} = \max\left(\mathcal{H}_n, \frac{\bar{\sigma}_{eq}^{(k+1)2}}{2 E_0}\right).$
\State $Evaluate updated residuals \mathbf{g}^{(k+1)} and residual increment \delta \mathbf{g} = \mathbf{g}^{(k+1)} - \mathbf{g}^{(k)}.$
\State $Update inverse stiffness matrix \tilde{\mathbf{K}}_{k+1}^{-1} using rank-two BFGS update formula: \tilde{\mathbf{K}}_{k+1}^{-1} = \left(\mathbf{I} - \frac{\delta \mathbf{z} \delta \mathbf{g}^T}{\delta \mathbf{z}^T \delta \mathbf{g}}\right) \tilde{\mathbf{K}}_k^{-1} \left(\mathbf{I} - \frac{\delta \mathbf{g} \delta \mathbf{z}^T}{\delta \mathbf{z}^T \delta \mathbf{g}}\right) + \frac{\delta \mathbf{z} \delta \mathbf{z}^T}{\delta \mathbf{z}^T \delta \mathbf{g}}.$
\State $Increment iteration counter k \leftarrow k + 1.$
\EndWhile
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_


## 4. Known Pitfalls

- **pf-czm-length-scale-upper-bound-violation**: If the regularization length scale b exceeds the critical material upper bound b > \frac{1}{3} l_{ch} = \frac{1}{3} \frac{E_0 G_f}{f_t^2}, the positive-definiteness condition -\partial Q / \partial d \ge 0 of the damage sub-problem is violated upon damage initiation. This causes loss of length-scale insensitivity and premature loss of numerical stability. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory)_
- **pf-czm-localization-band-mesh-resolution**: Although PF-CZM structural load-displacement responses are insensitive to length scale parameter b, the finite element mesh size h within the active damage localization band B must still be sufficiently fine (typically h \le b/5) to resolve the localized damage gradient \nabla d, otherwise numerical locking or mesh alignment bias occurs. _(Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory)_

## References

- Wu, J.-Y. (2017). A unified phase-field theory for the mechanics of damage and quasi-brittle failure. Journal of the Mechanics and Physics of Solids, 103, 72-99.
- Wu, J.-Y., and Huang, Y. (2020). Comprehensive implementations of phase-field damage models in Abaqus. Theoretical and Applied Fracture Mechanics, 106, 102440.
- Wu, J.-Y., Huang, Y., and Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase field damage theory. Computer Methods in Applied Mechanics and Engineering, 360, 112704.
- Alessi, R., Marigo, J.-J., Maurini, C., and Vidoli, S. (2018). Coupling damage and plasticity for a phase-field regularisation of brittle, cohesive and ductile fracture: One-dimensional examples. International Journal of Mechanical Sciences, 149, 559-576.
- Zhang, H., Pei, X.-Y., Peng, H., and Wu, J.-Y. (2021). Phase-field modeling of spontaneous shear bands in collapsing thick-walled cylinders. Engineering Fracture Mechanics, 249, 107706.
