---
id: fft-solver-krylov-minres
title: MINRES for Symmetric FFT Systems
domain: fft-galerkin
subdomain: solver-algorithms
tags:
- solvers
- krylov-solver
- fft-galerkin
- convergence
- iterative
- preconditioning
- polarization
status: established
confidence: 0.9
source: hybrid
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: MINRES solves the polarization-based L-S equation
- to: fft-green-operator
  type: requires
  weight: 0.9
  note: Green's operator Gamma0 appears in the polarization L-S system
- to: fft-reference-medium
  type: requires
  weight: 1.0
  note: Definiteness of (C - C0)^{-1} + Gamma0 depends critically on C0 choice
- to: fft-solver-krylov-cg
  type: refines
  weight: 0.9
  note: CG is preferred when the polarization operator is definite; MINRES handles indefinite case
- to: fft-solver-basic-scheme
  type: refines
  weight: 0.8
  note: MINRES achieves sqrt(kappa) convergence vs linear kappa for basic scheme
context_size: medium
reading_priority: full
load_with:
- fft-solver-krylov-cg
- fft-lippmann-schwinger
- fft-reference-medium
content_ref: null
akms_schema: v2
---

# MINRES for Symmetric FFT Systems

## Summary
The Minimum Residual method (MINRES) is a Krylov subspace solver for symmetric but potentially indefinite linear systems. In FFT-based homogenization, MINRES is applied to the polarization-based Lippmann-Schwinger equation $(\mathbf{C} - \mathbf{C}^0)^{-1} \colon \boldsymbol{\tau} + \boldsymbol{\Gamma}^0 \colon \boldsymbol{\tau} = \bar{\boldsymbol{\varepsilon}}$, where the operator $(\mathbf{C} - \mathbf{C}^0)^{-1} + \boldsymbol{\Gamma}^0$ is symmetric and invertible but not necessarily positive definite. MINRES minimizes the residual norm $\|A\mathbf{x} - \mathbf{b}\|^2$ over the Krylov subspace, in contrast to CG which minimizes the energy functional. MINRES is required when the reference medium $\mathbf{C}^0$ is neither uniformly softer nor uniformly stiffer than all material phases, making the operator indefinite. The method requires 7 strain fields in memory (vs. 4 for CG), and is restricted to linear problems with no direct nonlinear extension. It has also been applied to indefinite coupled multi-physics problems (e.g., piezoelectrics) and lattice microstructures with large void fractions.


## 1. Core Concept
MINRES solves the polarization-based Lippmann-Schwinger equation proposed by Brisard and Dormieux. The unknown is the stress polarization field $\boldsymbol{\tau} = (\mathbf{C} - \mathbf{C}^0) \colon \boldsymbol{\varepsilon}$, and the linear operator $(\mathbf{C} - \mathbf{C}^0)^{-1} + \boldsymbol{\Gamma}^0$ is inherently symmetric on the entire space of voxel-wise constant polarization fields (unlike the strain-based operator which is only symmetric on compatible fields). The definiteness of this operator depends on the reference medium choice: if $\mathbf{C}^0$ is softer than all phases, the operator is positive definite (use CG); if $\mathbf{C}^0$ is stiffer than all phases, it is negative definite (use CG on $-A$); for intermediate $\mathbf{C}^0$, the operator is indefinite and MINRES must be used. The convergence rate scales as $\sqrt{\kappa}$ and is independent of mesh size, matching CG. However, MINRES requires 7 vector fields in memory and cannot be extended to nonlinear constitutive problems.


## 2. Mathematical Formulation
The polarization-based formulation converts the cell problem into a symmetric system for the stress polarization. The operator combines the local compliance deviation $(C - C_0)^{-1}$ with the Green's operator, yielding a system that is always symmetric but whose definiteness depends on the reference medium. MINRES minimizes the $L^2$-norm of the residual at each step, making it applicable to indefinite systems where CG would fail.


**Polarization-based L-S equation:**

$$
((\mathbf{C} - \mathbf{C}^0)^{-1} + \boldsymbol{\Gamma}^0) \colon \boldsymbol{\tau} = \bar{\boldsymbol{\varepsilon}}
$$

