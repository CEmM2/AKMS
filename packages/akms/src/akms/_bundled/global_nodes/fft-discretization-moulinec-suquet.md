---
id: fft-discretization-moulinec-suquet
title: Moulinec-Suquet Discretization (Original)
domain: fft-galerkin
subdomain: discretization
tags:
- fft-galerkin
- spectral
- discretization
- homogenization
- green-operator
- periodic-bc
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: Discretizes the Lippmann-Schwinger equation via trigonometric collocation
- to: fft-green-operator
  type: requires
  weight: 1.0
  note: Uses the continuous Eshelby-Green operator evaluated at discrete frequencies
- to: fft-reference-medium
  type: requires
  weight: 0.9
  note: Requires a homogeneous reference medium C0 for the Lippmann-Schwinger formulation
- to: fft-freq-grid
  type: requires
  weight: 0.9
  note: Operates on the discrete frequency grid Z_N with Nyquist treatment
- to: fft-solver-basic-scheme
  type: feeds-into
  weight: 1.0
  note: The basic scheme fixed-point iteration is the canonical solver for this discretization
- to: fft-galerkin-basics
  type: feeds-into
  weight: 0.7
  note: Galerkin discretization refines Moulinec-Suquet by replacing collocation with projection
- to: fft-discretization-willot
  type: feeds-into
  weight: 0.6
  note: Willot's scheme was developed as a finite-difference alternative to this spectral approach
- to: fft-composite-voxels
  type: feeds-into
  weight: 0.7
  note: Composite voxels improve interface resolution of the standard voxelized discretization
context_size: large
reading_priority: full
load_with:
- fft-lippmann-schwinger
- fft-green-operator
- fft-solver-basic-scheme
content_ref: null
akms_schema: v2
---

# Moulinec-Suquet Discretization (Original)

## Summary
The Moulinec-Suquet discretization (1994) is the original FFT-based computational homogenization scheme for periodic microstructures. It discretizes the Lippmann-Schwinger integral equation on a regular voxel grid by introducing a homogeneous reference medium and solving via fixed-point (Picard) iteration. The method can be interpreted either as trigonometric collocation (the DFT interpolates discrete field values as global trigonometric polynomials via operator $Q_N$) or equivalently as a non-conforming Galerkin approximation where spatial integrals are evaluated with the trapezoidal quadrature rule. The continuous Eshelby-Green operator is used directly at the discrete frequencies, and the constitutive law is evaluated locally at voxel centers. The scheme suffers from Gibbs ringing at sharp interfaces, convergence degradation with increasing phase contrast, and outright failure for porous materials with infinite contrast.


## 1. Core Concept
The Moulinec-Suquet method transforms the governing PDEs of a heterogeneous elastic medium into a periodic Lippmann-Schwinger integral equation by introducing a homogeneous reference medium $\mathbf{C}^0$. The local strain fluctuations caused by material heterogeneities are treated as an eigenstrain (stress polarization) field $\boldsymbol{\tau} = \boldsymbol{\sigma}(\boldsymbol{\varepsilon}) - \mathbf{C}^0 : \boldsymbol{\varepsilon}$ within this reference medium. The continuous fields are discretized on a regular voxel grid, and the DFT finds the unique trigonometric polynomial that interpolates discrete values at voxel centers. This is a trigonometric collocation approach: the continuous balance of linear momentum is solved exactly, but the constitutive law is approximated via trigonometric interpolation at the grid points. Equivalently, the scheme can be derived from the continuous variational principle of minimum potential energy with the trapezoidal quadrature rule replacing exact spatial integration. A crucial feature is that the method uses the exact continuous Green's operator $\hat{\boldsymbol{\Gamma}}^0$ evaluated at discrete frequencies, not a modified discrete operator.


## 2. Mathematical Formulation
The Moulinec-Suquet discretization operates on a regular grid $Y_N$ with corresponding frequency set $Z_N$. The strain field is decomposed as $\boldsymbol{\varepsilon}(\mathbf{x}) = \bar{\boldsymbol{\varepsilon}} + \tilde{\boldsymbol{\varepsilon}}(\mathbf{x})$ with $\bar{\boldsymbol{\varepsilon}}$ the prescribed macroscopic strain. The stress polarization captures the deviation from the reference medium response. The continuous Green's operator maps this polarization to strain fluctuations in Fourier space, vanishing at zero frequency (macroscopic strain is prescribed) and requiring special treatment at Nyquist frequencies on even grids. The trigonometric collocation operator $Q_N$ interpolates grid-point values as global trigonometric polynomials.


**Discretized Lippmann-Schwinger equation (collocation form):**

$$
\boldsymbol{\varepsilon}_{k+1} = \bar{\boldsymbol{\varepsilon}} - \boldsymbol{\Gamma}^0 : Q_N \left[ \frac{\partial w}{\partial \boldsymbol{\varepsilon}}(\cdot, \boldsymbol{\varepsilon}_k) - \mathbf{C}^0 : \boldsymbol{\varepsilon}_k \right]
$$

