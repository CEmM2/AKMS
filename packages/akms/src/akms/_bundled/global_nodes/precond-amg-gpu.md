---
id: precond-amg-gpu
title: 'AMG on GPU: Setup, Smoothers, & Coarse-Solve'
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- AMG
- GPU
- AmgX
- hypre
- parallel-smoother
status: established
confidence: 0.9
source: hybrid
edges:
- to: precond-amg-theory
  type: refines
  weight: 0.7
- to: precond-gpu-alternatives
  type: requires
  weight: 1.0
- to: solver-pcg-algorithm
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# AMG on GPU: Setup, Smoothers, & Coarse-Solve

## Summary

Algebraic Multigrid (AMG) on Graphics Processing Units (GPUs) accelerates iterative linear solvers for large-scale finite element discretizations by executing multi-level V-cycles entirely within GPU device memory. To maximize throughput on heterogeneous GPU architectures, standard sequential Jacobi or Gauss-Seidel relaxations are replaced by fine-grained parallel polynomial (e.g., 2nd-order Chebyshev with Jacobi scaling) or block-diagonal smoothers. By combining matrix-free p-multigrid discretizations at high polynomial orders with GPU-accelerated sparse AMG coarse solvers (such as hypre BoomerAMG or AmgX) and eliminating host-device memory transfers via direct array pointers, GPU AMG achieves high parallel efficiency across millions to billions of degrees of freedom.

## 1. Core Concept

Algebraic Multigrid on GPUs solves large, sparse, symmetric positive-definite linear systems Ax = b arising from finite element discretizations without requiring explicit geometric grid hierarchies. On parallel GPU hardware, the AMG V-cycle performs hierarchical error elimination: high-frequency error components are damped on fine grids using parallel-friendly smoothers (such as Chebyshev-polynomial Jacobi iterations), while low-frequency error components are restricted to coarser levels using Galerkin projections A_c = P^T A_f P. In high-order finite element frameworks, AMG serves as the coarse-level solver for matrix-free p-multigrid (p-MG) hierarchies, where linear Q1 elements are assembled into CSR sparse matrices on the GPU using split-phase COO interfaces. Eliminating CPU-GPU data transfers by maintaining sparse operators, vectors, and preconditioner structures in device memory is critical, as host-device memory transfer latency can destroy GPU speedup. Furthermore, in non-linear or transient simulations, AMG setup costs (coarsening analysis and Galerkin operator construction) are amortized across multiple time steps or quasi-Newton iterations.

## 2. Mathematical Formulation

**galerkin-coarse-operator**
$$
A_c = P_{c \to f}^T A_f P_{c \to f}
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Section III.A, p. 3_

**chebyshev-jacobi-smoother-update**
$$
u^{(l+1)} = u^{(l)} + \hat{M}^{-1} (b - A_f u^{(l)})
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Section III.A, p. 3_

**gpu-device-matrix-pointer-access**
$$
A_{\text{device}} = \text{MatSeqAIJCUSPARSEGetArray}(A)
$$
_Source: Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 3.5, p. 5_

**Notation:**
A_f, A_c represent fine and coarse linear system stiffness matrices; P_{c \to f} represents prolongation operator from coarse to fine level; r_f represents residual vector; u_f represents primal displacement solution vector; \hat{M}^{-1} represents Chebyshev/Jacobi smoother operator; \lambda_{\max} represents maximum eigenvalue estimate of preconditioned operator.


## 3. Algorithmic Implementation

**gpu-amg-v-cycle-step**
$$
\begin{algorithmic}
\State $\text{Initialize fine solution } u_f \text{ and residual } r_f = b - A_f u_f \text{ on GPU device}$
\State $u_f \leftarrow u_f + \hat{M}^{-1} r_f \quad \text{(Pre-smoothing via Chebyshev/Jacobi iteration on GPU)}$
\State $r_c = P_{c \to f}^T (b - A_f u_f) \quad \text{(Restrict residual to coarse grid via GPU SpMV)}$
\If{$\text{Level } c \text{ is coarsest grid}$}
\State $e_c = A_c^{-1} r_c \quad \text{(Solve coarse system via GPU BoomerAMG or sparse factorization)}$
\Else
\EndIf
\State $u_f \leftarrow u_f + P_{c \to f} e_c \quad \text{(Prolong error correction to fine grid on GPU)}$
\State $u_f \leftarrow u_f + \hat{M}^{-1} (b - A_f u_f) \quad \text{(Post-smoothing via Chebyshev/Jacobi iteration on GPU)}$
\Return $u_f$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Section III.A, p. 3, Fig. 2; Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 4.5, pp. 10-12_

**matrix-free-pmg-amg-coarse-solve**
$$
\begin{algorithmic}
\State $\text{Execute high-order } Q_p \text{ matrix-free smoothing loops on GPU via fused quadrature kernels}$
\State $\text{Restrict residual down to linear } Q_1 \text{ coarse element level } r_1 = P_{1 \to p}^T r_p$
\State $\text{Assemble } Q_1 \text{ CSR matrix } A_1 \text{ on GPU using split-phase COO } \text{MatSetValuesCOO}$
\State $\text{Solve } A_1 e_1 = r_1 \text{ using GPU BoomerAMG (hypre) or GAMG preconditioner}$
\State $\text{Prolong error correction } e_p = P_{1 \to p} e_1 \text{ to high-order } Q_p \text{ space}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Section II.C-III.A, pp. 2-4_


## 4. Known Pitfalls

- **cpu-gpu-data-transfer-latency-penalty**: Assembling linear systems on the host CPU and copying matrices or vectors to the GPU prior to AMG preconditioning introduces massive PCI-e communication latency. Unnecessary CPU-GPU data transfers eliminate all computational performance gains of GPU acceleration. Assembly and linear solves must reside entirely in GPU device memory using direct device array pointers (e.g., MatSeqAIJCUSPARSEGetArray). _(Source: Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 3.5, p. 5; Section 4.5, p. 10)_
- **amg-setup-overhead-unamortized**: Constructing algebraic multigrid hierarchies (coarsening graphs, Galerkin matrix-matrix products A_c = P^T A_f P, and eigenvalue estimation) carries high computational overhead on GPUs (often accounting for ~50% or more of total solution time per step). Re-building AMG preconditioners at every step without reusing setup across multiple quasi-Newton or transient time increments degrades overall solver efficiency. _(Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Section V.C, pp. 8-10; Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 5.3.1, p. 22)_
- **gpu-memory-capacity-exhaustion-coarse-level**: High-order finite element discretizations generate dense connectivity graphs when coarsened via CSR sparse matrix assembly. For models exceeding tens of millions of degrees of freedom, allocating assembled coarse-grid CSR sparse matrices and AMG multi-level hierarchy buffers on a single GPU can exhaust GPU VRAM capacity, causing out-of-memory solver failure unless managed via matrix-free p-multigrid or multi-GPU distribution. _(Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Section V.B, p. 6; Trotter et al_2023_Targeting performance and user-friendliness.pdf, Section 4.5, p. 12)_

## References

- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf
- Trotter et al_2023_Targeting performance and user-friendliness.pdf
- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
- IterMethBook_2ndEd.pdf.pdf
