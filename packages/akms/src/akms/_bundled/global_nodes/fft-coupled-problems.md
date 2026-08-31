---
id: fft-coupled-problems
title: FFT for Coupled & Multi-Physics Problems
domain: fft-galerkin
subdomain: coupled-problems
tags:
- fft-galerkin
- homogenization
- spectral
- continuum-mechanics
- multi-physics
status: established
confidence: 0.9
source: hybrid
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: Coupled problems extend the Lippmann-Schwinger framework with additional polarization terms
- to: fft-green-operator
  type: requires
  weight: 0.8
  note: Green's operator used in the mechanical sub-problem of coupled systems
- to: fft-galerkin-basics
  type: requires
  weight: 0.9
  note: FFT framework provides the spectral solver infrastructure
- to: fft-solver-basic-scheme
  type: feeds-into
  weight: 0.6
  note: Basic scheme or ADMM can solve the primal non-symmetric piezoelectric formulation
- to: fft-phase-field
  type: feeds-into
  weight: 0.7
  note: Phase-field fracture is a specific instance of coupled multi-physics with FFT
- to: fft-reference-medium
  type: requires
  weight: 0.7
  note: Reference medium selection affects convergence of the mechanical sub-problem
context_size: large
reading_priority: full
load_with:
- fft-lippmann-schwinger
- fft-galerkin-basics
content_ref: null
akms_schema: v2
---

# FFT for Coupled & Multi-Physics Problems

## Summary
FFT-based methods extend to coupled multi-physics problems where mechanical response interacts with thermal, electrical, magnetic, or chemical fields. The general approach uses staggered algorithms that sequentially solve the mechanical and auxiliary field sub-problems at each load step. For thermo-mechanical coupling, the thermal strain enters as an eigenstrain in the stress polarization tensor $\boldsymbol{\tau} = (\mathbf{C} - \mathbf{C}_0) : \boldsymbol{\varepsilon} - \boldsymbol{\beta}(T - T_{\mathrm{ref}})$. For piezoelectricity, three formulations exist: (1) primal (non-symmetric, solvable by basic scheme/ADMM), (2) indefinite symmetric (requires MINRES, high memory), and (3) partial Legendre-Fenchel transform (symmetric positive-definite, solvable by CG, lowest memory). Applications span conductivity/diffusivity, thermo-mechanics, piezoelectricity, ferroelectrics, electro-chemo-mechanical coupling in batteries, and phase-field recrystallization.


## 1. Core Concept
The FFT homogenization framework is highly versatile for multi-physics problems because the Lippmann-Schwinger structure naturally accommodates additional fields through modified polarization tensors or augmented constitutive operators. In the simplest case (thermo-mechanical coupling), the temperature field enters the mechanical equilibrium as a thermal eigenstrain added to the stress polarization. For fully coupled electro-mechanical problems (piezoelectricity), the constitutive law links stress $\boldsymbol{\sigma}$ and electric induction $\mathbf{D}$ to strain $\boldsymbol{\varepsilon}$ and electric field $\mathbf{E}$ through the elastic stiffness $\mathbf{C}$, piezoelectric moduli $\mathbf{e}$, and dielectric permittivity $\boldsymbol{\gamma}$. The mathematical structure of the coupled operator matrix (symmetric vs. non-symmetric, definite vs. indefinite) determines which FFT solver can be used, creating fundamental trade-offs between solver efficiency and memory.


## 2. Mathematical Formulation
Multi-physics FFT problems modify the standard Lippmann-Schwinger framework by either adding eigenstrain contributions to the polarization tensor (weak coupling) or by augmenting the constitutive operator to a block matrix system (strong coupling). For thermo-mechanical coupling, the standard approach treats temperature as a prescribed input field via the eigenstrain method, modifying only the stress polarization. When the temperature field itself must be computed (steady-state heat conduction), the scalar Lippmann-Schwinger equation with a second-order Green's operator is used — mathematically analogous to the conductivity problem. For strongly coupled problems like piezoelectricity, the constitutive operator becomes a block matrix and the corresponding Green's operator in Fourier space is block diagonal, combining the fourth-order mechanical Green's operator and the second-order scalar (electric/dielectric) Green's operator. The choice of mathematical formulation for the coupled operator has profound consequences for solver selection: the primal form is non-symmetric, the negated form is symmetric indefinite, and the Legendre-Fenchel transform yields symmetric positive-definite operators enabling CG.


**Thermo-mechanical stress polarization with thermal eigenstrain:**

$$
\boldsymbol{\tau} = (\mathbf{C} - \mathbf{C}_0) : \boldsymbol{\varepsilon} - \boldsymbol{\beta}(T - T_{\mathrm{ref}})
$$

where C is local elastic stiffness, C_0 is reference stiffness, beta is the thermal moduli tensor, T is local temperature, T_ref is the reference temperature

**Piezoelectric constitutive equations:**

$$
\boldsymbol{\sigma} = \mathbf{C} : \boldsymbol{\varepsilon} - \mathbf{e}^T \cdot \mathbf{E}, \quad \mathbf{D} = \mathbf{e} : \boldsymbol{\varepsilon} + \boldsymbol{\gamma} \cdot \mathbf{E}
$$

where sigma is stress, D is electric induction, e is the piezoelectric moduli tensor, gamma is the dielectric permittivity tensor, E is the electric field

**Primal formulation (non-symmetric):**

$$
\begin{bmatrix} \boldsymbol{\sigma} \\ \mathbf{D} \end{bmatrix} = \begin{bmatrix} \mathbf{C} & -\mathbf{e}^T \\ \mathbf{e} & \boldsymbol{\gamma} \end{bmatrix} \begin{bmatrix} \boldsymbol{\varepsilon} \\ \mathbf{E} \end{bmatrix}
$$

where Non-symmetric operator; solvable by basic scheme or ADMM

**Indefinite symmetric formulation:**

$$
\begin{bmatrix} \boldsymbol{\sigma} \\ -\mathbf{D} \end{bmatrix} = \begin{bmatrix} \mathbf{C} & -\mathbf{e}^T \\ -\mathbf{e} & -\boldsymbol{\gamma} \end{bmatrix} \begin{bmatrix} \boldsymbol{\varepsilon} \\ \mathbf{E} \end{bmatrix}
$$

where Symmetric but indefinite; requires MINRES with high memory cost

**Partial Legendre-Fenchel formulation (symmetric positive-definite):**

$$
\begin{bmatrix} \boldsymbol{\sigma} \\ \mathbf{E} \end{bmatrix} = \begin{bmatrix} \mathbf{C} + \mathbf{e}^T \cdot \boldsymbol{\gamma}^{-1} \cdot \mathbf{e} & -\mathbf{e}^T \cdot \boldsymbol{\gamma}^{-1} \\ -\boldsymbol{\gamma}^{-1} \cdot \mathbf{e} & \boldsymbol{\gamma}^{-1} \end{bmatrix} \begin{bmatrix} \boldsymbol{\varepsilon} \\ \mathbf{D} \end{bmatrix}
$$

where Eliminates D as independent variable; symmetric positive-definite operator solvable by CG with lowest memory

**Augmented Lippmann-Schwinger equation for SPD piezoelectric formulation:**

$$
\begin{bmatrix} \hat{\boldsymbol{\varepsilon}}(\boldsymbol{\xi}) \\ \hat{\mathbf{D}}(\boldsymbol{\xi}) \end{bmatrix} = \begin{bmatrix} \bar{\boldsymbol{\varepsilon}} \\ \bar{\mathbf{D}} \end{bmatrix} - \begin{bmatrix} \hat{\boldsymbol{\Gamma}}^0_{\mathrm{mech}}(\boldsymbol{\xi}) & \mathbf{0} \\ \mathbf{0} & \hat{\boldsymbol{\Gamma}}^0_{\mathrm{elec}}(\boldsymbol{\xi}) \end{bmatrix} \begin{bmatrix} \hat{\boldsymbol{\tau}}_{\mathrm{mech}}(\boldsymbol{\xi}) \\ \hat{\boldsymbol{\tau}}_{\mathrm{elec}}(\boldsymbol{\xi}) \end{bmatrix}
$$

where The block diagonal Green's operator decouples in Fourier space: Gamma^0_mech is the standard fourth-order mechanical Green's operator, Gamma^0_elec is the second-order scalar Green's operator for the electric potential. tau_mech and tau_elec are the mechanical and electric polarization tensors computed from the SPD constitutive operator and the respective reference operators. The off-diagonal zeros arise because the differential constraints (mechanical equilibrium and Gauss's law) are independent in Fourier space.

**Scalar Green's operator for the electric/thermal sub-problem:**

$$
\hat{\boldsymbol{\Gamma}}^0_{\mathrm{elec}}(\boldsymbol{\xi}) = \frac{1}{\gamma_0 |\boldsymbol{\xi}|^2} \boldsymbol{\xi} \otimes \boldsymbol{\xi}, \quad \boldsymbol{\xi} \neq \mathbf{0}
$$

where gamma_0 is the reference dielectric permittivity (scalar, for isotropic reference), xi is the frequency vector. This second-order tensor operates on vectors, in contrast to the fourth-order mechanical Green's operator that operates on second-order tensors.

**Conductivity/thermal Lippmann-Schwinger equation:**

$$
\hat{\mathbf{E}}(\boldsymbol{\xi}) = \bar{\mathbf{E}} - \hat{\boldsymbol{\Gamma}}^0_{\mathrm{th}}(\boldsymbol{\xi}) \cdot \hat{\mathbf{p}}(\boldsymbol{\xi}), \quad \mathbf{p}(\mathbf{x}) = (\boldsymbol{\kappa}(\mathbf{x}) - \boldsymbol{\kappa}_0) \cdot \mathbf{E}(\mathbf{x})
$$

where E = -nabla T is the temperature gradient vector, E_bar is the macroscopic temperature gradient, p is the thermal/conductivity polarization vector, kappa is the local thermal conductivity tensor, kappa_0 is the reference conductivity. Gamma^0_th has the same structure as Gamma^0_elec with kappa_0 replacing gamma_0.

**Notation:**

- $\boldsymbol{\tau}$ — Stress polarization tensor (modified for multi-physics)
- $\boldsymbol{\beta}$ — Second-order thermal moduli tensor
- $\mathbf{e}$ — Third-order piezoelectric moduli tensor
- $\boldsymbol{\gamma}$ — Second-order dielectric permittivity tensor
- $\mathbf{D}$ — Electric induction (electric displacement) vector
- $\mathbf{E}$ — Electric field vector (or temperature gradient vector in thermal context)
- $\hat{\boldsymbol{\Gamma}}^0_{\mathrm{mech}}$ — Fourth-order mechanical Green's operator in Fourier space
- $\hat{\boldsymbol{\Gamma}}^0_{\mathrm{elec}}$ — Second-order scalar Green's operator for the electric potential in Fourier space
- $\hat{\boldsymbol{\Gamma}}^0_{\mathrm{th}}$ — Second-order scalar Green's operator for thermal conductivity in Fourier space
- $\boldsymbol{\kappa}$ — Second-order thermal conductivity tensor
- $\boldsymbol{\kappa}_0$ — Reference thermal conductivity (scalar for isotropic reference)
- $\gamma_0$ — Reference dielectric permittivity (scalar for isotropic reference)
- $\mathbf{p}$ — Thermal/conductivity polarization vector


## 3. Algorithmic Implementation
**Algorithm: Staggered Algorithm for Thermo-Mechanical Coupling**

$$
\begin{algorithmic}
\State $Initialize \colon \boldsymbol{\varepsilon}_0(\mathbf{x}) = \bar{\boldsymbol{\varepsilon}}, \; T(\mathbf{x}) = T_{\mathrm{ref}} + \Delta T(\mathbf{x})$
\For{$\text{each load/time step } n = 1, 2, \ldots$}
    \State $\text{Step 1a (eigenstrain approach)} \colon T(\mathbf{x}) \gets \text{prescribed temperature field (uniform } \Delta T \text{ or heterogeneous input)}$
    \State $\text{Step 1b (conductivity solve, optional)} \colon \hat{\mathbf{E}}(\boldsymbol{\xi}) = \bar{\mathbf{E}} - \hat{\boldsymbol{\Gamma}}^0_{\mathrm{th}}(\boldsymbol{\xi}) \cdot \hat{\mathbf{p}}(\boldsymbol{\xi}), \quad \mathbf{p}(\mathbf{x}) = (\boldsymbol{\kappa}(\mathbf{x}) - \boldsymbol{\kappa}_0) \cdot \mathbf{E}(\mathbf{x})$
    \State $\text{Step 2} \colon \boldsymbol{\tau}(\mathbf{x}) = (\mathbf{C}(\mathbf{x}) - \mathbf{C}_0) \colon \boldsymbol{\varepsilon}(\mathbf{x}) - \boldsymbol{\beta}(\mathbf{x})(T(\mathbf{x}) - T_{\mathrm{ref}})$
    \State $\text{Step 3} \colon \hat{\boldsymbol{\varepsilon}}(\boldsymbol{\xi}) = \bar{\boldsymbol{\varepsilon}} - \hat{\boldsymbol{\Gamma}}^0(\boldsymbol{\xi}) \colon \hat{\boldsymbol{\tau}}(\boldsymbol{\xi})$
    \State $\text{Iterate Steps 2-3 until mechanical convergence}$
\EndFor
\end{algorithmic}
$$

**Taichi Mapping:**
Thermal eigenstrain computation is a local per-voxel operation, embarrassingly parallel on GPU. The modified polarization adds one vector subtraction per voxel. The conductivity solve (Step 1b) uses the same FFT infrastructure as the mechanical solve but with a second-order (not fourth-order) Green's operator, reducing memory. The mechanical solver uses the same FFT infrastructure as the isothermal case.

**Algorithm: Piezoelectric Coupling via Legendre-Fenchel Formulation**

$$
\begin{algorithmic}
\State $Initialize \colon \boldsymbol{\varepsilon}_0 = \bar{\boldsymbol{\varepsilon}}, \; \mathbf{D}_0 = \bar{\mathbf{D}}$
\State $\text{Precompute reference operators} \colon \hat{\boldsymbol{\Gamma}}^0_{\mathrm{mech}}(\boldsymbol{\xi}) = \xi_l \xi_j [C^0_{ijkl} \xi_l \xi_j]^{-1}, \quad \hat{\boldsymbol{\Gamma}}^0_{\mathrm{elec}}(\boldsymbol{\xi}) = \frac{1}{\gamma_0 |\boldsymbol{\xi}|^2} \boldsymbol{\xi} \otimes \boldsymbol{\xi}$
\State $\text{Compute transformed SPD constitutive operator per voxel} \colon \mathbf{L}^{*}(\mathbf{x}) = \begin{bmatrix} \mathbf{C} + \mathbf{e}^T \boldsymbol{\gamma}^{-1} \mathbf{e} & -\mathbf{e}^T \boldsymbol{\gamma}^{-1} \\ -\boldsymbol{\gamma}^{-1} \mathbf{e} & \boldsymbol{\gamma}^{-1} \end{bmatrix}$
\While{$\text{residual} > \mathrm{tol}$}
    \State $\begin{bmatrix} \boldsymbol{\sigma} \\ \mathbf{E} \end{bmatrix} = \mathbf{L}^{*}(\mathbf{x}) \begin{bmatrix} \boldsymbol{\varepsilon} \\ \mathbf{D} \end{bmatrix}$
    \State $\text{Compute augmented polarization} \colon \begin{bmatrix} \hat{\boldsymbol{\tau}}_{\mathrm{mech}} \\ \hat{\boldsymbol{\tau}}_{\mathrm{elec}} \end{bmatrix} = \begin{bmatrix} \hat{\boldsymbol{\sigma}} - \mathbf{L}^{*,0}_{\mathrm{mech}} \colon \hat{\boldsymbol{\varepsilon}} \\ \hat{\mathbf{E}} - \mathbf{L}^{*,0}_{\mathrm{elec}} \cdot \hat{\mathbf{D}} \end{bmatrix}$
    \State $\text{Update fields via block Green's operator} \colon \begin{bmatrix} \hat{\boldsymbol{\varepsilon}} \\ \hat{\mathbf{D}} \end{bmatrix} \gets \begin{bmatrix} \bar{\boldsymbol{\varepsilon}} \\ \bar{\mathbf{D}} \end{bmatrix} - \begin{bmatrix} \hat{\boldsymbol{\Gamma}}^0_{\mathrm{mech}} & \mathbf{0} \\ \mathbf{0} & \hat{\boldsymbol{\Gamma}}^0_{\mathrm{elec}} \end{bmatrix} \begin{bmatrix} \hat{\boldsymbol{\tau}}_{\mathrm{mech}} \\ \hat{\boldsymbol{\tau}}_{\mathrm{elec}} \end{bmatrix}$
\EndWhile
\end{algorithmic}
$$

**Taichi Mapping:**
Per-voxel constitutive evaluation of the block operator is embarrassingly parallel. The block Green's operator is applied as two independent FFT operations: one for the mechanical strain (6 components) and one for the electric displacement (3 components). CG iterations use standard FFT pairs. Memory per voxel: 6 strain + 6 stress + 3 D + 3 E components plus the block constitutive matrix entries.


## 4. Known Pitfalls
**Non-symmetric primal formulation prevents CG:** The direct (primal) piezoelectric constitutive matrix is non-symmetric because $\mathbf{e}$ and $-\mathbf{e}^T$ appear in off-diagonal positions. CG requires symmetry, so the primal form forces use of the basic scheme or ADMM, which converge slower than Krylov solvers.


**MINRES memory overhead for indefinite formulation:** The indefinite symmetric formulation preserves the conditioning of the primal form but requires MINRES, which has a comparatively high memory demand. This acts as a severe limitation for high-resolution 3D microstructures.


**Spectral shift in Legendre-Fenchel formulation:** The partial Legendre-Fenchel transformation alters the spectrum of the linear operator compared to the primal formulation. While the resulting operator is symmetric positive-definite (allowing CG), the spectral shift can affect the convergence rate of iterative solvers, potentially requiring more iterations than expected.


**Operator splitting errors in staggered schemes:** Staggered algorithms decouple the multi-physics fields and solve them sequentially. This operator splitting introduces temporal integration errors (typically first or second order), which can lead to artificial dissipation or reduced accuracy in strongly coupled regimes. Sufficient staggered iterations or small time steps are needed.


**Memory inflation from multiple field storage:** Multi-physics problems require simultaneous storage of multiple vector and tensor fields (displacement, electric displacement, electric field, polarization, temperature). For high-resolution 3D microstructures, this memory overhead can become the practical bottleneck, especially when combined with tangent storage for Newton-type solvers.


## 5. References
- Schneider (2021) -- Coupled problems framework, conductivity, thermo-mechanics, piezoelectricity
- Brenner (2009) -- Thermo-mechanical eigenstrain approach, accelerated polarization schemes
- Wicht et al. (2020) -- Piezoelectric formulations, primal vs Legendre-Fenchel comparison
- Lucarini et al. (2022) -- Multi-physics FFT overview, staggered algorithms

