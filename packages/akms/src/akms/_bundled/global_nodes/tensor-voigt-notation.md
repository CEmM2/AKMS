---
id: tensor-voigt-notation
title: Voigt Notation for Symmetric Tensors
domain: computational-mechanics
subdomain: tensor-algebra
tags:
- tensors
- continuum-mechanics
- voigt
- tensor-notation
- matrix-free
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-products-contractions
  type: requires
  weight: 0.9
- to: tensor-mandel-notation
  type: feeds-into
  weight: 1.0
- to: fem-tl-b-matrix
  type: feeds-into
  weight: 1.0
- to: plasticity-consistent-tangent-general
  type: feeds-into
  weight: 0.9
context_size: small
reading_priority: full
content_ref: null
akms_schema: v2
---

# Voigt Notation for Symmetric Tensors

## Summary

Voigt notation compresses symmetric second-order tensors into column vectors and fourth-order tangent moduli into 6x6 matrices. By doubling kinematic shear strain components, Voigt array operations preserve energy inner products and work conjugacy in finite element implementations.

## 1. Core Concept

In computational solid mechanics, storing symmetric 3x3 second-order tensors as 6x1 column vectors and 4th-order tangent operators as 6x6 matrices reduces storage memory and enables matrix-vector operations. Voigt notation enforces a distinct rule for kinetic tensors (such as Cauchy stress \boldsymbol{\sigma} or Second Piola-Kirchhoff stress \mathbf{S}) versus kinematic tensors (such as Green-Lagrange strain \mathbf{E} or rate of deformation \mathbf{D}). Kinetic vectors store unscaled tensor components \{\sigma\} = [\sigma_{11}, \sigma_{22}, \sigma_{33}, \sigma_{23}, \sigma_{13}, \sigma_{12}]^T. Kinematic vectors double the off-diagonal shear components to store engineering shear strains \gamma_{ij} = 2\varepsilon_{ij}, yielding \{\varepsilon\} = [\varepsilon_{11}, \varepsilon_{22}, \varepsilon_{33}, 2\varepsilon_{23}, 2\varepsilon_{13}, 2\varepsilon_{12}]^T. This factor-of-two scaling ensures that vector dot products match tensor double contractions \boldsymbol{\sigma} : \boldsymbol{\varepsilon} = \{\sigma\}^T \{\varepsilon\}, preserving virtual work expressions.

## 2. Mathematical Formulation

**Kinetic and Kinematic Voigt Vector Mappings**
$$
\{\sigma\} = \begin{bmatrix} \sigma_{11} \\ \sigma_{22} \\ \sigma_{33} \\ \sigma_{23} \\ \sigma_{13} \\ \sigma_{12} \end{bmatrix}, \quad \{\varepsilon\} = \begin{bmatrix} \varepsilon_{11} \\ \varepsilon_{22} \\ \varepsilon_{33} \\ 2\varepsilon_{23} \\ 2\varepsilon_{13} \\ 2\varepsilon_{12} \end{bmatrix} = \begin{bmatrix} \varepsilon_{11} \\ \varepsilon_{22} \\ \varepsilon_{33} \\ \gamma_{23} \\ \gamma_{13} \\ \gamma_{12} \end{bmatrix}
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Appendix 1, Eqs. A.1.1–A.1.4, pp. 751–752; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 1.3, p. 22_

**Work Conjugacy Preservation in Voigt Form**
$$
\delta W^{\mathrm{int}} = \int_V \boldsymbol{\sigma} : \delta \boldsymbol{\varepsilon} \, \mathrm{d}V = \int_V \{\sigma\}^T \{\delta \varepsilon\} \, \mathrm{d}V
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Appendix 1, Eq. A.1.5, p. 752; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 1.3, p. 22_

**Isotropic Elasticity Modulus Matrix in Voigt Notation**
$$
\{\sigma\} = [D^{\mathrm{e}}] \{\varepsilon\}, \quad [D^{\mathrm{e}}] = \frac{E}{(1+\nu)(1-2\nu)} \begin{bmatrix} 1-\nu & \nu & \nu & 0 & 0 & 0 \\ \nu & 1-\nu & \nu & 0 & 0 & 0 \\ \nu & \nu & 1-\nu & 0 & 0 & 0 \\ 0 & 0 & 0 & \frac{1-2\nu}{2} & 0 & 0 \\ 0 & 0 & 0 & 0 & \frac{1-2\nu}{2} & 0 \\ 0 & 0 & 0 & 0 & 0 & \frac{1-2\nu}{2} \end{bmatrix}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 1.4, Eq. 1.115, p. 25; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 5.4, Eq. 5.4.9, p. 243_

**Notation:**
{'\\{\\sigma\\}': '6x1 kinetic stress vector array.', '\\{\\varepsilon\\}': '6x1 kinematic strain vector array.', '\\gamma_{ij}': 'Engineering shear strain \\gamma_{ij} = 2\\varepsilon_{ij} (i \\neq j).', '[D^{\\mathrm{e}}]': '6x6 elastic material stiffness matrix.', '\\delta W^{\\mathrm{int}}': 'Internal virtual work rate scalar.'}


## 3. Algorithmic Implementation

**Voigt Conversion and Internal Force Vector Assembly Algorithm**
$$
\begin{algorithmic}
\State $Given 3x3 symmetric Second Piola-Kirchhoff stress S_{ij} and 3x3 strain tensor E_{ij}$
\State $Construct kinetic stress vector \{S\} \gets [S_{11}, S_{22}, S_{33}, S_{23}, S_{13}, S_{12}]^T$
\State $Construct kinematic strain vector \{E\} \gets [E_{11}, E_{22}, E_{33}, 2E_{23}, 2E_{13}, 2E_{12}]^T$
\State $Verify internal energy density rate equivalence: \dot{w} \gets \{S\}^T \{\dot{E}\} = S_{ij} \dot{E}_{ij}$
\State $Compute internal force contribution: \mathbf{f}^{\mathrm{int}}_I \gets \int_{\Omega_0} \mathbf{B}_{0I}^T \{S\} \, \mathrm{d}\Omega_0$
\Return $\{S\}, \{E\}, \mathbf{f}^{\mathrm{int}}_I$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 4.6 & Appendix 1, pp. 211, 751–752; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 1.3 & 3.4.1, pp. 22, 94_


## 4. Known Pitfalls

- **Omitting Factor of Two in Kinematic Strain Vector Components**: Converting symmetric second-order strain tensors E_{ij} into Voigt vectors using tensor shear components \varepsilon_{ij} instead of engineering shear strains \gamma_{ij} = 2\varepsilon_{ij}. Omitting the factor of two causes an incorrect evaluation of internal energy rates \{S\}^T \{E\} \neq \mathbf{S} : \mathbf{E} and corrupts shear terms in material stiffness matrices. _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Appendix 1, p. 752; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 1.3, p. 22)_
- **Applying Matrix Operations to Two-Point Tensors in Voigt Form**: Attempting to perform coordinate transformations or push-forward operations on Voigt vectors using 6x6 transformations designed for symmetric tensors on two-point non-symmetric operators (such as deformation gradient F). Push-forward operations must be evaluated in tensor form \boldsymbol{\tau} = \mathbf{F} \mathbf{S} \mathbf{F}^T before mapping to Voigt vectors. _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 4.6 & Appendix 1, pp. 211, 751–752)_

## References

- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
