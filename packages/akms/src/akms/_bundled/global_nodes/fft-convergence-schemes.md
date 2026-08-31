---
id: fft-convergence-schemes
title: Convergence Criteria & Solver Comparison
domain: fft-galerkin
subdomain: solver-algorithms
tags:
- solvers
- fft-galerkin
- convergence
- iterative
- benchmarks
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-solver-basic-scheme
  type: requires
  weight: 0.8
  note: Baseline solver in convergence comparisons; convergence rate scales linearly with contrast
- to: fft-solver-krylov-cg
  type: requires
  weight: 0.8
  note: Conjugate gradient is the fastest linear solver in benchmarks (4 fields)
- to: fft-solver-eyre-milton
  type: requires
  weight: 0.8
  note: Eyre-Milton achieves sqrt(kappa) scaling, fastest method to moderate tolerance
- to: fft-solver-polarization-admm
  type: requires
  weight: 0.7
  note: ADMM requires dual convergence criteria (compatibility + constitutive)
- to: fft-solver-barzilai-borwein
  type: requires
  weight: 0.7
  note: BB shows non-monotone residual but competitive iteration counts (2 fields)
- to: fft-solver-fast-gradient
  type: requires
  weight: 0.7
  note: Nesterov-type methods converge linearly with momentum-based acceleration
- to: fft-solver-newton-krylov
  type: requires
  weight: 0.7
  note: Newton-CG is optimal when constitutive evaluation dominates cost (8.5-12 fields)
- to: fft-solver-quasi-newton
  type: requires
  weight: 0.7
  note: L-BFGS/Anderson acceleration competitive at moderate tolerances (2m+2 fields)
- to: fft-green-operator
  type: requires
  weight: 0.6
  note: Equilibrium criterion uses the non-dimensional Green's operator in Fourier space
- to: fft-galerkin-basics
  type: requires
  weight: 0.5
  note: H^{-1} norm and Galerkin framework underlie the mathematically rigorous convergence criterion
context_size: large
reading_priority: full
load_with:
- fft-solver-basic-scheme
- fft-solver-eyre-milton
- fft-solver-krylov-cg
content_ref: null
akms_schema: v2
---

# Convergence Criteria & Solver Comparison

