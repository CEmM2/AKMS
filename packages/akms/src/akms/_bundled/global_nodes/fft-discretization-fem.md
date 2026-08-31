---
id: fft-discretization-fem
title: FEM-Based FFT (Hex Elements & FANS)
domain: fft-galerkin
subdomain: discretization-schemes
tags:
- discretization
- fft-galerkin
- spectral
- homogenization
- convergence
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-discretization-willot
  type: refines
  weight: 1.0
  note: Willot's scheme is equivalent to trilinear FEM with reduced integration (1 Gauss point); full FEM uses 8 Gauss points
- to: fft-green-operator
  type: requires
  weight: 0.9
  note: FEM discretization produces a semi-explicit Green's operator requiring 3x3 Hermitian matrix inversion
- to: fft-lippmann-schwinger
  type: feeds-into
  weight: 0.9
  note: Lippmann-Schwinger equation and solvers are constructed for the FEM-discretized system
- to: fft-convergence-schemes
  type: feeds-into
  weight: 0.7
  note: FANS uses Newton-Krylov solver for the FEM-discretized nonlinear system
- to: fft-discretization-staggered
  type: refines
  weight: 0.5
  note: Both use sub-grids separating displacement and strain evaluation points; FEM uses 8 Gauss points vs staggered grid's
    voxel-center evaluation
context_size: large
reading_priority: full
load_with:
- fft-discretization-willot
- fft-green-operator
- fft-lippmann-schwinger
content_ref: null
akms_schema: v2
---

# FEM-Based FFT (Hex Elements & FANS)

## Summary
The FEM-based FFT approach uses trilinear hexahedral finite elements on the regular periodic voxel grid, with nodal displacements at voxel corners and strain/stress evaluation at 8 Gauss points per element. Since FEM stencils on regular meshes can be interpreted as specific finite difference stencils, they produce Fourier multipliers that enable FFT-based solution. The key difference from Willot's scheme (which is equivalent to under-integrated FEM with 1 Gauss point) is that full integration with 8 Gauss points eliminates hourglass instabilities, at the cost of 8x memory and computational overhead. The FANS (Fourier-Accelerated Nodal Solver) method by Fritzen and Leuschner mitigates this cost through displacement-based formulation, sparse Newton tangent storage, and selective reduced integration.


## 1. Core Concept
The FEM-FFT method introduced by Schneider et al. places nodal displacement values on the nodal grid $Y^{\text{node}}_N$ (voxel corners) and introduces a Gauss-point grid $Y^{\text{Gauss}}_N$ with eight integration points per element. The discrete symmetrized gradient operator $D$ maps displacement fields from the nodal grid to strain values at the Gauss points. The crucial insight linking FEM to FFT is that FEM on regular periodic meshes yields specific finite difference stencils whose Fourier transforms are known, enabling the same FFT-based solution machinery. Willot's finite difference discretization is mathematically identical to trilinear FEM with reduced integration (one Gauss point at the voxel center). This FEM interpretation settles questions about convergence and stability: for non-porous materials only global hourglass instabilities occur (concentrated at Nyquist frequencies, fixable by zeroing the Green's operator there), but for porous materials local hourglass modes emerge that cannot be stabilized. Full 8-point integration eliminates these instabilities entirely.


## 2. Mathematical Formulation
The FEM variational principle minimizes the total discrete energy over all admissible displacement fluctuation fields on the nodal grid. The discrete symmetrized gradient $D$ maps nodal displacements to Gauss-point strains. The resulting Euler-Lagrange equations can be reformulated as a Lippmann-Schwinger equation, but the discrete Green's operator requires inverting a Hermitian $3 \times 3$ matrix at each frequency point (semi-explicit operator), unlike the fully explicit operators of finite difference schemes.


**FEM variational principle on the voxel grid:**

$$
\sum_{\mathbf{x} \in Y^{\text{Gauss}}_N} w\!\left(\mathbf{x},\, \bar{\boldsymbol{\varepsilon}} + D\mathbf{u}_N(\mathbf{x})\right) \longrightarrow \min_{\mathbf{u}_N} \quad \text{among } \mathbf{u}_N \colon Y^{\text{node}}_N \to \mathbb{R}^d
$$

where w is the local free energy density, bar{varepsilon} is the prescribed macroscopic strain, D is the discrete symmetrized gradient, u_N is the nodal displacement fluctuation

**Euler-Lagrange equation (discrete equilibrium):**

$$
D^* \left[ \frac{\partial w}{\partial \boldsymbol{\varepsilon}}\!\left(\cdot,\, \bar{\boldsymbol{\varepsilon}} + D\mathbf{u}_N\right) \right] = \mathbf{0}
$$

where D* is the negative of the discrete divergence operator associated with the symmetrized gradient D

**Semi-explicit Green's operator:**

$$
\hat{\boldsymbol{\Gamma}}^0(\boldsymbol{\xi}) \text{ requires solving } \mathbf{A}(\boldsymbol{\xi})\,\hat{\mathbf{u}}(\boldsymbol{\xi}) = \hat{\mathbf{f}}(\boldsymbol{\xi})
$$

where A(xi) is a Hermitian 3x3 acoustic tensor matrix at each frequency xi, computed from the FEM stencil Fourier transform; this inversion makes the operator semi-explicit rather than fully closed-form

**Equivalence of Willot's scheme to reduced-integration FEM:**

$$
\left.\text{Willot's discretization}\right|_{\text{1 Gauss pt}} \equiv \left.\text{Trilinear hex FEM}\right|_{\text{reduced integration}}
$$

where Both evaluate at a single point per voxel (the voxel center), leading to identical discrete systems

**Notation:**

- $Y^{\text{node}}_N$ — Nodal grid — voxel corners where displacement degrees of freedom live
- $Y^{\text{Gauss}}_N$ — Gauss-point grid — 8 integration points per voxel element
- $D$ — Discrete symmetrized gradient operator (nodal grid to Gauss-point grid)
- $D^*$ — Negative discrete divergence operator (adjoint of D)
- $w$ — Local condensed free energy density
- $\bar{\boldsymbol{\varepsilon}}$ — Prescribed macroscopic strain
- $\mathbf{u}_N$ — Nodal displacement fluctuation field


## 3. Algorithmic Implementation
**Algorithm: FANS (Fourier-Accelerated Nodal Solver)**

$$
\begin{algorithmic}
\State $\text{Input}\colon \bar{\boldsymbol{\varepsilon}},\; \mathbf{C}(\mathbf{x}),\; \text{tol}$
\State $\mathbf{u}_N^{(0)} \leftarrow \mathbf{0} \text{ (initial guess on nodal grid)}$
\While{$\|\mathbf{r}\| > \text{tol}$}
    \State $\boldsymbol{\varepsilon}(\mathbf{x}) \leftarrow \bar{\boldsymbol{\varepsilon}} + D\mathbf{u}_N^{(k)}(\mathbf{x}) \quad \forall \mathbf{x} \in Y^{\text{Gauss}}_N \text{ (8 pts/voxel)}$
    \State $\boldsymbol{\sigma}(\mathbf{x}) \leftarrow \frac{\partial w}{\partial \boldsymbol{\varepsilon}}(\mathbf{x}, \boldsymbol{\varepsilon}(\mathbf{x})) \quad \text{(constitutive law at all Gauss pts)}$
    \State $\mathbf{r} \leftarrow D^* \boldsymbol{\sigma} \quad \text{(discrete residual on nodal grid)}$
    \State $\mathbf{K}_{\text{sparse}} \leftarrow \text{assemble sparse Newton tangent from } \partial\boldsymbol{\sigma}/\partial\boldsymbol{\varepsilon}$
    \State $\delta\mathbf{u} \leftarrow \text{CG solve with FFT-preconditioned } \mathbf{K}_{\text{sparse}}\,\delta\mathbf{u} = -\mathbf{r}$
    \State $\mathbf{u}_N^{(k+1)} \leftarrow \mathbf{u}_N^{(k)} + \delta\mathbf{u}$
\EndWhile
\Return $\boldsymbol{\varepsilon},\; \boldsymbol{\sigma},\; \bar{\boldsymbol{\sigma}} = \langle \boldsymbol{\sigma} \rangle$
\end{algorithmic}
$$


## 4. Known Pitfalls
**Eightfold memory and computational overhead:** The full FEM-FFT approach with 8 Gauss points per voxel requires storing eight times the number of strain and stress fields compared to single-point schemes (Willot, Moulinec-Suquet). The constitutive law must also be evaluated eight times per voxel per iteration. This overhead can be prohibitive for large 3D microstructures. FANS mitigates this by operating on nodal displacements and storing the Newton tangent sparsely.


**Semi-explicit Green's operator cost:** Unlike finite difference discretizations that yield fully explicit (closed-form) Green's operators, the FEM discretization requires inverting a Hermitian $3 \times 3$ acoustic tensor matrix at every non-zero frequency point. While a $3 \times 3$ inversion is cheap per point, the cost accumulates over all $N_1 \times N_2 \times N_3$ frequency points and must be performed at each iteration (or precomputed and stored, adding memory overhead).


**Volumetric locking with full integration:** Fully integrated trilinear hexahedral elements are prone to volumetric locking when applied to nearly incompressible or highly plastic materials. The constraint ratio becomes too high, producing artificially stiff responses. FANS addresses this through selective reduced integration, where the volumetric part uses reduced integration while the deviatoric part uses full integration.


**Hourglass instabilities survive in under-integrated (Willot) variant:** The FEM interpretation reveals that Willot's scheme (equivalent to reduced-integration FEM) admits local hourglass modes for porous materials that cannot be fixed by the Nyquist-frequency zeroing strategy. Only the full 8-point integration or the standard staggered grid avoids these local instabilities. Users must understand that switching from Willot to full FEM is not just a refinement but a qualitative change in stability properties.


## 5. References
- Schneider, Merkert, Kabel (2017) — FFT-based solvers for trilinear hexahedral elements on regular periodic grids
- Fritzen and Leuschner (2013) — Fourier-Accelerated Nodal Solvers (FANS) with sparse Newton tangent and selective reduced integration
- Schneider (2021) — Review of nonlinear FFT-based computational homogenization, FEM-based discretizations

