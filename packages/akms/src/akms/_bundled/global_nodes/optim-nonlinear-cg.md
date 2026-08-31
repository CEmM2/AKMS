---
id: optim-nonlinear-cg
title: Nonlinear Conjugate Gradient
domain: computational-mechanics
subdomain: optimization
tags:
- optimization
- nonlinear-CG
- fletcher-reeves
- polak-ribiere
- hestenes-stiefel
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-cg-algorithm
  type: refines
  weight: 0.7
- to: optim-unconstrained-basics
  type: refines
  weight: 0.7
- to: optim-line-search
  type: requires
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Nonlinear Conjugate Gradient

## Summary

The nonlinear conjugate gradient (NCG) method generalizes the linear conjugate gradient algorithm to unconstrained nonlinear optimization problems in computational mechanics. By generating search directions using gradient vectors and momentum weighting parameters (such as Fletcher-Reeves, Polak-Ribière, or Dai-Kou), NCG operates with a minimal memory footprint (requiring storage of only 2 to 3 vector fields) and avoids forming or factorizing dense global Hessian matrices.

## 1. Core Concept

Nonlinear conjugate gradient methods solve large-scale non-convex optimization problems arising in continuum mechanics, FFT-based micromechanics, and interior-point real-time hyperelasticity. Unlike linear CG where conjugate directions are orthogonalized with respect to a constant symmetric positive-definite matrix A, NCG computes search directions d_k = -g_k + \beta_{k-1} d_{k-1} using nonlinearly updated scalar momentum parameters \beta_k. Popular \beta_k formulations include Fletcher-Reeves (FR), Polak-Ribière-Polyak (PRP), Hestenes-Stiefel (HS), Dai-Yuan (DY), and Dai-Kou (DK). Continuous dynamic analysis reveals that Fletcher-Reeves NCG corresponds to a second-order Newtonian dynamical system with state-dependent nonlinear damping determined by residual gradient reduction rates. Combined with Jacobi preconditioning and one-pass step size selection, NCG provides a memory-efficient, parameter-choice-free alternative to quasi-Newton and Newton-Raphson solvers for high-dimensional discretizations.

## 2. Mathematical Formulation

**fletcher-reeves-beta**
$$
\beta_k^{\text{FR}} = \frac{\|g_{k+1}\|_2^2}{\|g_k\|_2^2}
$$
_Source: Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf, Section 2.1, p. 242_

**polak-ribiere-beta**
$$
\beta_k^{\text{PRP}} = \frac{g_{k+1}^T (g_{k+1} - g_k)}{\|g_k\|_2^2}
$$
_Source: Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf, Section 2.1, p. 242_

**dai-kou-beta**
$$
\beta_k^{\text{DK}} = \frac{g_{k+1}^T y_k}{y_k^T p_k} - \frac{y_k^T y_k}{y_k^T p_k} \frac{p_k^T g_{k+1}}{y_k^T p_k}
$$
_Source: Shen et al. - 2024 - Preconditioned Nonlinear Conjugate Gradient Method for Real-time Interior-point Hyperelasticity.pdf, Section 4.1, p. 5_

**fletcher-reeves-dynamical-system**
$$
\ddot{x} - \frac{2 \langle \nabla f(x), \nabla^2 f(x) \dot{x} \rangle}{\|\nabla f(x)\|^2} \dot{x} = -\nabla f(x)
$$
_Source: Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf, Section 2.3, p. 244_

**Notation:**
x represents solution vector; f represents objective functional; g represents gradient vector; d, p represent search direction vectors; \beta represents momentum weighting parameter; \alpha represents step length parameter; y_k represents gradient increment g_{k+1} - g_k; P represents Jacobi preconditioning matrix.


## 3. Algorithmic Implementation

