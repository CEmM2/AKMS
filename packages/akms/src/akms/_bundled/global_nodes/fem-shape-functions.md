---
id: fem-shape-functions
title: Shape Function Families
domain: computational-mechanics
subdomain: finite-elements
tags:
- fem
- shape-functions
- lagrange
- serendipity
- elements
status: established
confidence: 0.9
source: hybrid
edges:
- to: fem-isoparametric-mapping
  type: feeds-into
  weight: 1.0
- to: fem-weak-form-derivation
  type: feeds-into
  weight: 1.0
- to: fem-tl-b-matrix
  type: feeds-into
  weight: 0.9
- to: fem-mixed-methods
  type: refines
  weight: 0.6
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Shape Function Families

## Summary

Shape functions interpolate spatial coordinates and field variables across finite element domains from discrete nodal degrees of freedom. Shape function families include standard Lagrangian polynomials, serendipity boundary-node formulations, hierarchical p-version extensions, and B-spline/NURBS basis functions in isogeometric analysis. All valid shape function families satisfy partition of unity and interpolation conditions to guarantee rigid-body representation and convergence.

## 1. Core Concept

Finite element spatial discretizations construct continuous trial and test function spaces using piecewise polynomial shape functions defined on a master/parent element domain. Lagrangian shape functions use tensor products of 1D Lagrange polynomials passing through all grid nodes, including interior points. Serendipity shape functions eliminate internal nodes by placing degrees of freedom exclusively along element boundaries. Hierarchical shape functions add higher-order polynomial modes onto existing lower-order nodal modes without altering lower-order functions, simplifying p-refinement. All valid shape function sets satisfy the partition of unity condition \sum_I N_I(\boldsymbol{\xi}) = 1, ensuring exact representation of rigid-body translations and passing the patch test.

## 2. Mathematical Formulation

**Partition of Unity Condition**
$$
\sum_{I=1}^{n_{\mathrm{en}}} N_I(\boldsymbol{\xi}) = 1
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 11.2, Eq. 11.2.1, p. 647; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.2, p. 33_

**Bilinear Quadrilateral (Quad4) Shape Functions**
$$
N_I(\xi, \eta) = \frac{1}{4} (1 + \xi_I \xi)(1 + \eta_I \eta), \quad I \in \{1, 2, 3, 4\}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.3, p. 40; ME280A.pdf, Sec. 5.36, p. 124_

**Trilinear Hexahedral (Hexa8) Shape Functions**
$$
N_I(\xi, \eta, \zeta) = \frac{1}{8} (1 + \xi_I \xi)(1 + \eta_I \eta)(1 + \zeta_I \zeta), \quad I \in \{1, \dots, 8\}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.2, Box 2.2, p. 36; ME280A.pdf, Sec. 5.36, Eq. 5.103, p. 132_

**One-Dimensional Hierarchical Shape Functions**
$$
N_1(\xi) = \frac{1}{2}(1 - \xi), \quad N_2(\xi) = \frac{1}{2}(1 + \xi), \quad N_c(\xi) = 1 - \xi^2
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 9.1, Eq. 9.14a, p. 310; ME280A.pdf, Sec. 5.7, p. 133_

**Notation:**
{'N_I': 'Interpolation shape function associated with node I.', '\\xi, \\eta, \\zeta': 'Parametric coordinates in parent element domain.', 'u_I': 'Vector or scalar degree of freedom at node I.', 'n_{\\mathrm{en}}': 'Number of element nodes / basis functions.'}


## 3. Algorithmic Implementation

**Bilinear Quadrilateral Shape Function and Derivative Evaluation**
$$
\begin{algorithmic}
\State $Given parent coordinates \boldsymbol{\xi} = (\xi, \eta)$
\State $Evaluate N_1 \gets \frac{1}{4}(1-\xi)(1-\eta), \quad N_2 \gets \frac{1}{4}(1+\xi)(1-\eta)$
\State $Evaluate N_3 \gets \frac{1}{4}(1+\xi)(1+\eta), \quad N_4 \gets \frac{1}{4}(1-\xi)(1+\eta)$
\State $Compute parametric derivatives \frac{\partial N_1}{\partial \boldsymbol{\xi}} \gets \begin{pmatrix} -\frac{1}{4}(1-\eta) \\ -\frac{1}{4}(1-\xi) \end{pmatrix}, \quad \frac{\partial N_2}{\partial \boldsymbol{\xi}} \gets \begin{pmatrix} \frac{1}{4}(1-\eta) \\ -\frac{1}{4}(1+\xi) \end{pmatrix}$
\State $Compute parametric derivatives \frac{\partial N_3}{\partial \boldsymbol{\xi}} \gets \begin{pmatrix} \frac{1}{4}(1+\eta) \\ \frac{1}{4}(1+\xi) \end{pmatrix}, \quad \frac{\partial N_4}{\partial \boldsymbol{\xi}} \gets \begin{pmatrix} -\frac{1}{4}(1+\eta) \\ \frac{1}{4}(1-\xi) \end{pmatrix}$
\Return $N, \frac{\partial N}{\partial \boldsymbol{\xi}}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.3, p. 40; ME280A.pdf, Sec. 5.36, p. 124_


## 4. Known Pitfalls

- **Violation of Partition of Unity in Incomplete Bases**: Constructing custom polynomial shape function sets without verifying that \sum_I N_I(\boldsymbol{\xi}) = 1 prevents the element from representing constant field translation, failing the patch test and causing convergence failure under mesh refinement. Mitigation: Ensure shape function derivations enforce partition of unity across the entire element domain. _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 8.3, p. 488 & Sec. 11.2, p. 647; ME280A.pdf, Sec. 5.36, p. 128)_
- **Incompatible Inter-Element Continuity in Higher-Order Serendipity Elements**: Mixing serendipity elements with different polynomial orders or distorted element geometries can cause displacement field discontinuities across element boundaries because boundary edge interpolations fail to match. Mitigation: Ensure matching node configurations along shared interfaces or use isoparametric mappings with compatible boundary interpolations. _(Source: ME280A.pdf, Sec. 5.7, Problem 6, p. 134; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 7.6, p. 275)_

## References

- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- ME280A.pdf
