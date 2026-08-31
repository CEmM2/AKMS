---
id: fft-solver-polarization-admm
title: Polarization Methods & ADMM for FFT
domain: fft-galerkin
subdomain: solver-algorithms
tags:
- solvers
- polarization
- fft-galerkin
- convergence
- accelerated-schemes
- iterative
- operator-splitting
- admm
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: ADMM reformulates the Lippmann-Schwinger problem as constrained optimization with augmented Lagrangian
- to: fft-green-operator
  type: requires
  weight: 1.0
  note: Strain update uses the Green's operator Gamma^0 in Fourier space
- to: fft-reference-medium
  type: requires
  weight: 0.9
  note: Reference stiffness C^0 = alpha_0 Id controls the augmented Lagrangian penalty
- to: fft-solver-basic-scheme
  type: requires
  weight: 0.7
  note: ADMM strain update has the same structure as the basic scheme applied to a modified right-hand side
- to: fft-solver-eyre-milton
  type: refines
  weight: 0.9
  note: ADMM is Douglas-Rachford (gamma=1/2); Eyre-Milton is Peaceman-Rachford (gamma=0) in the unified framework
- to: fft-convergence-schemes
  type: feeds-into
  weight: 0.7
  note: ADMM convergence and comparison with other solver families
- to: fft-galerkin-basics
  type: requires
  weight: 0.6
  note: Variational formulation underlying the augmented Lagrangian
context_size: medium
reading_priority: full
load_with:
- fft-solver-eyre-milton
- fft-reference-medium
- fft-green-operator
content_ref: null
akms_schema: v2
---

# Polarization Methods & ADMM for FFT

