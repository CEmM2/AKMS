---
id: tensor-isotropic-functions
title: Isotropic Tensor Functions (exp, log, power)
domain: computational-mechanics
subdomain: tensor-algebra
tags:
- tensors
- continuum-mechanics
- isotropic-functions
- log-strain
- hencky-strain
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-spectral-decomposition
  type: requires
  weight: 1.0
- to: tensor-derivatives-tensors
  type: requires
  weight: 1.0
- to: kinematics-logarithmic-strain
  type: feeds-into
  weight: 1.0
- to: kinematics-multiplicative-decomp
  type: feeds-into
  weight: 0.7
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Isotropic Tensor Functions (exp, log, power)

## Summary

Isotropic tensor functions evaluate scalar, vector, or tensor operations on second-order tensors independently of spatial coordinate rotations. Computed spectrally via eigenvalue-eigenprojection representations, isotropic functions define matrix exponentials, logarithms, and powers critical for logarithmic strain measures, hyperelastic strain energy potentials, and multiplicative elastic-plastic return-mapping updates.

## 1. Core Concept

An isotropic tensor function f(C) of a symmetric second-order tensor C commutes with arbitrary orthogonal rotation transformations, satisfying f(Q C Q^T) = Q f(C) Q^T. Using spectral decomposition, C is represented by its principal eigenvalues k_i and orthonormal eigenprojections E_i = N_i \otimes N_i. The isotropic function f(C) is evaluated by applying the scalar function f(\cdot) directly to eigenvalues k_i, giving f(C) = \sum_{i=1}^3 f(k_i) E_i. Key applications in finite deformation mechanics include evaluating logarithmic strain E = 1/2 \ln C, matrix exponential return mapping (F^e)^{t+\Delta t} = \exp((D^e)^{-1} : \kappa), and fractional stretch powers C^{1/2}. Computing fourth-order derivatives \partial f(C) / \partial C requires divided differences that handle distinct, double, and triple coalescent eigenvalues smoothly to prevent division-by-zero singularities.

## 2. Mathematical Formulation

**Spectral Evaluation of Isotropic Tensor Function**
$$
f(C) = \sum_{i=1}^3 f(k_i) E_i, \quad E_i = N_i \otimes N_i
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.3, p. 387; Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf, Box 3, p. 5406_

**Logarithmic Tensor Strain Evaluation**
$$
E = \frac{1}{2} \ln C = \sum_{i=1}^3 \left( \frac{1}{2} \ln k_i \right) N_i \otimes N_i
$$
_Source: Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf, Box 2 & Box 3, pp. 5391, 5406; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 11.8, Eq. 11.108, p. 388_

**Exponential Return-Mapping Tensor Update**
$$
(F^e)^{t+\Delta t} = \exp \left( (D^e)^{-1} : \kappa^{n+1} \right)
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 12.2, p. 421_

**Fourth-Order Isotropic Derivative Coefficients via Divided Differences**
$$
\theta_{ij} = \begin{cases} \frac{e_i - e_j}{k_i - k_j} & \text{if } k_i \neq k_j \\ \frac{1}{2 k_i} & \text{if } k_i = k_j \end{cases}
$$
_Source: Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf, Box 3, p. 5406; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.3, p. 387_

**Notation:**
{'C': 'Symmetric positive-definite second-order tensor.', 'k_i': 'Principal eigenvalues of tensor C.', 'N_i': 'Orthonormal eigenvectors of tensor C.', 'E_i': 'Rank-one eigenprojection tensor E_i = N_i \\otimes N_i.', 'e_i': 'Scalar evaluation e_i = f(k_i) on principal eigenvalue k_i.', '\\theta_{ij}': 'Divided difference coefficient for fourth-order isotropic tensor derivatives.'}


## 3. Algorithmic Implementation

**Spectral Evaluation and Differentiation of Isotropic Logarithmic Tensor Function**
$$
\begin{algorithmic}
\State $Given symmetric positive-definite second-order tensor C$
\State $Solve eigenvalue problem C N_i = k_i N_i to obtain principal eigenvalues k_i and orthonormal eigenvectors N_i for i \in \{1, 2, 3\}$
\State $Evaluate scalar logarithmic function e_i \gets \frac{1}{2} \ln k_i \text{ and eigenprojections } E_i \gets N_i \otimes N_i$
\State $Construct logarithmic strain tensor E \gets \sum_{i=1}^3 e_i E_i$
\If{$Eigenvalues k_i are distinct (k_1 \neq k_2 \neq k_3)$}
\State $Compute divided difference coefficients \theta_{ij} \gets \frac{e_i - e_j}{k_i - k_j} \text{ for } i \neq j$
\Else
\EndIf
\State $Assemble fourth-order isotropic derivative tensor \frac{\partial E}{\partial C}$
\Return $E, \frac{\partial E}{\partial C}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf, Box 3, p. 5406; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.3, p. 387_


## 4. Known Pitfalls

- **Division-by-Zero Singularities at Coalescent Eigenvalues**: Evaluating fourth-order derivatives of isotropic tensor functions using raw finite difference formulas (k_i - k_j)^{-1} when two or three eigenvalues coalesce (k_i \approx k_j) causes severe floating-point division-by-zero errors. Mitigation: Use analytical limit expressions for equal eigenvalues (\theta_{ij} = \frac{1}{2 k_i}) or Taylor series expansions when |k_i - k_j| < \epsilon. _(Source: Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf, Box 3, p. 5406; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.3, p. 387)_
- **Loss of Coaxiality in Anisotropic Constitutive Updates**: Assuming that isotropic tensor functions preserve diagonal spectral representations in anisotropic materials. While isotropic strain energy functions guarantee that stress S and Cauchy-Green tensor C share identical principal eigenprojections E_i, anisotropic structural tensors break coaxiality and require full tensor transformations. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 11.3, p. 387; Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf, Sec. 3.2, pp. 5393–5395)_

## References

- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Miehe et al. - 2002 - Anisotropic additive plasticity in the logarithmic strain space modular kinematic formulation and i.pdf
