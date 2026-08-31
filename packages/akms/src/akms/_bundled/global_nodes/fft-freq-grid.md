---
id: fft-freq-grid
title: Frequency Grid & Nyquist Treatment
domain: fft-galerkin
subdomain: spectral-foundations
tags:
- freq-grid
- fft-galerkin
- spectral
- discretization
- periodic-bc
- homogenization
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-galerkin-basics
  type: requires
  weight: 1.0
  note: Frequency grid is the fundamental discrete domain on which all Fourier-space operations are defined
- to: fft-green-operator
  type: feeds-into
  weight: 1.0
  note: Green's operator is evaluated pointwise on the frequency grid; Nyquist treatment directly affects operator symmetry
- to: fft-discretization-moulinec-suquet
  type: feeds-into
  weight: 0.9
  note: Moulinec-Suquet basic scheme iterates on the frequency grid using continuous frequency vectors
- to: fft-discretization-willot
  type: feeds-into
  weight: 0.8
  note: Willot's scheme modifies the frequency vector but operates on the same grid
- to: fft-discretization-staggered
  type: feeds-into
  weight: 0.8
  note: Staggered grid uses modified frequency vector defined on this grid
- to: fft-discretization-fd-highorder
  type: feeds-into
  weight: 0.8
  note: Higher-order FD schemes define trigonometric frequency vectors on this grid
- to: fft-solver-basic-scheme
  type: feeds-into
  weight: 0.7
  note: Basic scheme iteration alternates between real-space grid and frequency grid via DFT/IDFT
context_size: medium
reading_priority: full
load_with:
- fft-galerkin-basics
- fft-green-operator
content_ref: null
akms_schema: v2
---

# Frequency Grid & Nyquist Treatment

## Summary
The frequency grid defines the discrete set of integer frequency vectors on which all Fourier-space operations in FFT-based homogenization are performed. For a computational cell of dimensions $L_1 \times \ldots \times L_d$ discretized into $N_1 \times \ldots \times N_d$ voxels, the integer frequencies range from $-N_j/2$ to $N_j/2 - 1$ in each direction. The re-scaled frequency vector maps these integers to physical frequencies via $\xi_{Y,j} = 2\pi\xi_j/L_j$. Critical to correct implementation is the treatment of the Nyquist frequency ($\xi_j = -N_j/2$) on even grids, where Fourier operator symmetries are lost and artificial zeroing or redefinition of operators is required to ensure real-valued solution fields.


