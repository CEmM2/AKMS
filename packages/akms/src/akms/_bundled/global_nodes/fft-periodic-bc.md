---
id: fft-periodic-bc
title: Periodic Boundary Conditions for FFT
domain: fft-galerkin
subdomain: boundary-conditions
tags:
- periodic-bc
- boundary-conditions
- fft-galerkin
- homogenization
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
  note: Periodic BCs are the defining boundary conditions for the homogenization cell problem
- to: fft-lippmann-schwinger
  type: feeds-into
  weight: 1.0
  note: Periodicity enables reformulation as Lippmann-Schwinger integral equation solvable via FFT
- to: fft-galerkin-basics
  type: feeds-into
  weight: 0.9
  note: Periodic fields are represented as Fourier series in the Galerkin discretization
- to: fft-freq-grid
  type: feeds-into
  weight: 0.8
  note: Periodicity of the domain maps directly to the discrete frequency grid
- to: fft-mixed-bc
  type: feeds-into
  weight: 0.8
  note: Mixed and non-periodic BCs are extensions beyond the standard periodic assumption
context_size: medium
reading_priority: full
load_with:
- homogenization-cell-problem
- fft-lippmann-schwinger
content_ref: null
akms_schema: v2
---

# Periodic Boundary Conditions for FFT

## Summary
Periodic boundary conditions are the foundational assumption enabling FFT-based computational homogenization. The representative volume element (RVE) is treated as a periodic cell, requiring that the microscopic strain field is periodic across opposite faces, the traction vector is anti-periodic (ensuring equilibrium between adjacent cells), and the volume average of the local strain equals the prescribed macroscopic strain. This periodicity naturally aligns with the discrete Fourier transform: local fields decompose into Fourier series, and differential operators become algebraic multiplications in frequency space, yielding O(N log N) computational cost. Empirically, periodic BCs produce homogenized results with smaller bias than Dirichlet or Neumann conditions.


## 1. Core Concept
In FFT-based computational homogenization, the rectangular domain $\Omega$ representing the microstructure is assumed to tile space periodically. This periodic cell assumption has three consequences: (1) it enables representation of all fields as Fourier series, converting spatial convolutions into frequency-space products for efficient O(N log N) evaluation; (2) it allows the Lippmann-Schwinger integral equation reformulation that underpins all FFT solvers; and (3) it produces the smallest statistical bias in effective properties compared to Dirichlet or Neumann boundary conditions for finite-size RVEs. The local strain field is decomposed as $\boldsymbol{\varepsilon}(\mathbf{x}) = \bar{\boldsymbol{\varepsilon}} + \tilde{\boldsymbol{\varepsilon}}(\mathbf{x})$, where $\bar{\boldsymbol{\varepsilon}}$ is the prescribed macroscopic strain and $\tilde{\boldsymbol{\varepsilon}}$ is the periodic fluctuation with zero spatial average. For finite strain formulations in a total Lagrangian framework, the periodicity condition applies to the deformation gradient field $\mathbf{F}(\mathbf{X})$ and anti-periodicity to the first Piola-Kirchhoff stress traction $\tilde{\mathbf{P}}(\mathbf{X}) \cdot \mathbf{N}$.


## 2. Mathematical Formulation
The periodic cell problem seeks local strain $\boldsymbol{\varepsilon}(\mathbf{x})$ and stress $\boldsymbol{\sigma}(\mathbf{x})$ fields satisfying equilibrium, compatibility, the constitutive law, and three boundary constraints that enforce periodicity, anti-periodicity of tractions, and volume averaging.


**Volume averaging constraint:**

$$
\langle \boldsymbol{\varepsilon}(\mathbf{x}) \rangle_\Omega = \bar{\boldsymbol{\varepsilon}}
$$

where angle brackets denote spatial average over the periodic domain Omega, epsilon-bar is the prescribed macroscopic strain

**Strain decomposition into mean and fluctuation:**

$$
\boldsymbol{\varepsilon}(\mathbf{x}) = \bar{\boldsymbol{\varepsilon}} + \tilde{\boldsymbol{\varepsilon}}(\mathbf{x}), \quad \langle \tilde{\boldsymbol{\varepsilon}}(\mathbf{x}) \rangle_\Omega = 0
$$

where epsilon-tilde is the periodic strain fluctuation with zero spatial average

**Periodicity of strain:**

$$
\boldsymbol{\varepsilon}(\mathbf{x}) \quad \text{periodic on } \partial\Omega
$$

where strain values on opposite faces of the RVE are identical

**Anti-periodicity of traction:**

$$
\boldsymbol{\sigma}(\mathbf{x}) \cdot \mathbf{n}(\mathbf{x}) \quad \text{anti-periodic on } \partial\Omega
$$

where n(x) is the outward unit normal; traction is equal and opposite on opposing faces, ensuring equilibrium between adjacent cells

**Equilibrium (divergence-free stress):**

$$
\nabla \cdot \boldsymbol{\sigma}(\mathbf{x}) = 0 \quad \text{in } \Omega
$$

where Cauchy stress satisfies balance of linear momentum with zero body forces

**Finite strain periodicity (total Lagrangian):**

$$
\mathbf{F}(\mathbf{X}) \text{ periodic}, \quad \tilde{\mathbf{P}}(\mathbf{X}) \cdot \mathbf{N} \text{ anti-periodic}
$$

where F is the deformation gradient, P-tilde is the first Piola-Kirchhoff stress fluctuation, N is the reference normal

**Notation:**

- $\boldsymbol{\varepsilon}$ — Infinitesimal strain tensor
- $\bar{\boldsymbol{\varepsilon}}$ — Prescribed macroscopic strain
- $\tilde{\boldsymbol{\varepsilon}}$ — Periodic strain fluctuation (zero mean)
- $\boldsymbol{\sigma}$ — Cauchy stress tensor
- $\mathbf{n}$ — Outward unit normal on domain boundary
- $\Omega$ — Periodic computational domain (RVE)
- $\mathbf{F}$ — Deformation gradient tensor (finite strain)
- $\mathbf{P}$ — First Piola-Kirchhoff stress tensor


## 3. Algorithmic Implementation
Not applicable — this is a foundational concept node defining the periodic boundary conditions and their mathematical structure, not an algorithmic procedure.

## 4. Known Pitfalls
**Gibbs phenomenon at material interfaces:** Global trigonometric polynomials used by FFT cannot accurately represent the discontinuous fields at sharp material interfaces, producing spurious high-frequency oscillations (ringing artifacts). This is especially severe for high-contrast materials and higher-order spatial derivatives (e.g., strain gradient plasticity). Discrete finite-difference differentiation rules (central differences, rotated staggered grids) can mitigate these artifacts.


**Inapplicability to non-periodic microstructures:** Standard FFT algorithms strictly require periodic domains and cannot naturally handle finite-sized geometries or general non-periodic boundary conditions such as traction-free surfaces. Workarounds include the Fourier Continuation (FC) method, which constructs smooth periodic extensions by appending artificial points at domain boundaries, and Bloch boundary conditions for problems with long-wavelength periodic fluctuations across multiple unit cells.


**Failure for infinite contrast (porous/rigid):** The basic continuous FFT scheme requires a continuous elastic extension into void or rigid regions via global trigonometric polynomials. Because these polynomials cannot prescribe exact boundary values at solid-pore interfaces, small numerical errors propagate globally, causing the average stress to falsely converge to zero. Finite-difference discretizations (e.g., Willot's rotated staggered grid) can resolve pore boundaries but may introduce hourglass instabilities.


**Statistical bias from insufficient RVE size:** Even with periodic BCs producing less bias than Dirichlet or Neumann conditions, the RVE must be sufficiently large relative to the microstructural correlation length. Undersized RVEs yield unreliable effective properties dominated by statistical randomness. There is no universal formula for minimum RVE size — it depends on contrast ratio, volume fraction, and the property of interest.


## 5. References
- Schneider (2021) — Review of nonlinear FFT-based computational homogenization, periodic boundary conditions and cell problem formulation
- Lucarini et al. (2022) — FFT-based approaches review, periodic BCs and finite strain extensions

