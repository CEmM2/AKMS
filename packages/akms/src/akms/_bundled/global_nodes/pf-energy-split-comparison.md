---
id: pf-energy-split-comparison
title: Comparison of Strain Energy Decompositions
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- energy-split
- comparison
- no-tension
- star-convex
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-spectral-split
  type: refines
  weight: 0.7
- to: pf-voldev-split
  type: refines
  weight: 0.7
- to: pf-at2-regularization
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

# Comparison of Strain Energy Decompositions

## Summary

Comparative analysis of strain energy decomposition methods in phase-field fracture modeling, evaluating four canonical formulations: Strain Volumetric-Deviatoric (StrainDe / Amor et al., 2009), Strain Spectral (StrainSp / Miehe et al., 2010), Stress Spectral (StressSp / Zhang et al., 2020), and Stress Volumetric-Deviatoric (StressDe / Zhang et al., 2022), alongside Rankine no-tension criteria (Wu and Huang, 2020). All four energy splits perform identically in pure Mode I tensile loading. However, under pure compression, mixed-mode, or shear loading, their behaviors diverge significantly: volumetric-deviatoric splits accurately capture shear band localization but accumulate unphysical damage under pure hydrostatic compression because deviatoric strain energy is fully degraded. Spectral splits correctly suppress crack initiation under compressive stress states. Computational efficiency differences reported across literature (3x-7x speedup) stem from the choice of global solver (BFGS quasi-Newton monolithic vs. staggered alternate minimization), not the local energy split.

## 1. Core Concept

In regularized phase-field fracture mechanics, strain energy decomposition separates the total elastic strain energy density \psi_0(\boldsymbol{\epsilon}) into a crack-driving tensile component \psi^+ (degraded by (1-d)^2) and a non-driving compressive component \psi^- (undegraded). This split models physical unilateral crack-closure contact and prevents artificial cracking in purely compressive domains. Comparative benchmark studies (Zhang et al., 2022) categorize decompositions into strain-based and stress-based splits: (1) Volumetric-Deviatoric splits (Amor et al., 2009; Zhang et al., 2022) partition energy based on trace and deviatoric tensors; while excellent for shear localization, they allow pure shear or compression-shear states to generate damage unless modified. (2) Spectral splits (Miehe et al., 2010) project positive principal strain or stress components using Macaulay brackets \langle \cdot \rangle_\pm, preventing damage under compressive pressure and providing superior accuracy in mixed-mode failure (e.g. SENS, L-shaped panel). Rankine no-tension models (Wu and Huang, 2020) drive damage using maximum principal effective stress \bar{\sigma}_{eq} = \langle \bar{\sigma}_1 \rangle_+. Contrary to prior misconceptions, spectral splits do not cause 3-5x computational slowdowns; overall runtime is governed by monolithic vs. staggered FE solution algorithms.

## 2. Mathematical Formulation

**strain_volumetric_deviatoric_split**
$$
\psi^+(\boldsymbol{\epsilon}) = \frac{1}{2} K_n \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_+^2 + \mu \left( \boldsymbol{\epsilon}_{dev} : \boldsymbol{\epsilon}_{dev} \right), \quad \psi^-(\boldsymbol{\epsilon}) = \frac{1}{2} K_n \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_-^2
$$
_Source: Zhang et al. (2022), Assessment of four strain energy decomposition methods for phase field fracture models; Amor et al. (2009), Regularized formulation of the variational brittle fracture_

**strain_spectral_decomposition**
$$
\psi^+(\boldsymbol{\epsilon}) = \frac{1}{2} \lambda \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_+^2 + \mu \sum_{a=1}^3 \langle \epsilon_a \rangle_+^2, \quad \psi^-(\boldsymbol{\epsilon}) = \frac{1}{2} \lambda \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_-^2 + \mu \sum_{a=1}^3 \langle \epsilon_a \rangle_-^2
$$
_Source: Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture; Zhang et al. (2022), Assessment of four strain energy decomposition methods_

**stress_spectral_decomposition**
$$
\boldsymbol{\sigma}_0 = \mathbf{C} : \boldsymbol{\epsilon} = \sum_{a=1}^3 \sigma_a^0 \mathbf{m}_a \otimes \mathbf{m}_a, \quad \boldsymbol{\sigma}^+ = \sum_{a=1}^3 \langle \sigma_a^0 \rangle_+ \mathbf{m}_a \otimes \mathbf{m}_a, \quad \psi^\pm = \frac{1}{2} \boldsymbol{\sigma}^\pm : \boldsymbol{\epsilon}
$$
_Source: Zhang et al. (2022), Assessment of four strain energy decomposition methods for phase field fracture models_

**rankine_no_tension_effective_stress**
$$
\bar{\sigma}_{eq} = \langle \bar{\sigma}_1 \rangle_+, \quad \bar{Y} = \frac{\bar{\sigma}_{eq}^2}{2 E_0} = \frac{\langle \bar{\sigma}_1 \rangle_+^2}{2 E_0}
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory_

**Notation:**
\boldsymbol{\epsilon}: small strain tensor; \boldsymbol{\epsilon}_{dev}: deviatoric strain tensor; \boldsymbol{\sigma}_0, \boldsymbol{\sigma}^+, \boldsymbol{\sigma}^-: undamaged, positive, and negative stress tensors; \epsilon_a, \sigma_a^0: principal strains and stresses; \bar{\sigma}_1: maximum principal effective stress; \bar{\sigma}_{eq}: Rankine equivalent stress; \psi^+, \psi^-: positive and negative strain energy density components; K_n: n-dimensional bulk modulus; \lambda, \mu: Lamé constants; E_0: Young's modulus; \mathcal{H}: energy release rate history field.


## 3. Algorithmic Implementation

**strain-energy-split-evaluation-and-history-update**
$$
\begin{algorithmic}
\State $At load step n+1 and element Gauss integration point, receive updated total strain tensor \boldsymbol{\epsilon}_{n+1}.$
\If{$Energy split option == Volumetric-Deviatoric (StrainDe).$}
\State $Compute volumetric strain \text{tr}(\boldsymbol{\epsilon}_{n+1}) and deviatoric strain \boldsymbol{\epsilon}_{dev} = \boldsymbol{\epsilon}_{n+1} - \frac{1}{3}\text{tr}(\boldsymbol{\epsilon}_{n+1})\mathbf{I}.$
\State $Evaluate positive strain energy: \psi^+ = \frac{1}{2} K_n \langle \text{tr}(\boldsymbol{\epsilon}_{n+1}) \rangle_+^2 + \mu (\boldsymbol{\epsilon}_{dev} : \boldsymbol{\epsilon}_{dev}).$
\ElsIf{$Energy split option == Spectral (StrainSp / StressSp).$}
\State $Perform spectral Eigendecomposition of strain tensor \boldsymbol{\epsilon}_{n+1} = \sum_{a=1}^3 \epsilon_a \mathbf{n}_a \otimes \mathbf{n}_a or stress tensor \boldsymbol{\sigma}_0 = \sum_{a=1}^3 \sigma_a^0 \mathbf{m}_a \otimes \mathbf{m}_a.$
\State $Evaluate positive tensile strain energy density \psi^+ = \frac{1}{2}\lambda \langle \text{tr}(\boldsymbol{\epsilon}_{n+1})\rangle_+^2 + \mu \sum_{a=1}^3 \langle \epsilon_a \rangle_+^2 (for StrainSp) or \psi^+ = \frac{1}{2} \boldsymbol{\sigma}^+ : \boldsymbol{\epsilon}_{n+1} (for StressSp).$
\EndIf
\State $Update damage history field enforcing irreversibility: \mathcal{H}_{n+1} = \max\left(\mathcal{H}_n, \psi_{n+1}^+\right).$
\State $Pass history field \mathcal{H}_{n+1} to phase-field evolution equation: \frac{g_c}{l_c}(d - l_c^2 \Delta d) = 2(1-d)\mathcal{H}_{n+1}.$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Zhang et al. (2022), Assessment of four strain energy decomposition methods; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture_


## 4. Known Pitfalls

- **voldev-split-spurious-damage-under-pure-compression**: The volumetric-deviatoric strain energy decomposition (StrainDe) includes the full deviatoric strain energy \mu(\boldsymbol{\epsilon}_{dev} : \boldsymbol{\epsilon}_{dev}) in the positive driving energy \psi^+. Under pure hydrostatic compression or high compressive shear where no tensile principal strain exists, StrainDe continues to accumulate deviatoric strain energy, causing unphysical crack initiation and damage evolution under compression. _(Source: Zhang et al. (2022), Assessment of four strain energy decomposition methods for phase field fracture models; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture)_
- **misattributing-solver-speedup-to-energy-split**: Attributing a 3x-7x computational speedup to the choice of strain energy split is incorrect. Literature benchmarks show that energy split evaluation adds negligible overhead compared to global solver iterations. The documented 3x-7x speedup is achieved by switching from an alternating minimization (staggered) solver to a Broyden-Fletcher-Goldfarb-Shanno (BFGS) monolithic quasi-Newton solver. _(Source: Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus)_
- **spectral-split-tangent-discontinuity-at-zero-eigenvalues**: Spectral strain/stress energy decompositions involve Macaulay bracket projections \langle \cdot \rangle_\pm of principal values. When principal strains or stresses cross zero or when repeated eigenvalues occur, numerical derivative transitions in the constitutive tangent matrix can cause NR convergence slowdowns unless perturbation or C1 smoothing is applied. _(Source: Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Zhang et al. (2022), Assessment of four strain energy decomposition methods)_

## References

- Zhang, S., Jiang, W., and Tonks, M. R. (2022). Assessment of four strain energy decomposition methods for phase field fracture models using quasi-static and dynamic benchmark cases. Materials Theory, 6, 6.
- Miehe, C., Hofacker, M., and Welschinger, F. (2010). Thermodynamically consistent phase-field models of fracture: Variational principles and multi-field FE implementations. International Journal for Numerical Methods in Engineering, 83(10), 1273-1311.
- Amor, H., Marigo, J.-J., and Maurini, C. (2009). Regularized formulation of the variational brittle fracture with unilateral contact: Numerical experiments. Journal of the Mechanics and Physics of Solids, 57(8), 1209-1229.
- Wu, J.-Y., and Huang, Y. (2020). Comprehensive implementations of phase-field damage models in Abaqus. Theoretical and Applied Fracture Mechanics, 106, 102440.
- Wu, J.-Y., Huang, Y., and Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase field damage theory. Computer Methods in Applied Mechanics and Engineering, 360, 112704.
- Wang, T., Ye, X., Liu, Z., Liu, X., Chu, D., and Zhuang, Z. (2020). A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration. Computational Mechanics, 65(5), 1305-1321.
- Molnar, G., Gravouil, A., Seghir, R., and Réthoré, J. (2020). An open-source Abaqus implementation of the phase-field method to study the effect of plasticity on the instantaneous fracture toughness in dynamic crack propagation. Computer Methods in Applied Mechanics and Engineering, 365, 113004.
