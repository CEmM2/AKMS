---
id: optim-lbfgs
title: 'L-BFGS Algorithm: Two-Loop Recursion'
domain: computational-mechanics
subdomain: optimization
tags:
- optimization
- lbfgs
- quasi-newton
- two-loop
- liu-nocedal
status: established
confidence: 0.9
source: hybrid
edges:
- to: optim-unconstrained-basics
  type: refines
  weight: 0.7
- to: optim-line-search
  type: requires
  weight: 1.0
- to: optim-lbfgs-fem
  type: feeds-into
  weight: 0.5
- to: pf-monolithic-bfgs
  type: refines
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# L-BFGS Algorithm: Two-Loop Recursion

## Summary

The limited-memory Broyden-Fletcher-Goldfarb-Shanno (L-BFGS) algorithm is a quasi-Newton optimization method designed for large-scale non-convex systems. By replacing full dense inverse Hessian storage with a two-loop recursion operating on a sliding window of m recent displacement and residual vector pairs, L-BFGS computes effective search directions in O(m n) time and memory per iteration while maintaining superlinear convergence.

## 1. Core Concept

Quasi-Newton methods approximate second-order curvature without evaluating or factorizing full Hessian matrices. In classical BFGS, rank-two updates accumulate curvature information from differences between consecutive iterates s_k = x_{k+1} - x_k and residual gradients y_k = r_{k+1} - r_k. However, classical BFGS generates dense n x n matrices, rendering it intractable for large finite element or continuum mechanics problems. The L-BFGS algorithm circumvents dense matrix storage by representing the inverse Hessian implicitly through a two-loop recursion that applies m vector pairs {s_i, y_i}. Coupled with initial inverse Hessian scaling H_0^k and line search strategies (such as strong Wolfe conditions), L-BFGS enforces the curvature condition s_k^T y_k > 0 to maintain positive definiteness and guaranteed descent directions across non-convex mechanical energy landscapes.

## 2. Mathematical Formulation

**lbfgs-search-direction**
$$
p_k = -H_k r_k
$$
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.2, p. 11_

**bfgs-inverse-hessian-update**
$$
H_{k+1} = (I - \rho_k s_k y_k^T) H_k (I - \rho_k y_k s_k^T) + \rho_k s_k s_k^T
$$
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.1, p. 10; Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, p. 5_

**curvature-condition**
$$
s_k^T y_k > 0
$$
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.1, p. 10; Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, p. 6_

**initial-hessian-scaling**
$$
H_0^k = \frac{s_{k-1}^T y_{k-1}}{y_{k-1}^T y_{k-1}} I
$$
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.2, p. 11_

**modified-nonconvex-lbfgs-update**
$$
H_{k+1} = \begin{cases} (I - \rho_k s_k y_k^T) H_k (I - \rho_k y_k s_k^T) + \rho_k s_k s_k^T, & \text{if } s_k^T y_k > 0 \\ H_k, & \text{otherwise} \end{cases}
$$
_Source: Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, p. 6_

**Notation:**
x represents the optimization solution vector; r represents the gradient/residual vector; p represents the search direction vector; s_k represents the solution step vector x_{k+1} - x_k; y_k represents the residual vector increment r_{k+1} - r_k; H_k represents the inverse Hessian operator; \rho_k represents the curvature weighting parameter 1 / (y_k^T s_k); m represents the memory buffer depth; \hat{m} represents min(m, k).


## 3. Algorithmic Implementation

**lbfgs-two-loop-recursion**
$$
\begin{algorithmic}
\State $q \leftarrow r_k, \quad \hat{m} \leftarrow \min(m, k)$
\For{$i = k - 1 \text{ down to } k - \hat{m}$}
\State $\rho_i \leftarrow \frac{1}{y_i^T s_i}$
\State $\alpha_i \leftarrow \rho_i s_i^T q$
\State $q \leftarrow q - \alpha_i y_i$
\EndFor
\State $p_k \leftarrow H_0^k q$
\For{$i = k - \hat{m} \text{ to } k - 1$}
\State $\beta \leftarrow \rho_i y_i^T p_k$
\State $p_k \leftarrow p_k + s_i (\alpha_i - \beta)$
\EndFor
\State $p_k \leftarrow -p_k$
\Return $p_k$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.2, p. 11, Algorithm 1; Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, p. 7, Algorithm 2_

**lbfgs-outer-iteration-driver**
$$
\begin{algorithmic}
\State $\text{Initialize } x_0, \text{ memory horizon } m, \text{ and buffer } \mathcal{S} = \emptyset$
\For{$k = 0, 1, 2, \dots \text{ until } \|r_k\|_2 < \text{tol}$}
\State $\text{Evaluate residual } r_k = \nabla f(x_k)$
\State $\text{Compute search direction } p_k \text{ via L-BFGS two-loop recursion}$
\State $\text{Find step length } \alpha_k > 0 \text{ satisfying strong Wolfe conditions}$
\State $x_{k+1} = x_k + \alpha_k p_k$
\State $s_k = x_{k+1} - x_k, \quad y_k = r_{k+1} - r_k$
\If{$s_k^T y_k > 0$}
\State $\text{Store pair } \{s_k, y_k\} \text{ in } \mathcal{S} \text{ (evicting oldest if } |\mathcal{S}| > m\text{)}$
\EndIf
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.2, p. 12, Algorithm 2; Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, p. 7, Algorithm 2_


## 4. Known Pitfalls

- **dense-hessian-memory-explosion**: Storing explicit BFGS inverse Hessian updates in large-scale discretizations requires dense n x n matrices, leading to quadratic O(n^2) memory complexity that quickly exhausts available RAM. L-BFGS avoids explicit matrix storage by maintaining only m vector pairs {s_i, y_i}, reducing memory complexity to O(mn). _(Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.1, pp. 10-11; Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, p. 6)_
- **loss-of-positive-definiteness-nonconvex**: In non-convex optimization, step updates can yield negative curvature s_k^T y_k <= 0. Updating the quasi-Newton inverse Hessian under negative curvature destroys positive definiteness and produces non-descent search directions. Skipping the update when s_k^T y_k <= 0 or enforcing strong Wolfe line search conditions guarantees s_k^T y_k > 0. _(Source: Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, pp. 5-6; Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.1, p. 10)_
- **insufficient-memory-horizon-sluggish-convergence**: Setting the memory buffer depth m too small (e.g., m = 0) discards crucial curvature history, causing L-BFGS to degrade toward unconditioned steepest descent with extremely high iteration counts. Selecting m between 5 and 10 restores quasi-Newton superlinear convergence without incurring high memory overhead. _(Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 4.2, p. 18; Wu et al. - 2020 - On the BFGS monolithic algorithm for the unified phase field damage theory.pdf, Section 3.3, p. 10)_

## References

- Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf
- Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf
- Wu et al. - 2020 - On the BFGS monolithic algorithm for the unified phase field damage theory.pdf
- Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf
- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