where tau = (C - C0) : eps is the stress polarization, C0 is the reference stiffness

**MINRES objective (residual minimization):**

$$
\phi_{A,b}(\mathbf{x}) = \|A\mathbf{x} - \mathbf{b}\|^2 \longrightarrow \min_{\mathbf{x} \in \mathcal{K}_{k+1}(A;\mathbf{b})}
$$

where A = (C - C0)^{-1} + Gamma0, b = eps_bar; minimizes residual norm over the Krylov subspace

**CG objective for comparison:**

$$
\phi_{A,b}(\mathbf{x}) = \frac{1}{2}\mathbf{x}^T A \mathbf{x} - \mathbf{b}^T \mathbf{x}
$$

where CG minimizes the energy functional (requires positive definiteness)

**Positive definite condition (CG applicable):**

$$
\mathbf{C}^0 \prec \mathbf{C}(\mathbf{x}) \quad \forall \mathbf{x} \in Y \implies (\mathbf{C} - \mathbf{C}^0)^{-1} + \boldsymbol{\Gamma}^0 \succ 0
$$

where C0 softer than all local phases yields a positive definite operator

**Indefinite condition (MINRES required):**

$$
\exists\, \mathbf{x}_1, \mathbf{x}_2 \in Y \colon \mathbf{C}(\mathbf{x}_1) \prec \mathbf{C}^0 \prec \mathbf{C}(\mathbf{x}_2) \implies (\mathbf{C} - \mathbf{C}^0)^{-1} + \boldsymbol{\Gamma}^0 \text{ indefinite}
$$

where Intermediate reference medium makes the operator a saddle-point system

**Convergence rate:**

$$
N_{\text{iter}} \sim \sqrt{\kappa}, \quad \kappa = \alpha_+ / \alpha_-
$$

where Same optimal rate as CG; independent of mesh size

**Hashin-Shtrikman variational principle:**

$$
\frac{1}{2}\langle \boldsymbol{\tau}, (\mathbf{C} - \mathbf{C}^0)^{-1} \colon \boldsymbol{\tau} + \boldsymbol{\Gamma}^0 \colon \boldsymbol{\tau} \rangle_{L^2} - \langle \boldsymbol{\tau}, \bar{\boldsymbol{\varepsilon}} \rangle_{L^2} \longrightarrow \min_{\boldsymbol{\tau}}
$$

where Strongly convex when C0 is uniformly softer; becomes a saddle point for intermediate C0

**Notation:**

- $\boldsymbol{\tau}$ — Stress polarization field tau = (C - C0) : eps
- $(\mathbf{C} - \mathbf{C}^0)^{-1}$ — Local compliance deviation tensor (requires C - C0 invertible)
- $\boldsymbol{\Gamma}^0$ — Green's operator for the reference medium
- $\mathbf{C}^0$ — Reference medium stiffness tensor
- $\kappa$ — Phase contrast ratio alpha_+/alpha_-
- $\prec, \succ$ — Definiteness ordering on symmetric tensors


## 3. Algorithmic Implementation
**Algorithm: MINRES for Polarization-Based L-S Equation**

