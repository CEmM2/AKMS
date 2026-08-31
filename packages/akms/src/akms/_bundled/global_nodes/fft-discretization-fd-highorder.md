---
id: fft-discretization-fd-highorder
title: Higher-Order Finite Difference Schemes
domain: fft-galerkin
subdomain: discretization-schemes
tags:
- discretization
- finite-difference
- fft-galerkin
- spectral
- homogenization
- convergence
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-discretization-moulinec-suquet
  type: refines
  weight: 1.0
  note: Higher-order FD replaces continuous frequency with trigonometric approximations of increasing order
- to: fft-green-operator
  type: requires
  weight: 0.9
  note: Modified frequency vectors are substituted into the Green's operator formula
- to: fft-freq-grid
  type: requires
  weight: 0.8
  note: Frequency vector modifications operate on the discrete frequency grid
- to: fft-discretization-staggered
  type: refines
  weight: 0.6
  note: Both are finite difference alternatives to Moulinec-Suquet; staggered grid converges where high-order FD fails for
    porous media
- to: fft-discretization-willot
  type: refines
  weight: 0.6
  note: Willot's rotated staggered grid is another FD scheme; high-order CD lacks discrete combinatorial consistency that
    Willot provides
context_size: medium
reading_priority: full
load_with:
- fft-discretization-moulinec-suquet
- fft-green-operator
content_ref: null
akms_schema: v2
---

# Higher-Order Finite Difference Schemes

## Summary
Higher-order finite difference schemes replace continuous spatial derivatives in the FFT-based homogenization framework with central difference approximations of increasing order (2nd, 4th, 12th). Each order produces a modified purely imaginary frequency vector involving weighted sums of sine functions. These schemes excel for smooth microstructures without material property jumps (e.g., non-convex energy minimization), but suffer from oscillatory artifacts at sharp interfaces that worsen with increasing order. For porous materials with infinite contrast, higher-order schemes fail to converge entirely.


## 1. Core Concept
The core idea, introduced by Mueller (1998), is to replace the continuous spatial derivative in the Green's operator with central finite difference approximations on the regular voxel grid. Homogeneous finite difference stencils produce Fourier multipliers upon discrete Fourier transformation, so the modification amounts to replacing the continuous frequency vector $2\pi\xi_j/L_j$ with a trigonometric expression involving $\sin(2\pi\xi_j/N_j)$ and its harmonics. Higher-order stencils use longer-range neighbors to achieve better approximation of the derivative for smooth fields. However, these schemes lack discrete combinatorial consistency, meaning they do not preserve the exact algebraic structure of the underlying differential operators on the discrete grid. This deficiency makes them unsuitable for problems with large phase contrast, where oscillatory artifacts propagate away from interfaces and intensify with increasing order.


## 2. Mathematical Formulation
Each higher-order central difference scheme defines a modified frequency vector $k_j$ that replaces the continuous frequency in the Green's operator. All central difference schemes produce purely imaginary frequency vectors (unlike the staggered grid which yields a general complex vector). The Green's operator is then applied using the standard algebraic sequence with the normalized frequency vector $\boldsymbol{\eta} = \mathbf{k}/\|\mathbf{k}\|$.


**2nd-order central difference frequency vector:**

$$
k_j = i \sin\!\left(\frac{2\pi \xi_j}{N_j}\right) \frac{N_j}{L_j}
$$

where xi_j is the integer frequency index, N_j the number of voxels, L_j the cell dimension in direction j

**4th-order central difference frequency vector:**

$$
k_j = i \left[ 8 \sin\!\left(\frac{2\pi \xi_j}{N_j}\right) - \sin\!\left(\frac{4\pi \xi_j}{N_j}\right) \right] \frac{N_j}{L_j}
$$

where The coefficients 8 and -1 arise from the 4th-order central difference stencil (a global scaling factor of 1/6 is absorbed into the expression)

**12th-order central difference frequency vector:**

