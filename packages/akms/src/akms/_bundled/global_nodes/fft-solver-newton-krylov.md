---
id: fft-solver-newton-krylov
title: Newton-Krylov Methods for FFT (Newton-CG/GMRES)
domain: fft-galerkin
subdomain: solver-algorithms
tags:
- solvers
- newton
- krylov-solver
- conjugate-gradient
- fft-galerkin
- convergence
- iterative
- nonlinear
status: established
confidence: 0.9
source: hybrid
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 0.9
  note: Linearized equilibrium can be rewritten in L-S form with residual stresses
- to: fft-green-operator
  type: requires
  weight: 0.9
  note: Green's operator used in the L-S form of the linearized system
- to: fft-reference-medium
  type: requires
  weight: 0.7
  note: Reference medium appears in the L-S reformulation of the tangent system
- to: fft-solver-krylov-cg
  type: requires
  weight: 1.0
  note: CG is the standard inner Krylov solver (Newton-CG)
- to: fft-solver-basic-scheme
  type: refines
  weight: 0.7
  note: Basic scheme can serve as inner solver for the linearized equation
- to: fft-solver-quasi-newton
  type: refines
  weight: 0.9
  note: Quasi-Newton (L-BFGS, Anderson) are memory-efficient alternatives to Newton-Krylov
- to: fft-solver-nonlinear-cg
  type: feeds-into
  weight: 0.7
  note: Nonlinear CG avoids tangent storage but converges more slowly
context_size: large
reading_priority: full
load_with:
- fft-solver-krylov-cg
- fft-solver-quasi-newton
- fft-lippmann-schwinger
content_ref: null
akms_schema: v2
---

# Newton-Krylov Methods for FFT (Newton-CG/GMRES)

## Summary
Newton-Krylov methods couple a Newton-Raphson outer loop for the nonlinear balance equation with an iterative Krylov subspace inner solver for the linearized system. The outer loop updates the displacement field via $\mathbf{u}_{k+1} = \mathbf{u}_k + s_k \delta\mathbf{u}_k$, where the increment $\delta\mathbf{u}_k$ solves the linearized equilibrium equation $\mathrm{div}\,(\frac{\partial^2 w}{\partial\boldsymbol{\varepsilon}^2} \colon \nabla^s \delta\mathbf{u}_k) = -\mathrm{div}\,\frac{\partial w}{\partial\boldsymbol{\varepsilon}}$. The inner linear system is solved iteratively using CG (Newton-CG) or GMRES, making this an inexact Newton method. Newton-CG is the most effective solver combination when the tangent stiffness application is cheaper than the nonlinear constitutive law evaluation. However, it carries massive memory costs: for $512^3$ voxels, Newton-CG requires ~51 GB (21 GB for tangent + 5 strain fields), compared to 6 GB for the basic scheme. Global convergence requires back-tracking line search and a dynamically adjusted forcing term (inner solver tolerance). The method extends to finite strains but loses tangent symmetry, requiring GMRES instead of CG.


## 1. Core Concept
Newton-Krylov methods are the standard approach for nonlinear FFT-based homogenization when the material tangent is available and cheap to evaluate. The Newton-Raphson outer loop linearizes the nonlinear balance equation $\mathrm{div}\,\frac{\partial w}{\partial\boldsymbol{\varepsilon}}(\cdot, \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}) = 0$ around the current iterate, producing a linear system involving the tangent stiffness tensor $\frac{\partial^2 w}{\partial\boldsymbol{\varepsilon}^2}$. This linearized system is solved iteratively by a Krylov solver (typically CG for symmetric tangents), making the overall method an inexact Newton method. The key advantage is quadratic convergence of the outer loop near the solution, meaning far fewer nonlinear constitutive evaluations than fixed-point schemes. The linearized system can equivalently be written in Lippmann-Schwinger form with residual stresses: $\delta\boldsymbol{\varepsilon}_k + \boldsymbol{\Gamma}^0 \colon ((\frac{\partial^2 w}{\partial\boldsymbol{\varepsilon}^2} - \mathbf{C}^0) \colon \delta\boldsymbol{\varepsilon}_k + \frac{\partial w}{\partial\boldsymbol{\varepsilon}}) = 0$.


## 2. Mathematical Formulation
The Newton-Krylov framework consists of two nested iterations: an outer Newton loop that handles nonlinearity and an inner Krylov loop that solves the linearized system. The tangent stiffness operator at each Newton step defines a linear system whose solution is the displacement increment. The forcing term controls the accuracy of the inner solve and must be adapted to the outer residual to maintain overall convergence.


**Nonlinear balance equation:**

$$
\mathrm{div}\,\frac{\partial w}{\partial\boldsymbol{\varepsilon}}(\cdot, \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}) = 0
$$

where w is the free energy density, u is the displacement fluctuation

**Newton update:**

$$
\mathbf{u}_{k+1} = \mathbf{u}_k + s_k \delta\mathbf{u}_k
$$

where s_k in (0,1] is the step size from line search, delta u_k is the Newton increment

**Linearized equilibrium (tangent system):**

$$
\mathrm{div}\left(\frac{\partial^2 w}{\partial\boldsymbol{\varepsilon}^2}(\cdot, \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}_k) \colon \nabla^s \delta\mathbf{u}_k\right) = -\mathrm{div}\,\frac{\partial w}{\partial\boldsymbol{\varepsilon}}(\cdot, \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}_k)
$$

where The tangent stiffness tensor d^2w/deps^2 is evaluated at the current strain state

**L-S form of linearized system (with residual stresses):**

$$
\delta\boldsymbol{\varepsilon}_k + \boldsymbol{\Gamma}^0 \colon \left[\left(\frac{\partial^2 w}{\partial\boldsymbol{\varepsilon}^2}(\cdot, \boldsymbol{\varepsilon}_k) - \mathbf{C}^0\right) \colon \delta\boldsymbol{\varepsilon}_k + \frac{\partial w}{\partial\boldsymbol{\varepsilon}}(\cdot, \boldsymbol{\varepsilon}_k)\right] = 0
$$

where eps_k = eps_bar + grad^s u_k, delta_eps_k = grad^s delta_u_k

**Tangent stiffness tensor:**

$$
\mathbb{C}_k(\mathbf{x}) = \frac{\partial^2 w}{\partial\boldsymbol{\varepsilon}^2}(\mathbf{x}, \boldsymbol{\varepsilon}_k(\mathbf{x}))
$$

where Fourth-order tensor evaluated pointwise at each voxel; symmetric for small-strain potential-based models

**Memory cost estimate (512^3 voxels, symmetric tangent):**

$$
\text{Memory} \approx 21\,\text{GB (tangent)} + 5 \times 6\,\text{GB (strain fields)} = 51\,\text{GB}
$$

where A single strain field occupies 6 GB at 512^3 resolution in double precision

**Notation:**

- $w$ — Free energy density (stored energy function)
- $\frac{\partial w}{\partial\boldsymbol{\varepsilon}}$ — Stress tensor sigma = dw/deps
- $\frac{\partial^2 w}{\partial\boldsymbol{\varepsilon}^2}$ — Material tangent stiffness (fourth-order tensor)
- $\delta\mathbf{u}_k$ — Newton displacement increment at step k
- $s_k$ — Newton step size from back-tracking line search, s_k in (0,1]
- $\boldsymbol{\Gamma}^0$ — Green's operator for the reference medium


## 3. Algorithmic Implementation
**Algorithm: Newton-CG for Nonlinear FFT Homogenization**

