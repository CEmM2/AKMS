---
id: tensor-index-notation
title: Index Notation & Einstein Convention
domain: computational-mechanics
subdomain: tensor-algebra
tags:
- tensors
- continuum-mechanics
- index-notation
- einstein-convention
status: established
confidence: 0.9
source: hybrid
edges:
- to: tensor-products-contractions
  type: feeds-into
  weight: 1.0
- to: tensor-invariants
  type: feeds-into
  weight: 0.9
- to: kinematics-motion-deformation-gradient
  type: feeds-into
  weight: 0.8
- to: fem-tl-b-matrix
  type: feeds-into
  weight: 0.7
context_size: small
reading_priority: full
content_ref: null
akms_schema: v2
---

# Index Notation & Einstein Convention

## Summary

Index notation and the Einstein summation convention provide a concise indicial framework for representing vector and tensor operations in continuum mechanics. By implicitly summing over repeated indices and utilizing index operators like the Kronecker delta and Levi-Civita permutation symbol, index notation expresses complex tensor contractions, gradients, and balance equations in component form.

## 1. Core Concept

Index notation replaces direct tensor operators with component expressions referred to Cartesian or curvilinear coordinate bases. Under the Einstein summation convention, any index appearing twice in a single term implies a summation over spatial dimensions (typically 1, 2, 3). Free indices appear once per term and dictate the tensorial rank of the resulting expression. The Kronecker delta \delta_{ij} acts as an identity operator and index substitution tool, while the Levi-Civita permutation symbol e_{ijk} expresses cross products and determinants. Spatial partial differentiation is denoted compactly using comma notation (a_{i,j} = \partial a_i / \partial x_j).

## 2. Mathematical Formulation

**Einstein Summation and Tensor Contraction**
$$
c = a \cdot b = a_i b_i, \quad (A \cdot B)_{ij} = A_{ik} B_{kj}, \quad A : B = A_{ij} B_{ij}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Notation & Sec. 1, pp. xv, 8, 22; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, pp. 777–778_

**Kronecker Delta Properties and Index Substitution**
$$
\delta_{ij} = \begin{cases} 1 & \text{if } i = j \\ 0 & \text{if } i \neq j \end{cases}, \quad \delta_{ij} v_j = v_i, \quad \delta_{ij} A_{jk} = A_{ik}, \quad \delta_{ii} = 3
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Notation, p. xv; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, p. 778_

**Permutation Symbol and Cross Product**
$$
(a \times b)_i = e_{ijk} a_j b_k, \quad e_{ijk} = \begin{cases} 1 & \text{if } (i,j,k) \in \{(1,2,3), (2,3,1), (3,1,2)\} \\ -1 & \text{if } (i,j,k) \in \{(1,3,2), (3,2,1), (2,1,3)\} \\ 0 & \text{otherwise} \end{cases}
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Notation, p. xv; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, p. 778_

**Comma Derivative Notation**
$$
f_{,i} = \frac{\partial f}{\partial x_i}, \quad v_{i,j} = \frac{\partial v_i}{\partial x_j}, \quad \sigma_{ij,j} = \frac{\partial \sigma_{ij}}{\partial x_j}
$$
_Source: Bathe et al_1975_Finite element formulations for large deformation dynamic analysis.pdf, App. Nomenclature, p. 383; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Box 2.1, p. 32_

**Notation:**
{'\\delta_{ij}': 'Kronecker delta identity component.', 'e_{ijk}': 'Levi-Civita permutation symbol.', 'A_{ij}': 'Second-order tensor component.', 'C_{ijkl}': 'Fourth-order tensor component.', 'v_{i,j}': 'Partial derivative of vector component v_i with respect to coordinate x_j.'}


## 3. Algorithmic Implementation

**Conversion of Direct Tensor Expressions to Index Notation and Matrix Form**
$$
\begin{algorithmic}
\State $Given direct tensor expression for internal virtual work rate \dot{W}^{\mathrm{int}} = \int_V \boldsymbol{\sigma} : \mathbf{D} \, \mathrm{d}V$
\State $Expand double contraction in index notation: \boldsymbol{\sigma} : \mathbf{D} \to \sigma_{ij} D_{ij}$
\State $Apply symmetry of Cauchy stress \sigma_{ij} = \sigma_{ji} to write \sigma_{ij} D_{ij} = \sigma_{xx} D_{xx} + \sigma_{yy} D_{yy} + \sigma_{zz} D_{zz} + 2 \sigma_{xy} D_{xy} + 2 \sigma_{yz} D_{yz} + 2 \sigma_{zx} D_{zx}$
\State $Map symmetric tensor components to Voigt vector arrays: \{\sigma\}^T = (\sigma_{xx}, \sigma_{yy}, \sigma_{zz}, \sigma_{xy}, \sigma_{yz}, \sigma_{zx}) \text{ and } \{\varepsilon\}^T = (\varepsilon_{xx}, \varepsilon_{yy}, \varepsilon_{zz}, 2\varepsilon_{xy}, 2\varepsilon_{yz}, 2\varepsilon_{zx})$
\State $Re-evaluate inner product in vector form: \sigma_{ij} \varepsilon_{ij} = \{\sigma\}^T \{\varepsilon\}$
\Return $\{\sigma\}^T \{\varepsilon\}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 1, p. 22; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, pp. 777–778_


## 4. Known Pitfalls

- **Repeated Indices Beyond Dyadic Pair Limits**: Writing expressions where an index appears three or more times in a single term (such as A_{ii} B_{ij} v_i). Einstein summation is strictly defined for indices appearing exactly twice per term; three or more identical indices create ambiguous summation operations. Mitigation: Rename dummy indices or use explicit summation signs. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Notation & Sec. 1, pp. xv, 8; Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Glossary, p. 778)_
- **Mismatched Free Indices in Tensor Equations**: Inconsistent free index placement across terms in an equation (e.g. A_{ij} = B_{ik} C_{kj} + v_i), which violates tensorial rank consistency. Every term in a valid tensor equation must have identical unsummed free indices. Mitigation: Verify that free indices match in name and position across all terms. _(Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Notation, p. xv; Bathe et al_1975_Finite element formulations for large deformation dynamic analysis.pdf, App. Nomenclature, p. 383)_

## References

- Bathe et al_1975_Finite element formulations for large deformation dynamic analysis.pdf
- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