## Summary
The ADMM (Alternating Direction Method of Multipliers) approach to FFT homogenization reformulates the unconstrained variational problem as a constrained optimization by introducing an auxiliary strain field $\mathbf{e}$ tied to the compatible strain $\boldsymbol{\varepsilon}$ via a Lagrange multiplier $\lambda$. The augmented Lagrangian functional adds a quadratic penalty scaled by the reference stiffness $\alpha_0$. The three-step iteration alternates between a global strain update (FFT-based Green's operator application), a local nonlinear auxiliary strain update (proximal operator), and a Lagrange multiplier update. The scheme is mathematically equivalent to Douglas-Rachford splitting and corresponds to the damping parameter $\gamma = 1/2$ in the generalized Monchiet-Bonnet framework. It converges for any reference material and any initial iterate, requiring 3 fields in memory. The un-damped variant ($\gamma = 0$) recovers the Eyre-Milton scheme with faster convergence.


## 1. Core Concept
The variational problem $\min_u \int_Y w(\mathbf{x}, \bar{\varepsilon} + \nabla^s \mathbf{u}) \, d\mathbf{x}$ is converted to a constrained problem by introducing an auxiliary strain $\mathbf{e}$ subject to $\varepsilon = \mathbf{e}$, then solved via the augmented Lagrangian $L_{\alpha_0}(\mathbf{u}, \mathbf{e}, \lambda)$. The ADMM approach finds saddle points by alternating partial minimizations. The strain update minimizes $L$ over compatible fields (global, FFT-based); the auxiliary update minimizes $L$ over $\mathbf{e}$ pointwise (local, nonlinear); and the multiplier update enforces the constraint. This three-field splitting isolates the nonlinear constitutive evaluation into a purely local proximal operator, avoiding global tangent matrices. The generalized framework with damping parameter $\gamma \in [0,1)$ unifies Douglas-Rachford ($\gamma = 1/2$) and Peaceman-Rachford ($\gamma = 0$), with all variants converging linearly.


## 2. Mathematical Formulation
The augmented Lagrangian combines the free energy evaluated on the auxiliary strain, the constraint enforcement via the Lagrange multiplier, and a quadratic penalty. The ADMM iteration splits into three sub-problems that decouple the global compatibility projection from the local constitutive evaluation. The generalized framework introduces an intermediate strain that interpolates between ADMM and Eyre-Milton behavior.


**Augmented Lagrangian functional:**

$$
L_{\alpha_0}(\mathbf{u}, \mathbf{e}, \lambda) = \int_Y w(\mathbf{x}, \mathbf{e}) + \lambda \colon (\bar{\varepsilon} + \nabla^s \mathbf{u} - \mathbf{e}) + \alpha_0 \|\bar{\varepsilon} + \nabla^s \mathbf{u} - \mathbf{e}\|^2 \, d\mathbf{x}
$$

where w is the condensed free energy, lambda is the Lagrange multiplier, alpha_0 is the penalty parameter

**ADMM strain update (global, FFT-based):**

$$
\boldsymbol{\varepsilon}_{k+1} = \bar{\boldsymbol{\varepsilon}} - \boldsymbol{\Gamma}^0 \colon (\lambda_k - \mathbf{C}^0 \colon \mathbf{e}_k)
$$

where Gamma^0 is the Green's operator; this projects onto compatible strain fields

**ADMM auxiliary strain update (local, nonlinear):**

$$
\mathbf{e}_{k+1} = \left(\frac{\partial w}{\partial \varepsilon} + \mathbf{C}^0\right)^{-1}(\lambda_k + \mathbf{C}^0 \colon \boldsymbol{\varepsilon}_{k+1})
$$

where Local nonlinear solve (proximal operator) at each grid point

**ADMM Lagrange multiplier update:**

$$
\lambda_{k+1} = \lambda_k + \mathbf{C}^0 \colon (\boldsymbol{\varepsilon}_{k+1} - \mathbf{e}_{k+1})
$$

where lambda converges to the true stress field sigma = dw/depsilon at the solution

**Generalized framework with damping (Monchiet-Bonnet):**

$$
\boldsymbol{\varepsilon}^{k+1/2} = \bar{\varepsilon} - \Gamma^0 \colon (\lambda^k - \mathbf{C}^0 \colon \mathbf{e}^k), \quad \boldsymbol{\varepsilon}^{k+1} = 2(1-\gamma)\boldsymbol{\varepsilon}^{k+1/2} - (1-2\gamma)\mathbf{e}^k
$$

where gamma = 1/2 gives ADMM (Douglas-Rachford), gamma = 0 gives Eyre-Milton (Peaceman-Rachford)

**Douglas-Rachford equivalence:**

$$
\gamma = \tfrac{1}{2} \implies \boldsymbol{\varepsilon}^{k+1} = \boldsymbol{\varepsilon}^{k+1/2} \quad \text{(standard ADMM)}
$$

where With gamma = 1/2 the intermediate and final strain coincide

**Notation:**

- $L_{\alpha_0}$ — Augmented Lagrangian functional
- $\mathbf{e}_k$ — Auxiliary strain field at iteration k
- $\lambda_k$ — Lagrange multiplier (converges to stress at solution)
- $\boldsymbol{\varepsilon}_k$ — Compatible strain field at iteration k
- $\mathbf{C}^0$ — Reference medium stiffness tensor (C^0 = alpha_0 Id)
- $\boldsymbol{\Gamma}^0$ — Green's operator of the reference medium
- $\gamma$ — Damping parameter in the generalized framework
- $\alpha_0$ — Scalar reference stiffness / penalty parameter


## 3. Algorithmic Implementation
**Algorithm: ADMM Polarization Scheme (Douglas-Rachford)**

$$
\begin{algorithmic}
\State $\boldsymbol{\varepsilon}_0(\mathbf{x}) \leftarrow \bar{\boldsymbol{\varepsilon}}, \quad \mathbf{e}_0(\mathbf{x}) \leftarrow \bar{\boldsymbol{\varepsilon}}, \quad \lambda_0(\mathbf{x}) \leftarrow \mathbb{C}(\mathbf{x}) \colon \bar{\boldsymbol{\varepsilon}}$
\While{$\|\boldsymbol{\varepsilon}_{k+1} - \mathbf{e}_{k+1}\|_{L^2} / \|\boldsymbol{\varepsilon}\| > \text{tol} \;\text{ or }\; \|\mathbb{C}(\mathbf{x}) \colon \boldsymbol{\varepsilon}_{k+1} - \lambda_{k+1}\|_{L^2} / \|\mathbf{C}^0 \colon \boldsymbol{\varepsilon}\| > \text{tol}$}
    \State $\hat{\boldsymbol{r}}_k \leftarrow \text{DFT}(\lambda_k - \mathbf{C}^0 \colon \mathbf{e}_k)$
    \State $\hat{\boldsymbol{\varepsilon}}_{k+1}(\boldsymbol{\xi}) \leftarrow -\hat{\boldsymbol{\Gamma}}^0(\boldsymbol{\xi}) \colon \hat{\boldsymbol{r}}_k(\boldsymbol{\xi}) \quad \forall \boldsymbol{\xi} \neq \mathbf{0}$
    \State $\hat{\boldsymbol{\varepsilon}}_{k+1}(\mathbf{0}) \leftarrow \bar{\boldsymbol{\varepsilon}}$
    \State $\boldsymbol{\varepsilon}_{k+1} \leftarrow \text{DFT}^{-1}(\hat{\boldsymbol{\varepsilon}}_{k+1})$
    \State $\mathbf{e}_{k+1}(\mathbf{x}) \leftarrow \left(\frac{\partial w}{\partial \varepsilon}(\mathbf{x}, \cdot) + \mathbf{C}^0\right)^{-1}\!\bigl(\lambda_k(\mathbf{x}) + \mathbf{C}^0 \colon \boldsymbol{\varepsilon}_{k+1}(\mathbf{x})\bigr) \quad \text{(local solve)}$
    \State $\lambda_{k+1}(\mathbf{x}) \leftarrow \lambda_k(\mathbf{x}) + \mathbf{C}^0 \colon \bigl(\boldsymbol{\varepsilon}_{k+1}(\mathbf{x}) - \mathbf{e}_{k+1}(\mathbf{x})\bigr)$
\EndWhile
\end{algorithmic}
$$

**Taichi Mapping:**
The strain update decomposes into forward FFT, pointwise Green's operator kernel in Fourier space, and inverse FFT. The auxiliary strain update (local nonlinear solve) and Lagrange multiplier update are purely pointwise Taichi kernels over the voxel grid. Convergence checks require two parallel reductions for the compatibility and constitutive norms. Memory footprint is 3 symmetric tensor fields (strain, auxiliary strain, Lagrange multiplier).


## 4. Known Pitfalls
**Intermediate iterates are neither compatible nor in equilibrium:** Unlike gradient-based solvers where the strain iterate is always compatible, ADMM iterates split compatibility and constitutive consistency across separate fields. The auxiliary strain $\mathbf{e}$ satisfies the constitutive law but is not compatible, while $\varepsilon$ is compatible but does not satisfy the constitutive law until convergence. This requires dual convergence criteria (compatibility and constitutive) rather than a single equilibrium residual.


**Higher memory than Eyre-Milton:** ADMM requires 3 fields ($\varepsilon$, $\mathbf{e}$, $\lambda$) compared to 2 fields for the Eyre-Milton scheme. For large 3D microstructures with symmetric second-order tensor fields (6 components per voxel), the additional field can be significant. If memory is a constraint, the un-damped Eyre-Milton formulation is preferred.


**Slower convergence than un-damped Eyre-Milton:** The ADMM scheme corresponds to $\gamma = 1/2$ in the generalized framework, which has a larger contraction factor than the Eyre-Milton scheme ($\gamma = 0$). In practice, ADMM may require roughly twice as many iterations as Eyre-Milton for the same tolerance. The tradeoff is that ADMM provides direct access to the stress field $\lambda$ during iteration.


**Local nonlinear solve cost:** Like Eyre-Milton, each ADMM iteration requires solving a local nonlinear equation $(\frac{\partial w}{\partial \varepsilon} + \mathbf{C}^0)^{-1}$ at every grid point. For complex constitutive models, this local Newton iteration dominates the per-iteration cost and can be more expensive than a single forward stress evaluation in gradient-based schemes.


**Reference medium independence can mask suboptimal choices:** Since ADMM converges for any reference material $\mathbf{C}^0$, there is no divergence signal for a poor parameter choice. However, a poorly chosen $\alpha_0$ can drastically increase iteration count. The optimal choice for the fastest convergence still requires estimating the material contrast bounds $\alpha_-$ and $\alpha_+$.


## 5. References
- Schneider (2021) -- review of nonlinear FFT-based computational homogenization, ADMM and augmented Lagrangian formulations
- Michel et al. (2001) -- augmented Lagrangian method for FFT-based computational homogenization
- Monchiet and Bonnet (2012) -- generalized polarization framework unifying Douglas-Rachford and Peaceman-Rachford

