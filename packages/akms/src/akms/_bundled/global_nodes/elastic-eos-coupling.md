---
id: elastic-eos-coupling
title: Volumetric-Deviatoric Split & EOS Coupling
domain: computational-mechanics
subdomain: elasticity
tags:
- elasticity
- EOS
- voldev-split
- mie-gruneisen
- hyperelastic
status: established
confidence: 0.9
source: hybrid
edges:
- to: elastic-anisotropic
  type: refines
  weight: 0.7
- to: eos-mie-gruneisen
  type: requires
  weight: 1.0
- to: pf-spallation
  type: feeds-into
  weight: 0.5
- to: eos-polynomial
  type: refines
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Volumetric-Deviatoric Split & EOS Coupling

## Summary

Volumetric-deviatoric stress and strain tensor decomposition partitions isotropic continuum mechanical behavior into hydrostatic (spherical) and shear (deviatoric) components. In linear isotropic elasticity, stress and strain tensors are split into hydrostatic mean stress sigma = tr(sigma) and deviatoric stress s_ij, governed independently by bulk modulus K and shear modulus G. In composite micromechanics and multiscale continuum modeling, volumetric-deviatoric projections utilize fourth-order spherical N_1 and deviatoric N_2 tensor operators to decompose stiffness tensors. Hydrostatic stress and strain invariants drive scalar progressive damage initiation in quasi-brittle matrix subcells during manufacturing cool-down. Furthermore, in phase-field fracture formulations, strain energy is decomposed into tensile and compressive volumetric/deviatoric components or mode-specific directional energy density invariants to prevent unphysical damage under pure compressive hydrostatic loading.

## 1. Core Concept

Volumetric-deviatoric tensor splitting separates mechanical field responses that alter material volume from those that change geometric shape. In classical linear elasticity, Hooke's law decomposes the second-order stress tensor into isotropic mean normal stress (pressure) and deviatoric shear stress s_ij, relating them through local bulk modulus K and shear modulus G. In isotropic fourth-order elasticity, this split is expressed using spherical projection tensor N_1 = (1/d) (delta x delta) and deviatoric projection tensor N_2 = I - N_1, where total elastic stiffness L = d K N_1 + 2 G N_2.

In multiscale composite modeling, hydrostatic equivalent stress and strain invariants govern progressive damage initiation in quasi-brittle matrix constituents (e.g., SiC matrices), where microcracking is activated by tensile volumetric dilation during thermal cool-down. In variational phase-field fracture, strain energy density is split into positive (tensile/volumetric expansion) and negative (compressive/volumetric contraction) parts using spectral strain decomposition or transversely isotropic stress invariants, ensuring degradation affects only crack-opening volumetric and shear modes.

## 2. Mathematical Formulation

**Isotropic Linear Elastic Volumetric-Deviatoric Stress Split**
$$
\sigma_{ij} = \frac{\sigma}{3} \delta_{ij} + s_{ij}, \quad \varepsilon_{ij} = \frac{\varepsilon}{3} \delta_{ij} + e_{ij}, \quad \sigma = 3 K \varepsilon, \quad s_{ij} = 2 G e_{ij}
$$
_Source: Hashin - THE ELASTIC MODULI OF HETEROGENEOUS MATERIALS.pdf, Section 2, Eqs. 2.6-2.7_

**Fourth-Order Stiffness Tensor Projection Decomposition**
$$
L = d K N_1 + 2 G N_2, \quad N_1 = \frac{1}{d} (\delta \otimes \delta), \quad N_2 = I - N_1
$$
_Source: Buryachenko - 2025 - Unified Micromechanics Theory of Composites.pdf, Section 2.1, Eq. 2.5_

**Isotropic Spectral Strain Energy Volumetric-Deviatoric Split**
$$
\psi_b^{\pm} = \frac{\lambda}{2} \langle \text{tr}(\boldsymbol{\varepsilon}) \rangle_{\pm}^2 + G \, \text{tr}\left( \langle \boldsymbol{\varepsilon} \rangle_{\pm}^2 \right)
$$
_Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 2.1, Eq. 19_

**Hydrostatic Stress-Driven Matrix Thermoelastic Damage**
$$
r_{\text{eq}} = 3 (1 - \phi) K_0 \left[ e_{\text{eq}} - \alpha_0 \Delta T \right] \ge r_{\text{crit}}(T, \dot{\epsilon})
$$
_Source: Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf, Section 2.2, Eqs. 1, 17_

