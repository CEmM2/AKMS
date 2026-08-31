---
id: fft-polycrystal
title: FFT for Polycrystalline Materials
domain: fft-galerkin
subdomain: coupled-problems
tags:
- fft-galerkin
- crystal-plasticity
- polycrystal
- homogenization
- spectral
- plasticity
status: established
confidence: 0.9
source: hybrid
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: Mechanical equilibrium solved via Lippmann-Schwinger with anisotropic crystal stiffness
- to: fft-green-operator
  type: requires
  weight: 0.9
  note: Green's operator used in the iterative solver for polycrystal equilibrium
- to: fft-reference-medium
  type: requires
  weight: 0.7
  note: Reference medium choice affects convergence; contrast is limited to single-crystal anisotropy
- to: plasticity-general-return-mapping
  type: requires
  weight: 0.5
  note: Implicit return mapping is an alternative to the explicit Euler integration described inline; see this node for implicit
    algorithms
- to: fft-solver-basic-scheme
  type: feeds-into
  weight: 0.5
  note: Basic scheme is feasible for polycrystals due to low anisotropy contrast
- to: fft-solver-newton-krylov
  type: feeds-into
  weight: 0.8
  note: Newton-type solvers preferred to minimize expensive crystal plasticity evaluations
- to: fft-finite-strain
  type: feeds-into
  weight: 0.8
  note: Finite-strain polycrystal simulations use the total Lagrangian framework with F and P
- to: kinematics-multiplicative-decomp
  type: requires
  weight: 0.5
  note: Multiplicative decomposition F=FeFp is included inline; this edge is for detailed kinematics theory
context_size: large
reading_priority: full
load_with:
- fft-lippmann-schwinger
content_ref: null
akms_schema: v2
---

# FFT for Polycrystalline Materials

