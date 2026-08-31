---
id: elastic-anisotropic
title: 'Anisotropic Elasticity: Symmetries and Constants'
domain: computational-mechanics
subdomain: elasticity
tags:
- elasticity
- anisotropic
- voigt
- orthotropic
- transverse-isotropic
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-products-contractions
  type: requires
  weight: 1.0
- to: composite-laminate-theory
  type: feeds-into
  weight: 0.5
- to: composite-homogenization
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Anisotropic Elasticity: Symmetries and Constants

## Summary

Anisotropic linear elasticity defines fourth-order tensor relations mapping second-order strain tensors to stress tensors across isotropic, transversely isotropic, and orthotropic material symmetries in heterogeneous composite media. Constitutive formulations split elastic behavior into volumetric and deviatoric components for isotropic phases, or invariant stress projections for transversely isotropic plies via Gibbs free energy density functions governed by five independent elastic constants. In 3D woven composites, orthotropic symmetry relates macroscopic volume-averaged stresses and strains via a 6x6 compliance matrix parameterized by nine independent moduli. Advanced non-local continuum mechanics and state-based peridynamics utilize correspondence models to replicate full anisotropic fourth-order elasticity tensors.

## 1. Core Concept

Anisotropic elasticity formulates linear stress-strain relationships for materials whose mechanical response depends on spatial orientation. In isotropic media, Hooke's law splits fourth-order stiffness into bulk and shear components using volumetric and deviatoric projection tensors. For unidirectional fiber-reinforced composite laminas exhibiting transverse isotropy, five independent elastic constants—longitudinal Young's modulus E_11, transverse Young's modulus E_22, in-plane shear modulus G_12, longitudinal Poisson's ratio nu_12, and transverse Poisson's ratio nu_23—govern constitutive behavior, with transverse shear modulus G_23 constrained by G_23 = E_22 / [2(1 + nu_23)].

In 3D woven fabric composites and homogenized representative volume elements, material symmetry is orthotropic, characterized by nine independent elastic constants defining a symmetric 6x6 compliance matrix S*. Macroscopic volume-averaging over repeating unit cells computes effective orthotropic compliance under six independent loading conditions. In non-local continuum frameworks such as peridynamics, classical bond-based formulations restrict Poisson's ratio to fixed values (e.g., 1/4 in 3D), necessitating ordinary state-based correspondence models to accurately represent general anisotropic elasticity tensors.

## 2. Mathematical Formulation

**Isotropic Linear Elastic Stiffness Tensor and Projection Decomposition**
$$
\sigma(x) = L(x) \varepsilon(x) + \alpha(x), \quad L(x) = d k(x) N_1 + 2 \mu(x) N_2
$$
_Source: Buryachenko - 2025 - Unified Micromechanics Theory of Composites.pdf, Section 2.1, Eqs. 2.1-2.2, 2.5_

**Transversely Isotropic Gibbs Free Energy Density**
$$
\psi(\tilde{\sigma}) = \frac{1}{2} \left[ \frac{\tilde{\sigma}_L^2}{E_{11}} - \frac{4 \nu_{12} \tilde{\sigma}_L \tilde{p}_T}{E_{11}} + \frac{\tilde{p}_T^2}{E_T} + \frac{\tilde{\tau}_T^2}{G_T} + \frac{\tilde{\tau}_L^2}{G_{12}} \right]
$$
_Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 3.6, Eqs. 123-125_

**Orthotropic Macroscopic Compliance Homogenization Relation**
$$
E_{ij} = S_{ijkl}^* \Sigma_{kl}, \quad \Sigma_{ij} = \frac{1}{V_{\text{RUC}}} \int_{V_{\text{RUC}}} \sigma_{ij} \, dV, \quad E_{ij} = \frac{1}{V_{\text{RUC}}} \int_{V_{\text{RUC}}} \varepsilon_{ij} \, dV
$$
_Source: Carvelli and Poggi - 2001 - A homogenization procedure for the numerical analysis of woven fabric composites.pdf, Section 2 & 3, Eqs. 1-8_

**Isotropic Elastic Moduli Conversion Relations**
$$
K = \lambda + \frac{2}{3} G, \quad E = \frac{9 K G}{3 K + G}, \quad \nu = \frac{3 K - 2 G}{2 (3 K + G)}
$$
_Source: Hashin - THE ELASTIC MODULI OF HETEROGENEOUS MATERIALS.pdf, Section 2 & 6, Eqs. 2.7, 6.3-6.4_