**Notation:**
- \sigma_{ij}, s_{ij}: Cauchy stress tensor and deviatoric stress tensor
- \varepsilon_{ij}, e_{ij}: Total strain tensor and deviatoric strain tensor
- \sigma, \varepsilon: Trace of stress tensor and trace of strain tensor (volumetric strain)
- K, G: Bulk modulus and shear modulus
- N_1, N_2: Fourth-order spherical and deviatoric projection tensors
- \delta, I: Second-order Kronecker delta and fourth-order symmetric identity tensor
- d: Spatial dimension (2 or 3)
- \lambda: Lamé first parameter
- \psi_b^+, \psi_b^-: Tensile and compressive strain energy density splits
- \phi: Scalar degradation damage parameter
- r_{\text{eq}}, e_{\text{eq}}: Equivalent hydrostatic stress and strain invariants
- r_{\text{crit}}: Critical hydrostatic stress threshold for damage initiation
- \alpha_0: Matrix thermal expansion coefficient
- \Delta T: Temperature differential relative to reference state


## 3. Algorithmic Implementation

**ComputeVolumetricDeviatoricStressSplit**
$$
\begin{algorithmic}
\State $\sigma = \text{tr}(\sigma_{ij}) = \sigma_{11} + \sigma_{22} + \sigma_{33}$
\State $\varepsilon = \text{tr}(\varepsilon_{ij}) = \varepsilon_{11} + \varepsilon_{22} + \varepsilon_{33}$
\For{$i = 1 \text{ To } 3$}
\For{$j = 1 \text{ To } 3$}
\If{$i == j$}
\State $s_{ij} = \sigma_{ij} - \frac{1}{3} \sigma, \quad e_{ij} = \varepsilon_{ij} - \frac{1}{3} \varepsilon$
\Else
\State $s_{ij} = \sigma_{ij}, \quad e_{ij} = \varepsilon_{ij}$
\EndIf
\EndFor
\EndFor
\State $w_{\text{vol}} = \frac{1}{2} K \varepsilon^2, \quad w_{\text{dev}} = G \sum_{i,j} e_{ij} e_{ij}$
\State $w_{\text{total}} = w_{\text{vol}} + w_{\text{dev}}$
\Return $s_{ij}, e_{ij}, w_{\text{vol}}, w_{\text{dev}}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Hashin - THE ELASTIC MODULI OF HETEROGENEOUS MATERIALS.pdf, Section 2, Eqs. 2.6-2.9_

**EvaluatePhaseFieldVolumetricStrainSplit**
$$
\begin{algorithmic}
\State $\varepsilon_{\text{vol}} = \text{tr}(\boldsymbol{\varepsilon})$
\State $\varepsilon_{\text{vol}}^+ = \max(0, \varepsilon_{\text{vol}}), \quad \varepsilon_{\text{vol}}^- = \min(0, \varepsilon_{\text{vol}})$
\State $\psi_b^+ = \frac{1}{2} \lambda (\varepsilon_{\text{vol}}^+)^2 + G \sum_{i} (\langle \hat{\varepsilon}_i \rangle_+)^2$
\State $\psi_b^- = \frac{1}{2} \lambda (\varepsilon_{\text{vol}}^-)^2 + G \sum_{i} (\langle \hat{\varepsilon}_i \rangle_-)^2$
\State $\psi_{\text{degraded}} = (1 - d)^2 \psi_b^+ + \psi_b^-$
\Return $\psi_b^+, \psi_b^-, \psi_{\text{degraded}}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 2.1, Eqs. 18-20_


## 4. Known Pitfalls

- **unsplit-strain-energy-causes-compression-damage**: Failing to split strain energy into tensile (positive) and compressive (negative) volumetric parts in phase-field fracture formulations causes unphysical material damage degradation under pure compressive hydrostatic stress states. _(Source: Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf, Section 2.1)_
- **ignoring-volumetric-thermal-dilation-microcracking**: Neglecting hydrostatic dilation induced by fiber-matrix thermal expansion mismatch during post-manufacturing cool-down overpredicts initial composite laminate stiffness by at least 25% due to omitted pre-existing matrix microcracks. _(Source: Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf, Section 3)_
- **constant-strain-subcell-elimination-in-gmc**: Assuming constant subcell strain fields in GMC homogenization causes any subcell with zero bulk or shear stiffness (e.g., a void) to eliminate the entire row and column in which it resides unless a sub-RUC architecture is used. _(Source: Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf, Section 2.1)_

## References

- Hashin - THE ELASTIC MODULI OF HETEROGENEOUS MATERIALS.pdf
- Buryachenko - 2025 - Unified Micromechanics Theory of Composites.pdf
- Borkowski and Chattopadhyay - 2015 - Multiscale model of woven ceramic matrix composites considering manufacturing induced damage.pdf
- Bui and Hu - 2021 - A review of phase-field models, fundamentals and their applications to composite laminates.pdf
