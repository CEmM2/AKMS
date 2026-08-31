---
id: solver-matrix-free-operator
title: Matrix-Free Operator Evaluation (libCEED Pattern)
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- matrix-free
- libCEED
- sum-factorization
- high-order
- FE
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-matrix-free-gpu
  type: refines
  weight: 0.7
- to: solver-pcg-algorithm
  type: feeds-into
  weight: 0.5
- to: precond-geometric-mg
  type: feeds-into
  weight: 0.5
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Matrix-Free Operator Evaluation (libCEED Pattern)

## Summary

Matrix-free operator evaluation represents finite element linear operators through partial assembly, evaluating stiffness and residual actions on-the-fly without assembling or storing global sparse matrices. Following the libCEED decomposition A = \mathcal{P}^T \mathcal{E}^T B^T D \mathcal{E} \mathcal{P}, operator evaluations compose global restriction (\mathcal{P}), element restriction (\mathcal{E}), basis evaluation (B), and quadrature-point constitutive tensor transformations (D). By bypassing assembled CSR matrix storage, matrix-free methods drastically reduce memory bandwidth demands and enable high throughput on CPU and GPU architectures.

## 1. Core Concept

Traditional finite element solvers rely on assembled sparse matrices (e.g. CSR format). For high-order discretizations (Q_p elements with p >= 2), storing sparse tangent matrices requires streaming O(p^{2d}) nonzeros per row, causing memory bandwidth saturation at less than 2% of peak GPU floating-point capacity. Matrix-free operator evaluation avoids sparse matrix allocation by factoring operator application into modular tensor operations. In the libCEED abstraction, a global vector (T-vector) is mapped to sub-domain local representations (L-vectors) via scatter/gather restriction operator \mathcal{P}, localized into element representations (E-vectors) via element restriction \mathcal{E}, evaluated at quadrature points (Q-vectors) via basis transform B, transformed by material constitutive laws via D, and accumulated back via transpose operations. For Q2 hexahedral elements, matrix-free partial assembly streams ~140 B/DoF compared to ~750 B/DoF for assembled CSR matrices (with 63 nonzeros per row). Furthermore, matrix-free data structures provide up to 2x efficiency gains even for linear (Q1) elements.

## 2. Mathematical Formulation

**libceed-operator-decomposition**
$$
A = \mathcal{P}^T \mathcal{E}^T B^T D \mathcal{E} \mathcal{P}
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section II.C, p. 2, Fig. 1_

**libceed-jacobian-action**
$$
J du = \sum_e (\mathcal{E}^e)^T [B_I, B_\xi]^T W^e \Lambda \begin{bmatrix} \hat{f}_{0,0} & \hat{f}_{0,1} \\ \hat{f}_{1,0} & \hat{f}_{1,1} \end{bmatrix} \begin{bmatrix} B_I \\ B_\xi \end{bmatrix} \mathcal{E}^e du
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section II.B, p. 2, Eq. 11_

**matrix-free-memory-footprint-reduction**
$$
\text{Memory Footprint}_{\text{MF, } Q_2} \approx 140 \text{ B/DoF} \ll \text{Memory Footprint}_{\text{CSR, } Q_2} \approx 750 \text{ B/DoF}
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section V.B, p. 5_

**Notation:**
A represents global matrix-free operator; \mathcal{P} represents global scatter/gather restriction operator; \mathcal{E} represents element restriction operator; B represents basis evaluation matrix at quadrature points; D represents quadrature-point constitutive tensor matrix; J represents Jacobian operator; \hat{f}_{i,j} represent constitutive functional derivatives.


## 3. Algorithmic Implementation

**libceed-matrix-free-operator-apply**
$$
\begin{algorithmic}
\State $v_L = \mathcal{P} v_T \quad \text{(gather global T-vector DOFs to sub-domain local L-vector)}$
\State $v_E = \mathcal{E} v_L \quad \text{(extract element DOFs into E-vector)}$
\State $q = B v_E \quad \text{(evaluate fields and gradients at quadrature points Q-vector)}$
\State $q' = D q \quad \text{(apply material constitutive tangent transformation at quadrature points)}$
\State $w_E = B^T q' \quad \text{(apply transposed basis evaluation at quadrature points)}$
\State $w_L = \mathcal{E}^T w_E \quad \text{(assemble element contributions into local sub-domain vector)}$
\State $w_T = \mathcal{P}^T w_L \quad \text{(scatter/sum local updates into global T-vector)}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section II.C, p. 2, Fig. 1_


## 4. Known Pitfalls

- **assembled-matrix-storage-memory-bottleneck**: Assembling and storing sparse CSR matrices for high-order finite elements (Q_p for p >= 2) generates dense row connectivity (O(p^{2d}) nonzeros per row), leading to severe memory consumption and memory bandwidth bottlenecks that cap SpMV throughput at under 2% of peak GPU FLOPS. Matrix-free partial assembly bypasses global matrix storage. _(Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section I, p. 1; Section V.B, p. 5)_
- **misconception-linear-element-matrix-free-disadvantage**: It is a common misconception that matrix-free operator representations are only beneficial for high-order elements and incur overhead for low-order discretizations. In reality, matrix-free data structures offer up to 2x efficiency benefits even for linear (Q_1) elements compared to assembled CSR sparse matrices. _(Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Abstract, p. 1; Section V.B, p. 5)_

## References

- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf
- Trotter et al_2023_Targeting performance and user-friendliness.pdf
- Xue et al_2023_JAX-FEM.pdf
