---
id: precond-domain-decomp
title: Domain Decomposition Preconditioners
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- preconditioner
- domain-decomposition
- schwarz
- BDDC
- FETI-DP
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-pcg-algorithm
  type: feeds-into
  weight: 0.5
- to: precond-amg-theory
  type: refines
  weight: 0.7
- to: precond-field-split-block
  type: refines
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Domain Decomposition Preconditioners

## Summary

Domain decomposition preconditioners divide large-scale computational domains into smaller, manageable subdomains to accelerate Krylov subspace iterative linear solvers (such as PCG or GMRES) on parallel distributed-memory architectures. Key paradigms include non-overlapping domain decomposition (such as Schur complement reduction and Balancing Domain Decomposition by Constraints [BDDC]) and overlapping Schwarz methods (such as Additive Schwarz [ASM] and Restricted Additive Schwarz [RASM]).

## 1. Core Concept

Domain decomposition preconditioners accelerate parallel iterative linear solvers for discretized boundary value problems by decomposing global domain mesh graphs into s subdomains. In overlapping Additive Schwarz Methods (ASM), local subproblems are solved on overlapping regions using restriction operators R_i and local sub-Jacobians J_i. Global updates are formed by prolonging and summing local solutions. To reduce parallel communication latency in high-performance computing, Restricted Additive Schwarz (RASM) applies non-overlapping prolongation operators \tilde{R}_i^T, eliminating interprocess message passing during interpolation. In non-overlapping domain decomposition, global systems are partitioned into subdomain interiors and shared interfaces, reducing equations to Schur complement interface systems S = A_{II} - A_{IE} A_{EE}^{-1} A_{EI}. Dual-primal and constraint-balancing methods (such as PCBDDC) enforce continuity across subdomain corners and edges, providing robust concurrency and algorithmic scalability across thousands of MPI processes.

## 2. Mathematical Formulation

**additive-schwarz-preconditioner**
$$
P_{\text{1ASM}}^{-1} = \sum_{i=1}^s R_i^T J_i^{-1} R_i
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 3.2, p. 367; IterMethBook_2ndEd.pdf.pdf, Section 14.3, p. 488_

**restricted-additive-schwarz-rasm**
$$
P_{\text{1RASM}}^{-1} = \sum_{i=1}^s \tilde{R}_i^T J_i^{-1} R_i
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 3.2, p. 367_

**additive-schwarz-iteration-update**
$$
x^{(k+1)} = x^{(k)} + \sum_{i=1}^s R_i^T A_i^{-1} R_i (b - A x^{(k)})
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 14.3, p. 488_

**domain-decomposition-schur-complement**
$$
S = A_{II} - A_{IE} A_{EE}^{-1} A_{EI}
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 14.2, p. 477_

**Notation:**
x represents global solution vector; b represents global right-hand side vector; r represents global residual vector; R_i represents restriction operator for subdomain i; \tilde{R}_i^T represents restricted prolongation operator; J_i, A_i represent local subdomain matrices; s represents number of subdomains; S represents Schur complement matrix.


## 3. Algorithmic Implementation

**additive-schwarz-preconditioned-krylov-step**
$$
\begin{algorithmic}
\State $\text{Given global residual } r_k = b - A x_k \text{ at Krylov iteration } k$
\For{$i = 1 \text{ to } s \quad \text{(parallel loop over subdomains } P_i\text{)}$}
\State $r_{i,\text{local}} = R_i r_k \quad \text{(restrict global residual to subdomain } \Omega_i\text{)}$
\State $z_{i,\text{local}} = A_i^{-1} r_{i,\text{local}} \quad \text{(solve local subdomain problem via exact or ILU factorization)}$
\State $z_{i,\text{global}} = R_i^T z_{i,\text{local}} \quad \text{(prolong local update to global space)}$
\EndFor
\State $z_k = \sum_{i=1}^s z_{i,\text{global}} \quad \text{(accumulate preconditioned update vector)}$
\Return $z_k$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 3.2, p. 367; IterMethBook_2ndEd.pdf.pdf, Section 14.3, p. 488_

**restricted-additive-schwarz-preconditioner-step**
$$
\begin{algorithmic}
\State $\text{Given global residual } r_k = b - A x_k$
\For{$i = 1 \text{ to } s \quad \text{(concurrent MPI processes)}$}
\State $r_{i,\text{local}} = R_i r_k \quad \text{(gather residual with overlap data from neighbors)}$
\State $z_{i,\text{local}} = J_i^{-1} r_{i,\text{local}} \quad \text{(local subdomain linear solve)}$
\State $z_{i,\text{global}} = \tilde{R}_i^T z_{i,\text{local}} \quad \text{(non-overlapping prolongation without communication)}$
\EndFor
\State $z_k = \sum_{i=1}^s z_{i,\text{global}} \quad \text{(sum local updates)}$
\Return $z_k$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 3.2, p. 367_


## 4. Known Pitfalls

- **rasm-communication-overhead-reduction**: Standard Additive Schwarz (ASM) requires interprocess MPI communication during both restriction (R_i) and prolongation (R_i^T) phases. Restricted Additive Schwarz (RASM) replaces R_i^T with non-overlapping operator \tilde{R}_i^T, eliminating interpolation communication overhead while improving Krylov convergence rates. _(Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 3.2, p. 367)_
- **block-jacobi-communication-efficiency-tradeoff**: Block Jacobi preconditioning solves subproblems on localized domain partitions without subdomain overlap. While Block Jacobi minimizes communication overhead compared to overlapping Schwarz methods, it requires more Krylov iterations to converge as problem sizes scale, resulting in higher total execution times on moderate core counts. _(Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 5.3.1, p. 21; Section 5.3.2, p. 23)_
- **subdomain-solver-ill-conditioning-in-damage**: In non-linear fracture mechanics, localized stiffness loss causes local subdomain matrices A_i to become severely ill-conditioned or singular as damage d approaches 1. Solving local subdomain systems via incomplete factorizations (e.g. ILU or IC) without regularization or pivoting leads to local solver breakdown. _(Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 5.2.3, p. 16; Section 5.3, p. 21)_

## References

- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
- IterMethBook_2ndEd.pdf.pdf
- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf
