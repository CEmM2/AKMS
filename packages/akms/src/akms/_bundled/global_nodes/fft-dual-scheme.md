---
id: fft-dual-scheme
title: Dual (Stress-Based) FFT Formulation
domain: fft-galerkin
subdomain: solver-algorithms
tags:
- solvers
- fft-galerkin
- spectral
- dual-formulation
- stress-based
- homogenization
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: Dual scheme reformulates the Lippmann-Schwinger equation in stress space
- to: fft-green-operator
  type: requires
  weight: 1.0
  note: Uses the Green operator to project onto divergence-free stress fields
- to: fft-reference-medium
  type: requires
  weight: 0.9
  note: Reference compliance D0 = (C0)^{-1} controls convergence of the dual iteration
- to: fft-solver-basic-scheme
  type: refines
  weight: 0.9
  note: Dual basic scheme is the stress-space analog of the primal basic scheme
- to: fft-galerkin-basics
  type: requires
  weight: 0.8
  note: Dual scheme builds on the Galerkin framework with divergence-free test functions
context_size: medium
reading_priority: full
load_with:
- fft-lippmann-schwinger
- fft-solver-basic-scheme
- fft-reference-medium
content_ref: null
akms_schema: v2
---

# Dual (Stress-Based) FFT Formulation

## Summary
The dual (stress-based) FFT formulation reformulates the classical strain-based Lippmann-Schwinger equation into stress space, minimizing the Legendre-Fenchel dual energy over the space of equilibrated (divergence-free) stress fields. The primary unknown is the stress field rather than the strain field, and the formulation relies on the reference compliance tensor D0 = (C0)^{-1} instead of the reference stiffness. The dual scheme has two key practical advantages: it naturally handles perfectly rigid inclusions (characterized by vanishing compliance), and for constitutive models where computing strain from stress is cheaper than the reverse (e.g., certain crystal plasticity models), it can accelerate the solver by an order of magnitude. All solver families (basic scheme, Krylov, Newton) carry over to the dual setting with equivalent convergence guarantees. The main disadvantages are increased memory requirements (no reduced-memory displacement storage) and no benefit when combined with polarization methods which are inherently primal-dual.


## 1. Core Concept
The dual formulation rewrites the unconstrained primal variational principle (minimizing elastic energy over compatible strain fields) as a constrained optimization where the primary unknown is the equilibrated stress field $\boldsymbol{\sigma}$ belonging to the divergence-free space $S = \{\boldsymbol{\sigma} \in L^2(Y; \text{Sym}(d)) \mid \text{div}\,\boldsymbol{\sigma} = 0\}$. The standard free energy density $w(\mathbf{x}, \boldsymbol{\varepsilon})$ is replaced by its Legendre-Fenchel dual, the condensed Helmholtz free energy $w^*(\mathbf{x}, \boldsymbol{\sigma})$. Instead of the Green operator $\boldsymbol{\Gamma}^0$ projecting onto compatible strain fields, the dual formulation uses a complementary projection operator $(\mathbf{Id} - \boldsymbol{\Gamma}^0 \colon \mathbf{C}^0 - \frac{1}{\text{vol}(Y)} \int_Y \cdot\, dx)$ that projects onto the discretely divergence-free subspace. Every stress iterate automatically satisfies mechanical equilibrium, mirroring how every strain iterate in the primal scheme automatically satisfies compatibility. The dual framework is particularly suited for composites containing rigid phases, where the compliance vanishes but the stiffness is infinite.


## 2. Mathematical Formulation
The dual variational principle minimizes the Legendre-Fenchel dual energy over equilibrated stress fields. The dual basic scheme iteratively solves this by computing the dual strain polarization (difference between local strain from the dual potential and reference compliance response), then projecting it onto the divergence-free subspace using the complementary Green operator.


**Dual variational principle:**

$$
\int_Y w^*(\mathbf{x}, \boldsymbol{\sigma}) - \boldsymbol{\sigma} \colon \bar{\boldsymbol{\varepsilon}} \, d\mathbf{x} \longrightarrow \min_{\boldsymbol{\sigma} \in S}
$$

where w* is the condensed Helmholtz free energy (Legendre-Fenchel dual of w), S is the space of divergence-free stress fields, epsilon-bar is prescribed macroscopic strain

**Divergence-free stress space:**

$$
S = \{\boldsymbol{\sigma} \in L^2(Y; \text{Sym}(d)) \mid \text{div}\,\boldsymbol{\sigma} = 0\}
$$

where Y is the periodic cell, Sym(d) is the space of symmetric second-order tensors in d dimensions

**Dual basic scheme iteration:**

$$
\boldsymbol{\sigma}_{k+1} = \mathbf{C}^0 \colon \bar{\boldsymbol{\varepsilon}} + \mathbf{C}^0 \colon \left( \mathbf{Id} - \boldsymbol{\Gamma}^0 \colon \mathbf{C}^0 - \frac{1}{\text{vol}(Y)} \int_Y \cdot\, d\mathbf{x} \right) \colon \left( \frac{\partial w^*}{\partial \boldsymbol{\sigma}}(\cdot, \boldsymbol{\sigma}_k) - \mathbf{D}^0 \colon \boldsymbol{\sigma}_k \right)
$$

where C0 is reference stiffness, D0 = (C0)^{-1} is reference compliance, Gamma0 is the Green operator, dw*/dsigma evaluates local strain from dual potential

**Divergence-free projection operator:**

$$
\mathbf{P}_S = \mathbf{Id} - \boldsymbol{\Gamma}^0 \colon \mathbf{C}^0 - \frac{1}{\text{vol}(Y)} \int_Y \cdot\, d\mathbf{x}
$$

where P_S projects fields into the discretely divergence-free subspace; complement of the compatibility projection

**Reference compliance tensor:**

$$
\mathbf{D}^0 = (\mathbf{C}^0)^{-1}
$$

where D0 is the compliance of the reference medium; vanishes for rigid phases (infinite stiffness) making the dual scheme well-defined

**Dual convergence criterion (compatibility residual):**

$$
\left\| \boldsymbol{\varepsilon}_k - \bar{\boldsymbol{\varepsilon}} - \boldsymbol{\Gamma} : \boldsymbol{\varepsilon}_k \right\|_{L^2} \leq \text{tol} \left\| \bar{\boldsymbol{\varepsilon}} \right\|
$$

where epsilon_k = dw*/dsigma(x, sigma_k) is the strain derived from the dual potential at iteration k, Gamma = nabla_s G div is the non-dimensional L2-orthogonal projection onto the space of compatible strain fields, epsilon_bar is the prescribed macroscopic strain; the term (epsilon_k - epsilon_bar - Gamma : epsilon_k) measures the incompatible part of the strain field

**Non-dimensional projection operator (convergence evaluation):**

$$
\boldsymbol{\Gamma} = \nabla_s G \, \text{div}, \quad G = (\text{div}\,\nabla_s)^{-1}
$$

where Gamma is the L2-orthogonal projector onto compatible strain fields; in Fourier space hat{Gamma}_{ijkl}(xi) = (1/4)(delta_{ik} xi_j xi_l + delta_{jk} xi_i xi_l + delta_{jl} xi_i xi_k + delta_{il} xi_j xi_k) / |xi|^2, set to zero at xi=0 and Nyquist frequencies

**Primal-dual duality of convergence criteria:**

