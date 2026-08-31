---
id: fft-composite-voxels
title: Composite Voxel Technique
domain: fft-galerkin
subdomain: discretization
tags:
- discretization
- fft-galerkin
- homogenization
- micromechanics
- interface-treatment
- composite-voxels
- laminate
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-discretization-moulinec-suquet
  type: requires
  weight: 1.0
  note: Composite voxels augment the standard voxelized discretization at material interfaces
- to: fft-galerkin-basics
  type: requires
  weight: 0.8
  note: Technique applies within the Galerkin or collocation FFT framework on uniform grids
- to: fft-reference-medium
  type: requires
  weight: 0.7
  note: Hashin-Shtrikman variational origin connects composite voxels to reference medium theory
- to: fft-periodic-bc
  type: requires
  weight: 0.7
  note: Operates within the periodic FFT framework on regular grids
- to: fft-finite-strain
  type: feeds-into
  weight: 0.6
  note: Extended to finite strains for industrial-scale simulations
context_size: medium
reading_priority: full
load_with:
- fft-discretization-moulinec-suquet
- fft-galerkin-basics
content_ref: null
akms_schema: v2
---

# Composite Voxel Technique

## Summary
The composite voxel technique addresses the accuracy and resolution limitations of standard FFT-based homogenization at material interfaces by incorporating sub-voxel scale information directly into the regular grid. Instead of assigning a single material phase to each voxel, interface voxels straddling material boundaries are modeled as miniature two-phase laminates with effective stiffness computed from the sub-voxel volume fractions and the approximate interface normal vector. For finite phase contrast, the laminate mixing rule produces the most accurate results; for porous (void) voxels, Voigt averaging is preferred, and for rigid inclusions, Reuss averaging yields the best results. The technique originates from the Hashin-Shtrikman variational principle applied with voxel-wise constant polarization fields. It has been extended to finite strains, inelastic constitutive behavior (requiring discrete internal variables per phase within composite voxels), and crystal plasticity. The method enables significant grid coarsening while maintaining accuracy, making industrial-scale FFT simulations feasible.


## 1. Core Concept
Standard FFT-based methods assign a single material property to each voxel, creating a staircase approximation of curved material interfaces that requires very fine grids for adequate resolution. The composite voxel technique replaces this binary assignment at interface voxels with an effective stiffness derived from a two-phase rank-1 laminate model. Each composite voxel is characterized by (1) the sub-voxel volume fractions of the constituent phases and (2) an interface normal vector approximating the average geometric orientation of the material boundary within the voxel. The conceptual origin traces to Brisard and Dormieux's application of the Hashin-Shtrikman variational principle with voxel-wise constant polarization fields, which naturally produces a sub-voxel averaging rule: $(C_{N,0}(\mathbf{y}) - \mathbf{C}^0)^{-1} = \frac{1}{\text{vol}(V)} \int_V (\mathbf{C}(\mathbf{x}) - \mathbf{C}^0)^{-1}\, d\mathbf{x}$. This Hashin-Shtrikman-derived averaging brought attention to the necessity of handling sub-voxel material distributions accurately, directly triggering the development of composite voxel methods. For inelastic materials, the composite voxel introduces discrete internal variables for each phase and solves the material evolution equations on the laminate sub-structure, effectively creating a nested homogenization at the sub-voxel scale.


## 2. Mathematical Formulation
The composite voxel technique replaces the standard single-phase voxel assignment at material interfaces with an effective stiffness derived from laminate mixing theory. The Hashin-Shtrikman variational principle provides the theoretical foundation, yielding a natural sub-voxel averaging rule. For finite contrast, the rank-1 laminate formula gives optimal accuracy; for extreme contrasts, simpler Voigt or Reuss bounds are used.


**Hashin-Shtrikman sub-voxel averaging rule:**

$$
(\mathbf{C}_{N,0}(\mathbf{y}) - \mathbf{C}^0)^{-1} = \frac{1}{\text{vol}(V)} \int_V (\mathbf{C}(\mathbf{x}) - \mathbf{C}^0)^{-1}\, d\mathbf{x}
$$