## Summary
FFT homogenization of polycrystalline materials computes the local and macroscopic mechanical response of a polycrystalline aggregate where all grains are the same material differing only in crystallographic orientation. The material contrast is limited to the single-crystal anisotropy, making the basic scheme feasible without severe ill-conditioning. The viscoplastic flow rule $\dot{\boldsymbol{\varepsilon}}^p = \sum_s \mathrm{sym}(\mathbf{m}^s) \dot{\gamma}^s_0 (\mathbf{m}^s : \boldsymbol{\sigma}' / \tau^s_c)^n$ governs plastic deformation on each slip system, with the Schmid tensor $\mathbf{m}^s(\mathbf{x})$ rotated by the local grain orientation. The EVP-FFT framework extends this to include elastic strains via $\boldsymbol{\sigma} = \mathbf{C}(\mathbf{x}) : (\boldsymbol{\varepsilon} - \boldsymbol{\varepsilon}^p)$. Quasi-Newton solvers are strongly preferred because crystal plasticity constitutive evaluation is the computational bottleneck. FFT polycrystal models naturally capture intragranular heterogeneity, strain localization, and texture evolution, and accept EBSD microstructural images directly without meshing.


## 1. Core Concept
In FFT polycrystal simulations, the representative volume element is composed of multiple grains of the same material, where the spatially varying crystallographic orientation defines the local elastic stiffness tensor $\mathbf{C}(\mathbf{x})$ and the Schmid tensors $\mathbf{m}^s(\mathbf{x})$ for each slip system. The orientation field enters the constitutive law by rotating the slip systems into the global frame, setting the resolved shear stress that drives plastic flow, and by rotating the anisotropic elastic stiffness. Two main model classes exist: VP-FFT (viscoplastic only, no elastic strains) and EVP-FFT (elasto-viscoplastic, including elastic strains). The phase contrast in polycrystals is restricted to the inner anisotropy of the single crystal, which is relatively low compared to composite materials. This allows the basic scheme to work, but the extreme computational cost of crystal plasticity constitutive evaluations makes quasi-Newton or Newton-type solvers strongly preferred to minimize the number of evaluations. A key advantage over mean-field models (VPSC) is the ability to capture intragranular heterogeneity, grain neighborhood interactions, and complex strain localization patterns.


## 2. Mathematical Formulation
The polycrystal FFT framework combines the standard Lippmann-Schwinger mechanical equilibrium with crystal plasticity constitutive laws evaluated at each voxel. The orientation field rotates both the elastic stiffness and the slip system Schmid tensors from the crystal reference frame into the sample frame. The viscoplastic flow rule sums shear contributions from all active slip systems governed by a power-law relation. Hardening is tracked through evolution of the critical resolved shear stress, either phenomenologically or through physically-based dislocation density models.


**Resolved shear stress:**

$$
\tau^s(\mathbf{x}) = \mathbf{m}^s(\mathbf{x}) : \boldsymbol{\sigma}'(\mathbf{x})
$$

where tau^s is the resolved shear stress on slip system s, m^s is the Schmid tensor, sigma' is the deviatoric Cauchy stress

**Viscoplastic flow rule (VP-FFT):**

$$
\dot{\boldsymbol{\varepsilon}}^p(\mathbf{x}) = \sum_s \mathrm{sym}(\mathbf{m}^s(\mathbf{x}))\,\dot{\gamma}^s_0 \left(\frac{\mathbf{m}^s(\mathbf{x}) : \boldsymbol{\sigma}'(\mathbf{x})}{\tau^s_c(\mathbf{x})}\right)^n
$$

where m^s is the Schmid tensor for slip system s, gamma_0_dot_s is the reference shear rate, sigma' is deviatoric stress, tau_c^s is critical resolved shear stress, n is the power-law exponent (inverse rate sensitivity)

**Elasto-viscoplastic constitutive law (EVP-FFT):**

$$
\boldsymbol{\sigma}(\mathbf{x}) = \mathbf{C}(\mathbf{x}) : (\boldsymbol{\varepsilon}(\mathbf{x}) - \boldsymbol{\varepsilon}^p(\mathbf{x}))
$$

where C(x) is the local anisotropic elastic stiffness rotated by grain orientation, epsilon is total strain, epsilon^p is plastic strain

**Schmid tensor from orientation:**

$$
\mathbf{m}^s(\mathbf{x}) = \mathbf{R}^*(\mathbf{x})\,\mathbf{m}^s_0\,\mathbf{R}^{*T}(\mathbf{x}), \quad \mathbf{m}^s_0 = \mathbf{d}^s_0 \otimes \mathbf{n}^s_0
$$

where R* is the lattice rotation matrix, m^s_0 is the Schmid tensor in the crystal frame, d^s_0 is the slip direction, n^s_0 is the slip plane normal

**Stiffness tensor rotation (crystal to sample frame):**

$$
C_{ijkl}^{\mathrm{sample}}(\mathbf{x}) = R^*_{im}(\mathbf{x})\, R^*_{jn}(\mathbf{x})\, R^*_{ko}(\mathbf{x})\, R^*_{lp}(\mathbf{x})\, C_{mnop}^{\mathrm{crystal}}
$$

where R*_{ij} are the components of the lattice rotation matrix, C^crystal is the single-crystal stiffness in the crystal frame. The compact notation R* star C_crystal star R*^T denotes this four-index Rayleigh product. In Voigt notation this becomes [C^sample] = [M] [C^crystal] [M]^T where [M] is the 6x6 Bond transformation matrix constructed from R*.

**Phenomenological hardening (Voce-type):**

$$
\dot{\tau}^s_c = \sum_{s'} h^{ss'} |\dot{\gamma}^{s'}|, \quad h^{ss'} = q^{ss'}\left[h_0\left(1 - \frac{\tau^s_c}{\tau_{\mathrm{sat}}}\right)^a\right]
$$

where h^{ss'} is the hardening moduli matrix, q^{ss'} is the latent hardening ratio (1 for coplanar, q for non-coplanar systems), h_0 is initial hardening rate, tau_sat is saturation stress, a is hardening exponent

**Dislocation density hardening law:**

$$
\tau^s_c = \mu\,b^s \sqrt{\sum_{s'} h^{ss'}\,\rho^{s'}}
$$

where mu is shear modulus, b^s is Burgers vector magnitude, h^{ss'} is slip system interaction matrix, rho^{s'} is total dislocation density on system s'

**SSD dislocation density evolution:**

$$
\dot{\rho}^s_{\mathrm{SSD}} = \frac{1}{b^s}\left(\frac{1}{l^s} - 2y_c\,\rho^s_{\mathrm{SSD}}\right)|\dot{\gamma}^s|, \quad l^s = \frac{K}{\sqrt{\sum_{s' \neq s}(\rho^{s'}_{\mathrm{SSD}} + \rho^{s'}_{\mathrm{GND}})}}
$$

where rho_SSD is statistically stored dislocation density, y_c is annihilation distance, l^s is mean free path, K is material constant

**GND dislocation density (from curl of plastic strain):**

$$
\boldsymbol{\alpha} = -\nabla \times \boldsymbol{\varepsilon}^p, \quad \bar{\rho}_{\mathrm{GND}} = (\mathbf{A}^T\mathbf{A})^{-1}\mathbf{A}^T\bar{\boldsymbol{\alpha}}
$$

where alpha is the polar dislocation density tensor computed in Fourier space, A is the projection matrix for GND density via L2 minimization

**Finite-strain multiplicative decomposition:**

$$
\mathbf{F} = \mathbf{F}_e\,\mathbf{F}_p, \quad \dot{\mathbf{F}}_p = \mathbf{L}_p\,\mathbf{F}_p, \quad \mathbf{L}_p = \sum_s \dot{\gamma}^s\,\mathbf{m}^s_0
$$

where F is total deformation gradient, F_e is elastic part, F_p is plastic part, L_p is plastic velocity gradient

**Texture update (lattice rotation):**

$$
\mathbf{W}_e = \mathbf{W} - \mathbf{W}_p, \quad \mathbf{W}_p = \sum_s \dot{\gamma}^s\,\mathrm{skew}(\mathbf{m}^s_0), \quad \dot{\mathbf{R}}^* = \mathbf{W}_e\,\mathbf{R}^*
$$

where W is total continuum spin, W_p is plastic spin, W_e is elastic (lattice) spin, R* is lattice rotation

**Notation:**

- $\mathbf{m}^s$ — Schmid tensor for slip system s
- $\dot{\gamma}^s_0$ — Reference shear rate
- $\tau^s_c$ — Critical resolved shear stress for slip system s
- $n$ — Power-law exponent (inverse rate sensitivity)
- $\mathbf{R}^*$ — Lattice rotation matrix tracking crystallographic orientation
- $\rho_{\mathrm{SSD}}$ — Statistically stored dislocation density
- $\rho_{\mathrm{GND}}$ — Geometrically necessary dislocation density
- $\mathbf{L}_p$ — Plastic velocity gradient in the intermediate configuration
- $\tau^s$ — Resolved shear stress on slip system s
- $\mathbf{C}_{\mathrm{crystal}}$ — Single-crystal elastic stiffness tensor in the crystal reference frame
- $R^*_{im}$ — Components of the lattice rotation matrix (Rayleigh product index notation)
- $\star$ — Rayleigh product operator — shorthand for four-index rotation C_ijkl = R_im R_jn R_ko R_lp C_mnop
- $[M]$ — 6x6 Bond transformation matrix for Voigt rotation of stiffness, constructed from R*
- $h_0$ — Initial hardening rate in Voce hardening law
- $\tau_{\mathrm{sat}}$ — Saturation stress in Voce hardening law
- $q^{ss'}$ — Latent hardening ratio between slip systems
- $\Delta t_{\mathrm{crit}}$ — Critical time step for explicit Euler stability of viscoplastic flow


## 3. Algorithmic Implementation
**Algorithm: EVP-FFT Polycrystal Simulation**

$$
\begin{algorithmic}
\State $Initialize \colon \mathbf{R}^*(\mathbf{x}) \text{ from EBSD/orientation data}, \; \boldsymbol{\varepsilon}^p_0 = \mathbf{0}, \; \rho^s_0 = \rho_{\mathrm{init}}$
\State $C_{ijkl}(\mathbf{x}) = R^*_{im} R^*_{jn} R^*_{ko} R^*_{lp}\, C_{mnop}^{\mathrm{crystal}}, \; \mathbf{m}^s(\mathbf{x}) = \mathbf{R}^*(\mathbf{x})\,\mathbf{m}^s_0\,\mathbf{R}^{*T}(\mathbf{x})$
\For{$\text{each load step } n = 1, 2, \ldots$}
    \While{$\|\mathrm{div}\,\boldsymbol{\sigma}_k\| > \mathrm{tol}$}
        \State $\boldsymbol{\sigma}_k(\mathbf{x}) = \mathbf{C}(\mathbf{x}) \colon (\boldsymbol{\varepsilon}_k(\mathbf{x}) - \boldsymbol{\varepsilon}^p(\mathbf{x}))$
        \State $\dot{\gamma}^s = \dot{\gamma}^s_0 \left(\frac{\mathbf{m}^s(\mathbf{x}) \colon \boldsymbol{\sigma}'(\mathbf{x})}{\tau^s_c(\mathbf{x})}\right)^n$
        \State $\dot{\boldsymbol{\varepsilon}}^p(\mathbf{x}) = \sum_s \mathrm{sym}(\mathbf{m}^s(\mathbf{x}))\,\dot{\gamma}^s$
        \State $\boldsymbol{\varepsilon}^p_{n+1}(\mathbf{x}) = \boldsymbol{\varepsilon}^p_n(\mathbf{x}) + \Delta t\,\dot{\boldsymbol{\varepsilon}}^p(\mathbf{x})$
        \State $\hat{\boldsymbol{\tau}}_k = \mathcal{F}\{\boldsymbol{\sigma}_k - \mathbf{C}^0 \colon \boldsymbol{\varepsilon}_k\}$
        \State $\hat{\boldsymbol{\varepsilon}}_{k+1}(\boldsymbol{\xi}) = \bar{\boldsymbol{\varepsilon}} - \hat{\boldsymbol{\Gamma}}^0(\boldsymbol{\xi}) \colon \hat{\boldsymbol{\tau}}_k(\boldsymbol{\xi})$
        \State $\boldsymbol{\varepsilon}_{k+1}(\mathbf{x}) = \mathcal{F}^{-1}\{\hat{\boldsymbol{\varepsilon}}_{k+1}\}$
    \EndWhile
    \State $\tau^s_c \gets \mu\,b^s\sqrt{\sum_{s'} h^{ss'}\,\rho^{s'}}, \quad \dot{\rho}^s_{\mathrm{SSD}} = \frac{1}{b^s}\left(\frac{1}{l^s} - 2y_c\,\rho^s_{\mathrm{SSD}}\right)|\dot{\gamma}^s|$
    \State $\mathbf{W}_p = \sum_s \dot{\gamma}^s\,\mathrm{skew}(\mathbf{m}^s_0), \; \mathbf{W}_e = \mathbf{W} - \mathbf{W}_p, \; \mathbf{R}^* \gets \mathbf{R}^* + \Delta t\,\mathbf{W}_e\,\mathbf{R}^*$
\EndFor
\end{algorithmic}
$$

**Taichi Mapping:**
The constitutive evaluation (stress, shear rates, plastic strain update) is the bottleneck and is embarrassingly parallel across voxels on GPU. Each voxel stores the rotation matrix R*, plastic strain, and dislocation densities as ti.field history variables. FFT/iFFT for the Lippmann-Schwinger update via cuFFT. Quasi-Newton outer solver recommended to minimize the number of constitutive evaluations per load step.


## 4. Known Pitfalls
**Crystal plasticity evaluation is the computational bottleneck:** Evaluating the nonlinear viscoplastic constitutive law at each voxel (resolving shear rates across all slip systems, updating dislocation densities) is far more expensive than the FFT solver operations. The basic scheme requires a full constitutive evaluation at every iteration, making it inefficient. Quasi-Newton or Newton-type solvers that minimize the number of constitutive evaluations are strongly preferred.


**Texture update rotation overhead:** At finite strains, tracking the continuous rotation of the crystal lattice via the elastic spin $\mathbf{W}_e$ introduces a time-consuming rotation step at each voxel during constitutive evaluation. This rotation overhead is absent in isotropic composite simulations and can dominate the computational cost for large polycrystalline aggregates.


**Gibbs oscillations at grain boundaries:** Sharp transitions in crystallographic orientation at grain boundaries produce spurious high-frequency ringing (Gibbs phenomenon) in the stress and strain fields when using continuous Fourier derivatives. The spatial variability of local fields can be artificially larger than in FEM. Discrete differentiation rules (e.g., Willot rotated staggered grid) are needed to smooth fields and maintain accuracy without prohibitively fine grids.


**Strain gradient plasticity requires higher-order derivatives:** Physically-based models that compute geometrically necessary dislocation (GND) densities from $\boldsymbol{\alpha} = -\nabla \times \boldsymbol{\varepsilon}^p$ require computing curl operators in Fourier space. These higher-order derivatives amplify Gibbs oscillations at grain boundaries, demanding even more aggressive smoothing or finer resolution than standard crystal plasticity simulations.


**Explicit Euler stability constraint for viscoplastic integration:** When explicit (forward) Euler is used to integrate the viscoplastic flow rule, the critical time step is bounded by $\Delta t_{\mathrm{crit}} \propto \tau^s_c / (n \mu \dot{\gamma}_{\mathrm{active}})$, where $n$ is the power-law exponent and $\mu$ is the shear modulus. As $n$ increases toward rate-independent behavior, $\Delta t_{\mathrm{crit}}$ shrinks drastically and the integration becomes unstable. Implicit backward Euler with a return-mapping algorithm is strongly preferred for large $n$. No CFL-type spatial constraint applies because EVP-FFT is quasi-static (no inertial wave propagation). For the lattice rotation update $\mathbf{R}^* \gets \mathbf{R}^* + \Delta t \mathbf{W}_e \mathbf{R}^*$, the explicit Euler does not preserve orthogonality of $\mathbf{R}^*$; for large rotation increments, use the exponential map $\mathbf{R}^* \gets \exp(\mathbf{W}_e \Delta t) \mathbf{R}^*$ instead.


**Basic scheme convergence adequate but slow for nonlinear power laws:** While the low phase contrast (only single-crystal anisotropy) makes the basic scheme stable for polycrystals, highly nonlinear viscoplastic power laws with large $n$ exponents degrade convergence significantly. The basic scheme adds nonlinearity to the implicit equation without tangent information, resulting in many more iterations than necessary.


## 5. References
- Schneider (2021) -- FFT polycrystal overview, solver recommendations, VP-FFT and EVP-FFT
- Lebensohn (2001) -- VP-FFT framework for polycrystal plasticity
- Lebensohn et al. (2012) -- EVP-FFT with elasto-viscoplastic constitutive law
- Lucarini et al. (2022) -- Finite-strain polycrystal FFT, DBFFT approach
- Lebensohn and Needleman (2016) -- Strain gradient crystal plasticity with GND via FFT

