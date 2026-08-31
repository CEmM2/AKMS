---
id: solver-convergence-diagnostics
title: Iterative Solver Convergence Diagnostics
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- diagnostics
- convergence
- residual
- condition-number
- eigenvalue
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-cg-algorithm
  type: refines
  weight: 0.7
- to: solver-gmres-algorithm
  type: refines
  weight: 0.7
- to: solver-pcg-algorithm
  type: refines
  weight: 0.7
- to: solver-jfnk
  type: refines
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Iterative Solver Convergence Diagnostics

## Summary

Convergence diagnostics for iterative linear and nonlinear solvers evaluate numerical progress, residual reduction rates, and operator spectrums to ensure solution accuracy in computational mechanics. Key diagnostic metrics include relative residual norms, absolute residual norms, solution update step sizes, inexact Newton forcing conditions, and Lanczos eigenvalue estimates used for polynomial preconditioner scaling.

## 1. Core Concept

Iterative linear solvers (such as Conjugate Gradient, GMRES, and BiCGSTAB) and nonlinear solvers (such as Newton-Raphson, JFNK, and L-BFGS) rely on robust convergence diagnostics to determine when solution iterates x_k have reached required engineering tolerances. In linear solvers, convergence is monitored by tracking the unpreconditioned relative residual norm ||r_k||_2 / ||r_0||_2 or absolute residual norm ||r_k||_2 against prescribed thresholds (e.g., 10^-10). In non-convex physical problems such as phase-field fracture, tracking energy functional values or solution increments alone is insufficient: total potential energy often reaches a flat numerical plateau during rapid crack propagation while residual norms remain unacceptably large (>10^-6), requiring strict dual-field residual and increment criteria. In inexact Newton-Krylov methods, forcing parameters \eta_k control inner linear solver convergence to prevent oversolving far from the root. Furthermore, Lanczos iterations are executed during preconditioner setup to estimate maximum eigenspectrum bounds \lambda_max(M^-1 A), ensuring optimal spectral scaling for Chebyshev polynomial smoothers.

## 2. Mathematical Formulation

**relative-residual-norm-criterion**
$$
\frac{\|r_k\|_2}{\|r_0\|_2} \le \text{tol}_{\text{res}} \quad \text{or} \quad \|r_k\|_2 \le \text{tol}_{\text{abs}}
$$
_Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 5.1, p. 11; Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.1, p. 360_

**inexact-newton-forcing-condition**
$$
\|J(u_k) du_k + F(u_k)\|_2 \le \eta_k \|F(u_k)\|_2
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.3.2, p. 363_

**coupled-field-residual-and-increment-diagnostics**
$$
\frac{\|r_u^{(k)}\|_2}{\|r_u^{(0)}\|_2} \le \text{TOL}_{\text{Res}}, \quad \frac{\|\Delta u^{(k)}\|_2}{\|\Delta u^{(0)}\|_2} \le \text{TOL}_{\text{Inc}}
$$
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.2, p. 12; Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2.1, p. 8_

**lanczos-eigenvalue-estimator**
$$
\lambda_{\max}(M^{-1} A) \approx \max_i \lambda_i(T_m)
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section III.A, p. 3; Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, p. 10_

**Notation:**
r_k represents unpreconditioned linear residual vector; F(u_k) represents nonlinear residual vector; J(u_k) represents Jacobian operator matrix; du_k, \Delta u_k represent solution update vectors; \eta_k represents inexact Newton forcing term parameter; T_m represents tridiagonal Lanczos matrix; \lambda_max represents maximum eigenvalue estimate.


## 3. Algorithmic Implementation

**inexact-newton-krylov-stopping-monitor**
$$
\begin{algorithmic}
\State $\text{Evaluate outer nonlinear residual } F(u_k) \text{ and check relative stopping criterion } \|F(u_k)\|_2 / \|F(u_0)\|_2 < \text{tol}_{\text{res}}$
\State $\text{Set inner Krylov forcing parameter } \eta_k \in (0, 1) \text{ to prevent oversolving}$
\State $\text{Execute Krylov linear solver iterations until inner residual satisfies } \|J(u_k) du_k + F(u_k)\|_2 \le \eta_k \|F(u_k)\|_2$
\State $\text{Compute update step } du_k \text{ and check solution update norm } \|du_k\|_2 / \|u_k\|_2 < \text{tol}_{\text{update}}$
\State $u_{k+1} = u_k + s_k du_k$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.1, p. 360; Section 2.3.2, p. 364_

**lanczos-preconditioner-eigenspectrum-estimator**
$$
\begin{algorithmic}
\State $\text{Initialize normalized seed vector } v_1 \text{ with } \|v_1\|_2 = 1, \text{ set } v_0 = 0, \beta_0 = 0$
\For{$j = 1 \text{ to } m \quad \text{(typically } m = 10 \text{ iterations during setup)}$}
\State $w_j = M^{-1} A v_j \quad \text{(apply preconditioned operator on seed vector)}$
\State $\alpha_j = v_j^T w_j$
\State $w_j \leftarrow w_j - \alpha_j v_j - \beta_{j-1} v_{j-1}$
\State $\beta_j = \|w_j\|_2$
\State $v_{j+1} = w_j / \beta_j$
\EndFor
\State $\text{Form } m \times m \text{ tridiagonal matrix } T_m \text{ with diagonal } \alpha_j \text{ and subdiagonals } \beta_j$
\State $\text{Compute maximum eigenvalue } \lambda_{\max} = \max_i \lambda_i(T_m) \text{ to set Chebyshev polynomial bounds } [0.1 \lambda_{\max}, 1.1 \lambda_{\max}]$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section III.A, p. 3; Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, p. 10_


## 4. Known Pitfalls

- **premature-termination-on-energy-plateau**: In non-convex mechanical problems like phase-field brittle fracture, the total potential energy functional E(u, d) reaches a flat numerical plateau during rapid crack propagation while absolute residual norms ||r_u||_2 and ||r_d||_2 remain unacceptably large (>10^-6). Terminating iterations based on energy flattening or solution increments under-predicts crack growth; strict residual-based stopping criteria are mandatory. _(Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 4.1, pp. 13-14)_
- **oversolving-far-from-root-linearization**: Solving inner Krylov linear systems to an overly tight relative tolerance (\eta_k << 1) when the outer Newton iterate u_k is far from the true root wastes linear solver iterations on an inaccurate linearization. Adaptive forcing terms \eta_k balance inner and outer convergence. _(Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.3.2, p. 364)_
- **recursive-vs-true-residual-drift**: In short-recurrence Krylov solvers (such as DQGMRES, BiCGSTAB, or restarted GMRES), the residual vector updated recursively in finite-precision arithmetic diverges from the true residual b - A x_k. Periodically evaluating the explicit residual b - A x_k prevents false convergence reporting. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 6.11, p. 182; Section 7.4.2, p. 247)_

## References

- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
- Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf
- Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf
- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf
- IterMethBook_2ndEd.pdf.pdf