## 1. Core Concept
The discrete Fourier transform (DFT) maps voxel-grid fields to a finite set of complex-valued Fourier coefficients indexed by integer frequency vectors $\boldsymbol{\xi} \in Z_N$. The integer frequency set $Z_N$ is bounded by the voxel counts: $-N_j/2 \le \xi_j < N_j/2$. The physical frequency content is captured by the re-scaled frequency vector $\boldsymbol{\xi}_Y$ which accounts for the cell dimensions. All Fourier-space operators (Green's operator, projection operators, finite-difference frequency multipliers) are evaluated pointwise on $Z_N$. Two special frequencies require dedicated handling: the zero frequency $\boldsymbol{\xi} = \mathbf{0}$ (which carries the macroscopic average and must be prescribed, not computed) and the Nyquist frequencies (which exist only on even grids and break the tensor symmetries of Fourier operators). The choice between even and odd grid sizes affects whether Nyquist treatment is needed at all.


## 2. Mathematical Formulation
The frequency grid is defined by the integer frequency set $Z_N$, the real-space voxel grid $Y_N$, and the re-scaled frequency vector $\boldsymbol{\xi}_Y$ that connects the two. The DFT and its inverse map fields between these grids. The Nyquist frequencies form a special subset where operator symmetries break down.


**Integer frequency set:**

$$
Z_N = \left\{ \boldsymbol{\xi} \in \mathbb{Z}^d \;\middle|\; -N_j/2 \le \xi_j < N_j/2 \;\text{for all}\; j = 1, \ldots, d \right\}
$$

where N_j is the number of voxels in direction j, d is the spatial dimension

**Real-space voxel grid:**

$$
Y_N = \left\{ \mathbf{x} \in Y \;\middle|\; x_j = I_j L_j / N_j \;\text{for all}\; j = 1, \ldots, d \;\text{and some}\; \mathbf{I} \in \mathcal{I}_N \right\}
$$

where I_j are integer indices, L_j are cell dimensions, Y is the periodic cell

**Re-scaled frequency vector:**

$$
\boldsymbol{\xi}_Y = \left( \frac{2\pi \xi_1}{L_1}, \frac{2\pi \xi_2}{L_2}, \ldots, \frac{2\pi \xi_d}{L_d} \right)
$$

where xi_j are integer frequency indices, L_j are cell dimensions

**Discrete Fourier transform:**

$$
\hat{\boldsymbol{\tau}}(\boldsymbol{\xi}) = \frac{1}{N_1 \cdots N_d} \sum_{\mathbf{I} \in Y_N} \boldsymbol{\tau}(\mathbf{x}_\mathbf{I}) \, e^{-i\, \mathbf{x}_\mathbf{I} \cdot \boldsymbol{\xi}_Y}, \quad \boldsymbol{\xi} \in Z_N
$$

where The phase product x_I . xi_Y = 2pi sum_j I_j xi_j / N_j is independent of cell dimensions L_j

**Nyquist frequency set:**

$$
\mathcal{N} = \left\{ \boldsymbol{\xi} \in \mathbb{Z}^d \;\middle|\; \xi_j = -N_j/2 \;\text{for some}\; j = 1, \ldots, d \right\}
$$

where These frequencies exist only when N_j is even

**Nyquist treatment option 1 (zero strain coefficients):**

$$
\hat{\boldsymbol{\varepsilon}}(\boldsymbol{\xi}) = \mathbf{0} \quad \text{for all } \boldsymbol{\xi} \in \mathcal{N}
$$

where Forces the Fourier coefficients of the strain field to zero at Nyquist frequencies

**Nyquist treatment option 2 (zero stress coefficients):**

$$
\hat{\boldsymbol{\varepsilon}}(\boldsymbol{\xi}) = -(\mathbf{C}^0)^{-1} \colon \hat{\boldsymbol{\tau}}(\boldsymbol{\xi}) \quad \text{for all } \boldsymbol{\xi} \in \mathcal{N}
$$

where Forces the Fourier coefficients of the stress field to zero at Nyquist by setting varepsilon = -(C0)^{-1} colon tau

**Frequency reordering for numerical implementations:**

$$
q = \begin{cases} 0, 1, 2, \ldots, \frac{N-1}{2}, -\frac{N-1}{2}, -\frac{N-1}{2}+1, \ldots, -1 & \text{if } N \text{ even} \\ 0, 1, 2, \ldots, \frac{N}{2}, -\frac{N}{2}+1, -\frac{N}{2}+2, \ldots, -1 & \text{if } N \text{ odd} \end{cases}
$$

where Standard frequency reordering used in numerical FFT libraries to center the spectrum around zero

**Notation:**

- $Z_N$ — Set of integer frequency d-tuples
- $Y_N$ — Set of real-space voxel grid points
- $\boldsymbol{\xi}$ — Integer frequency vector
- $\boldsymbol{\xi}_Y$ — Re-scaled frequency vector incorporating cell dimensions
- $\mathcal{N}$ — Nyquist frequency set
- $N_j$ — Number of voxels in direction j
- $L_j$ — Cell dimension in direction j
- $\mathbf{C}^0$ — Reference medium stiffness tensor


## 3. Algorithmic Implementation
Not applicable as a standalone algorithm. The frequency grid is a data structure, not a procedure. Its construction and Nyquist treatment are embedded as initialization steps within all FFT-based solvers (see fft-solver-basic-scheme and related nodes).

## 4. Known Pitfalls
**Complex-valued fields from unhandled Nyquist frequencies:** On even grids, the Fourier projection operator loses its tensor symmetries at the Nyquist frequency $\xi_j = -N_j/2$. If the operator is not explicitly zeroed or redefined at these frequencies, the inverse DFT will produce fields with spurious imaginary components. This is a common implementation bug that manifests as complex-valued stress or strain fields that should be purely real.


**Even vs odd grid parity choice:** Odd grids ($N_j$ odd) avoid the Nyquist frequency issue entirely because the integer range $-(N_j-1)/2$ to $(N_j-1)/2$ is symmetric and never hits the $-N_j/2$ boundary. Some practitioners deliberately choose odd grid sizes to sidestep Nyquist treatment, but this limits grid sizes (e.g., cannot use power-of-two grids that are optimal for FFT performance). Even grids require explicit Nyquist handling but allow optimal FFT sizes.


**Zero-frequency handling:** The Green's operator formula involves division by $\|\boldsymbol{\xi}_Y\|^2$, which is singular at $\boldsymbol{\xi} = \mathbf{0}$. The zero frequency carries the macroscopic average strain $\bar{\boldsymbol{\varepsilon}}$, which is prescribed as input, not computed by the Green's operator. All operator formulas must explicitly exclude $\boldsymbol{\xi} = \mathbf{0}$ and set $\hat{\boldsymbol{\varepsilon}}(\mathbf{0}) = \bar{\boldsymbol{\varepsilon}}$.


**Aliasing from DFT approximation of continuous Fourier transform:** Substituting the continuous Fourier transform with the DFT introduces aliasing because only a finite number of frequencies are represented. For piecewise-constant voxel fields, the exact Fourier transform involves a sinc-weighted DFT, not the raw DFT. Using the raw DFT to approximate spatial derivatives introduces high-frequency noise and Gibbs phenomena (ringing artifacts). This aliasing is particularly severe at sharp material interfaces.


**Cell-dimension independence of phase product:** The DFT phase product $\mathbf{x}_\mathbf{I} \cdot \boldsymbol{\xi}_Y = 2\pi \sum_j I_j \xi_j / N_j$ is independent of the physical cell dimensions $L_j$. This means the DFT itself is purely a function of the grid resolution $N_j$, while the cell dimensions $L_j$ enter only through the re-scaled frequency vector in operator evaluations. Incorrectly incorporating $L_j$ into the DFT phase computation is a subtle but critical bug.


## 5. References
- Schneider (2021) — Frequency grid construction, DFT definition, and Nyquist treatment in FFT-based homogenization
- Lucarini, Segurado, et al. (2022) — DFT discretization, frequency reordering, and aliasing effects in FFT homogenization
- Moulinec and Suquet (1998) — Original Nyquist frequency treatment and odd-grid operator redefinition