where Gamma0 is the continuous Green's operator, Q_N is the trigonometric interpolation operator, w is the free energy density, C0 is the reference medium stiffness, eps_bar is macroscopic strain

**Stress polarization (linear elasticity):**

$$
\boldsymbol{\tau}^k(\mathbf{x}_I) = [\mathbf{C}(\mathbf{x}_I) - \mathbf{C}^0] : \boldsymbol{\varepsilon}^k(\mathbf{x}_I), \quad \mathbf{x}_I \in Y_N
$$

where C(x_I) is local stiffness at grid point x_I, C0 is reference medium, eps^k is strain at iteration k

**Fourier-space strain update (non-zero frequencies):**

$$
\hat{\boldsymbol{\varepsilon}}^{k+1}(\boldsymbol{\xi}) = -\hat{\boldsymbol{\Gamma}}^0(\boldsymbol{\xi}) : \hat{\boldsymbol{\tau}}^k(\boldsymbol{\xi}), \quad \boldsymbol{\xi} \in Z_N \setminus \{\mathbf{0}\}
$$

where hat denotes Fourier transform; at xi=0 the macroscopic strain is enforced: hat{eps}(0) = eps_bar

**Continuous Green's operator for isotropic reference (C0 = 2 mu0 Id):**

$$
(\hat{\boldsymbol{\Gamma}}^0 : \hat{\boldsymbol{\tau}})(\boldsymbol{\xi}) = \frac{1}{\mu_0} \left[ \frac{\boldsymbol{\xi}_Y \otimes^s (\hat{\boldsymbol{\tau}} \boldsymbol{\xi}_Y)}{\|\boldsymbol{\xi}_Y\|^2} - \frac{\boldsymbol{\xi}_Y \cdot (\hat{\boldsymbol{\tau}} \boldsymbol{\xi}_Y)}{2\|\boldsymbol{\xi}_Y\|^4} \boldsymbol{\xi}_Y \otimes \boldsymbol{\xi}_Y \right]
$$

where xi_Y = (2 pi xi_1/L_1, ..., 2 pi xi_d/L_d) is the re-scaled frequency vector, mu_0 is reference shear modulus

**Trapezoidal quadrature variational form:**

$$
\sum_{\mathbf{x}_I \in Y_N} w(\mathbf{x}_I, \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}_N(\mathbf{x}_I)) \longrightarrow \min_{\mathbf{u}_N \in T_N}
$$

where w is local free energy, u_N is displacement fluctuation in trigonometric polynomial space T_N

**Convergence criterion (equilibrium residual in Fourier space):**

$$
\frac{\sqrt{\sum_{\boldsymbol{\xi}} \| \boldsymbol{\xi} \cdot \hat{\boldsymbol{\sigma}}^k(\boldsymbol{\xi}) \|^2}}{\| \hat{\boldsymbol{\sigma}}^k(\mathbf{0}) \|} < \text{tol}
$$

where hat{sigma}^k(0) is the macroscopic (mean) stress, the numerator measures the L2 norm of stress divergence via Parseval's theorem

**Notation:**

- $\boldsymbol{\Gamma}^0$ — Continuous Eshelby-Green operator of the reference medium
- $\hat{\boldsymbol{\Gamma}}^0$ — Fourier-space form of the Green's operator
- $Q_N$ — Trigonometric interpolation (collocation) operator mapping grid values to global trigonometric polynomials
- $\mathbf{C}^0$ — Stiffness of the homogeneous reference medium
- $\mathbf{C}(\mathbf{x})$ — Local heterogeneous stiffness tensor
- $\boldsymbol{\tau}$ — Stress polarization field (difference between true stress and reference stress)
- $\bar{\boldsymbol{\varepsilon}}$ — Prescribed macroscopic strain
- $\tilde{\boldsymbol{\varepsilon}}$ — Periodic strain fluctuation
- $\boldsymbol{\xi}_Y$ — Re-scaled frequency vector: (2 pi xi_j / L_j)
- $\mu_0$ — Shear modulus of the isotropic reference medium
- $\otimes^s$ — Symmetrized tensor product
- $w$ — Local condensed free energy density
- $T_N$ — Space of trigonometric polynomials of order N
- $Y_N$ — Discrete regular spatial grid of voxel centers
- $Z_N$ — Discrete frequency set: {xi in Z^d | -N_j/2 <= xi_j < N_j/2}


## 3. Algorithmic Implementation
**Algorithm: Algorithm**

$$
\begin{algorithmic}
\State $\boldsymbol{\varepsilon}^0(\mathbf{x}) \gets \bar{\boldsymbol{\varepsilon}} \quad \text{(initialize strain to macroscopic strain at all grid points)}$
\For{$$}
\State $\boldsymbol{\tau}^k(\mathbf{x}_I) \gets [\mathbf{C}(\mathbf{x}_I) - \mathbf{C}^0] \colon \boldsymbol{\varepsilon}^k(\mathbf{x}_I) \quad \text{for all } \mathbf{x}_I \in Y_N$
\State $\hat{\boldsymbol{\tau}}^k(\boldsymbol{\xi}) \gets \mathcal{F}\{\boldsymbol{\tau}^k(\mathbf{x})\}$
\State $\hat{\tilde{\boldsymbol{\varepsilon}}}^{k+1}(\boldsymbol{\xi}) \gets -\hat{\boldsymbol{\Gamma}}^0(\boldsymbol{\xi}) \colon \hat{\boldsymbol{\tau}}^k(\boldsymbol{\xi}) \quad \text{for } \boldsymbol{\xi} \in Z_N \setminus \{\mathbf{0}\}$
\State $\hat{\boldsymbol{\varepsilon}}^{k+1}(\mathbf{0}) \gets \bar{\boldsymbol{\varepsilon}}$
\State $\hat{\boldsymbol{\varepsilon}}^{k+1}(\boldsymbol{\xi}_{\text{Nyq}}) \gets \mathbf{0} \quad \text{(force Nyquist frequencies to zero)}$
\State $\boldsymbol{\varepsilon}^{k+1}(\mathbf{x}) \gets \mathcal{F}^{-1}\{\hat{\boldsymbol{\varepsilon}}^{k+1}(\boldsymbol{\xi})\}$
\State $\boldsymbol{\sigma}^{k+1}(\mathbf{x}_I) \gets \mathbf{C}(\mathbf{x}_I) \colon \boldsymbol{\varepsilon}^{k+1}(\mathbf{x}_I)$
\State $e_{k+1} \gets \frac{\sqrt{\sum_{\boldsymbol{\xi}} \| \boldsymbol{\xi} \cdot \hat{\boldsymbol{\sigma}}^{k+1}(\boldsymbol{\xi}) \|^2}}{\| \hat{\boldsymbol{\sigma}}^{k+1}(\mathbf{0}) \|}$
\If{$$}
\State $\textbf{break}$
\EndIf
\EndFor
\Return $\boldsymbol{\varepsilon}^{k+1}(\mathbf{x}), \boldsymbol{\sigma}^{k+1}(\mathbf{x})$
\end{algorithmic}
$$


## 4. Known Pitfalls
**Gibbs ringing at material interfaces:** The scheme uses global trigonometric polynomials to interpolate fields, which causes pronounced high-frequency ringing artifacts (Gibbs phenomenon) near sharp material interfaces and non-smooth boundaries. While macroscopic effective properties remain accurate, the local microscopic fields exhibit reduced accuracy compared to finite-difference or finite-element discretizations.


**Sensitivity to reference medium choice:** The reference medium $\mathbf{C}^0$ is a purely numerical parameter that does not affect the converged solution, but it critically controls the stability and convergence rate of the fixed-point iteration. Poor choice leads to slow convergence or instability. For linear elasticity, the optimal choice is the arithmetic mean of the phase stiffnesses.


**Convergence degradation with stiffness contrast:** The convergence rate of the basic scheme deteriorates severely as the stiffness contrast between phases increases. The number of iterations required scales proportionally to the phase contrast ratio, making the scheme impractical for composites with very stiff inclusions in a compliant matrix (or vice versa) without accelerated solvers.


**Failure for porous/void materials (infinite contrast):** Convergence is not ensured for materials with infinite phase contrast, such as porous foams. The scheme requires a continuous elastic extension into pore space, but trigonometric polynomials are global functions that cannot accommodate the required boundary values at solid-pore interfaces. Any small numerical error at the void boundary propagates globally, preventing convergence and yielding unphysical results (e.g., average stress converging to zero).


**Trigonometric interpolation accuracy at discontinuities:** The constitutive law is evaluated exactly only at voxel centers; the resulting stress field is interpolated globally via trigonometric polynomials. At material discontinuities, this global interpolation introduces errors because it fits continuous polynomials to physically discontinuous fields. The accuracy of local fields is inherently limited by these interpolation errors.


**Nyquist frequency symmetry loss on even grids:** On grids with even number of voxels, frequency symmetry is lost at the Nyquist frequencies. The Fourier coefficients of the strain must be forced to zero at these frequencies (or the Green's operator modified) to ensure the resulting real-space fields remain purely real-valued. Failure to handle this produces complex-valued (non-physical) mechanical fields.


## 5. References
- Moulinec, Suquet (1994) — Original FFT-based homogenization method
- Moulinec, Suquet (1998) — Accelerated scheme and convergence analysis
- Schneider (2021) — Moulinec-Suquet discretization as trigonometric collocation and trapezoidal quadrature

