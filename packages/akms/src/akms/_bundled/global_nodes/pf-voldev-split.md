---
id: pf-voldev-split
title: Volumetric-Deviatoric Energy Split (Amor)
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- voldev-split
- amor
- energy-decomposition
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-at2-regularization
  type: feeds-into
  weight: 0.5
- to: pf-spectral-split
  type: contradicts
  weight: 0.0
- to: pf-energy-split-comparison
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Volumetric-Deviatoric Energy Split (Amor)

## Summary

Formulation, physical behavior, and numerical implementation of the Volumetric-Deviatoric strain energy decomposition (Amor et al., 2009; Zhang et al., 2022) in phase-field fracture mechanics. The volumetric-deviatoric split partitions undamaged elastic strain energy density \psi_0(\boldsymbol{\epsilon}) into a positive crack-driving component \psi^+ (degraded by (1-d)^2) and a non-driving compressive component \psi^- (undegraded). The split isolates volumetric expansion \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_+ and deviatoric strain energy \boldsymbol{\epsilon}_{dev} : \boldsymbol{\epsilon}_{dev} to drive damage evolution while protecting compressive volumetric states \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_- from degradation. Benchmark evaluations (Zhang et al., 2022) demonstrate that volumetric-deviatoric splits accurately predict shear failure and local shear strain distributions under pure shear loading without the artificial stress overestimation seen in spectral splits. Claims of a 3x-5x speedup per Gauss point over spectral splits are misattributed; documented 3x-7x computational speedups in phase-field literature arise from global solver selection (monolithic BFGS vs. staggered solvers), not local energy decomposition.

## 1. Core Concept

The volumetric-deviatoric energy decomposition proposed by Amor et al. (2009) addresses unilateral crack contact by separating elastic strain energy into spherical (volumetric) and deviatoric (shear) parts. Unlike isotropic models that degrade total strain energy—causing spurious cracking under hydrostatic compression—the volumetric-deviatoric split degrades only the positive (tensile) volumetric strain energy \frac{1}{2} K_n \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_+^2 and the full deviatoric strain energy \mu (\boldsymbol{\epsilon}_{dev} : \boldsymbol{\epsilon}_{dev}). Compressive volumetric energy \frac{1}{2} K_n \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_-^2 remains undegraded, preventing crack initiation under pure hydrostatic compression. Under pure shear or shear-dominated loading, volumetric-deviatoric splits (StrainDe and StressDe) allow full deviatoric energy to drive crack propagation, enabling realistic shear band localization (Zhang et al., 2022). However, under combined compressive-shear states, un-degraded compressive protection applies only to the hydrostatic trace, so deviatoric strains can still accumulate damage unless pressure-dependent thresholds or multi-field modifications are applied. Local evaluation of the volumetric-deviatoric split is computationally simple and closed-form, but overall solver efficiency is governed by the global non-linear solver (BFGS quasi-Newton vs. staggered alternate minimization).

## 2. Mathematical Formulation

**volumetric_deviatoric_energy_split**
$$
\psi^+(\boldsymbol{\epsilon}) = \frac{1}{2} K_n \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_+^2 + \mu (\boldsymbol{\epsilon}_{dev} : \boldsymbol{\epsilon}_{dev}), \quad \psi^-(\boldsymbol{\epsilon}) = \frac{1}{2} K_n \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_-^2
$$
_Source: Zhang et al. (2022), Assessment of four strain energy decomposition methods for phase field fracture models; Amor et al. (2009), Regularized formulation of the variational brittle fracture; Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture_

**volumetric_deviatoric_degraded_stress**
$$
\boldsymbol{\sigma} = [(1-d)^2 + k] \left( K_n \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_+ \mathbf{I} + 2\mu \boldsymbol{\epsilon}_{dev} \right) + K_n \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_- \mathbf{I}
$$
_Source: Zhang et al. (2022), Assessment of four strain energy decomposition methods; Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture_

**stress_based_volumetric_deviatoric_variant**
$$
\boldsymbol{\sigma}_0 = -p \mathbf{I} + \mathbf{s}, \quad \psi^+ = \frac{1}{2 K_3} \langle -p \rangle_+^2 + \frac{1}{4\mu} (\mathbf{s} : \mathbf{s}), \quad \psi^- = \frac{1}{2 K_3} \langle -p \rangle_-^2
$$
_Source: Zhang et al. (2022), Assessment of four strain energy decomposition methods; Zhang et al. (2023), Phase-field modeling of coupled spall and adiabatic shear banding_

**Notation:**
\boldsymbol{\epsilon}: small strain tensor; \boldsymbol{\epsilon}_{dev}: deviatoric strain tensor; \mathbf{I}: second-order identity tensor; \boldsymbol{\sigma}: degraded Cauchy stress tensor; \boldsymbol{\sigma}_0: undamaged Cauchy stress tensor; \mathbf{s}: deviatoric Cauchy stress tensor; p: hydrostatic pressure; K_n: n-dimensional bulk modulus; \lambda, \mu: Lamé elastic constants; d: scalar phase-field damage variable (d \in [1]); k: residual stiffness parameter; \psi^+, \psi^-: positive (tensile/shear driving) and negative (compressive non-driving) strain energy density components; \mathcal{H}: historical maximum energy release rate field.


## 3. Algorithmic Implementation

**volumetric-deviatoric-split-constitutive-update**
$$
\begin{algorithmic}
\State $At finite element integration point, receive trial total strain tensor \boldsymbol{\epsilon}_{n+1}.$
\State $Compute volumetric strain \text{tr}(\boldsymbol{\epsilon}_{n+1}) and Macaulay brackets \langle \text{tr}(\boldsymbol{\epsilon}_{n+1}) \rangle_+ and \langle \text{tr}(\boldsymbol{\epsilon}_{n+1}) \rangle_-.$
\State $Compute deviatoric strain tensor: \boldsymbol{\epsilon}_{dev} = \boldsymbol{\epsilon}_{n+1} - \frac{1}{n}\text{tr}(\boldsymbol{\epsilon}_{n+1})\mathbf{I}.$
\State $Evaluate positive tensile and shear strain energy density: \psi^+ = \frac{1}{2} K_n \langle \text{tr}(\boldsymbol{\epsilon}_{n+1}) \rangle_+^2 + \mu (\boldsymbol{\epsilon}_{dev} : \boldsymbol{\epsilon}_{dev}).$
\State $Update damage history field enforcing irreversibility \dot{d} \ge 0: \mathcal{H}_{n+1} = \max(\mathcal{H}_n, \psi^+).$
\State $Evaluate degraded Cauchy stress tensor: \boldsymbol{\sigma}_{n+1} = [(1-d_{n+1})^2 + k] \left( K_n \langle \text{tr}(\boldsymbol{\epsilon}_{n+1}) \rangle_+ \mathbf{I} + 2\mu \boldsymbol{\epsilon}_{dev} \right) + K_n \langle \text{tr}(\boldsymbol{\epsilon}_{n+1}) \rangle_- \mathbf{I}.$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Zhang et al. (2022), Assessment of four strain energy decomposition methods; Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture; Amor et al. (2009)_


## 4. Known Pitfalls

- **spurious-damage-under-pure-compression-with-deviatoric-strains**: The volumetric-deviatoric strain energy split degrades the entire deviatoric strain energy \mu(\boldsymbol{\epsilon}_{dev} : \boldsymbol{\epsilon}_{dev}). In pure hydrostatic compression without shear, no damage develops. However, under high compressive shear where negative volumetric strain is present along with deviatoric strain, \psi^+ accumulates deviatoric energy, potentially causing spurious damage growth under compressive confinement. _(Source: Zhang et al. (2022), Assessment of four strain energy decomposition methods for phase field fracture models; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture)_
- **misattributing-3x-5x-speedup-to-volumetric-deviatoric-split**: Attributing a 3x-5x computational speedup per Gauss point to the volumetric-deviatoric split over spectral decomposition is incorrect. Literature benchmarks show that local closed-form volumetric-deviatoric calculations add negligible runtime differences compared to 3x3 spectral Eigendecompositions; the documented 3x-7x speedups stem from global solver selection (monolithic BFGS vs. staggered solvers). _(Source: Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Zhang et al. (2022), Assessment of four strain energy decomposition methods)_

## References

- Amor, H., Marigo, J.-J., and Maurini, C. (2009). Regularized formulation of the variational brittle fracture with unilateral contact: Numerical experiments. Journal of the Mechanics and Physics of Solids, 57(8), 1209-1229.
- Zhang, S., Jiang, W., and Tonks, M. R. (2022). Assessment of four strain energy decomposition methods for phase field fracture models using quasi-static and dynamic benchmark cases. Materials Theory, 6, 6.
- Miehe, C., Hofacker, M., and Welschinger, F. (2010). Thermodynamically consistent phase-field models of fracture: Variational principles and multi-field FE implementations. International Journal for Numerical Methods in Engineering, 83(10), 1273-1311.
- Wang, T., Ye, X., Liu, Z., Liu, X., Chu, D., and Zhuang, Z. (2020). A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration. Computational Mechanics, 65(5), 1305-1321.
- Wu, J.-Y., Huang, Y., and Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase field damage theory. Computer Methods in Applied Mechanics and Engineering, 360, 112704.
- Zhang, H., Peng, H., Pei, X.-Y., Wu, J.-Y., Li, P., Tang, T.-G., Cai, L.-C., Li, Y., and Liu, H. (2023). Phase-field modeling of coupled spall and adiabatic shear banding and simulation of complex cracks in ductile metals. Journal of the Mechanics and Physics of Solids, 172, 105186.
