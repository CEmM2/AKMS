---
id: tensor-curvilinear-bases
title: Covariant & Contravariant Base Vectors
domain: computational-mechanics
subdomain: tensor-algebra
tags:
- tensors
- continuum-mechanics
- curvilinear
- convected-coordinates
- tensor-notation
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-index-notation
  type: requires
  weight: 0.9
- to: tensor-metric
  type: feeds-into
  weight: 1.0
- to: tensor-christoffel-symbols
  type: feeds-into
  weight: 0.9
- to: kinematics-convected-coordinates
  type: feeds-into
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Covariant & Contravariant Base Vectors

## Summary

Curvilinear coordinate systems establish local tangent and cotangent vector spaces spanned by covariant and contravariant base vectors. Covariant base vectors align with coordinate tangent lines, while dual contravariant base vectors satisfy reciprocal orthogonality. Metric tensor components perform index raising and lowering, enabling frame-invariant vector and tensor expansions in non-Cartesian domains.

## 1. Core Concept

In non-Cartesian curvilinear coordinate systems, basis vectors change direction and magnitude from point to point across the continuum domain. Covariant base vectors \mathbf{g}_i are defined as partial derivatives of spatial position with respect to curvilinear coordinates \theta^i. Contravariant base vectors \mathbf{g}^i span the dual cotangent space and satisfy the reciprocal duality relation \mathbf{g}_i \cdot \mathbf{g}^j = \delta_i^j. A vector v can be expressed either as a linear combination of contravariant components v^i with covariant base vectors \mathbf{g}_i, or covariant components v_i with contravariant base vectors \mathbf{g}^i. Metric tensor components g_{ij} = \mathbf{g}_i \cdot \mathbf{g}_j and inverse metric components g^{ij} = \mathbf{g}^i \cdot \mathbf{g}^j serve as fundamental operators for raising and lowering indices.

## 2. Mathematical Formulation

**Covariant Basis Vectors and Metric Tensor**
$$
\mathbf{g}_i = \frac{\partial \mathbf{x}}{\partial \theta^i}, \quad g_{ij} = \mathbf{g}_i \cdot \mathbf{g}_j
$$
_Source: Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf, Eq. 2.10.7 & 2.10.49, p. 1; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.2, Def. A.22, p. 36_

**Dual Basis Reciprocal Orthogonality**
$$
\mathbf{g}_i \cdot \mathbf{g}^j = \delta_i^j
$$
_Source: Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf, Eq. 2.10.49, p. 1; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.2, Def. A.22, p. 36_

**Vector Component Expansion in Dual Bases**
$$
v = v^i \mathbf{g}_i = v_i \mathbf{g}^i, \quad v^i = v \cdot \mathbf{g}^i, \quad v_i = v \cdot \mathbf{g}_i
$$
_Source: Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf, Eq. 2.10.49, p. 1; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.2, Def. A.22, p. 36_

**Tensor Component Index Raising and Lowering**
$$
a_{ij} = g_{im} g_{jn} a^{mn}, \quad a^{ij} = g^{im} g^{jn} a_{mn}
$$
_Source: Kinematics_of_CM_12_Pull_Back_Lie_Derivative.pdf, Sec. 2.12, Eqs. 2.12.27 & 2.12.29–2.12.30, pp. 1–2_

**Notation:**
{'\\theta^i': 'Curvilinear coordinates.', '\\mathbf{g}_i': 'Covariant basis vector field.', '\\mathbf{g}^i': 'Dual contravariant basis vector field.', 'g_{ij}': 'Covariant metric tensor components.', 'g^{ij}': 'Contravariant inverse metric tensor components.', 'v^i': 'Contravariant vector components.', 'v_i': 'Covariant vector components.', '\\delta_i^j': 'Kronecker delta substitution tensor.'}


## 3. Algorithmic Implementation

**Curvilinear Basis Vector and Component Transformation Algorithm**
$$
\begin{algorithmic}
\State $Given spatial position x(\theta) in curvilinear coordinates \theta = (\theta^1, \theta^2, \theta^3) and vector components v^i$
\State $Compute covariant basis vectors \mathbf{g}_i \gets \frac{\partial x}{\partial \theta^i} \text{ for } i \in \{1, 2, 3\}$
\State $Compute covariant metric tensor components g_{ij} \gets \mathbf{g}_i \cdot \mathbf{g}_j$
\State $Compute inverse metric matrix g^{ij} \gets (g_{ij})^{-1}$
\State $Compute dual contravariant basis vectors \mathbf{g}^i \gets \sum_{j=1}^3 g^{ij} \mathbf{g}_j$
\State $Lower vector component indices to covariant form v_i \gets \sum_{j=1}^3 g_{ij} v^j$
\Return $\mathbf{g}_i, \mathbf{g}^i, g_{ij}, v_i$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf, Eq. 2.10.7 & 2.10.49, p. 1; Kinematics_of_CM_12_Pull_Back_Lie_Derivative.pdf, Sec. 2.12, Eqs. 2.12.27–2.12.30, pp. 1–2_


## 4. Known Pitfalls

- **Mixing Covariant and Contravariant Basis Vector Transformations**: Confusing covariant base vectors \mathbf{g}_i = \partial \mathbf{x}/\partial \theta^i with contravariant base vectors \mathbf{g}^i = \mathrm{d}\theta^i. Covariant base vectors transform with partial derivatives of position, whereas contravariant base vectors transform with coordinate gradients, leading to inverse matrix relationships between basis transformations. _(Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.2, Def. A.22, p. 36; Kinematics_of_CM_12_Pull_Back_Lie_Derivative.pdf, Sec. 2.12, pp. 1–2)_
- **Direct Summation over Identical Index Positions**: Attempting to contract two upper indices (such as v^i w^i) or two lower indices (v_i w_i) directly in curvilinear coordinates without inserting the metric tensor g_{ij} or g^{ij}. Metric components must be introduced to raise or lower an index before evaluating inner products. _(Source: Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf, Eq. 2.10.49–2.10.50, p. 1; Kinematics_of_CM_12_Pull_Back_Lie_Derivative.pdf, Sec. 2.12, Eqs. 2.12.27 & 2.12.30, pp. 1–2)_

## References

- Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf
- Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf
- Kinematics_of_CM_12_Pull_Back_Lie_Derivative.pdf
