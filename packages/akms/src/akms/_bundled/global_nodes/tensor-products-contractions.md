---
id: tensor-products-contractions
title: Tensor Products & Contractions
domain: computational-mechanics
subdomain: tensor-algebra
tags:
- tensors
- continuum-mechanics
- dyadic-product
- contraction
- fourth-order
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-index-notation
  type: requires
  weight: 1.0
- to: tensor-voigt-notation
  type: feeds-into
  weight: 0.9
- to: tensor-invariants
  type: feeds-into
  weight: 0.7
- to: tensor-derivatives-tensors
  type: feeds-into
  weight: 0.9
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Tensor Products & Contractions

## Summary

Tensor products and contractions form the operational building blocks of continuum mechanics, enabling dyadic product creation, tensor order reduction, and internal power calculations. Special fourth-order tensor products capture non-standard index pairings necessary for constructing consistent algorithmic tangent stiffness matrices.

## 1. Core Concept

Tensor products expand lower-order vector or tensor spaces into higher-order tensor structures, while contractions reduce tensor rank by summing over paired indices. Dyadic vector products a \otimes b yield second-order tensors a_i b_j. Double contractions A : B evaluate inner products of second-order tensors A_{ij} B_{ij}, representing work-conjugate energy rates. Contracting a fourth-order tangent tensor \mathbb{C} with a second-order strain tensor E produces a second-order stress tensor \sigma_{ij} = C_{ijkl} E_{kl}. In finite deformation mechanics, specialized fourth-order tensor products (such as (A \bar{\otimes} B)_{ijkl} = A_{ik} B_{jl} and (A \bar{\bar{\otimes}} B)_{ijkl} = A_{il} B_{jk}) express derivatives of non-linear strain metrics and deformation gradients.

## 2. Mathematical Formulation

**Single and Double Tensor Contractions**
$$
A \cdot B = A_{ij} B_{jk} \mathbf{e}_i \otimes \mathbf{e}_k, \quad A : B = A_{ij} B_{ij}, \quad \mathbb{C} : B = C_{ijkl} B_{kl} \mathbf{e}_i \otimes \mathbf{e}_j
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, pp. 777–778; Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, Sec. Notation, p. 47_

**Vector Dyadic and Fourth-Order Tensor Products**
$$
a \otimes b = a_i b_j \mathbf{e}_i \otimes \mathbf{e}_j, \quad A \otimes B = A_{ij} B_{kl} \mathbf{e}_i \otimes \mathbf{e}_j \otimes \mathbf{e}_k \otimes \mathbf{e}_l
$$
_Source: Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, Sec. Notation, p. 47; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, p. 778_

**Specialized Index-Permuted Fourth-Order Tensor Products**
$$
(A \bar{\otimes} B)_{ijkl} = A_{ik} B_{jl}, \quad (A \bar{\bar{\otimes}} B)_{ijkl} = A_{il} B_{jk}
$$
_Source: Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, Sec. Notation & App. A, Eqs. A.16 & A.21, pp. 47, 49–50; Generic_anisotropic_thermo-elastoviscoplasticity.pdf, Sec. Notation, p. 123_

**Elastic Strain Tangent Derivative via Specialized Tensor Products**
$$
\frac{\partial E^e}{\partial F^e} = \frac{1}{2} \left( I \bar{\otimes} F^{eT} + F^{eT} \bar{\bar{\otimes}} I \right)
$$
_Source: Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, App. A, Eq. A.21, p. 50_

**Notation:**
{'\\otimes': 'Dyadic / tensor product operator.', '\\cdot': 'Single index contraction operator.', ':': 'Double index contraction operator.', '\\bar{\\otimes}, \\bar{\\bar{\\otimes}}': 'Index-permuted fourth-order tensor product operators.', 'A_{ij}, B_{kl}': 'Components of second-order tensors.', 'C_{ijkl}': 'Components of fourth-order tensor.'}


## 3. Algorithmic Implementation

**Fourth-Order Tensor Product and Double Contraction Evaluation Algorithm**
$$
\begin{algorithmic}
\State $Given second-order tensors A and B with components A_{ij} and B_{ij}$
\State $Compute double contraction scalar s \gets \sum_{i=1}^3 \sum_{j=1}^3 A_{ij} B_{ij}$
\State $Evaluate standard 4th-order tensor product (A \otimes B)_{ijkl} \gets A_{ij} B_{kl}$
\State $Evaluate index-permuted 4th-order product (A \bar{\otimes} B)_{ijkl} \gets A_{ik} B_{jl}$
\State $Evaluate second permuted product (A \bar{\bar{\otimes}} B)_{ijkl} \gets A_{il} B_{jk}$
\State $Evaluate double contraction of (A \bar{\otimes} B) with tensor C: \mathbb{H}_{ij} \gets \sum_{k=1}^3 \sum_{l=1}^3 (A \bar{\otimes} B)_{ijkl} C_{kl}$
\Return $s, A \otimes B, A \bar{\otimes} B, \mathbb{H}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, Sec. Notation, p. 47; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, pp. 777–778_


## 4. Known Pitfalls

- **Index Order Inversion in Double Contractions**: Failing to maintain proper index ordering when evaluating double contractions A : B. Standard double contraction evaluates A_{ij} B_{ij} (or C_{ijkl} D_{kl}), whereas reversed index contraction A_{ij} B_{ji} is only equivalent when either tensor is symmetric. _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, p. 778; Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, Sec. Notation, p. 47)_
- **Mismatched Leg Pairing in Fourth-Order Tensor Products**: Substituting standard dyadic product A_{ij} B_{kl} for permuted tensor products A_{ik} B_{jl} or A_{il} B_{jk} during tangent modulus derivations produces incorrect index contractions when evaluating Jacobians and stress updates. _(Source: Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf, App. A, Eqs. A.16 & A.21, pp. 49–50; Generic_anisotropic_thermo-elastoviscoplasticity.pdf, Sec. Notation, p. 123)_

## References

- Abatour et al_2021_A generic formulation of anisotropic thermo-elastoviscoplasticity at finite.pdf
- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Generic_anisotropic_thermo-elastoviscoplasticity.pdf
