---
id: tensor-invariants
title: Tensor Invariants ($I_1, I_2, I_3, J_2, J_3$)
domain: computational-mechanics
subdomain: tensor-algebra
tags:
- tensors
- continuum-mechanics
- invariants
- lode-angle
- cayley-hamilton
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-products-contractions
  type: requires
  weight: 0.9
- to: tensor-derivatives-tensors
  type: feeds-into
  weight: 1.0
- to: plasticity-von-mises
  type: feeds-into
  weight: 1.0
- to: kinematics-strain-tensors
  type: feeds-into
  weight: 0.6
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Tensor Invariants ($I_1, I_2, I_3, J_2, J_3$)

## Summary

Tensor invariants are scalar quantities derived from second-order tensor fields that remain invariant under coordinate frame transformations. Primary invariants evaluate trace, double contraction, and determinant metrics, while deviatoric invariants quantify shear and distortion in constitutive modeling and yield surface formulations.

## 1. Core Concept

For any second-order tensor A, principal scalar invariants \(I_1, I_2, I_3\) characterize intrinsic geometric properties independent of coordinate basis choices. In continuum elasticity and hyperelasticity, the primary invariants of the right Cauchy-Green deformation tensor \(C\) govern strain energy density potentials. In continuum plasticity, the Cauchy stress tensor \(\boldsymbol{\sigma}\) is split into a hydrostatic pressure \(p = \frac{1}{3}\mathrm{tr}(\boldsymbol{\sigma})\) and a deviatoric stress tensor \(\mathbf{s} = \boldsymbol{\sigma} - p \mathbf{I}\). The second and third deviatoric stress invariants \(J_2 = \frac{1}{2}\mathrm{tr}(\mathbf{s}^2)\) and \(J_3 = \det(\mathbf{s})\) govern von Mises, Drucker-Prager, and Mohr-Coulomb yield criteria. The Lode angle parameterizes the stress state within the octahedral \(\pi\)-plane.

## 2. Mathematical Formulation

**Primary Invariants of Second-Order Tensor**
$$
I_1 = \mathrm{tr}(A), \quad I_2 = \frac{1}{2} \left[ (\mathrm{tr} A)^2 - \mathrm{tr}(A^2) \right], \quad I_3 = \det(A)
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 5.2, p. 251; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 11.2, Eq. 11.40, p. 373_

**Characteristic Invariant Equation**
$$
C_i^3 - I_1 C_i^2 + I_2 C_i - I_3 = 0
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 11.2, Eq. 11.39, p. 373; Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf, Sec. 3.2, p. 5395_

**Deviatoric Stress Invariants J2 and J3**
$$
J_2 = \frac{1}{2} \mathrm{tr}(\mathbf{s}^2) = \frac{1}{2} s_{ij} s_{ij}, \quad J_3 = \det(\mathbf{s}) = \frac{1}{3} \mathrm{tr}(\mathbf{s}^3)
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 1.3, p. 19 & Sec. 7.6, Eq. 7.169 & p. 262_

**Lode Angle Derivative Relation**
$$
\frac{\partial \theta}{\partial \boldsymbol{\sigma}} = \frac{\sqrt{3}}{2 \cos 3\theta} \left( \frac{3}{2} J_2^{-5/2} J_3 \frac{\partial J_2}{\partial \boldsymbol{\sigma}} - J_2^{-3/2} \frac{\partial J_3}{\partial \boldsymbol{\sigma}} \right)
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 7.6, Eq. 7.169, p. 262_

**Notation:**
{'I_1, I_2, I_3': 'Principal scalar invariants of second-order tensor.', 'J_2, J_3': 'Second and third invariants of deviatoric stress tensor.', '\\mathbf{s}': 'Deviatoric stress tensor \\mathbf{s} = \\boldsymbol{\\sigma} - p \\mathbf{I}.', 'p': 'Hydrostatic pressure scalar p = \\frac{1}{3}\\mathrm{tr}(\\boldsymbol{\\sigma}).', '\\theta': 'Lode angle stress state parameter.'}


## 3. Algorithmic Implementation

**Tensor Invariant and Deviatoric Invariant Evaluation Algorithm**
$$
\begin{algorithmic}
\State $Given 3x3 symmetric tensor A (or Cauchy stress tensor \boldsymbol{\sigma})$
\State $Compute trace I_1 \gets A_{11} + A_{22} + A_{33}$
\State $Compute second invariant I_2 \gets A_{11}A_{22} + A_{22}A_{33} + A_{33}A_{11} - A_{12}^2 - A_{23}^2 - A_{31}^2$
\State $Compute determinant I_3 \gets \det(A)$
\State $Evaluate hydrostatic component p \gets \frac{1}{3} I_1 \text{ and deviatoric tensor } \mathbf{s} \gets A - p \mathbf{I}$
\State $Compute second deviatoric invariant J_2 \gets \frac{1}{2}(s_{11}^2 + s_{22}^2 + s_{33}^2) + s_{12}^2 + s_{23}^2 + s_{31}^2$
\State $Compute third deviatoric invariant J_3 \gets \det(\mathbf{s})$
\Return $I_1, I_2, I_3, J_2, J_3$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 1.3, p. 19, Sec. 7.6, p. 262, & Box 5.2, p. 251_


## 4. Known Pitfalls

- **Assuming Invariance Under Non-Orthogonal Basis Transformations**: Evaluating tensor invariants using non-Cartesian or non-orthonormal components without incorporating metric tensor contractions. Invariants \\(I_1 = g^{ij} A_{ij}\\) and \\(I_2\\) require metric tensor \\(g^{ij}\\) in general curvilinear coordinate charts. _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 5.2, p. 251; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, Sec. 3, p. 19)_
- **Lode Angle Indeterminacy at Hydrostatic and Shear Axis Singularities**: Evaluating Lode angle derivatives \partial \theta / \partial \boldsymbol{\sigma} when J_2 \to 0 or \cos 3\theta \to 0 causes division-by-zero singularities along the hydrostatic axis and corners of yield surfaces (such as Mohr-Coulomb or Tresca criteria). Mitigation: Use smoothed yield function representations or corner roundings. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 7.6, Eq. 7.169, p. 262)_

## References

- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf
