---
id: fft-finite-strain
title: FFT at Finite Strains
domain: fft-galerkin
subdomain: coupled-problems
tags:
- fft-galerkin
- finite-strain
- homogenization
- spectral
- continuum-mechanics
- newton
status: established
confidence: 0.9
source: hybrid
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: Finite-strain Lippmann-Schwinger equation generalizes the small-strain form
- to: fft-green-operator
  type: requires
  weight: 0.9
  note: Finite-strain Green's operator loses minor symmetries compared to small-strain
- to: fft-reference-medium
  type: requires
  weight: 0.8
  note: Isotropic reference K0 = alpha0 I preferred at finite strains to commute with non-symmetric tangents
- to: fft-solver-newton-krylov
  type: feeds-into
  weight: 0.9
  note: Newton-Krylov is near-mandatory at finite strains due to poor basic scheme convergence
- to: fft-solver-basic-scheme
  type: feeds-into
  weight: 0.6
  note: Basic scheme can serve as inner solver for Newton linearization at finite strains
- to: fft-polycrystal
  type: feeds-into
  weight: 0.7
  note: Finite-strain framework used in polycrystal simulations with multiplicative decomposition
- to: kinematics-multiplicative-decomp
  type: requires
  weight: 0.7
  note: Multiplicative decomposition F=FeFp is the standard kinematics for finite-strain plasticity
context_size: large
reading_priority: full
load_with:
- fft-lippmann-schwinger
- fft-solver-newton-krylov
content_ref: null
akms_schema: v2
---

# FFT at Finite Strains

## Summary
FFT-based homogenization at finite strains reformulates the Lippmann-Schwinger framework in a total Lagrangian setting using the deformation gradient $\mathbf{F}$ and the first Piola-Kirchhoff stress $\mathbf{P}$ instead of the small-strain $\boldsymbol{\varepsilon}$ and $\boldsymbol{\sigma}$. The governing equilibrium is $\nabla_0 \cdot \mathbf{P}(\mathbf{X}) = 0$ with periodicity of $\mathbf{F}$ and average $\langle \mathbf{F} \rangle = \bar{\mathbf{F}}$. The finite-strain Green's operator $\hat{\Gamma}^0_f$ loses minor symmetries, and the material tangent $\mathbf{K} = \partial\mathbf{P}/\partial\mathbf{F}$ is fundamentally non-symmetric. This prevents use of CG (requiring GMRES instead), inflates memory from 21 to 36 tangent components per voxel, and makes Newton-Raphson with globalization near-mandatory because the basic scheme converges poorly. Three main algorithmic approaches exist: the basic scheme adapted for F and P, Newton-Raphson with the basic scheme as inner solver (Lahellec et al.), and the displacement-based DBFFT approach with preconditioning.


## 1. Core Concept
In the finite-strain total Lagrangian framework for FFT homogenization, equilibrium is formulated on the reference configuration using the first Piola-Kirchhoff stress $\mathbf{P}$ and the deformation gradient $\mathbf{F}$. The local deformation gradient $\mathbf{F}(\mathbf{X})$ replaces the small-strain tensor $\boldsymbol{\varepsilon}$ as the primary kinematic unknown and is decomposed into the macroscopic average $\bar{\mathbf{F}}$ and a periodic fluctuation $\tilde{\mathbf{F}}(\mathbf{X})$. By introducing a reference material tangent $\mathbf{K}_0$, the equilibrium can be transformed into a finite-strain Lippmann-Schwinger integral equation. The key complications relative to small strains are: (1) the modified Green's operator $\hat{\Gamma}^0_f$ only possesses major tensor symmetries, not minor ones, (2) the material tangent $\mathbf{K} = \partial\mathbf{P}/\partial\mathbf{F}$ is non-symmetric, preventing use of CG solvers, and (3) the basic scheme converges poorly because geometric nonlinearity is added to the implicit equation without tangent information.


## 2. Mathematical Formulation
The finite-strain framework operates on the reference configuration with the equilibrium $\nabla_0 \cdot \mathbf{P} = 0$ subject to periodicity of $\mathbf{F}$ and prescribed macroscopic average $\bar{\mathbf{F}}$. The Lippmann-Schwinger equation is written in Fourier space using a finite-strain Green's operator. The basic scheme iteration adapts directly by replacing $\boldsymbol{\varepsilon}$ with $\mathbf{F}$ and $\boldsymbol{\sigma}$ with $\mathbf{P}$. Newton linearization introduces the non-symmetric tangent $\mathbf{K}_i$ and requires globalization via line search.


**Finite-strain equilibrium:**

$$
\nabla_0 \cdot \mathbf{P}(\mathbf{X}) = 0, \quad \langle \mathbf{F} \rangle = \bar{\mathbf{F}}, \quad \mathbf{F} \text{ periodic}
$$

where P is the first Piola-Kirchhoff stress, F is the deformation gradient, F_bar is the prescribed macroscopic deformation gradient

**Finite-strain Lippmann-Schwinger equation in Fourier space:**

$$
\hat{\mathbf{F}}(\boldsymbol{\xi}) = \bar{\mathbf{F}} - \hat{\Gamma}^0_f(\boldsymbol{\xi}) : (\hat{\mathbf{P}}(\boldsymbol{\xi}) - \mathbf{K}_0 : \hat{\mathbf{F}}(\boldsymbol{\xi}))
$$

where Gamma^0_f is the finite-strain Green's operator, K_0 is the reference material tangent, xi is the frequency vector

**Finite-strain Green's operator (Fourier space):**

$$
\hat{\Gamma}^0_{f\,ijkl}(\boldsymbol{\xi}) = \hat{G}^0_{ik}(\boldsymbol{\xi})\,\xi_j\,\xi_l
$$

where G^0 is the Green's function (acoustic tensor inverse of the reference medium); only major symmetries are preserved, minor symmetries are lost

**Newton linearization of first Piola-Kirchhoff stress:**

$$
\mathbf{P}_{i+1} = \mathbf{P}_i + \frac{\partial \mathbf{P}}{\partial \mathbf{F}}\bigg|_{\mathbf{F}_i} : \delta\mathbf{F} = \mathbf{P}_i + \mathbf{K}_i : \delta\mathbf{F}
$$

where K_i = dP/dF at F_i is the non-symmetric material tangent at Newton iteration i, delta F is the deformation gradient correction

**Basic scheme iteration at finite strains:**

$$
\hat{\mathbf{F}}_{k+1}(\boldsymbol{\xi}) = \bar{\mathbf{F}} - \hat{\Gamma}^0_f(\boldsymbol{\xi}) : \hat{\boldsymbol{\tau}}_k(\boldsymbol{\xi})
$$

where tau_k(X) = P(F_k(X)) - K_0 : F_k(X) is the stress polarization at iteration k

**DBFFT Newton linearized system:**

$$
\mathbf{M} \cdot \hat{\nabla} : \mathcal{F}\left\{\mathbf{K}_i : \left(\mathcal{F}^{-1}\left\{\hat{\nabla} \cdot \delta\hat{\tilde{\mathbf{u}}}\right\}\right)\right\} = -\mathbf{M} \cdot \hat{\nabla} : \mathcal{F}\{\mathbf{P}_i\}
$$

where M is the preconditioner based on the average tangent, u_tilde is the displacement fluctuation, nabla_hat is the Fourier gradient operator

**Notation:**

- $\mathbf{F}$ — Deformation gradient (non-symmetric second-order tensor)
- $\mathbf{P}$ — First Piola-Kirchhoff stress tensor
- $\mathbf{K}$ — Material tangent dP/dF (non-symmetric fourth-order tensor)
- $\mathbf{K}_0$ — Reference material tangent stiffness
- $\hat{\Gamma}^0_f$ — Finite-strain Green's operator in Fourier space (only major symmetries)
- $\bar{\mathbf{F}}$ — Prescribed macroscopic deformation gradient
- $\delta\mathbf{F}$ — Newton correction to the deformation gradient


## 3. Algorithmic Implementation
**Algorithm: Basic Scheme at Finite Strains**

$$
\begin{algorithmic}
\State $Initialize \colon \mathbf{F}_0(\mathbf{X}) = \bar{\mathbf{F}}, \; \mathbf{K}_0 = \alpha_0 \mathbf{I}$
\While{$\|\boldsymbol{\xi} \cdot \hat{\mathbf{P}}_k\|_\infty / \|\hat{\mathbf{P}}_k(\mathbf{0})\| > \mathrm{tol}$}
    \State $\mathbf{P}_k(\mathbf{X}) = \mathbf{P}(\mathbf{F}_k(\mathbf{X})) \quad \text{(constitutive evaluation)}$
    \State $\hat{\boldsymbol{\tau}}_k(\boldsymbol{\xi}) = \mathcal{F}\{\mathbf{P}_k(\mathbf{X}) - \mathbf{K}_0 \colon \mathbf{F}_k(\mathbf{X})\}$
    \State $\hat{\mathbf{F}}_{k+1}(\boldsymbol{\xi}) = \bar{\mathbf{F}} - \hat{\Gamma}^0_f(\boldsymbol{\xi}) \colon \hat{\boldsymbol{\tau}}_k(\boldsymbol{\xi})$
    \State $\mathbf{F}_{k+1}(\mathbf{X}) = \mathcal{F}^{-1}\{\hat{\mathbf{F}}_{k+1}(\boldsymbol{\xi})\}$
\EndWhile
\end{algorithmic}
$$

**Taichi Mapping:**
Each voxel constitutive evaluation P(F) maps to a parallel GPU kernel. FFT/iFFT via cuFFT. The non-symmetric stress polarization and Green's operator application are local per-voxel operations. Poor convergence makes this approach impractical for large-strain increments.

**Algorithm: Newton-Raphson with Basic Scheme as Inner Solver (Lahellec)**

$$
\begin{algorithmic}
\State $Initialize \colon \mathbf{F}_0 = \mathbf{F}_t + \Delta\mathbf{F}_{t+\Delta t}$
\While{$\|\boldsymbol{\xi} \cdot \hat{\mathbf{P}}_i(\boldsymbol{\xi})\|_\infty / \|\hat{\mathbf{P}}_i(\mathbf{0})\| > \mathrm{tol}_{\mathrm{nw}}$}
    \State $\mathbf{P}_i = \mathbf{P}(\mathbf{F}_i), \quad \mathbf{K}_i = \frac{\partial \mathbf{P}}{\partial \mathbf{F}}\bigg|_{\mathbf{F}_i}$
    \State $\text{Inner solve (basic scheme to tol}_{lin}\text{)} \colon \delta\hat{\mathbf{F}}_{j+1} = -\hat{\Gamma}^0_f \colon [\mathcal{F}\{\mathbf{K}_i \colon \delta\mathbf{F}_j\} + \hat{\mathbf{P}}_i]$
    \State $\mathbf{F}_{i+1} = \mathbf{F}_i + \delta\mathbf{F}$
\EndWhile
\end{algorithmic}
$$

**Taichi Mapping:**
Outer Newton loop on host. Inner basic scheme iterations on GPU. Tangent K_i stored as 9x9 non-symmetric matrix per voxel (36 doubles). At 512^3 voxels, tangent storage alone exceeds 30 GB in double precision.


## 4. Known Pitfalls
**Non-symmetric tangent forces GMRES over CG:** The material tangent $\mathbf{K} = \partial\mathbf{P}/\partial\mathbf{F}$ is fundamentally non-symmetric at finite strains, preventing use of CG which requires symmetric positive-definite operators. GMRES or Bi-CGStab must be used instead, both of which are more expensive per iteration and require more storage for the Krylov basis vectors.


**Massive memory inflation from non-symmetric tensors:** The non-symmetric tangent requires storing 36 independent components per voxel instead of 21 for the symmetric small-strain tangent. For a $512^3$ grid in double precision, this increases tangent storage from 21 GB to over 30 GB. Combined with the additional strain fields needed by Krylov solvers, total memory can exceed 60 GB, making Newton-Krylov at finite strains prohibitively expensive for high-resolution microstructures.


**Poor convergence of the basic scheme:** Direct extension of the Moulinec-Suquet basic scheme to finite strains adds geometric nonlinearity to the implicit Lippmann-Schwinger equation without using tangent information. The convergence rate is drastically worse than in the small-strain case, making Newton-Raphson with globalization (back-tracking line search) near-mandatory for practical computations.


**Reference medium must be isotropic at finite strains:** The finite-strain Green's operator $\hat{\Gamma}^0_f$ loses minor symmetries. To ensure the reference medium commutes with all local non-symmetric tangents across the microstructure, the standard practice is to choose an isotropic reference $\mathbf{K}_0 = \alpha_0 \mathbf{I}$ proportional to the identity tensor. Anisotropic reference stiffnesses, while theoretically yielding linear convergence, are highly inefficient.


**Rotation overhead for anisotropic constitutive laws:** Finite-strain simulations of anisotropic materials (e.g., polycrystals) require continuously tracking the rotation of the crystal lattice. This introduces a time-consuming rotation step at each voxel during constitutive evaluation that is absent in isotropic or small-strain simulations.


## 5. References
- Schneider (2021) -- Finite-strain FFT formulation, basic scheme extension, reference medium selection
- Lahellec et al. (2003) -- Newton-Raphson with basic scheme as inner solver for finite strains
- Lucarini et al. (2022) -- DBFFT displacement-based formulation at finite strains, preconditioning
- Kabel et al. (2014) -- Newton-CG for finite-strain FFT, memory cost analysis

