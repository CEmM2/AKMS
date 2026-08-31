---
id: fft-lippmann-schwinger
title: Lippmann-Schwinger Equation
domain: fft-galerkin
subdomain: spectral-operators
tags:
- lippmann-schwinger
- fft-galerkin
- homogenization
- green-operator
- spectral
- micromechanics
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: homogenization-cell-problem
  type: requires
  weight: 1.0
  note: L-S equation reformulates the periodic cell problem
- to: fft-green-operator
  type: requires
  weight: 1.0
  note: L-S equation uses the Green's operator as its kernel
- to: fft-reference-medium
  type: requires
  weight: 0.9
  note: Polarization field depends on reference medium choice
- to: fft-solver-basic-scheme
  type: feeds-into
  weight: 1.0
  note: Basic scheme is the fixed-point iteration on L-S equation
- to: fft-galerkin-basics
  type: feeds-into
  weight: 0.8
  note: Galerkin approach provides alternative derivation
- to: fft-coupled-problems
  type: feeds-into
  weight: 0.7
  note: Lippmann-Schwinger equation extends to multi-physics coupled problems
context_size: medium
reading_priority: full
load_with:
- fft-green-operator
- fft-reference-medium
content_ref: null
akms_schema: v2
---

# Lippmann-Schwinger Equation

## Summary
The Lippmann-Schwinger equation is the integral equation reformulation of the periodic cell problem that underpins all FFT-based homogenization methods. It replaces the heterogeneous PDE with an implicit equation involving a stress polarization field convolved with the Green's operator of a homogeneous reference medium. In Fourier space, the convolution becomes a pointwise product, enabling O(N log N) solution via FFT. The equation is the starting point for the basic scheme, polarization methods, and Krylov solvers. Its convergence depends critically on reference medium selection and phase contrast ratio.


## 1. Core Concept
The Lippmann-Schwinger equation is derived by replacing the heterogeneous microstructure with a homogeneous linear elastic reference medium characterized by stiffness $\mathbf{C}^0$. The difference between the actual local stiffness and the reference stiffness creates a stress polarization field $\boldsymbol{\tau}$. The local strain fluctuations induced by these heterogeneities are expressed as a convolution of the polarization with the Green's operator $\boldsymbol{\Gamma}^0$ of the reference medium. Because the Green's operator has a closed-form expression in Fourier space, the convolution becomes a simple product, making the equation tractable via FFT. The equation is implicit because the polarization depends on the unknown strain field, requiring iterative solution.


## 2. Mathematical Formulation
The strain field is decomposed into a macroscopic average $\bar{\boldsymbol{\varepsilon}}$ and a periodic fluctuation $\tilde{\boldsymbol{\varepsilon}}$ with zero mean. A reference medium with stiffness $\mathbf{C}^0$ is introduced, and the stress polarization $\boldsymbol{\tau} = (\mathbf{C}(\mathbf{x}) - \mathbf{C}^0) \colon \boldsymbol{\varepsilon}(\mathbf{x})$ captures the heterogeneity. The Lippmann-Schwinger equation expresses the strain field as the macroscopic strain minus the convolution of the Green's operator with the polarization. In Fourier space, this convolution becomes a pointwise product, which is the key to FFT efficiency.


**Strain decomposition:**

$$
\boldsymbol{\varepsilon}(\mathbf{x}) = \bar{\boldsymbol{\varepsilon}} + \tilde{\boldsymbol{\varepsilon}}(\mathbf{x}), \quad \langle \tilde{\boldsymbol{\varepsilon}} \rangle_\Omega = 0
$$

where epsilon-bar is the prescribed macroscopic strain, epsilon-tilde is the zero-mean periodic fluctuation

**Stress polarization:**

$$
\boldsymbol{\tau}(\mathbf{x}) = [\mathbf{C}(\mathbf{x}) - \mathbf{C}^0] : \boldsymbol{\varepsilon}(\mathbf{x})
$$

where C(x) is the local stiffness tensor, C0 is the reference medium stiffness

**Lippmann-Schwinger equation (real space):**

$$
\boldsymbol{\varepsilon}(\mathbf{x}) = \bar{\boldsymbol{\varepsilon}} - (\boldsymbol{\Gamma}^0 * \boldsymbol{\tau})(\mathbf{x})
$$

where Gamma-0 is the Green's operator of the reference medium, * denotes spatial convolution

**Strain fluctuation form:**

$$
\tilde{\boldsymbol{\varepsilon}}(\mathbf{x}) = -(\boldsymbol{\Gamma}^0 * \boldsymbol{\tau}(\tilde{\boldsymbol{\varepsilon}}))(\mathbf{x})
$$

where The fluctuation form emphasizes the implicit nature — tau depends on epsilon-tilde

**Lippmann-Schwinger equation (Fourier space):**

$$
\hat{\boldsymbol{\varepsilon}}(\boldsymbol{\xi}) = \bar{\boldsymbol{\varepsilon}} \delta_{\boldsymbol{\xi},\mathbf{0}} - \hat{\boldsymbol{\Gamma}}^0(\boldsymbol{\xi}) : \hat{\boldsymbol{\tau}}(\boldsymbol{\xi})
$$

where xi is the frequency vector, hat denotes Fourier coefficients, delta is the Kronecker delta

**Notation:**

- $\boldsymbol{\varepsilon}$ — Local strain tensor
- $\bar{\boldsymbol{\varepsilon}}$ — Prescribed macroscopic strain
- $\tilde{\boldsymbol{\varepsilon}}$ — Periodic strain fluctuation (zero mean)
- $\boldsymbol{\tau}$ — Stress polarization tensor
- $\mathbf{C}$ — Local fourth-order stiffness tensor
- $\mathbf{C}^0$ — Reference medium stiffness tensor
- $\boldsymbol{\Gamma}^0$ — Green's operator of the reference medium
- $\hat{\boldsymbol{\Gamma}}^0$ — Green's operator in Fourier space
- $\boldsymbol{\xi}$ — Frequency vector in Fourier space


## 3. Algorithmic Implementation
Not applicable — the Lippmann-Schwinger equation defines the integral equation formulation. Iterative solution algorithms are covered in the solver nodes (fft-solver-basic-scheme, etc.).

## 4. Known Pitfalls
**Reference medium sensitivity:** The choice of $\mathbf{C}^0$ dictates convergence. If too soft, the fixed-point iteration diverges (overly large step size). If too stiff, convergence is extremely slow. The optimal choice for the basic scheme is the arithmetic mean of extreme phase stiffnesses; for polarization schemes it is the geometric mean.


**Linear scaling with contrast:** For the basic scheme, the number of iterations scales linearly with the phase contrast ratio $\kappa = \alpha_+ / \alpha_-$. For high-contrast composites (e.g., metal matrix with ceramic reinforcement), this makes the basic scheme impractically slow. Krylov and polarization methods improve to $\sqrt{\kappa}$ scaling.


**Failure at infinite contrast:** The continuous L-S formulation fails for porous materials (voids) or rigid inclusions. Trigonometric polynomials attempt continuous elastic extension into pore space; since they are global, boundary errors propagate throughout the domain. Average stress may falsely converge to zero in porous foams.


**Non-symmetry of the operator:** The continuous Lippmann-Schwinger operator is not symmetric over the general space of square-integrable fields — it is only symmetric and positive definite on the subspace of compatible strain fields. This historically complicated direct application of conjugate gradient solvers.


**Gibbs phenomenon at interfaces:** Standard Fourier discretization of the L-S equation produces ringing artifacts near sharp material interfaces due to Fourier series truncation. Alternative finite difference discretizations trade Gibbs for checkerboarding or oscillatory artifacts.


## 5. References
- Schneider (2021) — §2.1: Lippmann-Schwinger formulation
- Lucarini et al. (2022) — §3.2: Lippmann-Schwinger approaches for elasticity

