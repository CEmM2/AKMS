---
id: kinematics-polar-decomposition
title: Polar Decomposition & Rotation Tensor
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- continuum-mechanics
- polar-decomposition
- rotation
status: established
confidence: 0.9
source: hybrid
edges:
- to: kinematics-motion-deformation-gradient
  type: requires
  weight: 1.0
- to: tensor-spectral-decomposition
  type: requires
  weight: 1.0
- to: kinematics-strain-tensors
  type: feeds-into
  weight: 1.0
- to: kinematics-logarithmic-strain
  type: feeds-into
  weight: 1.0
- to: kinematics-corotational-update
  type: feeds-into
  weight: 0.9
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Polar Decomposition & Rotation Tensor

## Summary

The polar decomposition theorem multiplicatively decomposes the deformation gradient tensor F into a proper orthogonal rotation tensor R and a symmetric positive-definite stretch tensor—either the right stretch tensor U or the left stretch tensor V. This decomposition isolates rigid-body rotation from pure material stretching, forming the foundation for objective stress rates, logarithmic strain evaluations, and corotational continuum formulations.

## 1. Core Concept

In finite deformation kinematics, any non-singular deformation gradient F with positive determinant (J = det F > 0) can be uniquely factored into F = R U (right polar decomposition) or F = V R (left polar decomposition). The tensor R is proper orthogonal (R^T R = I, det R = +1) and represents local rigid-body rotation. The right stretch tensor U operates in the reference material configuration, whereas the left stretch tensor V operates in the current spatial configuration, related by V = R U R^T. Stretches are evaluated via the square roots of the Cauchy-Green deformation tensors C = F^T F = U^2 and b = F F^T = V^2, typically computed using spectral decomposition of C or explicit closed-form matrix square root algorithms.

## 2. Mathematical Formulation

**Right and Left Polar Decomposition**
$$
F = R U = V R, \quad R^T R = I, \quad \det R = +1
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 3.7.1, Eqs. 3.7.1–3.7.2, p. 131; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 3.3, Eqs. 3.58 & 3.62, pp. 86–87_

**Stretch Tensor and Cauchy-Green Relations**
$$
C = F^T F = U^2, \quad b = F F^T = V^2, \quad V = R U R^T
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 3.3, Eqs. 3.59–3.63, pp. 86–87; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, Sec. 6.1, p. 28_

**Spectral Representation of Stretch and Rotation**
$$
U = \sum_{i=1}^3 \lambda_i \boldsymbol{N}_i \otimes \boldsymbol{N}_i, \quad V = \sum_{i=1}^3 \lambda_i \boldsymbol{n}_i \otimes \boldsymbol{n}_i, \quad R = \sum_{i=1}^3 \boldsymbol{n}_i \otimes \boldsymbol{N}_i
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 3.3, pp. 85–86 & Box 11.3, p. 387; Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf, Sec. 2.10.5, Eqs. 2.10.70–2.10.71, p. 2_

**Explicit Incremental Rotation Extraction Formula**
$$
R = F U^{-1} = F (F^T F)^{-1/2}
$$
_Source: Rashid - 1993 - Incremental kinematics for finite element applications.pdf, Sec. 2 & 3, pp. 3940–3941; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 3.3, p. 86_

**Notation:**
{'F': 'Deformation gradient tensor F = \\partial \\boldsymbol{x} / \\partial \\boldsymbol{X}.', 'R': 'Proper orthogonal rotation tensor.', 'U': 'Symmetric positive-definite right stretch tensor.', 'V': 'Symmetric positive-definite left stretch tensor.', 'C': 'Right Cauchy-Green deformation tensor C = F^T F.', 'b': 'Left Cauchy-Green deformation tensor b = F F^T.', '\\lambda_i': 'Principal stretch ratios (\\lambda_i > 0).', '\\boldsymbol{N}_i, \\boldsymbol{n}_i': 'Orthonormal principal material and spatial direction vectors.'}


## 3. Algorithmic Implementation

**Polar Decomposition via Spectral Decomposition of C**
$$
\begin{algorithmic}
\State $Given 3x3 deformation gradient tensor F with \det F > 0$
\State $Compute right Cauchy-Green deformation tensor C \gets F^T F$
\State $Solve spectral eigenvalue problem for C to obtain eigenvalues \lambda_i^2 and orthonormal eigenvectors \boldsymbol{N}_i for i \in \{1, 2, 3\}$
\For{$i \gets 1 \text{ to } 3$}
\State $Compute principal stretches \lambda_i \gets \sqrt{\lambda_i^2}$
\State $Form material eigenprojection tensor E_i \gets \boldsymbol{N}_i \otimes \boldsymbol{N}_i$
\EndFor
\State $Construct right stretch tensor U \gets \sum_{i=1}^3 \lambda_i E_i$
\State $Compute inverse right stretch tensor U^{-1} \gets \sum_{i=1}^3 \left(\frac{1}{\lambda_i}\right) E_i$
\State $Compute proper orthogonal rotation tensor R \gets F U^{-1}$
\State $Compute left stretch tensor V \gets R U R^T$
\Return $R, U, V$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 3.3, pp. 85–86 & Box 11.3, p. 387; Rashid - 1993 - Incremental kinematics for finite element applications.pdf, Sec. 2 & 3, pp. 3940–3941_


## 4. Known Pitfalls

- **Inverting Ill-Conditioned Stretch Tensors Near Zero Stretches**: Evaluating R = F U^{-1} when elements undergo extreme localized distortion or near-zero stretches (\lambda_i \to 0) causes U to become nearly singular, leading to severe numerical ill-conditioning and loss of orthogonality in R. Mitigation: Use robust spectral decomposition or closed-form Cayley-Hamilton square-root algorithms that precondition or clamp small principal stretches. _(Source: Rashid - 1993 - Incremental kinematics for finite element applications.pdf, Sec. 3, pp. 3943–3945; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.3, p. 387)_
- **Coaxiality Misconception Between Stress and Deformation Gradients**: Assuming that principal stress directions always align with principal directions of the deformation gradient F or stretch tensor U. Coaxiality only holds for isotropic materials where principal axes of Cauchy stress \sigma coincide with left stretch tensor V, whereas anisotropic materials introduce distinct preferred material axes. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 3.3, p. 86 & Sec. 11.8, p. 386; Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf, Sec. 2, pp. 5385–5387)_

## References

- Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf
- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf
- Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf
- Rashid - 1993 - Incremental kinematics for finite element applications.pdf
