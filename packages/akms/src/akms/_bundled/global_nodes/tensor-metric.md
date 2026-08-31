---
id: tensor-metric
title: Metric Tensor & Index Manipulation
domain: computational-mechanics
subdomain: tensor-algebra
tags:
- tensors
- continuum-mechanics
- curvilinear
- metric-tensor
- convected-coordinates
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-curvilinear-bases
  type: requires
  weight: 1.0
- to: tensor-christoffel-symbols
  type: feeds-into
  weight: 1.0
- to: kinematics-strain-tensors
  type: feeds-into
  weight: 1.0
- to: kinematics-convected-coordinates
  type: feeds-into
  weight: 1.0
context_size: small
reading_priority: full
content_ref: null
akms_schema: v2
---

# Metric Tensor & Index Manipulation

## Summary

The metric tensor defines inner products, line elements, and geometric volume measures on Riemannian manifolds and curvilinear coordinate systems. Its covariant coefficients g_{ij} and contravariant inverse coefficients g^{ij} serve as canonical index lowering and raising operators, establishing the foundation for convected kinematics and pull-back strain formulations.

## 1. Core Concept

The metric tensor g evaluates inner products between tangent vectors on a continuum manifold. In local curvilinear coordinates \theta^i, covariant metric components g_{ij} = \mathbf{g}_i \cdot \mathbf{g}_j evaluate squared differential line elements \mathrm{d}s^2 = \mathrm{d}\mathbf{x} \cdot \mathrm{d}\mathbf{x} = g_{ij} \mathrm{d}\theta^i \mathrm{d}\theta^j. Inverse metric components g^{ij} satisfy g_{ik} g^{kj} = \delta_i^j, forming the identity tensor operator I_M = \delta_i^j \mathrm{d}\theta^i \otimes \frac{\partial}{\partial \theta^j}. Metric coefficients act as index lowering (\flat) and raising (\sharp) operators on vector and tensor fields. In Euclidean Cartesian systems, the metric tensor simplifies to the identity tensor g = I.

## 2. Mathematical Formulation

**Covariant Metric Coefficients and Differential Line Element**
$$
g_{ij} = \mathbf{g}_i \cdot \mathbf{g}_j = \left\langle \frac{\partial \mathbf{x}}{\partial \theta^i}, \frac{\partial \mathbf{x}}{\partial \theta^j} \right\rangle, \quad \mathrm{d}s^2 = g_{ij} \, \mathrm{d}\theta^i \, \mathrm{d}\theta^j
$$
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.2, Def. A.14, p. 35; Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf, Eq. 2.10.9 & 2.10.50, p. 1_

**Inverse Metric Tensor and Identity Operator**
$$
g_{ik} g^{kj} = \delta_i^j, \quad I_M = g \cdot g^{-1} = \delta_i^j \, \mathrm{d}\theta^i \otimes \frac{\partial}{\partial \theta^j}
$$
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.2, Def. A.15, p. 35_

**Index Lowering and Raising Operators**
$$
v_i = g_{ij} v^j, \quad v^i = g^{ij} v_j, \quad T_{ij} = g_{im} g_{jn} T^{mn}
$$
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.2, Def. A.16 & Remark A.3, pp. 35–36; Kinematics_of_CM_12_Pull_Back_Lie_Derivative.pdf, Sec. 2.12, Eqs. 2.12.27–2.12.30, pp. 1–2_

**Pull-Back Mapping of Spatial Metric to Cauchy-Green Tensor**
$$
C = \phi^* g = F^T \cdot g \cdot F
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 5.16, p. 315 & Sec. 5.10, p. 316_

**Notation:**
{'g_{ij}': 'Covariant metric tensor components.', 'g^{ij}': 'Contravariant inverse metric tensor components.', '\\theta^i': 'Curvilinear or convected coordinates.', '\\delta_i^j': 'Kronecker delta identity tensor component.', 'v^i, v_i': 'Contravariant vector and covariant 1-form components.', '\\flat, \\sharp': 'Index lowering and index raising operators.'}


## 3. Algorithmic Implementation

**Metric Tensor Evaluation and Index Manipulation Algorithm**
$$
\begin{algorithmic}
\State $Given spatial position mapping x(\theta) in curvilinear coordinates \theta^i and contravariant vector v^i$
\State $Compute covariant basis vectors \mathbf{g}_i \gets \frac{\partial x}{\partial \theta^i}$
\State $Evaluate covariant metric components g_{ij} \gets \mathbf{g}_i \cdot \mathbf{g}_j$
\State $Compute inverse matrix to obtain contravariant metric components g^{ij} \gets (g_{ij})^{-1}$
\State $Apply index lowering operator v_i \gets \sum_{j=1}^3 g_{ij} v^j$
\State $Verify inverse index raising v^i \gets \sum_{j=1}^3 g^{ij} v_j$
\Return $g_{ij}, g^{ij}, v_i$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.2, Def. A.14–A.16, pp. 35–36; Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf, Eq. 2.10.9 & 2.10.50, p. 1_


## 4. Known Pitfalls

- **Confusing Covariant and Contravariant Metric Indices in Vector Products**: Evaluating inner products v \cdot w as \sum_i v^i w^i without inserting the metric tensor g_{ij}. In non-Cartesian curvilinear coordinate systems, the inner product requires metric contractions v \cdot w = g_{ij} v^i w^j = v^i w_i. _(Source: Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf, Eq. 2.10.49–2.10.50, p. 1; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A.2, Def. A.15, p. 35)_
- **Assuming Spatial Metric g Is Variable in Flat Euclidean Space**: Failing to simplify g_{ij} = \delta_{ij} when operating in Cartesian coordinate frames. While general curvilinear systems require explicit metric calculations, Euclidean Cartesian frames satisfy g = I, reducing pull-back operations C = \phi^* g to C = F^T F. _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 5.16 & Sec. 5.10, pp. 315–316)_

## References

- Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf
- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Kinematics_of_CM_10_Convected_Coordinates.pdf.pdf
- Kinematics_of_CM_12_Pull_Back_Lie_Derivative.pdf