$$
\text{Primal: } \| \text{div}\,\boldsymbol{\sigma} \|_{H^{-1}_\#} = \| \boldsymbol{\Gamma} : \boldsymbol{\sigma} \|_{L^2} \leq \text{tol} \left\| \langle \boldsymbol{\sigma} \rangle \right\|, \quad \text{Dual: } \left\| \boldsymbol{\varepsilon}_k - \bar{\boldsymbol{\varepsilon}} - \boldsymbol{\Gamma} : \boldsymbol{\varepsilon}_k \right\|_{L^2} \leq \text{tol} \left\| \bar{\boldsymbol{\varepsilon}} \right\|
$$

where The primal criterion checks equilibrium (div sigma = 0) while the dual criterion checks compatibility (epsilon is a symmetric gradient); both use the same non-dimensional Gamma operator

**Notation:**

- $w^*$ — Condensed Helmholtz free energy (Legendre-Fenchel dual of w)
- $\boldsymbol{\sigma}$ — Cauchy stress field (primary unknown in dual formulation)
- $S$ — Space of divergence-free (equilibrated) stress fields
- $\mathbf{D}^0$ — Reference compliance tensor, inverse of reference stiffness C0
- $\mathbf{C}^0$ — Reference medium stiffness tensor
- $\boldsymbol{\Gamma}^0$ — Green operator of the reference medium
- $\bar{\boldsymbol{\varepsilon}}$ — Prescribed macroscopic strain
- $\mathbf{P}_S$ — Projection operator onto divergence-free stress subspace
- $\boldsymbol{\Gamma}$ — Non-dimensional L2-orthogonal projection operator onto compatible strain fields; Gamma = nabla_s G div
- $\boldsymbol{\varepsilon}_k$ — Strain field at iteration k, derived from dual potential: epsilon_k = dw*/dsigma(x, sigma_k)


## 3. Algorithmic Implementation
**Algorithm: Dual Basic Scheme (Stress-Based Fixed-Point)**

$$
\begin{algorithmic}
\State $\boldsymbol{\sigma}_0(\mathbf{x}) \leftarrow \mathbf{C}^0 \colon \bar{\boldsymbol{\varepsilon}}$
\While{$\left\| \boldsymbol{\varepsilon}_k - \bar{\boldsymbol{\varepsilon}} - \boldsymbol{\Gamma} \colon \boldsymbol{\varepsilon}_k \right\|_{L^2} > \text{tol} \left\| \bar{\boldsymbol{\varepsilon}} \right\|$}
    \State $\boldsymbol{\varepsilon}_k(\mathbf{x}) \leftarrow \frac{\partial w^*}{\partial \boldsymbol{\sigma}}(\mathbf{x}, \boldsymbol{\sigma}_k(\mathbf{x}))$
    \State $\boldsymbol{\eta}_k(\mathbf{x}) \leftarrow \boldsymbol{\varepsilon}_k(\mathbf{x}) - \mathbf{D}^0 \colon \boldsymbol{\sigma}_k(\mathbf{x})$
    \State $\hat{\boldsymbol{\eta}}_k \leftarrow \text{DFT}(\boldsymbol{\eta}_k)$
    \State $\hat{\boldsymbol{\eta}}_k^S(\boldsymbol{\xi}) \leftarrow \hat{\boldsymbol{\eta}}_k(\boldsymbol{\xi}) - \hat{\boldsymbol{\Gamma}}^0(\boldsymbol{\xi}) \colon \mathbf{C}^0 \colon \hat{\boldsymbol{\eta}}_k(\boldsymbol{\xi}) \quad \forall \boldsymbol{\xi} \neq \mathbf{0}$
    \State $\hat{\boldsymbol{\eta}}_k^S(\mathbf{0}) \leftarrow \mathbf{0}$
    \State $\boldsymbol{\eta}_k^S \leftarrow \text{DFT}^{-1}(\hat{\boldsymbol{\eta}}_k^S)$
    \State $\boldsymbol{\sigma}_{k+1}(\mathbf{x}) \leftarrow \mathbf{C}^0 \colon \bar{\boldsymbol{\varepsilon}} + \mathbf{C}^0 \colon \boldsymbol{\eta}_k^S(\mathbf{x})$
\EndWhile
\end{algorithmic}
$$

**Taichi Mapping:**
The dual strain polarization eta_k is computed pointwise (Taichi kernel). Forward/inverse FFT via ti.fft. The divergence-free projection is a pointwise Fourier-space kernel applying (Id - Gamma0:C0). Stress update is a pointwise real-space kernel. The compatibility residual is evaluated in Fourier space via Parseval theorem: apply hat{Gamma}(xi) to hat{epsilon}_k(xi) at each frequency and sum squared magnitudes.


## 4. Known Pitfalls
**Increased memory footprint:** The dual scheme operates on stress fields, preventing the reduced-memory implementations available in the primal scheme. In the primal formulation, memory can be drastically reduced by storing scalar displacement fields instead of full strain tensors. The dual scheme cannot exploit this because equilibrated stress fields do not have an analogous compact representation.


**No benefit with polarization methods:** Polarization-based solvers (Eyre-Milton, ADMM) are inherently primal-dual methods that operate on a combined stress-strain polarization field. There is no advantage to a dual formulation when using these solvers, as they already incorporate both stress and strain information by construction.


**Convergence criterion not equilibrium-based:** Unlike the primal scheme where the equilibrium residual (divergence of stress) serves as the natural convergence criterion, the dual scheme automatically satisfies equilibrium at every iterate. The convergence must instead be assessed through the compatibility of the resulting strain field: the incompatible part $\|\boldsymbol{\varepsilon}_k - \bar{\boldsymbol{\varepsilon}} - \boldsymbol{\Gamma} : \boldsymbol{\varepsilon}_k\|_{L^2}$ is measured using the non-dimensional projection operator $\boldsymbol{\Gamma} = \nabla_s G \text{div}$. This mirrors the primal criterion $\|\boldsymbol{\Gamma} : \boldsymbol{\sigma}\|_{L^2}$ but swaps equilibrium for compatibility. The residual is evaluated in Fourier space using $\hat{\boldsymbol{\Gamma}}(\boldsymbol{\xi})$ and Parseval's theorem.


**Limited to constitutive models with accessible dual potential:** The dual scheme requires evaluation of the Legendre-Fenchel dual energy $w^*(\mathbf{x}, \boldsymbol{\sigma})$ and its derivative (strain as a function of stress). For constitutive models where the stress-to-strain mapping is not analytically available or is computationally expensive, the dual scheme loses its advantage over the primal formulation.


## 5. References
- Schneider (2021) — Review of nonlinear FFT-based computational homogenization, dual formulation and stress-based iteration
- Bhattacharya, Suquet (2005) — Dual variational principle for FFT-based homogenization

