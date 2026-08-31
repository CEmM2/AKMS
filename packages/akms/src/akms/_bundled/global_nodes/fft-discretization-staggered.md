---
id: fft-discretization-staggered
title: Staggered Grid Discretization
domain: fft-galerkin
subdomain: discretization-schemes
tags:
- discretization
- staggered-grid
- finite-difference
- fft-galerkin
- spectral
- homogenization
- periodic-bc
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-discretization-willot
  type: refines
  weight: 1.0
  note: Staggered grid uses standard (non-rotated) staggering as alternative to Willot's rotated scheme
- to: fft-green-operator
  type: requires
  weight: 0.9
  note: Staggered grid modifies the Green's operator via complex-valued frequency vectors
- to: fft-freq-grid
  type: requires
  weight: 0.8
  note: Modified frequency vector depends on discrete frequency grid construction
- to: fft-lippmann-schwinger
  type: feeds-into
  weight: 0.9
  note: Lippmann-Schwinger solvers can be constructed for the staggered grid discretization
- to: fft-discretization-moulinec-suquet
  type: refines
  weight: 0.7
  note: Staggered grid replaces the continuous derivative with forward/backward finite difference stencils
context_size: large
reading_priority: full
load_with:
- fft-discretization-willot
- fft-green-operator
- fft-freq-grid
content_ref: null
akms_schema: v2
---

# Staggered Grid Discretization

## Summary
The staggered grid discretization for FFT-based homogenization adapts concepts from finite volume methods in fluid dynamics. Displacements live on voxel faces while strains, stresses, and material properties are evaluated at voxel centers. This physical separation of field evaluation points naturally mitigates hourglass instabilities that plague Willot's rotated staggered grid in porous materials. The scheme uses forward and backward finite difference operators to define a discrete symmetrized gradient, and yields an explicit Green's operator in Fourier space via a modified complex-valued frequency vector.


## 1. Core Concept
In the staggered grid approach, each voxel is treated as a control volume. Displacements live on voxel faces (analogous to velocities in fluid dynamics), while strains and stresses are evaluated strictly at voxel centers. This arrangement uses specific combinations of forward ($D^+$) and backward ($D^-$) finite difference operators to construct a discrete symmetrized gradient operator. Unlike Willot's rotated staggered grid (which evaluates at a single voxel-center Gauss point and is equivalent to reduced-integration FEM), the standard staggered grid physically separates the evaluation points across faces and centers. This separation is key to its robustness for porous materials, where Willot's scheme suffers from local hourglass instabilities that cannot be stabilized by zeroing the Green's operator at Nyquist frequencies. The staggered grid is compatible with fully anisotropic material behavior.


## 2. Mathematical Formulation
The staggered grid defines a discrete symmetrized gradient operator $D$ using forward ($D^+_j$) and backward ($D^-_j$) finite difference operators in each coordinate direction $j$. In Fourier space, these stencils produce a modified complex-valued frequency vector $k_j$ that replaces the continuous spatial derivative. The Green's operator action is then computed via a sequence of algebraic steps involving the normalized frequency vector and its complex conjugate.


**Discrete symmetrized gradient operator (3D):**

$$
D\mathbf{u} = \begin{bmatrix} D^+_1 u_1 & \frac{1}{2}(D^-_1 u_2 + D^-_2 u_1) & \frac{1}{2}(D^-_1 u_3 + D^-_3 u_1) \\ \frac{1}{2}(D^-_2 u_1 + D^-_1 u_2) & D^+_2 u_2 & \frac{1}{2}(D^-_2 u_3 + D^-_3 u_2) \\ \frac{1}{2}(D^-_3 u_1 + D^-_1 u_3) & \frac{1}{2}(D^-_3 u_2 + D^-_2 u_3) & D^+_3 u_3 \end{bmatrix}
$$

where D+_j and D-_j are forward and backward finite difference operators in direction j, u_i are displacement components on voxel faces

**Modified frequency vector (staggered grid):**

$$
k_j = \left(e^{-2\pi i \xi_j / N_j} - 1\right) \frac{N_j}{L_j}
$$

where xi_j is the integer frequency index, N_j the number of voxels, L_j the cell dimension in direction j

**Normalized frequency vector:**

$$
\boldsymbol{\eta} = \mathbf{k} / \|\mathbf{k}\|
$$

where k is the modified complex-valued frequency vector, bar{eta} denotes its complex conjugate

**Auxiliary force vector (staggered grid):**

$$
\mathbf{f} = \begin{bmatrix} -\hat{\tau}_{11}(\boldsymbol{\xi})\eta_1 + \hat{\tau}_{12}(\boldsymbol{\xi})\bar{\eta}_2 + \hat{\tau}_{13}(\boldsymbol{\xi})\bar{\eta}_3 \\ \hat{\tau}_{21}(\boldsymbol{\xi})\bar{\eta}_1 - \hat{\tau}_{22}(\boldsymbol{\xi})\eta_2 + \hat{\tau}_{23}(\boldsymbol{\xi})\bar{\eta}_3 \\ \hat{\tau}_{31}(\boldsymbol{\xi})\bar{\eta}_1 + \hat{\tau}_{32}(\boldsymbol{\xi})\bar{\eta}_2 - \hat{\tau}_{33}(\boldsymbol{\xi})\eta_3 \end{bmatrix}
$$

where hat{tau}_{ij} are Fourier-space stress polarization components, eta_j and bar{eta}_j are the normalized frequency and its conjugate

**Scalar projection and displacement intermediate:**

$$
s = \mathbf{f} \cdot \bar{\boldsymbol{\eta}}, \quad \mathbf{u} = \frac{-\mathbf{f} + s\,\boldsymbol{\eta}/2}{\mu_0}
$$

where mu_0 is the reference shear modulus

**Strain fluctuation assembly (staggered grid):**

$$
\hat{\boldsymbol{\varepsilon}}(\boldsymbol{\xi}) = \begin{bmatrix} -\bar{\eta}_1 u_1 & \frac{\eta_1 u_2 + \eta_2 u_1}{2} & \frac{\eta_1 u_3 + \eta_3 u_1}{2} \\ \frac{\eta_2 u_1 + \eta_1 u_2}{2} & -\bar{\eta}_2 u_2 & \frac{\eta_2 u_3 + \eta_3 u_2}{2} \\ \frac{\eta_3 u_1 + \eta_1 u_3}{2} & \frac{\eta_3 u_2 + \eta_2 u_3}{2} & -\bar{\eta}_3 u_3 \end{bmatrix}
$$

where u_i are the displacement intermediate vector components

**Notation:**

- $D^+_j, D^-_j$ — Forward and backward finite difference operators in direction j
- $k_j$ — Modified complex-valued frequency component for the staggered grid
- $\boldsymbol{\eta}$ — Normalized modified frequency vector
- $\bar{\boldsymbol{\eta}}$ — Complex conjugate of the normalized frequency vector
- $\mu_0$ — Shear modulus of the isotropic reference medium
- $\hat{\boldsymbol{\tau}}$ — Stress polarization field in Fourier space


## 3. Algorithmic Implementation
**Algorithm: Staggered Grid Green's Operator Application**

$$
\begin{algorithmic}
\For{$j = 1, 2, 3$}
    \State $k_j \leftarrow (e^{-2\pi i \xi_j / N_j} - 1) N_j / L_j$
\EndFor
\State $\boldsymbol{\eta} \leftarrow \mathbf{k} / \|\mathbf{k}\|$
\State $f_1 \leftarrow -\hat{\tau}_{11}\eta_1 + \hat{\tau}_{12}\bar{\eta}_2 + \hat{\tau}_{13}\bar{\eta}_3$
\State $f_2 \leftarrow \hat{\tau}_{21}\bar{\eta}_1 - \hat{\tau}_{22}\eta_2 + \hat{\tau}_{23}\bar{\eta}_3$
\State $f_3 \leftarrow \hat{\tau}_{31}\bar{\eta}_1 + \hat{\tau}_{32}\bar{\eta}_2 - \hat{\tau}_{33}\eta_3$
\State $s \leftarrow \mathbf{f} \cdot \bar{\boldsymbol{\eta}}$
\State $\mathbf{u} \leftarrow (-\mathbf{f} + s\,\boldsymbol{\eta}/2) / \mu_0$
\State $\hat{\varepsilon}_{ij} \leftarrow \text{assemble from } \boldsymbol{\eta}, \bar{\boldsymbol{\eta}}, \mathbf{u} \text{ (see strain fluctuation formula)}$
\Return $\hat{\boldsymbol{\varepsilon}}(\boldsymbol{\xi})$
\end{algorithmic}
$$


## 4. Known Pitfalls
**Non-symmetric solutions for symmetric geometries:** Because the grid staggering breaks perfect spatial symmetry by placing displacement components on varying voxel faces while evaluating strains at centers, the computed solution fields for a symmetric geometry may turn out non-symmetric. This is generally not problematic for naturally complex, non-symmetric microstructures but can be confusing during verification on simple test cases.


**Implementation complexity versus Willot scheme:** The staggered grid operator requires careful handling of forward and backward difference operators, complex-valued frequency vectors, and their conjugates in a multi-step algebraic sequence. This is significantly more complex than Willot's scheme or the continuous Moulinec-Suquet formulation, and sign/conjugation errors in the auxiliary vector $\mathbf{f}$ assembly are common implementation bugs.


**Interface artifacts at sharp material boundaries:** Like all regular-grid discretizations, the staggered grid produces numerical artifacts at sharp material interfaces. While it avoids the severe checkerboarding of Willot's scheme and the global ringing of the Moulinec-Suquet discretization, minor localized inaccuracies at the interface remain present.


**Anisotropy limitations noted in summary tables:** Although the staggered grid is compatible with anisotropic materials (unlike the finite volume discretization which is restricted to isotropic conductivity), it is listed with a caveat "(+)" for anisotropic support in Schneider's summary, indicating that practical implementation for fully general anisotropy requires additional care.


## 5. References
- Schneider, Ospald, Kabel (2016) — Computational homogenization of elasticity on a staggered grid
- Schneider (2021) — Review of nonlinear FFT-based computational homogenization methods, staggered grid discretization
- Harlow and Welch (1965) — Original staggered grid concept for fluid dynamics

