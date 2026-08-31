---
id: pf-spectral-split
title: Spectral Energy Decomposition (Miehe)
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- spectral-split
- energy-decomposition
- miehe
- tension-compression
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
- to: pf-voldev-split
  type: contradicts
  weight: 0.0
- to: pf-energy-split-comparison
  type: feeds-into
  weight: 0.5
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Spectral Energy Decomposition (Miehe)

## Summary

Formulation, physical behavior, and numerical implementation of Miehe's spectral strain energy decomposition in phase-field fracture mechanics. To model physical unilateral crack-closure contact and prevent unphysical crack propagation under compressive stress states, Miehe et al. (2010) introduced a spectral decomposition of the strain tensor \boldsymbol{\epsilon} = \sum_{a=1}^3 \epsilon_a \mathbf{n}_a \otimes \mathbf{n}_a into positive (tensile) and negative (compressive) principal parts using Macaulay brackets \langle \cdot \rangle_\pm. The positive strain energy density \psi_0^+(\boldsymbol{\epsilon}) = \frac{1}{2}\lambda \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_+^2 + \mu \sum_{a=1}^3 \langle \epsilon_a \rangle_+^2 is degraded by (1-d)^2 to drive phase-field evolution, while compressive energy \psi_0^- remains undegraded. Benchmark evaluations (Zhang et al., 2022) confirm that spectral decomposition provides superior accuracy in mixed-mode and compressive fracture scenarios compared to volumetric-deviatoric splits. Numerical stabilization methods, such as eigenvalue perturbation (\delta \approx 0.10) for degenerate states, resolve potential derivative stiffness matrix ill-conditioning (Molnar et al., 2020).

## 1. Core Concept

In variational phase-field fracture, applying degradation g(d) = (1-d)^2 indiscriminately to total strain energy causes cracks to nucleate and propagate under pure hydrostatic compression or shear-compression loading. Miehe's spectral energy decomposition resolves this physical inconsistency by performing an Eigendecomposition of the small strain tensor \boldsymbol{\epsilon} (or Cauchy stress tensor \boldsymbol{\sigma}_0) into orthogonal principal directions \mathbf{n}_a and principal strains \epsilon_a. The strain energy density \psi_0(\boldsymbol{\epsilon}) is additively split into a crack-driving tensile component \psi_0^+ (composed of positive principal strains \langle \epsilon_a \rangle_+) and a non-driving compressive component \psi_0^- (composed of negative principal strains \langle \epsilon_a \rangle_-). As a result, when crack faces close under compressive loads, the compressive stiffness is fully restored, preventing interpenetration. While spectral decomposition requires evaluating 3x3 local Eigendecompositions at integration points, literature benchmarks demonstrate that local spectral calculations add minimal overhead; global computational performance is determined by global solver selection (staggered vs. monolithic BFGS) rather than the energy split itself.

## 2. Mathematical Formulation

**strain_spectral_energy_split**
$$
\psi_0^+(\boldsymbol{\epsilon}) = \frac{1}{2}\lambda \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_+^2 + \mu \sum_{a=1}^3 \langle \epsilon_a \rangle_+^2, \quad \psi_0^-(\boldsymbol{\epsilon}) = \frac{1}{2}\lambda \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_-^2 + \mu \sum_{a=1}^3 \langle \epsilon_a \rangle_-^2
$$
_Source: Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture; Zhang et al. (2022), Assessment of four strain energy decomposition methods_

**spectral_degraded_stress_tensor**
$$
\boldsymbol{\sigma} = [(1-d)^2 + k] \boldsymbol{\sigma}_0^+ + \boldsymbol{\sigma}_0^-, \quad \boldsymbol{\sigma}_0^\pm = \lambda \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_\pm \mathbf{I} + 2\mu \sum_{a=1}^3 \langle \epsilon_a \rangle_\pm \mathbf{n}_a \otimes \mathbf{n}_a
$$
_Source: Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method_

**stress_spectral_decomposition_variant**
$$
\boldsymbol{\sigma}_0 = \mathbf{C} : \boldsymbol{\epsilon} = \sum_{a=1}^3 \sigma_a^0 \mathbf{m}_a \otimes \mathbf{m}_a, \quad \boldsymbol{\sigma}^+ = \sum_{a=1}^3 \langle \sigma_a^0 \rangle_+ \mathbf{m}_a \otimes \mathbf{m}_a, \quad \psi^\pm = \frac{1}{2} \boldsymbol{\sigma}^\pm : \boldsymbol{\epsilon}
$$
_Source: Zhang et al. (2022), Assessment of four strain energy decomposition methods for phase field fracture models_

**spectral_eigenvalue_perturbation**
$$
\text{If } |\epsilon_1 - \epsilon_2| \le \text{tol}, \quad \epsilon_2' = (1 + \delta) \epsilon_2, \quad \boldsymbol{\epsilon}' = \mathbf{V} \hat{\boldsymbol{\epsilon}}' \mathbf{V}^T
$$
_Source: Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Zhang et al. (2022), Assessment of four strain energy decomposition methods_