## Summary
This node consolidates convergence criteria formulas and a comparative overview of FFT-based solver performance. Three principal convergence measures are used across solver families. (1) The equilibrium criterion $\|\text{div}\,\boldsymbol{\sigma}\|_{H^{-1}_\#} \leq \text{tol}\,\|\langle\boldsymbol{\sigma}\rangle\|$ is computed in Fourier space as $\|\boldsymbol{\Gamma} \colon \boldsymbol{\sigma}\|_{L^2}$ and applies to gradient-based and Krylov solvers. (2) For polarization/ADMM schemes, the compatibility criterion $\|\boldsymbol{\varepsilon} - \mathbf{e}\|_{L^2}/\|\boldsymbol{\varepsilon}\| < \text{tol}$ and the constitutive criterion $\|\mathbb{C}\colon\boldsymbol{\varepsilon} - \lambda\|_{L^2}/\|\mathbb{C}^0\colon\boldsymbol{\varepsilon}\| < \text{tol}$ are used jointly. (3) Eyre-Milton monitors the polarization change $\|P_{k+1} - P_k\|/\|P_{k+1}\| < \text{tol}$. A benchmark on a porous bound-sand microstructure (40.14% porosity, 1% uniaxial extension, tolerance $10^{-5}$) establishes the relative performance: CG is fastest overall, BB and nonlinear CG are close seconds, Eyre-Milton and Anderson are fastest to moderate tolerance, the basic scheme fails to converge within 1000 iterations, and Newton-CG is preferred when constitutive evaluation is expensive.


## 1. Core Concept
Convergence assessment for FFT solvers requires criteria that match the solver structure. Gradient-based solvers (basic scheme, BB, fast gradient, nonlinear CG) produce compatible strain iterates, so checking equilibrium ($\text{div}\,\sigma = 0$) via the $H^{-1}$ norm suffices. Polarization/ADMM solvers produce iterates that are neither compatible nor in equilibrium during iteration, necessitating both a compatibility criterion (primal gap) and a constitutive criterion (dual gap). Solver comparison depends on the combined metric of iterations, FFT evaluations per iteration, and memory footprint. The iteration count alone is misleading since some methods (Newton-CG) require inner Krylov iterations with their own FFT calls. Memory footprint ranges from 1 field (basic scheme) to 12 fields (Newton-CG), creating a fundamental speed-memory tradeoff. The scaling of iteration count with the material contrast ratio $\kappa = \alpha_+/\alpha_-$ is the key theoretical differentiator: linear scaling ($\kappa$) for the basic scheme, square-root scaling ($\sqrt{\kappa}$) for CG, Eyre-Milton, and BB.


## 2. Mathematical Formulation
The equilibrium residual is most rigorously measured in the $H^{-1}$ norm, which corresponds to applying the non-dimensional Green's operator to the stress in Fourier space. This is the natural dual norm to the $H^1$ displacement space. An alternative $L^2$-based criterion is sometimes used but introduces a mesh-dependent prefactor. For ADMM schemes, both primal feasibility (compatibility gap) and dual feasibility (constitutive gap) must be below tolerance.


**Equilibrium criterion (H^{-1} norm):**

$$
\|\text{div}\,\boldsymbol{\sigma}\|_{H^{-1}_\#} = \|\boldsymbol{\Gamma} \colon \boldsymbol{\sigma}\|_{L^2} \leq \text{tol} \cdot \|\langle\boldsymbol{\sigma}\rangle\|
$$

where Gamma is the non-dimensional Green's operator; angle brackets denote volume average

**Equilibrium criterion (L^2 variant):**

$$
\|\text{div}\,\boldsymbol{\sigma}\|_{L^2} \leq \frac{\sqrt{2\pi}}{L}\,\text{tol}\,\|\langle\boldsymbol{\sigma}\rangle\|
$$

where L is the unit cell size; the prefactor sqrt(2pi)/L introduces mesh dependence

**Compatibility criterion (ADMM/polarization):**

$$
\frac{\|\boldsymbol{\varepsilon}_{k+1} - \mathbf{e}_{k+1}\|_{L^2}}{\|\boldsymbol{\varepsilon}\|_{L^2}} < \text{tol}
$$

where epsilon is the compatible strain, e is the auxiliary strain; primal feasibility gap

**Constitutive criterion (ADMM/polarization):**

$$
\frac{\|\mathbb{C}(\mathbf{x}) \colon \boldsymbol{\varepsilon}_{k+1} - \lambda_{k+1}\|_{L^2}}{\|\mathbb{C}^0 \colon \boldsymbol{\varepsilon}\|_{L^2}} < \text{tol}
$$

where lambda is the Lagrange multiplier converging to stress; dual feasibility gap

**Polarization change criterion (Eyre-Milton):**

$$
\frac{\|P_{k+1} - P_k\|_{L^2}}{\|P_{k+1}\|_{L^2}} < \text{tol}
$$

where P is the polarization field; natural convergence measure for the Eyre-Milton scheme

**Contrast ratio scaling summary:**

$$
\text{Basic scheme}\colon O(\kappa), \quad \text{CG / Eyre-Milton / BB}\colon O(\sqrt{\kappa}), \quad \text{Newton}\colon O(\log \kappa)
$$

where kappa = alpha_+/alpha_- is the material contrast; Newton scaling reflects quadratic inner convergence

**Notation:**

- $\boldsymbol{\Gamma}$ — Non-dimensional Green's operator
- $\|\cdot\|_{H^{-1}_\#}$ — H^{-1} dual norm on the periodic unit cell
- $\boldsymbol{\varepsilon}$ — Compatible strain field
- $\mathbf{e}$ — Auxiliary strain field (ADMM)
- $\lambda$ — Lagrange multiplier / stress (ADMM)
- $P$ — Polarization field (Eyre-Milton)
- $\kappa$ — Material contrast ratio alpha_+/alpha_-


## 3. Algorithmic Implementation
This node collects convergence criteria and benchmark data rather than defining a single algorithm.
Solver comparison (porous bound-sand, 40.14% porosity, 1% uniaxial, tol = 1e-5):
  Basic scheme:           >1000 iterations (did not converge), 1 field
  Fast gradient (Nesterov): converges but lags behind fastest methods, 2 fields
  Barzilai-Borwein:       competitive with CG, non-monotone residual, 2 fields
  Nonlinear CG (FR):      close to CG performance, 3 fields
  Linear CG:              fastest overall iteration count, 4 fields
  Anderson (m=4):         second fastest to tol=1e-3, slows for tighter tol, 10 fields
  Eyre-Milton:            fastest to tol=1e-3, 2 fields
  ADMM:                   slightly slower than Eyre-Milton, 3 fields
  Newton-CG:              best when constitutive law is expensive, 8.5-12 fields + tangent


## 4. Known Pitfalls
**Mixing convergence criteria across solver families:** The equilibrium criterion ($\|\Gamma \colon \sigma\|$) applies to gradient and Krylov solvers but is not directly computable for ADMM iterates, which are not in equilibrium until convergence. Comparing iteration counts at the same nominal tolerance across different criteria can be misleading. Always use the native criterion for each solver and verify with a common post-convergence check.


**L^2 equilibrium criterion is mesh-dependent:** The $L^2$ norm of $\text{div}\,\sigma$ depends on the mesh through the factor $\sqrt{2\pi}/L$, while the $H^{-1}$ norm is mesh-independent. Using the $L^2$ criterion without the scaling factor can lead to false convergence declarations on coarse meshes and overly strict tolerances on fine meshes.


**Non-monotone residuals in spectral methods:** The Barzilai-Borwein and Anderson acceleration methods exhibit non-monotone residual histories where the residual can temporarily increase. Monitoring convergence with strict monotonic decrease tests will incorrectly diagnose these methods as diverging. Use a running minimum or averaged residual instead.


**Memory footprint dominates for large 3D problems:** On a $512^3$ grid with 6-component symmetric tensors in double precision, each field requires approximately 6 GB. The difference between 2 fields (Eyre-Milton, 12 GB) and 12 fields (Newton-CG, 72 GB) can determine whether a problem fits in GPU memory. Memory constraints often override iteration-count advantages.


**Iteration count alone is insufficient for cost comparison:** Newton-CG may require only a few outer iterations but each contains many inner CG iterations with FFT evaluations. The total number of FFT calls (proportional to wall-clock time) is a better cost metric. Similarly, methods requiring local nonlinear solves (ADMM, Eyre-Milton) have higher per-iteration cost than gradient methods that only evaluate the forward constitutive law.


## 5. References
- Schneider (2021) -- review of nonlinear FFT-based computational homogenization, convergence criteria and solver comparison Table 4
- Lucarini et al. (2022) -- convergence criteria for FFT-based solvers, equilibrium and compatibility norms