$$
k_j = i \left[ 23760 \sin\!\left(\frac{2\pi \xi_j}{N_j}\right) - 7425 \sin\!\left(\frac{4\pi \xi_j}{N_j}\right) + 2200 \sin\!\left(\frac{6\pi \xi_j}{N_j}\right) - 495 \sin\!\left(\frac{8\pi \xi_j}{N_j}\right) + 72 \sin\!\left(\frac{10\pi \xi_j}{N_j}\right) - 5 \sin\!\left(\frac{12\pi \xi_j}{N_j}\right) \right] \frac{N_j}{L_j}
$$

where The coefficients arise from the 12th-order central difference stencil (a global scaling factor of 1/27720 is absorbed)

**Comparison with other discretization frequency vectors:**

$$
k_j^{\text{MS}} = \frac{2\pi \xi_j}{L_j}, \quad k_j^{\text{Willot}} = \prod_{k \neq j}\left(e^{2\pi i \xi_k/N_k} + 1\right)\left(e^{2\pi i \xi_j/N_j} - 1\right)\frac{N_j}{L_j}, \quad k_j^{\text{stag}} = \left(e^{-2\pi i \xi_j/N_j} - 1\right)\frac{N_j}{L_j}
$$

where MS = Moulinec-Suquet (continuous), Willot = rotated staggered grid, stag = standard staggered grid

**Green's operator application (common to all non-staggered FD schemes):**

$$
\boldsymbol{\eta} = \frac{\mathbf{k}}{\|\mathbf{k}\|}, \quad \mathbf{f} = \hat{\boldsymbol{\tau}}(\boldsymbol{\xi}) \bar{\boldsymbol{\eta}}, \quad s = \mathbf{f} \cdot \bar{\boldsymbol{\eta}}, \quad \mathbf{u} = \frac{-\mathbf{f} + s\,\bar{\boldsymbol{\eta}}/2}{\mu_0}
$$

where bar{eta} is the complex conjugate of the normalized frequency vector, mu_0 the reference shear modulus

**Notation:**

- $k_j$ — Modified frequency vector component for the chosen FD scheme
- $\boldsymbol{\eta}$ — Normalized modified frequency vector
- $\bar{\boldsymbol{\eta}}$ — Complex conjugate of the normalized frequency vector
- $i$ — Imaginary unit
- $N_j$ — Number of voxels in direction j
- $L_j$ — Cell dimension in direction j
- $\xi_j$ — Integer frequency index in direction j


## 3. Algorithmic Implementation
Not applicable as a standalone algorithm. Higher-order FD schemes only modify the frequency vector computation within the Green's operator application loop. The modified k_j is substituted into the same algebraic sequence used by the Moulinec-Suquet or other discretization schemes (see fft-green-operator and fft-discretization-moulinec-suquet).

## 4. Known Pitfalls
**Oscillatory artifacts at material interfaces:** At sharp material interfaces, higher-order central difference schemes produce oscillatory stress and strain fields that propagate away from the interface into the bulk material. The severity of these oscillations increases with the order of the scheme. This is a direct consequence of the lack of discrete combinatorial consistency in these discretizations.


**Failure for porous materials (infinite contrast):** For highly porous microstructures (e.g., bound sand with approximately 40% porosity), higher-order FD schemes fail to converge entirely. The Krylov solver residual decreases initially but then stalls, similar to the continuous Moulinec-Suquet discretization. In benchmark tests, only the staggered grid and 2nd-order central differences achieved convergence for such microstructures.


**Suitability restricted to small phase contrast:** Due to the lack of discrete combinatorial consistency, higher-order FD schemes are primarily suitable for problems with small contrast between phases. They excel for smooth microstructures without material property jumps (e.g., arising from non-convex energy minimization) but should not be used for high-contrast composites.


**Absorbed scaling factors in frequency vector expressions:** The standard algorithmic summary absorbs global scaling factors (1/6 for 4th-order, 1/27720 for 12th-order) into the frequency vector coefficients. If these are not consistently handled, the effective stiffness scaling will be incorrect. The absorbed form is convenient for implementation but obscures the connection to the underlying finite difference stencil weights.


## 5. References
- Schneider (2021) — Review of nonlinear FFT-based computational homogenization, higher-order finite difference discretizations
- Mueller (1998) — Original proposal for replacing continuous derivatives with finite differences in FFT homogenization
- Berbenni, Taupin, Djaka, Fressengeas (2018) — 2nd-order central difference scheme for spectral elasto-static problems

