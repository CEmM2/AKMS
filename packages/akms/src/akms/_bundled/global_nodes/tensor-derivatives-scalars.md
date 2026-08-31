---
id: tensor-derivatives-scalars
title: Derivatives of Scalar Functions of Tensors
domain: computational-mechanics
subdomain: tensor-algebra
tags:
- tensors
- continuum-mechanics
- tensor-derivatives
- hyperelastic
- chain-rule
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-invariants
  type: requires
  weight: 1.0
- to: tensor-products-contractions
  type: requires
  weight: 0.8
- to: tensor-derivatives-tensors
  type: feeds-into
  weight: 0.9
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Derivatives of Scalar Functions of Tensors

## Summary

Derivatives of scalar-valued functions with respect to second-order tensors establish the foundation for hyperelastic constitutive modeling, stress evaluation, and non-linear finite element linearizations. Through tensor chain rules and primary invariant derivatives, scalar strain energy potentials generate symmetric stress tensors such as the Second Piola-Kirchhoff and Kirchhoff stress measures.

## 1. Core Concept

In non-linear continuum mechanics, hyperelastic material response is defined by a scalar strain energy density function W(C) or w(E). Differentiating this scalar potential with respect to the right Cauchy-Green deformation tensor C or Green-Lagrange strain tensor E yields energetically conjugate stress tensors: Second Piola-Kirchhoff stress S = 2 \partial W / \partial C = \partial w / \partial E. When energy potentials depend on deformation through primary scalar invariants I_1, I_2, I_3 or modified volumetric/isochoric invariants J_1, J_2, J_3, the derivative is evaluated by combining scalar partial derivatives with explicit tensor derivatives of the invariants (\partial I_1 / \partial C = I, \partial I_3 / \partial C = I_3 C^{-1}) via the tensor chain rule.

## 2. Mathematical Formulation

**Second Piola-Kirchhoff Stress as Scalar Potential Derivative**
$$
S = 2 \frac{\partial W}{\partial C} = \frac{\partial w}{\partial E}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 11.4, Eq. 11.63, p. 376; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, p. 779_

**Derivatives of Primary Scalar Invariants**
$$
\frac{\partial I_1}{\partial C} = I, \quad \frac{\partial I_2}{\partial C} = I_1 I - C, \quad \frac{\partial I_3}{\partial C} = I_3 C^{-1}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.1, p. 380_

**Tensor Chain Rule for Invariant-Based Potentials**
$$
\frac{\partial W}{\partial C} = \sum_{k=1}^3 \frac{\partial W}{\partial J_k} \frac{\partial J_k}{\partial C}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.1, p. 380_

**Derivatives of Modified Isochoric and Volumetric Invariants**
$$
\frac{\partial J_1}{\partial C} = I_3^{-1/3} \frac{\partial I_1}{\partial C} - \frac{1}{3} I_1 I_3^{-4/3} \frac{\partial I_3}{\partial C}, \quad \frac{\partial J_3}{\partial C} = \frac{1}{2} I_3^{-1/2} \frac{\partial I_3}{\partial C}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.1, p. 380_

**Notation:**
{'W': 'Scalar strain energy density function.', 'C': 'Symmetric right Cauchy-Green deformation tensor C = F^T F.', 'S': 'Second Piola-Kirchhoff stress tensor.', 'I_1, I_2, I_3': 'Primary scalar invariants of tensor C.', 'J_1, J_2, J_3': 'Modified volumetric/isochoric invariants.', 'I': 'Second-order identity tensor.'}


## 3. Algorithmic Implementation

**Hyperelastic Stress Evaluation via Scalar Tensor Differentiation**
$$
\begin{algorithmic}
\State $Given right Cauchy-Green tensor C and hyperelastic energy potential W(J_1, J_2, J_3)$
\State $Compute primary invariants I_1 \gets \mathrm{tr}(C), I_2 \gets \frac{1}{2}[(\mathrm{tr} C)^2 - \mathrm{tr}(C^2)], I_3 \gets \det(C)$
\State $Compute modified invariants J_1 \gets I_1 I_3^{-1/3}, J_2 \gets I_2 I_3^{-2/3}, J_3 \gets I_3^{1/2}$
\State $Compute primary invariant derivatives \frac{\partial I_1}{\partial C} \gets I, \quad \frac{\partial I_2}{\partial C} \gets I_1 I - C, \quad \frac{\partial I_3}{\partial C} \gets I_3 C^{-1}$
\State $Compute modified invariant derivatives \frac{\partial J_k}{\partial C} \text{ for } k \in \{1, 2, 3\}$
\State $Evaluate partial scalar derivatives \frac{\partial W}{\partial J_k}$
\State $Assemble Second Piola-Kirchhoff stress tensor S \gets 2 \sum_{k=1}^3 \frac{\partial W}{\partial J_k} \frac{\partial J_k}{\partial C}$
\Return $S$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.1, p. 380_


## 4. Known Pitfalls

- **Omitting Symmetry in Differentiation of Symmetric Tensors**: Differentiating scalar functions of symmetric tensors (such as C or E) without accounting for symmetry constraints can lead to non-symmetric stress tensor outputs or incorrect off-diagonal factor scaling. Mitigation: Enforce symmetry on scalar tensor derivatives by evaluating symmetric projections \frac{1}{2}\left(\frac{\partial W}{\partial C} + \left(\frac{\partial W}{\partial C}\right)^T\right). _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.1, p. 380 & Box 11.2, p. 381)_
- **Singular Inverse Invariants at Zero Determinant**: Evaluating derivative expressions involving \frac{\partial I_3}{\partial C} = I_3 C^{-1} or \frac{\partial J_1}{\partial C} when \det C \to 0 causes division-by-zero singularities. Mitigation: Use adjugate matrix formulations or check for non-singular deformation states (\det F > 0) prior to invariant differentiation. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.1, p. 380)_

## References

- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