**Notation:**
- \sigma, \varepsilon: Cauchy stress tensor and strain tensor
- L(x), M(x): Fourth-order linear elastic stiffness and compliance tensors
- k(x), \mu(x): Bulk modulus and shear modulus
- N_1, N_2: Spherical and deviatoric projection operators
- \psi(\tilde{\sigma}): Transversely isotropic Gibbs free energy density
- \tilde{\sigma}_L, \tilde{p}_T: Longitudinal stress and transverse hydrostatic stress invariants
- \tilde{\tau}_L, \tilde{\tau}_T: Longitudinal shear and transverse shear stress invariants
- E_{11}, E_{22}: Longitudinal and transverse Young's moduli
- G_{12}, G_{23}: In-plane shear modulus and transverse shear modulus
- \nu_{12}, \nu_{23}: In-plane Poisson's ratio and transverse Poisson's ratio
- \Sigma_{ij}, E_{ij}: Macroscopic stress and strain tensors averaged over repeating unit cell
- S_{ijkl}^*: Macroscopic effective orthotropic compliance matrix


## 3. Algorithmic Implementation

**ComputeIsotropicElasticityTensor**
$$
\begin{algorithmic}
\State $K = \lambda + \frac{2.0}{3.0} \mu, \quad E = \frac{9.0 K \mu}{3.0 K + \mu}, \quad \nu = \frac{3.0 K - 2.0 \mu}{2.0 (3.0 K + \mu)}$
\State $N_1 = \frac{1.0}{d} (\delta \otimes \delta), \quad N_2 = I - N_1$
\State $L = d \cdot K \cdot N_1 + 2.0 \mu \cdot N_2$
\State $\sigma = L \cdot \varepsilon + \alpha$
\State $w = 0.5 \cdot (K \cdot (\text{tr}(\varepsilon))^2 + 2.0 \mu \cdot e_{ij} e_{ij})$
\Return $L, \sigma, w$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Buryachenko - 2025 - Unified Micromechanics Theory of Composites.pdf, Section 2.1, Eqs. 2.1-2.2_

**EvaluateTransverseIsotropicGibbsEnergy**
$$
\begin{algorithmic}
\State $\tilde{\sigma}_L = \tilde{\sigma}_{11}, \quad \tilde{p}_T = 0.5 \cdot (\tilde{\sigma}_{22} + \tilde{\sigma}_{33})$
\State $\tilde{\tau}_L = 0.5 \cdot \sqrt{(\tilde{\sigma}_{22} - \tilde{\sigma}_{33})^2 + 4.0 \tilde{\sigma}_{23}^2}, \quad \tilde{\tau}_T = \sqrt{\tilde{\sigma}_{12}^2 + \tilde{\sigma}_{13}^2}$
\State $E_T = \frac{E_{22}}{2.0 (1.0 - \nu_{23})}, \quad G_T = \frac{E_{22}}{2.0 (1.0 + \nu_{23})}$
\State $\psi(\tilde{\sigma}) = 0.5 \cdot \left[ \frac{\tilde{\sigma}_L^2}{E_{11}} - \frac{4.0 \nu_{12} \tilde{\sigma}_L \tilde{p}_T}{E_{11}} + \frac{\tilde{p}_T^2}{E_T} + \frac{\tilde{\tau}_T^2}{G_T} + \frac{\tilde{\tau}_L^2}{G_{12}} \right]$
\Return $\psi(\tilde{\sigma}), E_T, G_T$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 3.6, Eqs. 123-125_


## 4. Known Pitfalls

- **assuming-transverse-isotropy-independence-of-shear-modulus**: In transversely isotropic plies, treating transverse shear modulus G_23 as an independent parameter violates thermodynamic constraints; G_23 = G_T = E_22 / [2(1 + nu_23)] is strictly constrained by transverse Young's modulus E_22 and Poisson's ratio nu_23. _(Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 3.6, Eq. 125)_
- **peridynamic-bond-based-poisson-ratio-restriction**: Using bond-based peridynamics to represent anisotropic elasticity restricts Poisson's ratio to fixed values (nu = 1/4 in 3D, nu = 1/3 in 2D plane stress); state-based correspondence models must be used to represent arbitrary anisotropic fourth-order elasticity tensors. _(Source: Buryachenko - 2025 - Unified Micromechanics Theory of Composites.pdf, Section 1)_
- **violating-positive-definiteness-in-orthotropic-compliance**: Constructing orthotropic compliance matrices without verifying positive-definiteness of the 6x6 elasticity tensor produces unphysical negative strain energy densities and solver divergence under multiaxial stress states. _(Source: Carvelli and Poggi - 2001 - A homogenization procedure for the numerical analysis of woven fabric composites.pdf, Section 2)_

## References

- Buryachenko - 2025 - Unified Micromechanics Theory of Composites.pdf
- Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf
- Carvelli and Poggi - 2001 - A homogenization procedure for the numerical analysis of woven fabric composites.pdf
- Hashin - THE ELASTIC MODULI OF HETEROGENEOUS MATERIALS.pdf
- Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf
