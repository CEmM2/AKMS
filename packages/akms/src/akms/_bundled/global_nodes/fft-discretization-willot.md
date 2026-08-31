---
id: fft-discretization-willot
title: Willot's Rotated Finite Difference Scheme
domain: fft-galerkin
subdomain: discretization
tags:
- discretization
- finite-difference
- staggered-grid
- fft-galerkin
- homogenization
- periodic-bc
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-discretization-moulinec-suquet
  type: refines
  weight: 0.9
  note: Developed as a finite-difference alternative to eliminate Gibbs ringing of the Moulinec-Suquet spectral approach
- to: fft-green-operator
  type: requires
  weight: 0.9
  note: Uses a discrete Green's operator with modified frequency vector k(xi) replacing the continuous xi_Y
- to: fft-freq-grid
  type: requires
  weight: 0.8
  note: Operates on the same discrete frequency grid Z_N but with modified frequency vectors
- to: fft-lippmann-schwinger
  type: requires
  weight: 0.8
  note: Integrates with the Lippmann-Schwinger iteration via the discrete Green's operator
- to: fft-galerkin-basics
  type: feeds-into
  weight: 0.5
  note: Alternative discretization approach; shares variational foundation but uses local FD stencils
- to: fft-solver-basic-scheme
  type: feeds-into
  weight: 0.8
  note: Compatible with both strain-based and displacement-based solver formulations
- to: fft-discretization-staggered
  type: refines
  weight: 0.7
  note: Willot's rotated grid is a specific variant of the staggered grid family
context_size: large
reading_priority: full
load_with:
- fft-discretization-moulinec-suquet
- fft-green-operator
content_ref: null
akms_schema: v2
---

# Willot's Rotated Finite Difference Scheme

## Summary
Willot's rotated finite difference scheme replaces the exact continuous spatial derivatives of the Fourier-Galerkin and Moulinec-Suquet methods with central finite difference approximations on a rotated staggered grid, eliminating Gibbs ringing artifacts at material interfaces. Displacements live at voxel corners (nodal grid) while strains and stresses are evaluated at voxel centers (Gauss-point grid). The scheme is mathematically identical to trilinear hexahedral finite elements with reduced integration (one Gauss point per voxel). In Fourier space, the finite difference stencil yields a modified complex-valued frequency vector $k(\boldsymbol{\xi})$ that replaces the continuous $\boldsymbol{\xi}_Y$ in all operator definitions. The scheme enables displacement-based solver formulations that halve the memory footprint for 3D elasticity. Key limitations include checkerboarding artifacts inside inclusions, susceptibility to global hourglass instabilities requiring Nyquist zeroing, and convergence difficulties in highly porous microstructures.


## 1. Core Concept
Willot's rotated finite difference scheme operates on a rotated staggered grid where nodal displacements $\mathbf{u}_N$ are placed at voxel corners and gradients (strains) and stresses are evaluated at voxel centers. The grid architecture is conceptually a "resistor network" connecting diametrically opposite corners of each voxel, with connections meeting exactly at the center. Through a coordinate transformation, the gradient at the voxel center equals the averaged forward differences along coordinate axes. In Fourier space, this finite difference stencil produces a modified complex-valued frequency vector $k(\boldsymbol{\xi})$ that replaces the continuous re-scaled frequency vector $\boldsymbol{\xi}_Y$ in the Green's operator and all spatial derivative operators. The resulting system is mathematically identical to trilinear hexahedral finite elements (Q1 elements) with reduced integration at a single Gauss point per element located at the voxel center. Because the discrete gradient $D$ and divergence $D^*$ operators are defined between distinct sub-grids, iterative solvers can be formulated directly for the displacement field rather than the strain field, reducing memory by a factor of two for 3D elasticity.


## 2. Mathematical Formulation
The key mathematical object is the modified frequency vector $k(\boldsymbol{\xi})$, which encodes the rotated finite difference stencil in Fourier space. All spatial operators (gradient, divergence, Green's operator) are expressed algebraically in terms of $k(\boldsymbol{\xi})$ and its complex conjugate $\overline{k(\boldsymbol{\xi})}$. The discrete gradient maps nodal displacements to voxel-center strains via symmetrized tensor product with $k$, while the discrete divergence maps voxel-center stresses to nodal forces via contraction with $\overline{k}$. The discrete Green's operator retains the same algebraic structure as the continuous one but with $k(\boldsymbol{\xi})$ replacing $\boldsymbol{\xi}_Y$. Frequencies where $k(\boldsymbol{\xi}) = 0$ (including Nyquist) form the undefined set $U_N$ where the operator is forced to zero.


**Modified frequency vector (3D, rotated staggered grid):**

$$
k(\boldsymbol{\xi}) = \begin{bmatrix}
\frac{N_1}{4L_1} (e^{2\pi i \xi_1/N_1} - 1)(e^{2\pi i \xi_2/N_2} + 1)(e^{2\pi i \xi_3/N_3} + 1) \\
\frac{N_2}{4L_2} (e^{2\pi i \xi_1/N_1} + 1)(e^{2\pi i \xi_2/N_2} - 1)(e^{2\pi i \xi_3/N_3} + 1) \\
\frac{N_3}{4L_3} (e^{2\pi i \xi_1/N_1} + 1)(e^{2\pi i \xi_2/N_2} + 1)(e^{2\pi i \xi_3/N_3} - 1)
\end{bmatrix}
$$

where N_j is number of voxels in dimension j, L_j is cell length in dimension j, xi_j are integer frequency indices

**Discrete symmetrized gradient operator:**

$$
(\widehat{D\mathbf{u}})(\boldsymbol{\xi}) = k(\boldsymbol{\xi}) \otimes^s \hat{\mathbf{u}}(\boldsymbol{\xi})
$$

where D maps nodal displacements to voxel-center strains, otimes^s is symmetrized tensor product

**Discrete divergence operator:**

$$
(\widehat{D^*\boldsymbol{\tau}})(\boldsymbol{\xi}) = \hat{\boldsymbol{\tau}}(\boldsymbol{\xi}) \, \overline{k(\boldsymbol{\xi})}
$$

where D* maps voxel-center stresses to nodal forces, overline denotes complex conjugate

**Discrete Green's operator (isotropic reference C0 = 2 mu0 Id):**

$$
(\hat{\boldsymbol{\Gamma}}^0_N \hat{\boldsymbol{\tau}})(\boldsymbol{\xi}) = \frac{1}{\mu_0} \left[ \frac{k(\boldsymbol{\xi}) \otimes^s (\hat{\boldsymbol{\tau}} \, \overline{k(\boldsymbol{\xi})})}{\|k(\boldsymbol{\xi})\|^2} - \frac{1}{2} \frac{k(\boldsymbol{\xi}) \cdot (\hat{\boldsymbol{\tau}} \, \overline{k(\boldsymbol{\xi})})}{\|k(\boldsymbol{\xi})\|^4} k(\boldsymbol{\xi}) \otimes \overline{k(\boldsymbol{\xi})} \right]
$$

where Valid for xi not in U_N; mu_0 is reference shear modulus; the algebraic structure matches the continuous operator with k replacing xi_Y

**Discrete Green's operator (structural form):**

$$
\hat{\boldsymbol{\Gamma}}^0_N = D(D^* \mathbf{C}^0 D)^{-1} D^*
$$

where Compositional form showing relationship between gradient, divergence, and reference stiffness operators

**Undefined frequency set:**

$$
U_N = \{\boldsymbol{\xi} = \mathbf{0}\} \cup \{\boldsymbol{\xi} \mid 2\xi_j = -N_j \text{ for some } j\}
$$

where Includes zero frequency and all Nyquist frequencies; Green's operator is forced to zero on U_N

**Displacement-based Green's operator:**

$$
\mathbf{G}^0_N = (D^* \mathbf{C}^0 D)^{-1}
$$

where Maps nodal forces to displacement corrections; enables displacement-based solver with half the memory

**Displacement-based basic scheme update:**

$$
\mathbf{u}^{k+1}_N = - \mathbf{G}^0_N D^* \left[ \frac{\partial w}{\partial \boldsymbol{\varepsilon}}(\cdot, \bar{\boldsymbol{\varepsilon}} + D \mathbf{u}^k_N) - \mathbf{C}^0 : D \mathbf{u}^k_N \right]
$$

where u_N is nodal displacement, D u_N gives voxel-center strain, w is free energy, C0 is reference stiffness

**Notation:**

- $k(\boldsymbol{\xi})$ — Modified complex-valued frequency vector from the rotated FD stencil
- $\overline{k(\boldsymbol{\xi})}$ — Complex conjugate of the modified frequency vector
- $D$ — Discrete symmetrized gradient operator (nodal grid to Gauss-point grid)
- $D^*$ — Discrete divergence operator (Gauss-point grid to nodal grid), adjoint of D
- $\hat{\boldsymbol{\Gamma}}^0_N$ — Discrete Green's operator using modified frequency vector
- $\mathbf{G}^0_N$ — Displacement-based discrete Green's operator
- $U_N$ — Set of undefined frequencies (zero + Nyquist) where operator is zeroed
- $Y^{node}_N$ — Nodal grid at voxel corners where displacements live
- $Y^{Gauss}_N$ — Gauss-point grid at voxel centers where strains/stresses are evaluated
- $\otimes^s$ — Symmetrized tensor product
- $\mu_0$ — Shear modulus of the isotropic reference medium
- $\mathbf{C}^0$ — Reference medium stiffness tensor
- $w$ — Local condensed free energy density


## 3. Algorithmic Implementation
**Algorithm: Algorithm**

$$
\begin{algorithmic}
\State $\text{Set up frequency grid } Z_N \text{ and compute } k(\boldsymbol{\xi}) \text{ for all } \boldsymbol{\xi} \in Z_N$
\State $k_j(\boldsymbol{\xi}) \gets \frac{N_j}{4L_j} (e^{2\pi i \xi_j/N_j} - 1) \prod_{m \neq j} (e^{2\pi i \xi_m/N_m} + 1)$
\State $U_N \gets \{\boldsymbol{\xi} = \mathbf{0}\} \cup \{\boldsymbol{\xi} \mid 2\xi_j = -N_j \text{ for some } j\}$
\State $\boldsymbol{\varepsilon}^0_N(\mathbf{x}) \gets \bar{\boldsymbol{\varepsilon}} \quad \text{(initialize strain at voxel centers)}$
\For{$$}
\State $\boldsymbol{\tau}^k(\mathbf{x}) \gets [\mathbf{C}(\mathbf{x}) - \mathbf{C}^0] \colon \boldsymbol{\varepsilon}^k_N(\mathbf{x}) \quad \text{(polarization at voxel centers)}$
\State $\hat{\boldsymbol{\tau}}^k(\boldsymbol{\xi}) \gets \mathcal{F}\{\boldsymbol{\tau}^k(\mathbf{x})\}$
\If{$$}
\State $\hat{\boldsymbol{\varepsilon}}^{k+1}_N(\boldsymbol{\xi}) \gets \hat{\bar{\boldsymbol{\varepsilon}}} - \frac{1}{\mu_0} \left[ \frac{k \otimes^s (\hat{\boldsymbol{\tau}}^k \overline{k})}{\|k\|^2} - \frac{1}{2} \frac{k \cdot (\hat{\boldsymbol{\tau}}^k \overline{k})}{\|k\|^4} k \otimes \overline{k} \right]$
\Else
\State $\hat{\boldsymbol{\varepsilon}}^{k+1}_N(\boldsymbol{\xi}) \gets \hat{\bar{\boldsymbol{\varepsilon}}} \delta_{\boldsymbol{\xi},\mathbf{0}} \quad \text{(zero for Nyquist, macroscopic strain for } \boldsymbol{\xi}=\mathbf{0}\text{)}$
\EndIf
\State $\boldsymbol{\varepsilon}^{k+1}_N(\mathbf{x}) \gets \mathcal{F}^{-1}\{\hat{\boldsymbol{\varepsilon}}^{k+1}_N(\boldsymbol{\xi})\}$
\State $\boldsymbol{\sigma}^{k+1}(\mathbf{x}) \gets \mathbf{C}(\mathbf{x}) \colon \boldsymbol{\varepsilon}^{k+1}_N(\mathbf{x})$
\State $e_{k+1} \gets \frac{\sqrt{\sum_{\boldsymbol{\xi}} \| k(\boldsymbol{\xi}) \cdot \hat{\boldsymbol{\sigma}}^{k+1}(\boldsymbol{\xi}) \|^2}}{\| \hat{\boldsymbol{\sigma}}^{k+1}(\mathbf{0}) \|}$
\If{$$}
\State $\textbf{break}$
\EndIf
\EndFor
\Return $\boldsymbol{\varepsilon}^{k+1}_N(\mathbf{x}), \boldsymbol{\sigma}^{k+1}(\mathbf{x})$
\end{algorithmic}
$$


## 4. Known Pitfalls
**Checkerboarding artifacts inside inclusions:** Willot's discrete stencil introduces pronounced checkerboarding artifacts in the local microscopic fields, particularly visible inside inclusion phases. These replace the Gibbs ringing of the continuous operator but can still reduce the accuracy of local field predictions.


**Global hourglass instabilities:** Because the scheme is equivalent to trilinear FEM with reduced integration (one Gauss point per voxel), it is inherently susceptible to global hourglass instabilities — zero-energy deformation modes that are invisible to the single-point evaluation. The discrete Green's operator must be artificially set to zero at all Nyquist frequencies to suppress these modes. Failure to do so leads to divergent, non-physical solutions.


**Convergence failure in highly porous microstructures:** Although the local finite difference approach handles solid-pore interfaces better than global spectral methods, highly porous microstructures (e.g., ~40% porosity bound sand) can trigger local hourglass instabilities not stabilized by Nyquist zeroing. Iterative solvers typically stall after initial error reduction and fail to converge to tight tolerances, making the scheme less robust than the standard staggered grid for such applications.


**Staggered grid interpolation requirement:** Displacements live on the nodal grid (voxel corners) while strains, stresses, and material properties are evaluated at voxel centers (Gauss-point grid). If continuous field compatibility is required at identical spatial coordinates, additional interpolation between the two sub-grids is needed, adding complexity.


**No guaranteed variational bounds:** Unlike the Fourier-Galerkin discretization, which generates rigorous upper and lower bounds on effective elastic properties via exact integration over trigonometric polynomials, Willot's finite difference approximation cannot provide guaranteed theoretical bounds on homogenized properties. The effective properties are approximations without certified error bounds.


## 5. References
- Willot (2015) — Rotated finite difference scheme for FFT-based homogenization
- Schneider (2021) — Comparison of discretization schemes including Willot's rotated staggered grid
- Schneider, Ospald, Kabel (2017) — Equivalence of Willot scheme to trilinear FEM with reduced integration

