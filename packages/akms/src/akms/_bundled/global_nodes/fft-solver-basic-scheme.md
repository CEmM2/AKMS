---
id: fft-solver-basic-scheme
title: Basic Scheme (Moulinec-Suquet Fixed Point)
domain: fft-galerkin
subdomain: solver-algorithms
tags:
- solvers
- fft-galerkin
- spectral
- convergence
- iterative
- fixed-point
- gradient-descent
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: Basic scheme is the fixed-point iteration on the Lippmann-Schwinger equation
- to: fft-green-operator
  type: requires
  weight: 1.0
  note: Uses the Eshelby-Green operator Gamma^0 as the projection kernel
- to: fft-reference-medium
  type: requires
  weight: 0.9
  note: Convergence depends critically on reference medium parameter alpha_0
- to: fft-discretization-moulinec-suquet
  type: requires
  weight: 0.8
  note: Originally formulated with trigonometric collocation discretization
- to: fft-solver-barzilai-borwein
  type: feeds-into
  weight: 0.9
  note: BB method replaces fixed step size with adaptive spectral step
- to: fft-solver-fast-gradient
  type: feeds-into
  weight: 0.8
  note: Fast gradient methods augment the basic scheme with momentum
- to: fft-solver-nonlinear-cg
  type: feeds-into
  weight: 0.8
  note: Nonlinear CG generalizes gradient descent with conjugate directions
- to: fft-convergence-schemes
  type: feeds-into
  weight: 0.7
  note: Convergence rate analysis depends on contrast ratio kappa
context_size: medium
reading_priority: full
load_with:
- fft-lippmann-schwinger
- fft-reference-medium
- fft-green-operator
content_ref: null
akms_schema: v2
---

# Basic Scheme (Moulinec-Suquet Fixed Point)

## Summary
The basic scheme is the foundational fixed-point iteration for FFT-based computational homogenization, introduced by Moulinec and Suquet. It iteratively solves the Lippmann-Schwinger equation by computing the stress polarization in real space, applying the Green's operator via FFT in Fourier space, and updating the strain field. The method can be interpreted as gradient descent on the total condensed elastic energy, with the reference medium stiffness controlling the algorithmic step size. Convergence is globally linear and mesh-independent, but the iteration count scales linearly with the phase contrast ratio $\kappa = \alpha_+/\alpha_-$, making it impractically slow for high-contrast composites. Memory footprint is minimal (1 strain field), and each iteration requires exactly two FFT evaluations. The method fails for infinite contrast (porous or rigid inclusions) when using trigonometric polynomial discretizations.


## 1. Core Concept
The basic scheme iterates the Lippmann-Schwinger equation as a fixed-point method. Given a reference medium with isotropic stiffness $\mathbf{C}^0 = \alpha_0 \mathbf{Id}$, the stress polarization $\boldsymbol{\tau}_k = \boldsymbol{\sigma}(\boldsymbol{\varepsilon}_k) - \mathbf{C}^0 \colon \boldsymbol{\varepsilon}_k$ is computed pointwise in real space from the current strain iterate, then convolved with the Green's operator $\boldsymbol{\Gamma}^0$ via FFT to obtain the updated strain field. This is mathematically equivalent to gradient descent on the total condensed elastic energy $W(\mathbf{u}) = \int_Y w(\mathbf{x}, \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}) \, d\mathbf{x}$ with step size $s_k = 1/(2\mu_0)$. If the reference material is sufficiently stiff (small step size), the energy decreases monotonically. If too soft (large step size), the explicit gradient update becomes unstable. The iteration count is bounded independently of mesh resolution but grows linearly with the material contrast ratio, explaining why the method is practical only for moderate contrast composites.


## 2. Mathematical Formulation
The basic scheme update computes the next strain iterate from the current one by evaluating the nonlinear stress response, forming the polarization with respect to the reference medium, and applying the Green's operator. The convergence condition on $\alpha_0$ depends on the Lipschitz constant $\alpha_+$ and monotonicity constant $\alpha_-$ of the stress operator, with different bounds for general and potential-based nonlinearity. The optimal reference medium for the basic scheme is the arithmetic mean of the material bounds.


**Basic scheme fixed-point iteration:**

$$
\boldsymbol{\varepsilon}_{k+1} = \bar{\boldsymbol{\varepsilon}} - \boldsymbol{\Gamma}^0 \colon \left( \boldsymbol{\sigma}(\boldsymbol{\varepsilon}_k) - \mathbf{C}^0 \colon \boldsymbol{\varepsilon}_k \right), \quad k = 0, 1, \ldots
$$

where epsilon-bar is the prescribed macroscopic strain, Gamma^0 is the Green's operator, sigma is the nonlinear stress, C^0 is the reference stiffness

**Convergence condition (general nonlinearity):**

$$
\alpha_0 > \frac{\alpha_+^2}{2\alpha_-}
$$

where alpha_+ is the Lipschitz constant, alpha_- is the monotonicity constant of the stress operator

**Fastest theoretical rate (general nonlinearity):**

$$
\alpha_0^{\text{opt}} = \frac{\alpha_+^2}{\alpha_-}
$$

where This gives the smallest contraction factor for the general case

**Convergence condition (potential-based stress):**

$$
\alpha_0 > \frac{\alpha_+}{2}
$$

where Less restrictive bound when stress derives from a potential (symmetric positive definite tangent)

**Optimal reference medium (potential-based):**

$$
\alpha_0^{\text{opt}} = \frac{\alpha_+ + \alpha_-}{2}
$$

where Arithmetic mean of bounds; convergence rate is (alpha_+ - alpha_-)/(alpha_+ + alpha_-)

**Gradient descent interpretation:**

