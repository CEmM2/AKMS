---
id: fft-green-operator
title: Green's Operator (Γ⁰) in Fourier Space
domain: fft-galerkin
subdomain: spectral-operators
tags:
- green-operator
- fft-galerkin
- spectral
- lippmann-schwinger
- homogenization
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: Green's operator is the kernel of the Lippmann-Schwinger equation
- to: fft-reference-medium
  type: requires
  weight: 0.9
  note: Operator depends on the reference medium stiffness C0
- to: fft-freq-grid
  type: requires
  weight: 0.8
  note: Operator evaluation requires proper frequency grid with Nyquist treatment
- to: fft-galerkin-basics
  type: feeds-into
  weight: 0.7
  note: Galerkin discretization modifies the Green's operator
context_size: medium
reading_priority: full
load_with:
- fft-lippmann-schwinger
- fft-freq-grid
content_ref: null
akms_schema: v2
---

# Green's Operator (Γ⁰) in Fourier Space

## Summary
The Green's operator $\boldsymbol{\Gamma}^0$ (also called the Eshelby-Green operator) maps a stress-type polarization field to a strain fluctuation field in the Lippmann-Schwinger equation. In real space it acts as a singular convolution integral; in Fourier space it reduces to a closed-form algebraic expression involving the frequency vector and reference medium parameters. This Fourier-space form is what makes FFT-based homogenization computationally efficient. Key implementation concerns include the singularity at zero frequency, loss of symmetry at the Nyquist frequency for even grids, and the choice between continuous and discrete operator variants.


## 1. Core Concept
The Green's operator $\boldsymbol{\Gamma}^0$ is a fourth-order tensor-valued operator that relates the stress polarization field to the resulting strain fluctuation within a homogeneous reference medium. In real space, it acts via convolution with a singular integral kernel $\mathbf{K}^0$. The key advantage for FFT methods is that in Fourier space, this convolution becomes a pointwise algebraic product with an explicit closed-form formula depending only on the reference medium parameters and the frequency vector. For an isotropic reference medium $\mathbf{C}_0 = 2\mu_0 \mathbf{Id}$, the Fourier-space operator can be written in terms of the re-scaled frequency vector and the shear modulus $\mu_0$.


## 2. Mathematical Formulation
The Green's operator has a real-space form as a convolution integral and a Fourier-space form as an algebraic expression. The Fourier-space form is the one used in practice because it avoids evaluating the singular integral directly. The operator vanishes at zero frequency (corresponding to the macroscopic average), and its evaluation at the Nyquist frequency requires special treatment on even grids to preserve symmetry.


**Real-space form (convolution integral):**

$$
(\boldsymbol{\Gamma}^0 : \boldsymbol{\tau})(\mathbf{x}) = \int_Y \mathbf{K}^0(\mathbf{x} - \mathbf{y}) : \boldsymbol{\tau}(\mathbf{y}) \, d\mathbf{y}
$$

where K0 is the singular integral kernel, Y is the periodic cell, x-y is understood Y-periodically

**Fourier-space form (isotropic reference C0 = 2mu0 Id):**

$$
(\hat{\boldsymbol{\Gamma}}^0 : \boldsymbol{\tau})(\boldsymbol{\xi}) = \frac{1}{\mu_0} \left[ \frac{\boldsymbol{\xi}_Y \otimes^s (\hat{\boldsymbol{\tau}}(\boldsymbol{\xi})\boldsymbol{\xi}_Y)}{\|\boldsymbol{\xi}_Y\|^2} - \frac{\boldsymbol{\xi}_Y \cdot (\hat{\boldsymbol{\tau}}(\boldsymbol{\xi})\boldsymbol{\xi}_Y)}{2\|\boldsymbol{\xi}_Y\|^4} \boldsymbol{\xi}_Y \otimes \boldsymbol{\xi}_Y \right]
$$

where Valid for xi != 0. xi_Y is the re-scaled frequency vector, mu0 is the reference shear modulus

**Re-scaled frequency vector:**

$$
\boldsymbol{\xi}_Y = \left(\frac{2\pi\xi_1}{L_1}, \frac{2\pi\xi_2}{L_2}, \ldots, \frac{2\pi\xi_d}{L_d}\right)
$$

where xi_i are integer frequency indices, L_i are the cell dimensions in each direction

**Zero-frequency condition:**

$$
(\hat{\boldsymbol{\Gamma}}^0 : \boldsymbol{\tau})(\mathbf{0}) = 0
$$

where The operator vanishes at xi=0 — macroscopic strain is prescribed, not computed

**Notation:**

- $\boldsymbol{\Gamma}^0$ — Green's operator (Eshelby-Green operator) of the reference medium
- $\hat{\boldsymbol{\Gamma}}^0$ — Green's operator in Fourier space
- $\mathbf{K}^0$ — Singular integral kernel in real space
- $\boldsymbol{\tau}$ — Stress polarization field
- $\boldsymbol{\xi}$ — Integer frequency vector
- $\boldsymbol{\xi}_Y$ — Re-scaled frequency vector accounting for cell dimensions
- $\mu_0$ — Shear modulus of the isotropic reference medium
- $\otimes^s$ — Symmetrized tensor product
- $Y$ — Periodic computational cell with dimensions L1 x L2 x ... x Ld


## 3. Algorithmic Implementation
Not applicable — the Green's operator is a mathematical object, not an algorithm. Its evaluation is embedded within the solver iteration loops (see fft-solver-basic-scheme and related nodes).

## 4. Known Pitfalls
**Singularity at zero frequency:** The Green's operator formula requires dividing by $\|\boldsymbol{\xi}_Y\|^2$, which is undefined at $\boldsymbol{\xi} = \mathbf{0}$. This must be handled explicitly by setting $\hat{\boldsymbol{\Gamma}}^0(\mathbf{0}) = 0$. In displacement-based formulations (DBFFT), the zero-frequency terms must be removed from the linear system entirely.


**Symmetry loss at Nyquist frequency:** On grids with even number of discrete frequencies, the tensor symmetries of the Fourier projection operator are lost at the Nyquist frequency. Common fixes: set the operator to zero at Nyquist, or explicitly redefine it to recover symmetry. Failure to handle this produces complex-valued (non-physical) mechanical fields.


**Continuous vs discrete operator tradeoffs:** The continuous operator uses exact frequency vectors but suffers from Gibbs phenomena at interfaces and fails for porous materials. Discrete operators (finite difference stencils) replace $\boldsymbol{\xi}$ with modified trigonometric frequency multipliers, which suppress Gibbs but can introduce checkerboarding (Willot's scheme) or oscillations (central differences). Neither choice is universally superior.


**Consistent operator pre-computation cost:** Variational approaches (Hashin-Shtrikman by Brisard-Dormieux) require an energetically consistent discrete Green's operator whose Fourier coefficients converge slowly in 3D. This operator cannot be computed on-the-fly and must be pre-computed and stored, adding substantial memory overhead.


**Global error propagation in porous media:** The continuous Green's operator with trigonometric polynomial basis attempts elastic extension into void space. Since trigonometric polynomials are global functions, any boundary error at the solid-pore interface propagates throughout the entire domain, producing completely unphysical results.


## 5. References
- Schneider (2021) — Fourier-space and real-space Green's operator definitions
- Lucarini et al. (2022) — Green's function in Lippmann-Schwinger context

