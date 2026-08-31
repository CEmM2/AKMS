---
id: fft-galerkin-basics
title: Fourier-Galerkin Discretization
domain: fft-galerkin
subdomain: discretization
tags:
- fft-galerkin
- spectral
- discretization
- homogenization
- periodic-bc
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-lippmann-schwinger
  type: refines
  weight: 0.8
  note: Galerkin approach bypasses Lippmann-Schwinger by working directly from the weak form
- to: fft-freq-grid
  type: requires
  weight: 0.9
  note: Requires the discrete frequency grid Z_N and re-scaled frequency vectors
- to: fft-green-operator
  type: requires
  weight: 0.7
  note: Projection operator is mathematically equivalent to the continuous Green's operator derivative
- to: fft-discretization-moulinec-suquet
  type: refines
  weight: 0.8
  note: Galerkin uses projection operator P_N vs Moulinec-Suquet's interpolation operator Q_N
- to: fft-convergence-schemes
  type: feeds-into
  weight: 0.6
  note: Galerkin linear system is solved via conjugate gradient or other Krylov solvers
- to: fft-discretization-fem
  type: feeds-into
  weight: 0.7
  note: FEM-based FFT is an alternative discretization of the Galerkin framework
context_size: large
reading_priority: full
load_with:
- fft-freq-grid
- fft-discretization-moulinec-suquet
content_ref: null
akms_schema: v2
---

# Fourier-Galerkin Discretization

## Summary
The Fourier-Galerkin discretization derives directly from the weak formulation of mechanical equilibrium (the principle of virtual work) without reformulating the problem into a Lippmann-Schwinger integral equation and without introducing a fictitious reference medium. The approximation spaces for test and trial functions are spanned entirely by trigonometric polynomials, and a symmetric projection operator enforces field compatibility in Fourier space. The resulting Galerkin linear system is rank-deficient but symmetric positive-definite on compatible strain fields, making it well-suited for conjugate gradient solvers. A key theoretical advantage is that the method generates rigorous upper bounds on effective elastic properties. However, the approach suffers from Gibbs ringing at material interfaces, fails for porous materials, and requires expensive Fourier-space convolutions for the constitutive law, limiting it to linear materials without additional Newton linearization.


## 1. Core Concept
The Fourier-Galerkin discretization is a true Galerkin method for FFT-based computational homogenization where the continuous variational principle is evaluated exactly on a restricted subspace of global trigonometric polynomials. Unlike the Moulinec-Suquet collocation approach that interpolates fields at grid points via the operator $Q_N$, the Fourier-Galerkin method projects fields onto trigonometric polynomial space via an orthogonal projection operator $P_N$. This projection solves a regression problem that minimizes the $L^2$ error of the fields. Because the method works directly from the weak form of equilibrium, it does not require a fictitious reference medium $\mathbf{C}^0$, and the constitutive behavior must be projected into Fourier space, requiring explicit knowledge of the Fourier coefficients of the stiffness field. The exact integration over the trigonometric polynomial basis naturally generates a hierarchy of rigorous upper bounds (and, via dualization, lower bounds) on the effective elastic properties.


## 2. Mathematical Formulation
The Fourier-Galerkin discretization relies on a symmetric trigonometric projection operator $\hat{\mathbf{G}}^s$ derived from the curl-free component of the Helmholtz decomposition. This operator enforces compatibility of virtual strain fields in Fourier space. The discrete Galerkin linear system is obtained by applying this projection to the stress computed from the constitutive law. The total strain is decomposed as $\boldsymbol{\varepsilon}(\mathbf{x}) = \bar{\boldsymbol{\varepsilon}} + \tilde{\boldsymbol{\varepsilon}}(\mathbf{x})$ where $\bar{\boldsymbol{\varepsilon}}$ is the prescribed macroscopic strain and $\tilde{\boldsymbol{\varepsilon}}$ is the periodic fluctuation. The frequency grid is $Z_N = \{ \boldsymbol{\xi} \in \mathbb{Z}^d \mid -N_j/2 \le \xi_j < N_j/2 \}$ with re-scaled frequency vector $\boldsymbol{\xi}_Y = (2\pi\xi_1/L_1, \ldots, 2\pi\xi_d/L_d)$.


**Trigonometric projection operator (unsymmetrized):**

$$
\hat{G}_{ijkl}(\boldsymbol{\xi}) = \delta_{ik} \frac{\xi_j \xi_l}{\boldsymbol{\xi} \cdot \boldsymbol{\xi}}, \quad \boldsymbol{\xi} \neq \mathbf{0}
$$

where delta_ik is the Kronecker delta, xi are discrete frequency components

**Symmetrized projection operator:**

$$
\hat{G}^s_{ijkl} = \frac{1}{4}(\hat{G}_{ijkl} + \hat{G}_{jikl} + \hat{G}_{jilk} + \hat{G}_{ijlk})
$$

where Enforces minor symmetries of the strain tensor; set to zero at xi=0 and Nyquist frequencies

**Galerkin linear system:**

$$
\hat{\mathbf{G}}^s(\boldsymbol{\xi}) : \mathcal{F}\{\mathbf{C}(\mathbf{x}) : \tilde{\boldsymbol{\varepsilon}}(\mathbf{x})\}
= -\hat{\mathbf{G}}^s(\boldsymbol{\xi}) : \mathcal{F}\{\mathbf{C}(\mathbf{x}) : \bar{\boldsymbol{\varepsilon}}\}
$$

where C(x) is local stiffness, F denotes Fourier transform, eps_tilde is strain fluctuation, eps_bar is macroscopic strain

**Compact linear operator form:**

$$
A(\tilde{\boldsymbol{\varepsilon}}) = \mathbf{b}, \quad
A(\tilde{\boldsymbol{\varepsilon}}) = \mathcal{F}^{-1}\{ \hat{\mathbf{G}}^s : \mathcal{F}\{\mathbf{C} : \tilde{\boldsymbol{\varepsilon}}\} \}, \quad
\mathbf{b} = -\mathcal{F}^{-1}\{ \hat{\mathbf{G}}^s : \mathcal{F}\{\mathbf{C} : \bar{\boldsymbol{\varepsilon}}\} \}
$$

where A is symmetric positive-definite on compatible strain fields; solved via conjugate gradient

**Galerkin variational balance (nonlinear extension):**

$$
\text{div}\, \mathbf{P}_N \left[ \frac{\partial w}{\partial \boldsymbol{\varepsilon}}(\cdot, \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}_N) \right] = \mathbf{0}
$$

where P_N is the orthogonal trigonometric projection operator, w is local free energy density, u_N is the displacement fluctuation

**Linearized Newton system for nonlinear extension:**

$$
\mathcal{F}^{-1}\{ \hat{\mathbf{G}} : \mathcal{F}\{ K_i : \delta\mathbf{F} \} \}
= -\mathcal{F}^{-1}\{ \hat{\mathbf{G}} : \mathcal{F}\{ \mathbf{P}_i \} \}
$$

where K_i is the local consistent tangent at Newton iteration i, P_i is first Piola-Kirchhoff stress, delta F is the deformation gradient correction

**Notation:**

- $\hat{\mathbf{G}}^s$ — Symmetrized trigonometric projection operator in Fourier space
- $\hat{G}_{ijkl}$ — Components of the unsymmetrized projection operator
- $\boldsymbol{\xi}$ — Discrete frequency vector in Z_N
- $\boldsymbol{\xi}_Y$ — Re-scaled frequency vector accounting for cell dimensions
- $\bar{\boldsymbol{\varepsilon}}$ — Prescribed macroscopic strain
- $\tilde{\boldsymbol{\varepsilon}}$ — Periodic strain fluctuation field
- $\mathbf{C}(\mathbf{x})$ — Local stiffness tensor
- $\mathbf{P}_N$ — Orthogonal trigonometric projection operator truncating to Z_N
- $Q_N$ — Trigonometric interpolation (collocation) operator of Moulinec-Suquet
- $T_N$ — Space of trigonometric polynomials of order N
- $w$ — Local condensed free energy density
- $K_i$ — Local consistent tangent at Newton iteration i
- $Z_N$ — Discrete frequency set: {xi in Z^d | -N_j/2 <= xi_j < N_j/2}
- $Y_N$ — Discrete regular spatial grid
- $\mathcal{F}$ — Discrete Fourier Transform (DFT)


## 3. Algorithmic Implementation
**Algorithm: Algorithm**

$$
\begin{algorithmic}
\State $\text{Set up frequency grid } Z_N = \{ \boldsymbol{\xi} \in \mathbb{Z}^d \mid -N_j/2 \le \xi_j < N_j/2 \}$
\State $\text{Compute } \hat{G}^s_{ijkl}(\boldsymbol{\xi}) = \frac{1}{4}(\delta_{ik}\frac{\xi_j\xi_l}{\boldsymbol{\xi}\cdot\boldsymbol{\xi}} + \delta_{jk}\frac{\xi_i\xi_l}{\boldsymbol{\xi}\cdot\boldsymbol{\xi}} + \delta_{jl}\frac{\xi_i\xi_k}{\boldsymbol{\xi}\cdot\boldsymbol{\xi}} + \delta_{il}\frac{\xi_j\xi_k}{\boldsymbol{\xi}\cdot\boldsymbol{\xi}}) \text{ for } \boldsymbol{\xi} \neq \mathbf{0}$
\State $\hat{G}^s_{ijkl}(\mathbf{0}) = 0, \quad \hat{G}^s_{ijkl}(\boldsymbol{\xi}_{\text{Nyquist}}) = 0$
\State $\mathbf{b}(\mathbf{x}) \gets -\mathcal{F}^{-1}\{ \hat{\mathbf{G}}^s(\boldsymbol{\xi}) \colon \mathcal{F}\{\mathbf{C}(\mathbf{x}) \colon \bar{\boldsymbol{\varepsilon}}\} \}$
\State $\tilde{\boldsymbol{\varepsilon}}^{(0)}(\mathbf{x}) \gets \mathbf{0}, \quad \mathbf{r}^{(0)} \gets \mathbf{b} - A(\tilde{\boldsymbol{\varepsilon}}^{(0)}), \quad \mathbf{p}^{(0)} \gets \mathbf{r}^{(0)}$
\While{$$}
\State $\mathbf{q}^{(k)} \gets A(\mathbf{p}^{(k)}) = \mathcal{F}^{-1}\{ \hat{\mathbf{G}}^s \colon \mathcal{F}\{\mathbf{C} \colon \mathbf{p}^{(k)}\} \}$
\State $\alpha_k \gets \frac{\mathbf{r}^{(k)} \cdot \mathbf{r}^{(k)}}{\mathbf{p}^{(k)} \cdot \mathbf{q}^{(k)}}$
\State $\tilde{\boldsymbol{\varepsilon}}^{(k+1)} \gets \tilde{\boldsymbol{\varepsilon}}^{(k)} + \alpha_k \mathbf{p}^{(k)}$
\State $\mathbf{r}^{(k+1)} \gets \mathbf{r}^{(k)} - \alpha_k \mathbf{q}^{(k)}$
\State $\beta_k \gets \frac{\mathbf{r}^{(k+1)} \cdot \mathbf{r}^{(k+1)}}{\mathbf{r}^{(k)} \cdot \mathbf{r}^{(k)}}$
\State $\mathbf{p}^{(k+1)} \gets \mathbf{r}^{(k+1)} + \beta_k \mathbf{p}^{(k)}$
\EndWhile
\State $\boldsymbol{\varepsilon}(\mathbf{x}) \gets \bar{\boldsymbol{\varepsilon}} + \tilde{\boldsymbol{\varepsilon}}^{(\text{converged})}(\mathbf{x})$
\end{algorithmic}
$$


## 4. Known Pitfalls
**Gibbs phenomenon at material interfaces:** The Fourier-Galerkin method evaluates the variational principle on global trigonometric polynomials, which causes high-frequency ringing artifacts (Gibbs phenomenon) near sharp material interfaces and non-smooth boundaries. These oscillations reduce the accuracy of local microscopic fields even though macroscopic effective properties remain accurate.


**Failure for porous materials with infinite contrast:** The method fails for materials with infinite phase contrast (e.g., porous foams with voids). Trigonometric polynomials are global functions, so any small numerical error at a solid-pore interface propagates throughout the entire domain. The scheme cannot prescribe the required boundary values at pore surfaces, causing complete solver destabilization.


**Expensive Fourier-space constitutive law evaluation:** The Fourier-Galerkin approach must project the local constitutive behavior into Fourier space via spatial convolution of Fourier coefficients, requiring explicit knowledge of the stiffness field's Fourier coefficients. This is computationally expensive and fundamentally limits the method to linear elastic constitutive laws without additional Newton linearization.


**Symmetry loss at Nyquist on even grids:** When the grid has an even number of voxels per dimension, the strict symmetries of the projection operator $\hat{\mathbf{G}}^s$ are lost at the Nyquist frequencies. The operator must be explicitly set to zero at these frequencies to recover real-valued fields, introducing an approximation that affects accuracy.


**No reference medium required but CG convergence depends on contrast:** While the Galerkin formulation avoids the reference medium $\mathbf{C}^0$ of the basic scheme, the conjugate gradient solver's convergence rate still depends on the condition number of the linear operator $A$, which is governed by the stiffness contrast between phases. High contrast materials require preconditioning for practical efficiency.


## 5. References
- Schneider (2021) — Fourier-Galerkin discretization approach for FFT homogenization
- Vondrejc, Zeman, Marek — Galerkin method with trigonometric projection and CG solver
- Brisard, Dormieux — Hashin-Shtrikman variational principles and Galerkin bounds

