---
id: fem-assembly-algorithm
title: Global Assembly & Sparse Storage
domain: computational-mechanics
subdomain: finite-elements
tags:
- fem
- sparse
- assembly
- linear-algebra
- boundary-conditions
status: established
confidence: 0.9
source: hybrid
edges:
- to: fem-weak-form-derivation
  type: requires
  weight: 1.0
- to: fem-isoparametric-mapping
  type: requires
  weight: 0.8
- to: fem-tl-matrix-free-action
  type: contradicts
  weight: 0.6
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Global Assembly & Sparse Storage

## Summary

Global finite element assembly synthesizes element-level stiffness matrices and force vectors into global discrete linear or non-linear algebraic systems using element connectivity mapping arrays. The assembled global stiffness matrix is stored in sparse compressed formats or preallocated coordinate arrays, and essential boundary conditions are enforced either through symmetric submatrix partitioning or element-level elimination.

## 1. Core Concept

In finite element analysis, continuous weak forms are evaluated as sums of local integrals over individual element domains. Global assembly accumulates local element stiffness matrices and nodal force vectors into the global algebraic system using a local-to-global degree-of-freedom mapping. Because basis functions have local compact support, global stiffness matrices are highly sparse and banded. In multi-threaded parallel assembly, data race conditions are avoided by cell coloring or preallocated coordinate assembly. Essential Dirichlet boundary conditions are applied via submatrix partitioning or symmetric partial Gaussian elimination to preserve matrix properties for linear solvers.

## 2. Mathematical Formulation

**Global Stiffness Matrix Assembly**
$$
K = \sum_{e=1}^{n_e} (L^e)^T K_e L^e = \sum_{e=1}^{n_e} Z_e^T \left( \int_{V_e} B^T D B \, \mathrm{d}V \right) Z_e
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 2.5, Eq. 2.5.9, p. 42; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.2, Eq. 2.43, p. 44_

**Global Nodal Internal Force Vector Assembly**
$$
f^{\mathrm{int}} = \sum_{e=1}^{n_e} (L^e)^T f_e^{\mathrm{int}} = \sum_{e=1}^{n_e} Z_e^T \int_{V_e} B^T \sigma \, \mathrm{d}V
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Sec. 2.5, Eq. 2.5.5, p. 41; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.2, Eq. 2.18, p. 35_

**Local-to-Global Multi-Index Tensor Assembly**
$$
A_I = \sum_{T \in \mathcal{T}_I} A_{T, \iota_T^{-1}(I)}
$$
_Source: FE_Assembly.pdf, Sec. 6.1, Eq. 6.5, p. 142_

**Essential Boundary Condition Partitioning**
$$
K_{ff} a_f = f^{\mathrm{ext},f} - K_{fp} a_p
$$
_Source: Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.3, Eq. 2.60, p. 59; ME280A.pdf, Sec. 6.2, Eq. 6.27, p. 146_

**Notation:**
{'K': 'Assembled global stiffness matrix.', 'K_e': 'Local element stiffness matrix.', 'f^{\\mathrm{int}}': 'Assembled global internal nodal force vector.', 'f_e^{\\mathrm{int}}': 'Local element internal nodal force vector.', 'L^e, Z_e': 'Boolean element connectivity matrix (gather/scatter operator).', '\\iota_T': 'Local-to-global degree-of-freedom mapping function.', 'a_f': 'Vector of unknown displacements at unconstrained (free) degrees of freedom.', 'a_p': 'Vector of prescribed displacements at constrained degrees of freedom.'}


## 3. Algorithmic Implementation

**Standard Finite Element Scatter Assembly Algorithm**
$$
\begin{algorithmic}
\State $Initialize global stiffness matrix K \gets 0 and global force vector f^{\mathrm{int}} \gets 0$
\For{$e \gets 1 \text{ to } n_e$}
\State $Extract element degree-of-freedom map d_e \gets \mathrm{dofmap}(e)$
\State $Compute element stiffness matrix K_e = \int_{V_e} B^T D B \, \mathrm{d}V \text{ and force } f_e^{\mathrm{int}} = \int_{V_e} B^T \sigma \, \mathrm{d}V$
\For{$i \gets 1 \text{ to } n_{\mathrm{dof},e}$}
\State $I \gets d_e[i]$
\State $f^{\mathrm{int}}[I] \gets f^{\mathrm{int}}[I] + f_e^{\mathrm{int}}[i]$
\For{$j \gets 1 \text{ to } n_{\mathrm{dof},e}$}
\State $J \gets d_e[j]$
\State $K[I, J] \gets K[I, J] + K_e[i, j]$
\EndFor
\EndFor
\EndFor
\Return $K, f^{\mathrm{int}}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: FE_Assembly.pdf, Sec. 6.1, Alg. 2, p. 142; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.3, p. 58_


## 4. Known Pitfalls

- **Uninitialized Sparse Matrix Sparsity Pattern**: Inserting element matrix entries into an uninitialized compressed sparse row (CRS/CSR) matrix data structure without precalculating the non-zero sparsity pattern incurs severe memory reallocation and search overhead. Mitigation: Compute and preallocate the global sparsity pattern from element connectivity maps before assembly. _(Source: FE_Assembly.pdf, Sec. 6.2, p. 143; Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \(p\)-Multigrid.pdf, Sec. III-D, p. 7)_
- **Shared-Memory Race Conditions in Parallel Assembly**: In multi-threaded parallel assembly, multiple threads attempting to write local element contributions simultaneously into shared global matrix entries for boundary or shared nodes cause data race corruption. Mitigation: Apply mesh/cell coloring algorithms so that no two elements assembled concurrently share common global nodes, or use race-free preallocated coordinate assembly. _(Source: FE_Assembly.pdf, Sec. 6.4, p. 145; Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \(p\)-Multigrid.pdf, Sec. III-D, pp. 6–7)_
- **Loss of Matrix Symmetry Under Naive Boundary Condition Imposition**: Directly overwriting rows and columns of prescribed degrees of freedom in assembled global stiffness matrices without symmetric row-column reduction or element-level elimination destroys matrix symmetry, preventing the use of symmetric iterative solvers like Conjugate Gradient. Mitigation: Apply symmetric partial Gaussian elimination at the element level prior to assembly, or perform explicit submatrix partitioning K_{ff} a_f = f_f - K_{fp} a_p. _(Source: FE_Assembly.pdf, Sec. 6.3, pp. 144–145; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 2.3, p. 59)_

## References

- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \(p\)-Multigrid.pdf
- FE_Assembly.pdf
- ME280A.pdf
