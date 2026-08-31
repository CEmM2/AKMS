---
id: kinematics-convected-coordinates
title: Convected Coordinate System
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- continuum-mechanics
- convected-coordinates
- curvilinear
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-curvilinear-bases
  type: requires
  weight: 1.0
- to: tensor-metric
  type: requires
  weight: 1.0
- to: kinematics-motion-deformation-gradient
  type: refines
  weight: 0.9
- to: kinematics-strain-tensors
  type: feeds-into
  weight: 1.0
- to: fem-tl-b-matrix
  type: feeds-into
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Convected Coordinate System

## Summary

Convected coordinates track continuum deformation by embedding a curvilinear coordinate system into the material body that deforms continuously with the motion. Tensor components defined relative to convected base vectors implicitly absorb geometric deformation, simplifying strain definitions via metric tensor changes and enabling objective convected stress rate formulations.

## 1. Core Concept

In a convected coordinate description, curvilinear coordinates \(\theta^i\) are attached to material points in the reference configuration and remain continuously bound to those same material points throughout the motion. As the body deforms, the covariant base vectors \(\mathbf{g}_i = \partial \mathbf{x} / \partial \theta^i\) stretch and rotate with the continuum. Deformations are measured directly through changes in the metric tensor components \(g_{ij} = \mathbf{g}_i \cdot \mathbf{g}_j\) relative to reference metric components \(G_{ij} = \mathbf{G}_i \cdot \mathbf{G}_j\). Convected stress rates differentiate tensor components directly with respect to time in the convected frame, automatically yielding frame-invariant objective rate measures.

## 2. Mathematical Formulation

**Convected Base Vectors and Metric Tensor Evolution**
$$
\mathbf{g}_i = \frac{\partial \mathbf{x}}{\partial \theta^i} = F \mathbf{G}_i, \quad g_{ij} = \mathbf{g}_i \cdot \mathbf{g}_j = F^k{}_i F^k{}_j G_{ij}
$$
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.3, p. 34; Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf, Eq. 2.10.62, p. 1_

**Convected Green-Lagrange Strain Tensor Components**
$$
E_{ij} = \frac{1}{2} (g_{ij} - G_{ij})
$$
_Source: Kinematics_of_CM_12_Pull_Back_Lie_Derivative.pdf, Sec. 2.12, p. 2; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.3, p. 34_

**Convected Rate of Kirchhoff Stress**
$$
\tau^{\nabla c} = \dot{\tau}_{ij} \mathbf{g}^i \otimes \mathbf{g}^j = C^c_{ijkl} D_{kl} \mathbf{g}^i \otimes \mathbf{g}^j
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, p. 779 & App. 3.5, p. 137; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, Sec. 4.3, p. 23_

**Pull-Back Transformation of Covariant Strain**
$$
E = \phi^* e = \frac{1}{2} (\phi^* g - G)
$$
_Source: Kinematics_of_CM_12_Pull_Back_Lie_Derivative.pdf, Sec. 2.12, Eqs. 2.12.46–2.12.51, pp. 1–2; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.3, p. 34_

**Notation:**
{'\\theta^i': 'Convected curvilinear coordinates bound to material points.', '\\mathbf{G}_i': 'Reference covariant basis vector.', '\\mathbf{g}_i': 'Deformed covariant basis vector in current configuration.', 'G_{ij}': 'Reference metric tensor components.', 'g_{ij}': 'Current metric tensor components.', 'E_{ij}': 'Green-Lagrange strain components in convected system.', '\\tau^{\\nabla c}': 'Convected objective rate of Kirchhoff stress tensor.', 'C^c_{ijkl}': 'Material tangent constitutive tensor relating convected stress rate to rate of deformation.'}


## 3. Algorithmic Implementation

**Convected Metric and Strain Tensor Computation Algorithm**
$$
\begin{algorithmic}
\State $Given reference nodal position X, current position x(X,t), and element parametric coordinates \theta^i$
\State $Compute reference covariant base vectors \mathbf{G}_i \gets \frac{\partial X}{\partial \theta^i} \text{ and metric } G_{ij} \gets \mathbf{G}_i \cdot \mathbf{G}_j$
\State $Compute deformation gradient F \gets \frac{\partial x}{\partial X}$
\State $Compute current covariant base vectors \mathbf{g}_i \gets F \mathbf{G}_i = \frac{\partial x}{\partial \theta^i} \text{ and current metric } g_{ij} \gets \mathbf{g}_i \cdot \mathbf{g}_j$
\State $Compute convected Green-Lagrange strain components E_{ij} \gets \frac{1}{2} (g_{ij} - G_{ij})$
\Return $E_{ij}, g_{ij}, G_{ij}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf, Eq. 2.10.62, p. 1; Kinematics_of_CM_12_Pull_Back_Lie_Derivative.pdf, Sec. 2.12, pp. 1–2_


## 4. Known Pitfalls

- **Confusing Convected Coordinate Rates with Corotational Objective Rates**: Assuming the convected rate of Kirchhoff stress \tau^{\nabla c} is identical to corotational Jaumann or Green-Naghdi rates. The convected rate directly differentiates tensor components with respect to time in body-fitted convected coordinates, naturally incorporating metric stretch rates rather than rigid-body rotations alone. _(Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, Sec. 4.3 & App. A.3, pp. 23–25, 34; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, p. 779)_
- **Metric Singularities from Severe Grid Distortion**: Evaluating convected metric components g_{ij} = \mathbf{g}_i \cdot \mathbf{g}_j on highly distorted or self-intersecting curvilinear coordinates causes the metric determinant g = \det(g_{ij}) to approach zero or turn negative, invalidating strain and volume integrals. _(Source: Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf, Sec. 2.10, p. 1; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 3.2.6, p. 83)_

## References

- Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf
- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf
- Kinematics_of_CM_12_Pull_Back_Lie_Derivative.pdf
