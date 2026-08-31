---
id: precond-jacobi-block-jacobi
title: Jacobi & Block Jacobi Preconditioners
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- preconditioner
- jacobi
- block-jacobi
- GPU
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-pcg-algorithm
  type: feeds-into
  weight: 0.5
- to: solver-gmres-algorithm
  type: feeds-into
  weight: 0.5
- to: precond-amg-theory
  type: contradicts
  weight: 0.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Jacobi & Block Jacobi Preconditioners

## Summary

Jacobi and block Jacobi preconditioners accelerate Krylov subspace iterative solvers (such as PCG and GMRES) by extracting diagonal or block-diagonal submatrices from global finite element stiffness matrices. While point-Jacobi preconditioning scales diagonal entries with near-zero setup cost, block Jacobi preconditioning captures localized field connectivity within subdomain partitions via local incomplete Cholesky or LU factorizations. Both approaches offer fine-grained parallel concurrency, though point-Jacobi exhibits weak condition number reduction compared to multi-level algebraic multigrid solvers.

## 1. Core Concept

Preconditioning accelerates iterative linear solvers for discretized partial differential equations by transforming ill-conditioned coefficient matrices A into preconditioned systems M^-1 A with clustered eigenspectra. Point-Jacobi preconditioning sets M = diag(A), providing an embarrassingly parallel operator where inversion requires simply taking entrywise reciprocals M^-1_ii = 1 / A_ii with negligible setup time (~1% of total solution time). However, in elasticity and phase-field fracture mechanics, point-Jacobi provides weak condition number reduction, leading to high Conjugate Gradient (CG) iteration counts. Block Jacobi preconditioning improves robustness by partitioning domain degrees of freedom into local diagonal blocks M_i = A_i (corresponding to parallel process or mesh partitions). Each local block submatrix M_i is factorized independently using zero fill-in incomplete Cholesky IC(0) or incomplete LU ILU(0). By incorporating off-diagonal coupling within local subdomains, block Jacobi reflects the nonzero structure and physical field coupling of the global system, reducing CG iterations by 3-4x compared to scalar Jacobi while preserving high parallel efficiency across distributed-memory MPI processes.

## 2. Mathematical Formulation

**scalar-jacobi-preconditioning-operator**
$$
P_{\text{Jacobi}}^{-1} = \text{diag}(A)^{-1} = \text{diag}\left(\frac{1}{A_{11}}, \frac{1}{A_{22}}, \dots, \frac{1}{A_{nn}}\right)
$$
_Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, p. 9; IterMethBook_2ndEd.pdf.pdf, Section 4.1, p. 105_

**block-jacobi-preconditioning-operator**
$$
P_{\text{BJacobi}}^{-1} = \text{diag}(M_1^{-1}, M_2^{-1}, \dots, M_{s}^{-1})
$$
_Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, p. 9; IterMethBook_2ndEd.pdf.pdf, Section 4.2, p. 108_

**damped-jacobi-iteration**
$$
x^{(k+1)} = (1 - \omega) x^{(k)} + \omega D^{-1} (b - (A - D) x^{(k)})
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 4.1, p. 105; Section 13.4, p. 445_

**Notation:**
A represents global assembled stiffness matrix; D = diag(A) represents diagonal matrix; P_{\text{Jacobi}}^{-1} represents scalar Jacobi inverse preconditioner; P_{\text{BJacobi}}^{-1} represents block Jacobi inverse preconditioner operator; M_i represents local process diagonal block matrix; L_i represents lower triangular factor matrix from local IC(0); \omega represents damping weight parameter.


## 3. Algorithmic Implementation

**parallel-scalar-jacobi-apply**
$$
\begin{algorithmic}
\State $\text{Given linear system residual } r_k = b - A x_k$
\For{$i = 1 \text{ to } n \quad \text{(embarrassingly parallel loop)}$}
\State $z_i = \frac{r_{k,i}}{A_{ii}} \quad \text{(entrywise diagonal reciprocal multiplication)}$
\EndFor
\Return $z_k$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, p. 9; Shen et al. - 2024 - Preconditioned Nonlinear Conjugate Gradient Method for Real-time Interior-point Hyperelasticity.pdf, Section 4.2, p. 5_

**block-jacobi-ic-apply**
$$
\begin{algorithmic}
\State $\text{Extract local subdomain diagonal blocks } M_i = A_i \text{ for process } i = 1, \dots, s$
\State $\text{Factorize } M_i \approx \tilde{L}_i \tilde{L}_i^T \text{ using zero fill-in Incomplete Cholesky IC(0)}$
\For{$i = 1 \text{ to } s \quad \text{(concurrent MPI process loop)}$}
\State $z_{i,\text{local}} = (\tilde{L}_i \tilde{L}_i^T)^{-1} r_{i,\text{local}} \quad \text{(solve local block problem via forward/backward substitution)}$
\EndFor
\State $z_k = [z_{1,\text{local}}; z_{2,\text{local}}; \dots; z_{s,\text{local}}] \quad \text{(assemble global preconditioned vector)}$
\Return $z_k$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, p. 9; Section 5.3.1, p. 21_


## 4. Known Pitfalls

- **jacobi-weak-condition-number-reduction**: Point-Jacobi preconditioning (P = diag(A)^-1) requires minimal setup time (t_setup ~ 1%), but provides weak preconditioning power for ill-conditioned elasticity and phase-field fracture systems. In 2D phase-field fracture simulations, Jacobi-preconditioned CG required 593-920 iterations per time step compared to 152-202 for block Jacobi IC and 75-91 for AMG, resulting in significantly higher total solution times. _(Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 5.2.3, pp. 15-18)_
- **block-jacobi-subdomain-scaling-communication-tradeoff**: As the number of MPI processes scales to thousands, the subdomain block sizes m_i shrink, causing block Jacobi preconditioning to lose global coupling information and approach scalar Jacobi behavior. While block Jacobi exhibits high parallel efficiency (~87-97% on 1008 cores) due to localized block solves without interprocess overlap communication, iteration counts increase with fine mesh partitioning unless combined with coarse-grid corrections. _(Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 5.3.2, pp. 23-25; IterMethBook_2ndEd.pdf.pdf, Section 14.3, p. 488)_

## References

- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
- IterMethBook_2ndEd.pdf.pdf
- Shen et al. - 2024 - Preconditioned Nonlinear Conjugate Gradient Method for Real-time Interior-point Hyperelasticity.pdf