$$
\begin{algorithmic}
\State $Initialize \colon \mathbf{u}_0 = \mathbf{0}, \; \boldsymbol{\varepsilon}_0 = \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}_0$
\State $Evaluate \; \boldsymbol{\sigma}_0 = \frac{\partial w}{\partial\boldsymbol{\varepsilon}}(\cdot, \boldsymbol{\varepsilon}_0), \quad \mathbb{C}_0 = \frac{\partial^2 w}{\partial\boldsymbol{\varepsilon}^2}(\cdot, \boldsymbol{\varepsilon}_0)$
\While{$\|\mathrm{div}\,\boldsymbol{\sigma}_k\|_{H^{-1}} > \text{tol}_{\text{outer}}$}
    \State $\text{Set forcing term}\colon \eta_k = \min(0.9,\, c \|\mathrm{div}\,\boldsymbol{\sigma}_k\|)$
    \State $\text{Solve (CG)}\colon \delta\boldsymbol{\varepsilon}_k + \boldsymbol{\Gamma}^0 \colon ((\mathbb{C}_k - \mathbf{C}^0) \colon \delta\boldsymbol{\varepsilon}_k + \boldsymbol{\sigma}_k) = 0 \quad \text{to tolerance } \eta_k$
    \State $\text{Line search}\colon s_k = \text{backtrack}(\mathbf{u}_k, \delta\mathbf{u}_k) \in (0, 1]$
    \State $\mathbf{u}_{k+1} = \mathbf{u}_k + s_k \delta\mathbf{u}_k$
    \State $\boldsymbol{\varepsilon}_{k+1} = \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}_{k+1}$
    \State $\boldsymbol{\sigma}_{k+1} = \frac{\partial w}{\partial\boldsymbol{\varepsilon}}(\cdot, \boldsymbol{\varepsilon}_{k+1}), \quad \mathbb{C}_{k+1} = \frac{\partial^2 w}{\partial\boldsymbol{\varepsilon}^2}(\cdot, \boldsymbol{\varepsilon}_{k+1})$
\EndWhile
\end{algorithmic}
$$

**Taichi Mapping:**
Outer Newton loop on host. Inner CG loop maps to GPU kernels: (1) tangent application C_k : delta_eps at each voxel (embarrassingly parallel), (2) FFT/iFFT pair for Gamma0. Tangent tensor stored as a 6x6 symmetric matrix per voxel in a Taichi field (21 floats/voxel). Back-tracking line search requires additional constitutive evaluations on GPU. Memory-dominated by tangent storage.


## 4. Known Pitfalls
**Massive memory cost from tangent storage:** The spatially varying tangent stiffness $\mathbb{C}_k(\mathbf{x})$ must be stored at every voxel. For symmetric tangents (21 independent components) on a $512^3$ grid in double precision, this requires 21 GB. Including the 5 strain fields for CG (30 GB), total memory is ~51 GB. Single-precision tangent and displacement-based implementation can reduce this to ~25 GB, but it remains far above the 6-12 GB of gradient-based solvers.


**Not globally convergent without line search:** Pure Newton-Raphson diverges if the initial guess is outside the local region of attraction. A globalization strategy (back-tracking line search) is essential: reduce $s_k$ along the Newton direction until sufficient decrease in the residual or energy is achieved. Without line search, the method may oscillate or diverge for large strain increments or path-dependent materials.


**Forcing term must be adaptive:** The inner CG tolerance (forcing term $\eta_k$) must decrease as the outer Newton residual decreases. A fixed tight tolerance wastes inner iterations early when the outer solution is far from converged. A fixed loose tolerance prevents quadratic convergence near the solution. The standard choice is $\eta_k = \min(0.9, c\|\text{residual}_k\|)$ where $c$ is a small constant.


**Non-symmetric tangent at finite strains:** At finite strains with the first Piola-Kirchhoff stress and deformation gradient, the material tangent $\partial\mathbf{P}/\partial\mathbf{F}$ is fundamentally non-symmetric. This prevents use of CG for the inner solve (requiring GMRES instead) and forces storage of the full non-symmetric tangent (36 components instead of 21), further increasing memory demands.


**Inapplicable to black-box constitutive models:** Newton-Krylov requires explicit access to the tangent stiffness $\partial^2 w / \partial\boldsymbol{\varepsilon}^2$. For black-box material subroutines or models without analytical tangent expressions, the method cannot be used. Alternatives include numerical tangent approximation (expensive, inaccurate), or switching to tangent-free methods like Anderson mixing or nonlinear CG.


## 5. References
- Schneider (2021) -- Newton-Krylov methods, forcing term, line search, memory cost analysis
- Kabel et al. (2014) -- Newton-CG as most effective combination for finite strain FFT
- Wicht et al. (2020) -- Forcing term strategy and globalization for FFT Newton solvers
- Lahellec et al. (2003) -- Newton-Raphson with basic scheme as inner solver for finite strains
- Lucarini et al. (2022) -- DBFFT Newton framework, non-symmetric tangent at finite strains

