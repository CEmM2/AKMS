---
id: kinematics-strain-tensors
title: Strain Tensors & Seth-Hill Family
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- continuum-mechanics
- strain-tensor
- seth-hill
status: established
confidence: 0.9
source: hybrid
edges:
- to: kinematics-motion-deformation-gradient
  type: requires
  weight: 1.0
- to: kinematics-polar-decomposition
  type: requires
  weight: 0.9
- to: tensor-spectral-decomposition
  type: requires
  weight: 0.8
- to: kinematics-logarithmic-strain
  type: feeds-into
  weight: 1.0
- to: stress-piola-kirchhoff
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Strain Tensors & Seth-Hill Family

## Summary

Strain tensors measure continuous body deformation by quantifying local changes in length, angle, and volume relative to reference or spatial configurations. Finite strain measures include the Green-Lagrange material strain tensor, spatial Euler-Almansi strain, logarithmic (Hencky) strain, and generalized Seth-Hill family strains.

## 1. Core Concept

In finite-deformation continuum mechanics, displacement gradients contain both rigid-body motion and true stretching. Strain tensors eliminate rigid-body rotations by measuring metric variations between configurations. The Green-Lagrange strain tensor E evaluates changes in the squared lengths of material line elements in reference coordinates and is energetically conjugate to Second Piola-Kirchhoff stress. The spatial Euler-Almansi strain tensor e measures deformation in the current configuration and is related to E via geometric pull-back operations. The class of Seth-Hill strain measures generalizes finite strain metrics, incorporating logarithmic (Hencky) strain E = 1/2 ln C, which decouples volumetric and isochoric responses and facilitates additive elastoplastic splits.

## 2. Mathematical Formulation

**Green-Lagrange Material Strain Tensor**
$$
E = \frac{1}{2}(C - I) = \frac{1}{2}(F^T F - I)
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 3.3, Eq. 3.61, p. 88; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 3.2.6, Eq. 3.2.20, p. 83_

**Green-Lagrange Strain Component Expression**
$$
E_{IJ} = \frac{1}{2}\left( \frac{\partial x_k}{\partial X_I} \frac{\partial x_k}{\partial X_J} - \delta_{IJ} \right) = \frac{1}{2}\left( \frac{\partial u_I}{\partial X_J} + \frac{\partial u_J}{\partial X_I} + \frac{\partial u_k}{\partial X_I} \frac{\partial u_k}{\partial X_J} \right)
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 3.3, Eq. 3.61, p. 88; Bathe et al_1975_Finite element formulations for large deformation dynamic analysis.pdf, App. Nomenclature, p. 384_

**Logarithmic (Hencky) Strain Tensor**
$$
E = \frac{1}{2} \ln C = \ln U = \sum_{i=1}^3 (\ln \lambda_i) \boldsymbol{N}_i \otimes \boldsymbol{N}_i
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 11.8, Eq. 11.108, p. 388; Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf, Sec. 2.3 & Box 2, pp. 5385, 5390_

**Spatial Euler-Almansi and Pull-Back Relation**
$$
E = \phi^* e = \frac{1}{2}(\phi^* g - G)
$$
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.3, p. 34; Kinematics_of_CM_12_Pull_Back_Lie_Derivative.pdf, Sec. 2.12, pp. 1–2_

**Notation:**
{'F': 'Deformation gradient tensor F = \\partial x / \\partial X.', 'C': 'Right Cauchy-Green deformation tensor C = F^T F.', 'E': 'Green-Lagrange material strain tensor.', 'e': 'Euler-Almansi spatial strain tensor.', 'U': 'Right pure stretch tensor U = C^{1/2}.', '\\lambda_i': 'Principal stretch ratios.', '\\boldsymbol{N}_i': 'Material principal directions (eigenvectors of C).', '\\phi^*': 'Pull-back geometric mapping operator.'}


## 3. Algorithmic Implementation

**Material Green-Lagrange and Logarithmic Strain Evaluation Algorithm**
$$
\begin{algorithmic}
\State $Given 3x3 deformation gradient tensor F$
\State $Compute right Cauchy-Green tensor C \gets F^T F$
\State $Compute Green-Lagrange strain tensor E^{\mathrm{GL}} \gets \frac{1}{2}(C - I)$
\State $Solve spectral eigenvalues \lambda_i^2 and eigenvectors \boldsymbol{N}_i of C for i \in \{1, 2, 3\}$
\For{$i \gets 1 \text{ to } 3$}
\State $Compute principal stretches \lambda_i \gets \sqrt{\lambda_i^2} \text{ and eigenprojections } E_i \gets \boldsymbol{N}_i \otimes \boldsymbol{N}_i$
\EndFor
\State $Compute logarithmic strain tensor E^{\mathrm{log}} \gets \sum_{i=1}^3 (\ln \lambda_i) E_i$
\Return $E^{\mathrm{GL}}, E^{\mathrm{log}}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 3.3, p. 88 & Sec. 11.8, p. 388; Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf, Box 2 & Box 3, pp. 5390, 5393_


## 4. Known Pitfalls

- **Using Small-Strain Tensor Linearizations in Large Deformation Kinematics**: Omitting non-linear displacement gradient terms \frac{1}{2} \frac{\partial u_k}{\partial X_I} \frac{\partial u_k}{\partial X_J} when evaluating strains under finite rotations induces severe artificial volume changes and invalidates energy conjugacy with Second Piola-Kirchhoff stresses. Mitigation: Compute full Green-Lagrange strain E = \frac{1}{2}(F^T F - I) or corotational strain updates. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 3.3, pp. 88–91; Bathe et al_1975_Finite element formulations for large deformation dynamic analysis.pdf, App. Nomenclature, p. 384)_
- **Additive Stacking of Non-Coaxial Large Strain Tensors**: Additively accumulating finite strain increments without mapping to a common reference configuration or logarithmic strain space violates kinematic exactness when principal axes rotate. Mitigation: Transform strain tensors via push-forward/pull-back operators or evaluate strains in logarithmic strain space. _(Source: Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf, Sec. 2.1–2.3, pp. 5384–5385; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.3, p. 34)_

## References

- Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf
- Bathe et al_1975_Finite element formulations for large deformation dynamic analysis.pdf
- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Kinematics_of_CM_12_Pull_Back_Lie_Derivative.pdf
- Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf
