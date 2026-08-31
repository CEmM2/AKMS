---
id: precond-amg-theory
title: 'Algebraic Multigrid (AMG): Theory & Setup'
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- AMG
- multigrid
- coarsening
- interpolation
- near-null-space
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-pcg-algorithm
  type: feeds-into
  weight: 0.5
- to: precond-amg-gpu
  type: refines
  weight: 0.7
- to: precond-geometric-mg
  type: refines
  weight: 0.7
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Algebraic Multigrid (AMG): Theory & Setup

## Summary

Algebraic Multigrid (AMG) is a multi-level preconditioning methodology for large, sparse, symmetric positive-definite linear systems arising from finite element discretizations in computational mechanics. Unlike geometric multigrid, AMG constructs coarse-grid hierarchies, restriction/prolongation operators, and coarse system operators purely algebraically from assembled coefficient matrices without requiring access to geometric grid structures or unstructured mesh sequences. By pairing parallel smoothers (such as Chebyshev polynomials or Richardson relaxation) for high-frequency error reduction with Galerkin coarse-grid corrections for low-frequency error elimination, AMG bounds condition number growth and achieves scalable convergence.

## 1. Core Concept

Multigrid methods accelerate Krylov subspace iterative solvers (such as Preconditioned Conjugate Gradient) by eliminating algebraic error across a hierarchy of spatial discretization scales. High-frequency error components are rapidly damped on fine grids using local smoothing iterations (such as Jacobi, Gauss-Seidel, or 2nd-order Chebyshev polynomial smoothers), whereas low-frequency error components are restricted to coarser representations where they appear high-frequency and can be eliminated inexpensively. While geometric multigrid requires generating nested unstructured mesh hierarchies—a complex task for arbitrary 3D domains—AMG constructs coarse levels algebraically using matrix entry connectivity. Main AMG paradigms include classical AMG (Ruge and Stüben), agglomeration AMG, and smoothed aggregation AMG (Vaněk et al.). In smoothed aggregation AMG, aggregate nodal blocks are formed, and prolongation operators P are damped via local matrix smoothing to eliminate errors corresponding to small eigenvalues. The coarse operator is formed via Galerkin projection A_c = P^T A_f P. The hierarchy terminates at a coarsest level small enough to be solved directly via exact LU factorization or block Jacobi with incomplete Cholesky (IC) decomposition.

## 2. Mathematical Formulation

**galerkin-coarse-grid-operator**
$$
A_c = P^T A_f P
$$
_Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, p. 9; Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section III.A, p. 3; IterMethBook_2ndEd.pdf.pdf, Section 13.4, p. 440_

**smoothed-aggregation-prolongation**
$$
P = (I - \omega D^{-1} A_{\text{filtered}}) \tilde{P}
$$
_Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, p. 10_

**chebyshev-jacobi-smoother**
$$
u^{(l+1)} = u^{(l)} + \hat{M}^{-1} (b - A_f u^{(l)})
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section III.A, p. 3; Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, p. 10_

**amg-condition-number-reduction**
$$
\text{cond}_2(M_{\text{AMG}}^{-1} A) \approx \frac{\max |\lambda_i(M_{\text{AMG}}^{-1} A)|}{\min |\lambda_i(M_{\text{AMG}}^{-1} A)|} \ll \text{cond}_2(M_{\text{Jacobi}}^{-1} A)
$$
_Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 5.2.3, pp. 16-18_

**Notation:**
A_f, A_c represent fine and coarse level stiffness matrices; P represents prolongation operator matrix; R = P^T represents restriction operator matrix; \tilde{P} represents tentative un-smoothed aggregation matrix; \hat{M}^{-1} represents smoothing preconditioning operator; \lambda_i represents eigenspectrum computed via Lanczos iterations; cond_2 represents spectral condition number.


## 3. Algorithmic Implementation

**amg-setup-and-hierarchy-construction**
$$
\begin{algorithmic}
\State $\text{Given fine-grid assembled matrix } A_0 = A_f \text{ and level } l = 0$
\While{$\text{dim}(A_l) > n_{\text{coarsest}}$}
\State $\text{Construct un-smoothed aggregation blocks or C/F node partitioning from adjacency graph of } A_l$
\State $\text{Form prolongation matrix } P_{l+1 \to l} \text{ via smoothed aggregation } P = (I - \omega D^{-1} A_{\text{filt}}) \tilde{P}$
\State $\text{Build Galerkin coarse operator } A_{l+1} = P_{l+1 \to l}^T A_l P_{l+1 \to l}$
\State $l \leftarrow l + 1$
\EndWhile
\State $\text{Factorize coarsest matrix } A_l \text{ using exact LU factorization or block Jacobi IC}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, pp. 9-10; IterMethBook_2ndEd.pdf.pdf, Section 13.6, pp. 455-463_

**amg-v-cycle-preconditioner-application**
$$
\begin{algorithmic}
\State $u_l \leftarrow 0, \text{ given residual } r_l \text{ at level } l$
\State $u_l \leftarrow u_l + \text{Smooth}_{\nu_1}(A_l, r_l) \quad \text{(Pre-smoothing via Chebyshev or Richardson iteration)}$
\State $r_{l+1} = P_{l+1 \to l}^T (r_l - A_l u_l) \quad \text{(Restrict residual to coarse level)}$
\If{$l+1 == l_{\text{coarsest}}$}
\State $e_{l+1} = A_{l_{\text{coarsest}}}^{-1} r_{l+1} \quad \text{(Direct solve via exact LU or 2 Krylov iterations of block Jacobi IC)}$
\Else
\EndIf
\State $u_l \leftarrow u_l + P_{l+1 \to l} e_{l+1} \quad \text{(Prolong error correction to fine level)}$
\State $u_l \leftarrow u_l + \text{Smooth}_{\nu_2}(A_l, r_l - A_l u_l) \quad \text{(Post-smoothing via Chebyshev or Richardson iteration)}$
\Return $u_l$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, p. 10; Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section III.A, p. 3, Fig. 2; IterMethBook_2ndEd.pdf.pdf, Section 13.4, p. 444_


## 4. Known Pitfalls

- **amg-setup-cost-overhead**: Preconditioner setup time (t_setup), which includes coarsening graph analysis, prolongation matrix construction, Galerkin products A_c = P^T A_f P, and Lanczos eigenvalue estimation, represents a substantial fraction (~50%) of total solution time. Re-building AMG hierarchies at every iteration without reusing setup across transient or quasi-Newton steps severely impairs computational efficiency. _(Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 5.3, p. 22; Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section V.C, p. 8)_
- **coarse-level-stiffness-degradation-in-cracking**: In phase-field brittle fracture and non-linear damage continuum mechanics, local material degradation causes stiffness entries to scale as (1 - d)^2 E. As damage d approaches 1, the condition number cond_2(M^-1 A) increases exponentially, degrading one-level preconditioner performance and increasing AMG iteration counts unless smoothed aggregation coarse-grid corrections prevent ill-conditioning. _(Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 5.2.3, pp. 16-18)_
- **element-stretching-convergence-degradation**: High aspect-ratio element stretching in anisotropic mesh discretizations degrades AMG coarse-grid convergence and increases condition numbers. Tuning coarsening thresholds and smoothing parameters for stretched element regions is required to preserve convergence robustness. _(Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section V.D, p. 10)_

## References

- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf
- IterMethBook_2ndEd.pdf.pdf
- Trotter et al_2023_Targeting performance and user-friendliness.pdf
