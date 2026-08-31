---
id: fft-solver-quasi-newton
title: Quasi-Newton Methods (L-BFGS, Anderson Acceleration)
domain: fft-galerkin
subdomain: solver-algorithms
tags:
- solvers
- quasi-newton
- fft-galerkin
- convergence
- iterative
- nonlinear
- anderson-acceleration
status: established
confidence: 0.9
source: hybrid
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 0.8
  note: Anderson mixing accelerates the fixed-point L-S iteration
- to: fft-solver-basic-scheme
  type: refines
  weight: 1.0
  note: Anderson mixing wraps the basic scheme fixed-point iteration
- to: fft-solver-newton-krylov
  type: refines
  weight: 0.9
  note: Quasi-Newton methods are tangent-free alternatives to Newton-Krylov
- to: fft-solver-barzilai-borwein
  type: refines
  weight: 0.8
  note: Barzilai-Borwein can be interpreted as L-BFGS of depth 1 without line search
- to: fft-reference-medium
  type: requires
  weight: 0.6
  note: The underlying fixed-point scheme uses the reference medium
- to: fft-solver-krylov-cg
  type: feeds-into
  weight: 0.6
  note: Anderson mixing is equivalent to GMRES for linear problems
context_size: large
reading_priority: full
load_with:
- fft-solver-newton-krylov
- fft-solver-basic-scheme
- fft-solver-barzilai-borwein
content_ref: null
akms_schema: v2
---

# Quasi-Newton Methods (L-BFGS, Anderson Acceleration)

## Summary
Quasi-Newton methods for FFT-based homogenization approximate the tangent stiffness implicitly, avoiding the massive memory cost of storing the full tangent tensor. Two main approaches are used: L-BFGS (Limited-Memory BFGS) and Anderson acceleration (mixing). L-BFGS approximates the inverse Hessian via a two-loop recursion over the $m$ most recent gradient differences, requiring $2m + 4$ strain fields. However, L-BFGS is not competitive with the Barzilai-Borwein scheme for small-strain inelasticity because the FFT stiffness matrix is block-diagonal and sparse, making the L-BFGS overhead unwarranted. Anderson mixing of depth $m$ accelerates fixed-point iterations $\mathbf{u}_{k+1} = F(\mathbf{u}_k)$ by computing $\mathbf{u}_{k+1} = \sum \alpha_{i,m} F(\mathbf{u}_{k-i})$ with coefficients minimizing the mixed residual norm, requiring $2m + 2$ fields. Anderson mixing is equivalent to GMRES for linear problems and was introduced to FFT micromechanics as "nonlinear GMRES." With depth $m = 4$, Anderson-mixed basic scheme is the second-fastest method up to residual $10^{-3}$ and represents a highly robust, tangent-free general-purpose solver.


## 1. Core Concept
Quasi-Newton methods bypass the need for explicit tangent computation by building approximate curvature information from the iteration history. L-BFGS stores $m$ pairs of position and gradient differences and uses the two-loop recursion to efficiently compute an approximate Newton search direction without forming the full Hessian. Anderson mixing takes a different approach: given a fixed-point iteration $\mathbf{u}_{k+1} = F(\mathbf{u}_k)$ (such as the basic scheme), it stores the previous $m$ iterates and their images under $F$, then computes the next iterate as an optimal linear combination $\mathbf{u}_{k+1} = \sum_{i=0}^{m-1} \alpha_{i,m} F(\mathbf{u}_{k-i})$ where the coefficients minimize $\|\sum \alpha_{i,m}(\mathbf{u}_{k-i} - F(\mathbf{u}_{k-i}))\|^2$ subject to $\sum \alpha_{i,m} = 1$. This constrained least-squares problem is $m$-dimensional and involves only scalar products of residual vectors. Anderson mixing is a multi-secant method (Fang and Saad) and is equivalent to GMRES for linear problems (Walker and Ni). Both methods are tangent-free, making them applicable to black-box constitutive models.


## 2. Mathematical Formulation
The two quasi-Newton approaches differ in their mathematical foundation. L-BFGS operates in the optimization framework, approximating the inverse Hessian to compute search directions. Anderson mixing operates in the fixed-point iteration framework, optimally combining past iterates to accelerate convergence. Both achieve memory scaling linear in the depth parameter $m$ and avoid the $O(N_{\text{voxels}})$ tangent storage of Newton-Krylov.


**Anderson mixing update rule:**

$$
\mathbf{u}_{k+1} = \sum_{i=0}^{m-1} \alpha_{i,m} F(\mathbf{u}_{k-i})
$$

where F is the fixed-point operator (e.g., basic scheme), m is the mixing depth

**Anderson mixing coefficient optimization:**

$$
\left\|\sum_{i=0}^{m-1} \alpha_{i,m} (\mathbf{u}_{k-i} - F(\mathbf{u}_{k-i}))\right\|^2 \longrightarrow \min \quad \text{s.t.} \quad \sum_{i=0}^{m-1} \alpha_{i,m} = 1
$$

where Linearly constrained quadratic optimization in m dimensions; involves only scalar products of residual vectors

**L-BFGS memory requirement:**

$$
\text{Memory} = (2m + 4) \; \text{strain fields}
$$

where m is the depth (number of stored correction pairs)

**Anderson mixing memory requirement:**

$$
\text{Memory} = (2m + 2) \; \text{strain fields}
$$

where m iterates u_{k-i} and m images F(u_{k-i}), plus 2 working fields

**Barzilai-Borwein as L-BFGS depth 1:**

$$
\text{L-BFGS}(m=1, \text{no line search}) \equiv \text{Barzilai-Borwein}
$$

where The BB method can be interpreted as the simplest quasi-Newton approximation

**Equivalence to GMRES for linear problems:**

$$
\text{Anderson mixing} \equiv \text{GMRES} \quad \text{(for linear } F \text{)}
$$

where Proven by Walker and Ni; Anderson mixing is a multi-secant method (Fang and Saad)

**Notation:**

- $F$ — Fixed-point operator (e.g., basic scheme iteration)
- $m$ — Mixing depth / number of stored history pairs
- $\alpha_{i,m}$ — Optimal mixing coefficients from constrained least-squares
- $\mathbf{u}_k$ — Displacement fluctuation field at iteration k


## 3. Algorithmic Implementation
**Algorithm: Anderson-Mixed Basic Scheme (Depth m)**

$$
\begin{algorithmic}
\State $Initialize \colon \mathbf{u}_0 = \mathbf{0}, \; F(\mathbf{u}_0) = \text{basic\_scheme\_step}(\mathbf{u}_0)$
\While{$\|\mathbf{u}_k - F(\mathbf{u}_k)\| > \text{tol}$}
    \State $Store \; \mathbf{u}_{k-i}, \; F(\mathbf{u}_{k-i}) \quad \text{for } i = 0, \ldots, \min(m-1, k)$
    \State $\text{Form residuals} \colon \mathbf{r}_{k-i} = \mathbf{u}_{k-i} - F(\mathbf{u}_{k-i})$
    \State $\text{Solve} \colon \alpha_{i,m} = \arg\min \|\sum \alpha_{i,m} \mathbf{r}_{k-i}\|^2 \; \text{s.t.} \; \sum \alpha_{i,m} = 1$
    \State $\mathbf{u}_{k+1} = \sum_{i=0}^{m-1} \alpha_{i,m} F(\mathbf{u}_{k-i})$
    \State $F(\mathbf{u}_{k+1}) = \text{basic\_scheme\_step}(\mathbf{u}_{k+1})$
\EndWhile
\end{algorithmic}
$$

**Taichi Mapping:**
The basic scheme step (constitutive eval + FFT/iFFT) runs as GPU kernels. The m-dimensional QP is solved on the host (tiny problem). History buffer stores 2m+2 strain fields as Taichi fields. Scalar products for the QP are parallel reductions on GPU. Memory scales linearly with m; typical m=4 requires 10 strain fields.

**Algorithm: L-BFGS Two-Loop Recursion for FFT Homogenization**

$$
\begin{algorithmic}
\State $Initialize \colon \mathbf{u}_0 = \mathbf{0}, \; \mathbf{g}_0 = \nabla W(\mathbf{u}_0)$
\While{$\|\mathbf{g}_k\| > \text{tol}$}
    \State $\text{Store} \colon \mathbf{s}_k = \mathbf{u}_k - \mathbf{u}_{k-1}, \quad \mathbf{y}_k = \mathbf{g}_k - \mathbf{g}_{k-1}$
    \State $\mathbf{q} \leftarrow \mathbf{g}_k$
    \State $\text{Backward loop} \colon \text{for } i = k, \ldots, k-m+1 \colon \rho_i = 1/\langle\mathbf{y}_i, \mathbf{s}_i\rangle, \; \alpha_i = \rho_i \langle\mathbf{s}_i, \mathbf{q}\rangle, \; \mathbf{q} \leftarrow \mathbf{q} - \alpha_i \mathbf{y}_i$
    \State $\mathbf{z} = H_k^0 \mathbf{q}, \quad H_k^0 = \langle\mathbf{s}_k, \mathbf{y}_k\rangle / \langle\mathbf{y}_k, \mathbf{y}_k\rangle \cdot \mathbf{Id}$
    \State $\text{Forward loop} \colon \text{for } i = k-m+1, \ldots, k \colon \beta_i = \rho_i \langle\mathbf{y}_i, \mathbf{z}\rangle, \; \mathbf{z} \leftarrow \mathbf{z} + (\alpha_i - \beta_i)\mathbf{s}_i$
    \State $\mathbf{d}_k = -\mathbf{z}$
    \State $\mathbf{u}_{k+1} = \mathbf{u}_k + s_k \mathbf{d}_k$
    \State $\mathbf{g}_{k+1} = \nabla W(\mathbf{u}_{k+1})$
\EndWhile
\end{algorithmic}
$$

**Taichi Mapping:**
The two-loop recursion involves 2m inner products and 2m vector updates, all parallelizable on GPU. Gradient evaluation (constitutive law + FFT) is the dominant cost. Stores 2m+4 strain fields as Taichi fields. The backward/forward loops are lightweight compared to the FFT and constitutive evaluation.


## 4. Known Pitfalls
**L-BFGS not competitive for sparse FFT stiffness:** For FFT-based homogenization, the "stiffness matrix" (tangent operator) is block-diagonal and sparse. L-BFGS is designed for problems with dense Hessians and carries substantial computational overhead from the two-loop recursion over $m$ stored pairs. For small-strain inelasticity, L-BFGS is outperformed by the Barzilai-Borwein method, which is effectively L-BFGS of depth 1 without line search but avoids the overhead.


**Anderson mixing slows down for high accuracy:** The Anderson-mixed basic scheme with depth $m = 4$ is the second-fastest method up to a residual of $10^{-3}$, but slows down when pushing for higher accuracy (e.g., $10^{-5}$). This accuracy degradation likely results from the finite depth $m$ limiting the effective Krylov subspace dimension, causing the method to behave like a truncated GMRES.


**Memory scales linearly with depth m:** Anderson mixing requires $2m + 2$ strain fields and L-BFGS requires $2m + 4$ strain fields. For depth $m = 4$, Anderson needs 10 fields and L-BFGS needs 12 fields. At $512^3$ resolution (6 GB per strain field), this translates to 60-72 GB, comparable to Newton-CG. Practical GPU implementations must keep $m$ small (typically 3-5).


**No guaranteed convergence rate:** Unlike CG (with provable $\sqrt{\kappa}$ convergence) or Newton (with local quadratic convergence), quasi-Newton methods lack sharp convergence guarantees for the nonlinear FFT homogenization setting. Anderson mixing is a heuristic acceleration of the underlying fixed-point scheme, and its convergence can depend on the specific problem, microstructure, and material nonlinearity.


**Coefficient ill-conditioning at large depth:** The $m$-dimensional constrained least-squares problem for Anderson mixing coefficients can become ill-conditioned when the stored residual vectors become nearly linearly dependent. This occurs at large $m$ or when the iteration approaches convergence. Regularization (e.g., Tikhonov) or dropping old vectors may be needed.


## 5. References
- Schneider (2021) -- L-BFGS, Anderson mixing, comparison to Barzilai-Borwein, memory table
- Shanthraj et al. (2015) -- Anderson mixing as nonlinear GMRES for FFT homogenization
- Chen et al. (2019) -- Anderson-mixed basic scheme with depth m=4 for small strains
- Wicht et al. (2020) -- Comprehensive comparison of quasi-Newton methods for FFT homogenization
- Walker and Ni (2011) -- Equivalence of Anderson mixing and GMRES for linear problems
- Fang and Saad (2009) -- Anderson mixing as a multi-secant method

