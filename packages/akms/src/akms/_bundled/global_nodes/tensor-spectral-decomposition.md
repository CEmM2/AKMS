---
id: tensor-spectral-decomposition
title: Spectral Decomposition of Symmetric Tensors
domain: computational-mechanics
subdomain: tensor-algebra
tags:
- tensors
- continuum-mechanics
- eigenvalues
- eigenprojection
- spectral-decomposition
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-invariants
  type: requires
  weight: 1.0
  note: Spectral decomposition relies on characteristic equations and tensor invariants
- to: tensor-isotropic-functions
  type: feeds-into
  weight: 1.0
  note: Spectral representations enable scalar evaluation of isotropic tensor functions
- to: tensor-derivatives-tensors
  type: feeds-into
  weight: 1.0
  note: Derivative expressions for isotropic tensor functions utilize eigenprojections
- to: kinematics-polar-decomposition
  type: feeds-into
  weight: 0.9
  note: Polar stretch tensors U and V are evaluated via square roots of C and b spectra
- to: pf-spectral-split
  type: feeds-into
  weight: 0.8
  note: Constitutive strain/stress splits use spectral projection operators
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Spectral Decomposition of Symmetric Tensors

## Summary

Spectral decomposition represents a symmetric second-order tensor in terms of its real eigenvalues (principal values) and orthonormal eigenvectors (principal directions) or eigenprojections. This formulation reduces tensor operations, such as fractional powers, logarithms, and isotropic stress-strain return mappings, to scalar functions evaluated along principal axes.

## 1. Core Concept

Any symmetric second-order tensor in continuum mechanics (such as the right Cauchy-Green tensor C, Cauchy stress tensor sigma, or strain tensor) possesses three real eigenvalues and a set of mutually orthogonal principal directions. In spectral form, the tensor is expressed either as a sum of outer products of its orthonormal eigenvectors or as a linear combination of its rank-one eigenprojection matrices. This transformation simplifies non-linear isotropic tensor functions—including logarithmic strains, hyperelastic stored energy potentials, and yield criteria—by decoupling the tensor into independent scalar operations in principal space.

## 2. Mathematical Formulation

**Characteristic Equation and Principal Invariants**
$$
\det(C - \lambda I) = -\lambda^3 + I_1 \lambda^2 - I_2 \lambda + I_3 = 0
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 1.2, Eqs. 1.83–1.86, p. 20; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, App. A, p. 28_

**Spectral Decomposition and Eigenprojections**
$$
C = \sum_{i=1}^3 \lambda_i e_i \otimes e_i = \sum_{i=1}^3 \lambda_i E_i, \quad E_i = e_i \otimes e_i, \quad \sum_{i=1}^3 E_i = I
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 1.2, Eqs. 1.69–1.71, p. 16_

**Isotropic Tensor Function Evaluation**
$$
f(C) = \sum_{i=1}^3 f(\lambda_i) E_i, \quad \ln U = \frac{1}{2} \ln C = \sum_{i=1}^3 (\ln \lambda_i) E_i
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 11.8, Eq. 11.108, p. 388; Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf, Def. 2.16, p. 8; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 3.7.1, p. 131_

**Closed-Form Principal Stress via Lode Angle**
$$
\begin{pmatrix} \sigma_1 \\ \sigma_2 \\ \sigma_3 \end{pmatrix} = 2 \sqrt{\frac{J_2}{3}} \begin{pmatrix} \sin(\theta - 2\pi/3) \\ \sin(\theta) \\ \sin(\theta + 2\pi/3) \end{pmatrix} + p \begin{pmatrix} 1 \\ 1 \\ 1 \end{pmatrix}, \quad \sin(3\theta) = \frac{-J_3}{2 (J_2/3)^{3/2}}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 7.3.5, Eqs. 7.164–7.165, p. 261_

**Notation:**
{'C': 'Symmetric second-order tensor (e.g., right Cauchy-Green deformation tensor).', '\\lambda_i': 'Principal values (eigenvalues) of tensor C.', 'e_i': 'Orthonormal unit eigenvectors (principal directions).', 'E_i': 'Eigenprojection tensor e_i \\otimes e_i.', 'I_1, I_2, I_3': 'Principal invariants of a second-order tensor.', 'J_2, J_3': 'Second and third invariants of the deviatoric stress tensor.', '\\theta': 'Lode angle defined in deviatoric stress space.', 'p': 'Hydrostatic mean stress p = (1/3) tr(\\sigma).'}


## 3. Algorithmic Implementation

**Spectral Decomposition and Isotropic Function Evaluation Algorithm**
$$
\begin{algorithmic}
\State $Given symmetric 3x3 tensor C and scalar function f(\cdot)$
\State $Compute principal invariants I_1 = \mathrm{tr}(C), I_2 = \frac{1}{2}[(\mathrm{tr} C)^2 - \mathrm{tr}(C^2)], I_3 = \det(C)$
\State $Solve characteristic polynomial -\lambda^3 + I_1 \lambda^2 - I_2 \lambda + I_3 = 0 \text{ for eigenvalues } \lambda_1, \lambda_2, \lambda_3$
\If{$\lambda_1, \lambda_2, \lambda_3 \text{ are distinct } (\lambda_1 \neq \lambda_2 \neq \lambda_3)$}
\For{$i \gets 1 \text{ to } 3$}
\State $Compute eigenprojection E_i \gets \frac{\lambda_i}{2\lambda_i^3 - I_1 \lambda_i^2 + I_3} \left( C^2 - (I_1 - \lambda_i)C + I_3 I \right)$
\EndFor
\ElsIf{$\text{Two eigenvalues are equal } (\lambda_1 \neq \lambda_2 = \lambda_3)$}
\State $Evaluate degenerate eigenprojections via E_1 \gets \frac{C - \lambda_2 I}{\lambda_1 - \lambda_2} \text{ and } E_2 \gets I - E_1$
\Else
\State $Set E_1 \gets I \text{ and } E_2 \gets 0, E_3 \gets 0$
\EndIf
\State $Evaluate tensor function f(C) \gets \sum_{i=1}^3 f(\lambda_i) E_i$
\Return $f(C)$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 1.1, p. 16, Sec. 11.8, p. 388, & Box 11.3, p. 387_


## 4. Known Pitfalls

- **Ill-Conditioned Eigenprojection Formulas Near Coinciding Eigenvalues**: Using distinct-eigenvalue closed-form expressions for eigenprojections E_i when two or three eigenvalues are nearly equal causes division by near-zero denominators (\(\lambda_i - \lambda_j \to 0\)), leading to extreme loss of numerical precision. Mitigation: Use explicit degenerate branching conditions (such as \(E_1 = (C - \lambda_2 I)/(\lambda_1 - \lambda_2)\) when \(\lambda_2 = \lambda_3\), or \(E_1 = I\) when \(\lambda_1 = \lambda_2 = \lambda_3\)) when eigenvalues coincide. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.3, p. 387)_
- **Round-Off Error in Lode Angle Arccos/Arcsin Bounds**: Numerical floating-point round-off can cause the argument of \(\sin(3\theta) = -J_3 / [2(J_2/3)^{3/2}]\) to slightly exceed 1.0 or fall below -1.0 in magnitude, causing domain errors in inverse trigonometric functions. Mitigation: Clamp the argument to [-1, 1] prior to evaluating the arcsin or Lode angle. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 7.3.5, Eq. 7.165, p. 261)_

## References

- Aubram_2017_Notes on rate equations in nonlinear continuum mechanics.pdf
- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
