---
id: fft-mixed-bc
title: Mixed Boundary Conditions & Stress Control
domain: fft-galerkin
subdomain: boundary-conditions
tags:
- boundary-conditions
- stress-control
- mixed-loading
- fft-galerkin
- homogenization
- spectral
- non-periodic
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-periodic-bc
  type: requires
  weight: 1.0
  note: Mixed BCs extend the standard periodic BC framework with stress/strain component selection
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: Mixed control modifies the Lippmann-Schwinger equation with projection operators
- to: fft-reference-medium
  type: requires
  weight: 0.8
  note: Reference compliance D0 enters the modified L-S equation for mixed loading
- to: fft-solver-basic-scheme
  type: feeds-into
  weight: 0.8
  note: Modified L-S equation can be solved with any standard FFT solver
- to: fft-dual-scheme
  type: requires
  weight: 0.7
  note: Stress control is naturally handled in the dual formulation; mixed BCs bridge primal and dual
- to: fft-finite-strain
  type: feeds-into
  weight: 0.6
  note: Mixed loading is essential for realistic finite-strain simulations (e.g., uniaxial tension)
context_size: medium
reading_priority: full
load_with:
- fft-periodic-bc
- fft-lippmann-schwinger
content_ref: null
akms_schema: v2
---

# Mixed Boundary Conditions & Stress Control

## Summary
Standard FFT-based homogenization prescribes a fully determined macroscopic strain tensor, but many practical simulations require controlling macroscopic stress components (e.g., zero lateral stress in uniaxial tension) or imposing non-periodic boundary conditions. Mixed boundary conditions are formulated using orthogonal complementary projection operators P and Q that partition the macroscopic loading into strain-controlled and stress-controlled components. This leads to a modified Lippmann-Schwinger equation incorporating the reference compliance and a volume-averaging stress projection term. For non-periodic problems, the Fourier Continuation (FC) method constructs smooth periodic extensions via artificial boundary points, while Bloch boundary conditions handle long-wavelength periodic fluctuations across multiple unit cells.


## 1. Core Concept
The classical Lippmann-Schwinger equation is driven by a fully prescribed macroscopic strain $\bar{\boldsymbol{\varepsilon}}$, but real experiments often require mixed control: some macroscopic strain components are prescribed while complementary macroscopic stress components are constrained. The mixed formulation introduces two orthogonal complementary projection operators $\mathbb{P}$ and $\mathbb{Q} = \mathbf{Id} - \mathbb{P}$ acting on symmetric tensors $\text{Sym}(d)$. Operator $\mathbb{P}$ selects the strain-controlled components ($\mathbb{P} \colon \bar{\boldsymbol{\varepsilon}} = \bar{\boldsymbol{\varepsilon}}$) and $\mathbb{Q}$ selects the stress-controlled components ($\mathbb{Q} \colon \bar{\boldsymbol{\sigma}} = \bar{\boldsymbol{\sigma}}$). The cell problem under mixed control simultaneously enforces equilibrium, the prescribed strain components via $\mathbb{P}$, and the prescribed stress components via $\mathbb{Q}$ applied to the volume-averaged stress. The resulting modified Lippmann-Schwinger equation augments the standard Green operator with a compliance-weighted stress projection term, enabling any existing FFT solver to handle mixed loading without fundamental algorithmic changes. An older, less efficient approach iteratively corrected the fully prescribed macroscopic strain at each step based on the residual of the target macroscopic stress.


## 2. Mathematical Formulation
The mixed equilibrium problem seeks a macroscopic strain variable $\mathbf{E}$ and displacement fluctuation $\mathbf{u}$ satisfying equilibrium, the strain-controlled constraint via projector $\mathbb{P}$, and the stress-controlled constraint via projector $\mathbb{Q}$ applied to the volume-averaged stress. The system is reformulated into a modified Lippmann-Schwinger equation by incorporating the reference compliance and the stress projection into the operator.


**Mixed equilibrium problem — divergence condition:**

$$
\text{div}\, \frac{\partial w}{\partial \boldsymbol{\varepsilon}}(\cdot, \mathbf{E} + \nabla^s \mathbf{u}) = 0
$$

where w is the free energy density, E is the macroscopic strain variable, u is the displacement fluctuation

**Strain-controlled components:**

$$
\mathbb{P} \colon \mathbf{E} = \bar{\boldsymbol{\varepsilon}}
$$

where P is the projection operator selecting strain-controlled components, epsilon-bar is the prescribed macroscopic strain