$$
\mathbf{u}_{k+1} = \mathbf{u}_k - s_k \nabla W(\mathbf{u}_k), \quad s_k = \frac{1}{2\mu_0}
$$

where W is the total condensed elastic energy, nabla W = G dw/depsilon, mu_0 is the reference shear modulus

**Optimal reference (linear isotropic):**

$$
\lambda_0 = \frac{1}{2}\left(\inf_{\mathbf{x}} \lambda(\mathbf{x}) + \sup_{\mathbf{x}} \lambda(\mathbf{x})\right), \quad \mu_0 = \frac{1}{2}\left(\inf_{\mathbf{x}} \mu(\mathbf{x}) + \sup_{\mathbf{x}} \mu(\mathbf{x})\right)
$$

where Arithmetic mean of extreme Lame constants across the microstructure

**Notation:**

- $\boldsymbol{\varepsilon}_k$ — Strain field at iteration k
- $\bar{\boldsymbol{\varepsilon}}$ — Prescribed macroscopic strain
- $\boldsymbol{\Gamma}^0$ — Eshelby-Green operator of the reference medium
- $\mathbf{C}^0$ — Reference medium stiffness tensor (C^0 = alpha_0 Id)
- $\boldsymbol{\sigma}$ — Nonlinear stress operator
- $\alpha_0$ — Scalar reference medium parameter
- $\alpha_+$ — Lipschitz constant of the stress operator
- $\alpha_-$ — Strong monotonicity constant
- $\kappa$ — Phase contrast ratio alpha_+/alpha_-
- $W$ — Total condensed elastic energy functional


## 3. Algorithmic Implementation
**Algorithm: Basic Scheme (Moulinec-Suquet)**

$$
\begin{algorithmic}
\State $\boldsymbol{\varepsilon}_0(\mathbf{x}) \leftarrow \bar{\boldsymbol{\varepsilon}}$
\While{$\|\boldsymbol{\Gamma} \colon \boldsymbol{\sigma}(\boldsymbol{\varepsilon}_k)\|_{L^2} / \|\langle \boldsymbol{\sigma}_k \rangle\| > \text{tol}$}
    \State $\boldsymbol{\tau}_k(\mathbf{x}) \leftarrow \boldsymbol{\sigma}(\boldsymbol{\varepsilon}_k(\mathbf{x})) - \mathbf{C}^0 \colon \boldsymbol{\varepsilon}_k(\mathbf{x})$
    \State $\hat{\boldsymbol{\tau}}_k \leftarrow \text{DFT}(\boldsymbol{\tau}_k)$
    \State $\hat{\boldsymbol{\varepsilon}}_{k+1}(\boldsymbol{\xi}) \leftarrow -\hat{\boldsymbol{\Gamma}}^0(\boldsymbol{\xi}) \colon \hat{\boldsymbol{\tau}}_k(\boldsymbol{\xi}) \quad \forall \boldsymbol{\xi} \neq \mathbf{0}$
    \State $\hat{\boldsymbol{\varepsilon}}_{k+1}(\mathbf{0}) \leftarrow \bar{\boldsymbol{\varepsilon}}$
    \State $\boldsymbol{\varepsilon}_{k+1} \leftarrow \text{DFT}^{-1}(\hat{\boldsymbol{\varepsilon}}_{k+1})$
\EndWhile
\end{algorithmic}
$$

**Taichi Mapping:**
Pointwise stress and polarization evaluation maps to a Taichi kernel over the voxel grid. Forward and inverse FFT use ti.fft (or cuFFT via wrapper). Green's operator application is a pointwise kernel in Fourier space. The entire iteration loop runs on GPU with only the convergence check requiring a global reduction.


## 4. Known Pitfalls
**Linear scaling with contrast ratio:** The iteration count scales linearly with $\kappa = \alpha_+/\alpha_-$. For high-contrast composites ($\kappa > 100$), the basic scheme requires hundreds or thousands of iterations. Krylov and polarization methods reduce this to $\sqrt{\kappa}$ scaling. For moderate contrast ($\kappa < 10$), the basic scheme remains competitive due to its minimal memory footprint and simplicity.


**Divergence for infinite contrast:** The basic scheme fundamentally cannot converge for porous materials ($\alpha_- = 0$) or rigid inclusions ($\alpha_+ = \infty$) because the convergence bound $\alpha_0 > \alpha_+^2/(2\alpha_-)$ cannot be satisfied. With trigonometric polynomial discretizations, the global nature of the basis functions causes boundary errors at pore-solid interfaces to propagate across the entire domain, leading to the average stress falsely converging to zero.


**Reference medium sensitivity:** Choosing $\mathbf{C}^0$ too soft corresponds to an excessively large gradient descent step size, causing global instability. Choosing it too stiff yields impractically slow convergence. The optimal choice (arithmetic mean of phase stiffnesses) requires knowledge of the extreme material constants, which may be difficult to estimate for nonlinear materials.


**One constitutive evaluation per iteration:** Every iteration requires a full evaluation of the nonlinear constitutive law across all voxels. For expensive material models (crystal plasticity, finite strain), this dominates the computational cost. Newton-Krylov methods amortize expensive constitutive evaluations by solving the linearized system to high accuracy within each Newton step.


**No improvement from mesh refinement:** While the iteration count is bounded independently of the mesh size (a positive feature for scalability), increasing resolution does not accelerate convergence. The convergence rate depends solely on the material contrast and reference medium choice.


## 5. References
- Schneider (2021) -- review of nonlinear FFT-based computational homogenization, basic scheme and gradient descent interpretation
- Lucarini et al. (2022) -- basic scheme formulation, convergence criteria, and reference medium selection