$$
\begin{algorithmic}
\State $Initialize \colon \boldsymbol{\tau}_0 = \mathbf{0}, \; \mathbf{r}_0 = \bar{\boldsymbol{\varepsilon}} - ((\mathbf{C} - \mathbf{C}^0)^{-1} + \boldsymbol{\Gamma}^0) \colon \boldsymbol{\tau}_0$
\State $Set \; \mathbf{v}_0 = \mathbf{0}, \; \mathbf{v}_1 = \mathbf{r}_0 / \|\mathbf{r}_0\|, \; \beta_1 = \|\mathbf{r}_0\|$
\State $Set \; \phi_0 = \beta_1, \; c_0 = 1, \; s_0 = 0, \; \mathbf{d}_{-1} = \mathbf{0}, \; \mathbf{d}_0 = \mathbf{0}$
\While{$|\phi_k| / \|\bar{\boldsymbol{\varepsilon}}\| > \text{tol}$}
    \State $\mathbf{w}_k = ((\mathbf{C} - \mathbf{C}^0)^{-1} + \boldsymbol{\Gamma}^0) \colon \mathbf{v}_k$
    \State $\alpha_k = \langle \mathbf{w}_k, \mathbf{v}_k \rangle, \quad \mathbf{w}_k \leftarrow \mathbf{w}_k - \alpha_k \mathbf{v}_k - \beta_k \mathbf{v}_{k-1}$
    \State $\beta_{k+1} = \|\mathbf{w}_k\|, \quad \mathbf{v}_{k+1} = \mathbf{w}_k / \beta_{k+1}$
    \State $\delta_k^{(1)} = c_{k-1} \alpha_k - s_{k-1} \beta_k c_{k-2} \alpha_{k-1}$
    \State $\gamma_k = \sqrt{(\delta_k^{(1)})^2 + \beta_{k+1}^2}$
    \State $c_k = \delta_k^{(1)} / \gamma_k, \quad s_k = \beta_{k+1} / \gamma_k$
    \State $\mathbf{d}_k = \frac{1}{\gamma_k} \left( \mathbf{v}_k - \delta_k^{(0)} \mathbf{d}_{k-2} - \epsilon_k \mathbf{d}_{k-1} \right)$
    \State $\boldsymbol{\tau}_k = \boldsymbol{\tau}_{k-1} + (c_k \phi_{k-1}) \, \mathbf{d}_k$
    \State $\phi_k = -s_k \phi_{k-1}$
\EndWhile
\end{algorithmic}
$$

**Taichi Mapping:**
Each MINRES iteration requires one operator application (real-space kernel for (C-C0)^{-1} : tau + FFT/iFFT pair for Gamma0 : tau). The 7 strain fields stored as Taichi fields on GPU are: v_{k-1}, v_k, v_{k+1}, w_k, d_{k-2}, d_{k-1}, tau_k. Givens rotation scalars (c_k, s_k, phi_k, gamma_k, delta, epsilon) are host-side scalars — negligible memory. Memory-bound by the 7-field requirement.


## 4. Known Pitfalls
**High memory footprint (7 strain fields):** MINRES requires 7 vector fields in memory, nearly double the 4 fields needed by CG. For large 3D grids ($512^3$ voxels), each strain field occupies ~6 GB, making MINRES demand ~42 GB for strain storage alone. This severely limits the maximum grid resolution achievable on GPU hardware.


**Restricted to linear problems:** Unlike CG, which has a natural nonlinear extension via the Fletcher-Reeves nonlinear CG framework, MINRES has no established nonlinear generalization for FFT-based micromechanics. For nonlinear constitutive models, one must either use MINRES as an inner solver within Newton-Raphson or switch to a different solver family entirely.


**Singular (C - C0) breaks the formulation:** If $\mathbf{C}^0$ is chosen such that $\mathbf{C}(\mathbf{x}) = \mathbf{C}^0$ for any material phase in the microstructure, the difference $\mathbf{C} - \mathbf{C}^0$ becomes singular and the compliance deviation $(\mathbf{C} - \mathbf{C}^0)^{-1}$ is undefined. This completely breaks the polarization formulation. The reference medium must be chosen so that the difference is invertible everywhere.


**Solution depends on reference medium:** Unlike displacement-based discretizations where $\mathbf{C}^0$ is purely a numerical parameter, the Brisard-Dormieux polarization discretization produces solutions $\boldsymbol{\tau}_N$ that depend on the reference medium. A judicious choice of $\mathbf{C}^0$ is required to balance accuracy of the discrete solution and conditioning of the linear system.


**Poor conditioning for intermediate C0:** When $\mathbf{C}^0$ is intermediate (neither softer nor stiffer than all phases), the operator becomes indefinite and the system is a saddle-point problem. While MINRES can handle this, the condition number may be worse than in the definite case, leading to more iterations. The optimal $\mathbf{C}^0$ choice for MINRES is not as well-characterized as for CG.


## 5. References
- Schneider (2021) -- MINRES for polarization L-S equation, comparison with CG, memory footprint
- Brisard and Dormieux (2010) -- Polarization formulation with CG and MINRES for different C0 choices
- Lucarini et al. (2022) -- MINRES with Fourier-Galerkin and finite-difference frequencies for lattice microstructures