**Notation:**
\boldsymbol{\epsilon}: small strain tensor; \epsilon_a: principal strain eigenvalues; \mathbf{n}_a: principal strain eigenvectors; \boldsymbol{\sigma}_0, \boldsymbol{\sigma}_0^+, \boldsymbol{\sigma}_0^-: undamaged, positive, and negative stress tensors; \psi_0^+, \psi_0^-: positive (tensile) and negative (compressive) strain energy density components; \lambda, \mu: Lamé elastic constants; d: scalar phase-field damage variable (d \in); \langle \cdot \rangle_\pm: Macaulay bracket functions.


## 3. Algorithmic Implementation

**spectral-decomposition-and-constitutive-update**
$$
\begin{algorithmic}
\State $At finite element integration point, receive trial total strain tensor \boldsymbol{\epsilon}_{n+1}.$
\State $Compute trace \text{tr}(\boldsymbol{\epsilon}_{n+1}) = \epsilon_{11} + \epsilon_{22} + \epsilon_{33} and Macaulay brackets \langle \text{tr}(\boldsymbol{\epsilon}_{n+1}) \rangle_\pm.$
\State $Solve 3D eigenvalue problem for strain tensor: \boldsymbol{\epsilon}_{n+1} \mathbf{n}_a = \epsilon_a \mathbf{n}_a for a \in \{1, 2, 3\}.$
\If{$Eigenvalue degeneracy detected (|\epsilon_a - \epsilon_b| \le 10^{-7} \text{ for } a \neq b).$}
\State $Apply eigenvalue perturbation \epsilon_b' = (1 + \delta) \epsilon_b with \delta = 0.10 and reconstruct strain tensor \boldsymbol{\epsilon}' = \mathbf{V} \hat{\boldsymbol{\epsilon}}' \mathbf{V}^T.$
\EndIf
\State $Evaluate positive and negative strain energy densities: \psi_0^+ = \frac{1}{2}\lambda \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_+^2 + \mu \sum_{a=1}^3 \langle \epsilon_a \rangle_+^2, \psi_0^- = \frac{1}{2}\lambda \langle \text{tr}(\boldsymbol{\epsilon}) \rangle_-^2 + \mu \sum_{a=1}^3 \langle \epsilon_a \rangle_-^2.$
\State $Update energy release rate history field: \mathcal{H}_{n+1} = \max(\mathcal{H}_n, \psi_0^+).$
\State $Evaluate degraded Cauchy stress tensor: \boldsymbol{\sigma}_{n+1} = [(1-d_{n+1})^2 + k] \boldsymbol{\sigma}_0^+ + \boldsymbol{\sigma}_0^-.$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Zhang et al. (2022), Assessment of four strain energy decomposition methods_


## 4. Known Pitfalls

- **spurious-damage-under-compression-without-spectral-split**: Omitting spectral or positive-negative strain energy decomposition allows purely compressive or compression-shear hydrostatic states to generate damage. The spectral split ensures that only positive principal strains drive phase-field damage evolution, preventing unphysical crack growth under compressive confinement. _(Source: Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture; Zhang et al. (2022), Assessment of four strain energy decomposition methods)_
- **degenerate-eigenvalue-numerical-instability**: When two or three principal strains are identical (\epsilon_a \approx \epsilon_b), numerical derivatives in the constitutive tangent matrix can suffer floating-point instability or loss of convergence in Newton solvers. Implementing eigenvalue perturbation (\delta \sim 0.10) or restricting matrix updates to early Newton iterations stabilizes calculation. _(Source: Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Zhang et al. (2022), Assessment of four strain energy decomposition methods)_
- **misattributing-solver-speed-to-spectral-eigendecomposition**: Attributing global computational overhead or slowdowns to local 3x3 eigendecompositions is incorrect. Literature benchmarks show that local spectral Eigendecomposition adds negligible runtime compared to global linear system solves; global computational speed is governed by solver selection (staggered vs. monolithic BFGS). _(Source: Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Zhang et al. (2022), Assessment of four strain energy decomposition methods)_

## References

- Miehe, C., Hofacker, M., and Welschinger, F. (2010). Thermodynamically consistent phase-field models of fracture: Variational principles and multi-field FE implementations. International Journal for Numerical Methods in Engineering, 83(10), 1273-1311.
- Zhang, S., Jiang, W., and Tonks, M. R. (2022). Assessment of four strain energy decomposition methods for phase field fracture models using quasi-static and dynamic benchmark cases. Materials Theory, 6, 6.
- Molnar, G., Gravouil, A., Seghir, R., and Réthoré, J. (2020). An open-source Abaqus implementation of the phase-field method to study the effect of plasticity on the instantaneous fracture toughness in dynamic crack propagation. Computer Methods in Applied Mechanics and Engineering, 365, 113004.
- Borden, M. J., Hughes, T. J. R., Landis, C. M., Anvari, A., and Lee, I. J. (2016). A phase-field formulation for fracture in ductile materials: Finite deformation balance law derivation, plastic degradation, and stress triaxiality effects. Computer Methods in Applied Mechanics and Engineering, 312, 130-166.
- Wu, J.-Y., Huang, Y., and Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase field damage theory. Computer Methods in Applied Mechanics and Engineering, 360, 112704.