**fletcher-reeves-ncg-fft**
$$
\begin{algorithmic}
\State $x_0 \leftarrow \text{Initial guess}, \quad d_{-1} \leftarrow 0, \quad g_0 \leftarrow \nabla f(x_0)$
\For{$k = 0, 1, 2, \dots \text{ until } \|g_k\|_2 < \text{tol}$}
\If{$k == 0$}
\State $\beta_k^{\text{FR}} \leftarrow 0$
\Else
\EndIf
\State $d_k \leftarrow -g_k + \beta_k^{\text{FR}} d_{k-1}$
\State $\alpha_k \leftarrow \text{Determine via line search or fixed step } \alpha = \frac{2}{c_- + c_+}$
\State $x_{k+1} \leftarrow x_k + \alpha_k d_k, \quad g_{k+1} \leftarrow \nabla f(x_{k+1})$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf, Section 2.1, p. 242; Section 3, p. 246, Algorithm 1_

**preconditioned-dai-kou-ncg**
$$
\begin{algorithmic}
\State $x_0 \leftarrow x_t, \quad p_0 \leftarrow -P_0 g_0 \quad \text{where } g_0 = \nabla E(x_0)$
\For{$k = 0 \text{ to } \text{IterMax}$}
\State $g_{k+1}, P_{k+1} \leftarrow \text{Compute gradient and Jacobi preconditioner } P_{k+1} = \text{diag}(H_{k+1})^{-1}$
\State $y_k \leftarrow g_{k+1} - g_k$
\State $\beta_k^{\text{DK}} \leftarrow \frac{g_{k+1}^T P_{k+1} y_k}{y_k^T p_k} - \frac{y_k^T P_{k+1} y_k}{y_k^T p_k} \frac{p_k^T g_{k+1}}{y_k^T p_k}$
\State $p_{k+1} \leftarrow -P_{k+1} g_{k+1} + \beta_k^{\text{DK}} p_k$
\State $\alpha \leftarrow \min\left( \frac{\hat{d}}{2 \|p_{k+1}\|_\infty}, -\frac{g_{k+1}^T p_{k+1}}{p_{k+1}^T H_{k+1} p_{k+1}} \right)$
\State $x_{k+1} \leftarrow x_k + \alpha p_{k+1}$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: Implemented natively in Taichi using MeshTaichi for parallel element assembly, Jacobi diagonal preconditioning P_{k+1}, and parallel vector dot products.
_Source: Shen et al. - 2024 - Preconditioned Nonlinear Conjugate Gradient Method for Real-time Interior-point Hyperelasticity.pdf, Section 4.2, p. 5, Algorithm 1_


## 4. Known Pitfalls

- **ncg-lack-of-explicit-convergence-rate**: Unlike linear conjugate gradient or Newton methods, nonlinear conjugate gradient methods lack general theoretical proofs of superlinear convergence rates; for general non-convex objective functionals, convergence theorems typically establish asymptotic residual vanishing \lim_{k \to \infty} \|g_k\| = 0 without explicit rate bounds. _(Source: Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf, Section 2.1, p. 242)_
- **line-search-overhead-in-fft-micromechanics**: Standard NCG implementations require line search evaluations (such as Wolfe conditions) that evaluate objective function values. In FFT-based computational micromechanics, condensed energy functionals are typically unavailable (only stress gradients are computed), making line search costly or intractable unless replaced by fixed step bounds or gradient-based updates. _(Source: Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf, Section 1, p. 240; Section 2.1, p. 241)_
- **restarting-inefficiency**: Periodic restarting strategies (e.g., resetting search directions to steepest descent every n iterations) do not improve efficiency in FFT micromechanics or fast gradient methods; in practice, restarting schemes require roughly twice the iteration count compared to NCG solvers with optimal parameter selection. _(Source: Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf, Section 1, p. 240)_

## References

- Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf
- Shen et al. - 2024 - Preconditioned Nonlinear Conjugate Gradient Method for Real-time Interior-point Hyperelasticity.pdf
- IterMethBook_2ndEd.pdf.pdf