**Stress-controlled components (volume-averaged):**

$$
\mathbb{Q} \colon \frac{1}{\text{vol}(Y)} \int_Y \frac{\partial w}{\partial \boldsymbol{\varepsilon}}(\mathbf{x}, \mathbf{E} + \nabla^s \mathbf{u})\, d\mathbf{x} = \bar{\boldsymbol{\sigma}}
$$

where Q = Id - P is the complementary projector selecting stress-controlled components, sigma-bar is the prescribed macroscopic stress

**Modified Lippmann-Schwinger equation for mixed loading:**

$$
\boldsymbol{\varepsilon} + \left(\boldsymbol{\Gamma}^0 + \mathbf{D}^0 \colon \mathbb{Q} \colon \frac{1}{\text{vol}(Y)} \int_Y \cdot\, d\mathbf{x}\right) \colon \left(\frac{\partial w}{\partial \boldsymbol{\varepsilon}}(\cdot, \boldsymbol{\varepsilon}) - \mathbf{C}^0 \colon \boldsymbol{\varepsilon}\right) = \bar{\boldsymbol{\varepsilon}} + \mathbf{D}^0 \colon \bar{\boldsymbol{\sigma}}
$$

where Gamma0 is the Green operator, D0 = (1/alpha_0) Id is the reference compliance, C0 = alpha_0 Id is the reference stiffness

**Orthogonal projector admissibility:**

$$
\mathbb{P} + \mathbb{Q} = \mathbf{Id}, \quad \mathbb{P} \colon \mathbb{Q} = \mathbf{0}
$$

where P and Q are complementary orthogonal projectors on Sym(d); pure strain control sets Q=0, pure stress control sets P=0

**Notation:**

- $\mathbb{P}$ — Projection operator selecting strain-controlled macroscopic components
- $\mathbb{Q}$ — Complementary projection operator selecting stress-controlled macroscopic components
- $\bar{\boldsymbol{\varepsilon}}$ — Prescribed macroscopic strain (strain-controlled components)
- $\bar{\boldsymbol{\sigma}}$ — Prescribed macroscopic stress (stress-controlled components)
- $\mathbf{E}$ — Macroscopic strain variable (unknown for stress-controlled components)
- $\mathbf{D}^0$ — Reference compliance tensor, D0 = (C0)^{-1}
- $\boldsymbol{\Gamma}^0$ — Green operator of the reference medium
- $w$ — Local condensed free energy density


## 3. Algorithmic Implementation
Not applicable — this is a concept node describing the mathematical formulation of mixed boundary conditions. The modified Lippmann-Schwinger equation is solved using standard FFT solvers (basic scheme, Krylov, Newton) with the augmented operator replacing the standard Green operator.

## 4. Known Pitfalls
**Projector construction for non-standard loading:** The orthogonal projectors $\mathbb{P}$ and $\mathbb{Q}$ must be constructed carefully for each loading scenario. For standard cases (uniaxial tension, biaxial loading), the projectors select individual tensor components, but for more complex loading paths (e.g., proportional loading in a rotated frame), constructing the correct projectors requires care to maintain orthogonality and admissibility conditions.


**Non-periodic problems require specialized extensions:** The FFT framework strictly requires periodicity. Non-periodic problems (finite-sized components, traction-free surfaces, wave scattering) require the Fourier Continuation (FC) method, which appends artificial points at boundaries to construct smooth periodic extensions, or Bloch boundary conditions for long-wavelength fluctuations. Both add significant implementation complexity and computational cost.


**Iterative strain correction (legacy approach) is inefficient:** An older approach to stress control iteratively corrected the fully prescribed macroscopic strain at each solver step based on the residual between computed and target macroscopic stress. This nested iteration is significantly less efficient than the projector-based modified Lippmann-Schwinger approach, which handles mixed loading within a single unified iteration.


**Convergence may differ from pure strain control:** The modified Lippmann-Schwinger operator includes additional terms (compliance-weighted stress projection) that change the spectral properties of the iteration operator. Convergence behavior may differ from the standard strain-controlled case, particularly near material instabilities or for nearly incompressible materials where the compliance tensor becomes ill-conditioned.


## 5. References
- Schneider (2021) — Review of nonlinear FFT-based computational homogenization, mixed boundary conditions formulation
- Kabel, Fliegener, Schneider (2016) — Mixed boundary conditions for FFT-based homogenization at finite strains
- Lucarini, Segurado (2019) — FFT-based approach with mixed stress-strain control