where C_{N,0}(y) is the effective stiffness at voxel y, C0 is the reference stiffness, V is the voxel volume, C(x) is the local stiffness

**Rank-1 laminate effective stiffness (most accurate for finite contrast):**

$$
[INSUFFICIENT SOURCE]
$$

where C_lam is the effective laminate stiffness, C_1 and C_2 are the phase stiffnesses, f is the volume fraction of phase 1, n is the interface normal vector. The exact formula involves the acoustic tensor N_{ik} = n_j (C_2)_{ijkl} n_l and a planar Green's operator constructed from N^{-1}. The formula is given in Kabel, Merkert, Schneider (2015) but is not reproduced in the review sources available in this notebook.

**Voigt average (upper bound, preferred for porous voxels):**

$$
\mathbf{C}_{\text{Voigt}} = \sum_{\alpha} f_\alpha\, \mathbf{C}_\alpha
$$

where f_alpha are the sub-voxel volume fractions, C_alpha are the constituent phase stiffnesses

**Reuss average (lower bound, preferred for rigid inclusion voxels):**

$$
\mathbf{C}_{\text{Reuss}}^{-1} = \sum_{\alpha} f_\alpha\, \mathbf{C}_\alpha^{-1}
$$

where f_alpha are the sub-voxel volume fractions, C_alpha are the constituent phase stiffnesses

**Notation:**

- $\mathbf{C}_{N,0}$ — Effective stiffness of a composite voxel (depends on reference medium C0)
- $\mathbf{C}^0$ — Homogeneous reference medium stiffness
- $\mathbf{C}_\alpha$ — Stiffness tensor of phase alpha
- $f_\alpha$ — Sub-voxel volume fraction of phase alpha within the composite voxel
- $\mathbf{n}$ — Approximate interface normal vector within the composite voxel
- $V$ — Volume of the voxel


## 3. Algorithmic Implementation
Not applicable — this is a concept and discretization technique node. The composite voxel stiffness replaces the standard single-phase stiffness in the constitutive evaluation step of any FFT solver (basic scheme, Krylov, Newton). For inelastic materials, the laminate sub-problem is solved locally within each composite voxel at each constitutive evaluation.

## 4. Known Pitfalls
**Laminate formula fails at extreme phase contrast:** The two-phase laminate mixing rule produces the most accurate results for media with finite phase contrast but loses its accuracy advantage at extreme or infinite contrast ratios. For voxels intersecting pores (voids), Voigt averaging is more advantageous than the laminate formula. For voxels intersecting rigid inclusions, Reuss averaging yields better results. Selecting the wrong mixing rule for a given contrast regime degrades solution accuracy.


**Interface normal approximation error:** The laminate mixing rule requires an interface normal vector that approximates the average geometric normal between constituents within each voxel. This approximation cannot perfectly capture highly curved interfaces, complex geometries, or multiple intersecting boundaries within a single voxel. The accuracy of the composite voxel stiffness depends directly on the quality of this normal vector estimation.


**Inelastic extension introduces computational complexity:** Extending composite voxels to inelastic constitutive behavior requires introducing discrete internal variables for every phase within each composite voxel and solving the material evolution equations on the laminate sub-structure. This effectively creates a nested homogenization problem at the sub-voxel scale, significantly increasing the computational cost and implementation complexity of the constitutive evaluation step.


**Dependence on reference medium (Hashin-Shtrikman origin):** The Hashin-Shtrikman-derived averaging rule for composite voxel stiffness depends explicitly on the reference medium $\mathbf{C}^0$. While the converged solution should be independent of this choice, the effective stiffness assigned to each composite voxel changes with the reference medium, which can affect convergence behavior and intermediate iterates. This contrasts with single-phase voxels where the local stiffness is independent of the reference medium.


## 5. References
- Schneider (2021) — Review of nonlinear FFT-based computational homogenization, composite voxel technique
- Kabel, Merkert, Schneider (2015) — Composite voxels with laminate mixing for linear elasticity
- Kabel, Fink, Schneider (2017) — Extension of composite voxels to finite strains
- Schneider (2019) — Composite voxels for inelastic constitutive behavior with discrete internal variables

