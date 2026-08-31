---
id: fft-solver-barzilai-borwein
title: Barzilai-Borwein Accelerated Basic Scheme
domain: fft-galerkin
subdomain: solver-algorithms
tags:
- solvers
- fft-galerkin
- spectral
- convergence
- accelerated-schemes
- iterative
- spectral-step-size
- quasi-newton
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-solver-basic-scheme
  type: requires
  weight: 1.0
  note: BB method modifies the basic scheme by replacing fixed step size with adaptive spectral step
- to: fft-lippmann-schwinger
  type: requires
  weight: 0.9
  note: Iterates on the Lippmann-Schwinger equation with adaptive reference stiffness
- to: fft-green-operator
  type: requires
  weight: 0.9
  note: Uses the Green's operator for the strain update in Fourier space
- to: fft-reference-medium
  type: requires
  weight: 0.7
  note: BB bypasses manual reference medium selection via adaptive step size
- to: fft-solver-fast-gradient
  type: refines
  weight: 0.6
  note: Both are gradient-based accelerations of the basic scheme
- to: fft-solver-nonlinear-cg
  type: refines
  weight: 0.7
  note: Comparable iteration count to Fletcher-Reeves nonlinear CG in benchmarks
- to: fft-convergence-schemes
  type: feeds-into
  weight: 0.6
  note: Competitive convergence for moderate and high contrast
context_size: medium
reading_priority: full
load_with:
- fft-solver-basic-scheme
- fft-reference-medium
content_ref: null
akms_schema: v2
---

# Barzilai-Borwein Accelerated Basic Scheme

## Summary
The Barzilai-Borwein (BB) method accelerates the basic scheme by replacing the fixed reference medium parameter with an adaptive spectral step size computed from successive strain and stress differences. It can be interpreted as L-BFGS of depth one without line search, or equivalently as gradient descent with an adaptive learning rate. The spectral step size $\alpha_k$ is computed as the Rayleigh quotient of the stress-strain increment, requiring no manual parameter tuning. The method is highly competitive with the fastest nonlinear solvers (Fletcher-Reeves CG, L-BFGS of depth four) while requiring only 2 strain fields in memory and two FFT evaluations per iteration. A defining characteristic is its inherent non-monotonicity: the residual fluctuates between iterations but maintains a rapid overall downward trajectory.


## 1. Core Concept
The Barzilai-Borwein method modifies the basic scheme by dynamically adapting the effective reference medium stiffness at each iteration. Instead of using a fixed $\alpha_0$, it computes a spectral step size $\alpha_k$ from the inner product of successive stress and strain differences divided by the squared norm of the strain difference. This is equivalent to a secant approximation of the local curvature of the energy landscape, matching the L-BFGS interpretation of depth one. The adaptive step size eliminates the need for manual reference medium selection and automatically adjusts to the local nonlinearity. The resulting method is parameter-free, memory-efficient, and achieves convergence rates comparable to much more complex solvers. The non-monotone residual behavior is characteristic of spectral gradient methods and does not indicate instability.


## 2. Mathematical Formulation
The BB method replaces the constant reference parameter $\alpha_0$ in the basic scheme with an iteration-dependent parameter $\alpha_k$ computed from the Rayleigh quotient of successive stress and strain differences. The update formula is structurally identical to the basic scheme but with $1/\alpha_k$ scaling the Green's operator application instead of $1/\alpha_0$.


**Spectral step size (Barzilai-Borwein):**

$$
\alpha_k = \frac{\langle \boldsymbol{\sigma}(\boldsymbol{\varepsilon}_k) - \boldsymbol{\sigma}(\boldsymbol{\varepsilon}_{k-1}), \; \boldsymbol{\varepsilon}_k - \boldsymbol{\varepsilon}_{k-1} \rangle_{L^2}}{\|\boldsymbol{\varepsilon}_k - \boldsymbol{\varepsilon}_{k-1}\|^2_{L^2}}
$$

where sigma(epsilon_k) is the stress at iteration k, the inner product and norm are L^2 over the unit cell

**BB-accelerated basic scheme iteration:**

$$
\boldsymbol{\varepsilon}_{k+1} = \bar{\boldsymbol{\varepsilon}} - \frac{1}{\alpha_k} \boldsymbol{\Gamma} \colon \left( \boldsymbol{\sigma}(\boldsymbol{\varepsilon}_k) - \mathbf{C}^0 \colon \boldsymbol{\varepsilon}_k \right)
$$

where Gamma is the (non-dimensional) Green's operator, C^0 is the formal reference stiffness

**Interpretation as L-BFGS depth one:**

$$
\alpha_k \approx \frac{\mathbf{y}_k^T \mathbf{s}_k}{\mathbf{s}_k^T \mathbf{s}_k}, \quad \mathbf{s}_k = \boldsymbol{\varepsilon}_k - \boldsymbol{\varepsilon}_{k-1}, \quad \mathbf{y}_k = \boldsymbol{\sigma}(\boldsymbol{\varepsilon}_k) - \boldsymbol{\sigma}(\boldsymbol{\varepsilon}_{k-1})
$$

where s_k is the strain step, y_k is the stress step; this is the standard secant (BB1) formula

**Notation:**

- $\alpha_k$ — Adaptive spectral step size at iteration k
- $\boldsymbol{\varepsilon}_k$ — Strain field at iteration k
- $\boldsymbol{\sigma}$ — Nonlinear stress operator
- $\boldsymbol{\Gamma}$ — Non-dimensional Green's operator
- $\mathbf{C}^0$ — Formal reference stiffness (used in polarization)
- $\langle \cdot, \cdot \rangle_{L^2}$ — L^2 inner product over the unit cell


## 3. Algorithmic Implementation
**Algorithm: Barzilai-Borwein Accelerated Basic Scheme**

$$
\begin{algorithmic}
\State $\boldsymbol{\varepsilon}_0(\mathbf{x}) \leftarrow \bar{\boldsymbol{\varepsilon}}$
\State $\text{Run one basic scheme step to obtain } \boldsymbol{\varepsilon}_1$
\For{$k = 1, 2, \ldots$}
    \State $\boldsymbol{\sigma}_k \leftarrow \boldsymbol{\sigma}(\boldsymbol{\varepsilon}_k)$
    \State $\alpha_k \leftarrow \frac{\langle \boldsymbol{\sigma}_k - \boldsymbol{\sigma}_{k-1}, \; \boldsymbol{\varepsilon}_k - \boldsymbol{\varepsilon}_{k-1} \rangle_{L^2}}{\|\boldsymbol{\varepsilon}_k - \boldsymbol{\varepsilon}_{k-1}\|^2_{L^2}}$
    \State $\boldsymbol{\tau}_k \leftarrow \boldsymbol{\sigma}_k - \mathbf{C}^0 \colon \boldsymbol{\varepsilon}_k$
    \State $\hat{\boldsymbol{\tau}}_k \leftarrow \text{DFT}(\boldsymbol{\tau}_k)$
    \State $\hat{\boldsymbol{\varepsilon}}_{k+1}(\boldsymbol{\xi}) \leftarrow -\frac{1}{\alpha_k}\hat{\boldsymbol{\Gamma}}(\boldsymbol{\xi}) \colon \hat{\boldsymbol{\tau}}_k(\boldsymbol{\xi}) \quad \forall \boldsymbol{\xi} \neq \mathbf{0}$
    \State $\hat{\boldsymbol{\varepsilon}}_{k+1}(\mathbf{0}) \leftarrow \bar{\boldsymbol{\varepsilon}}$
    \State $\boldsymbol{\varepsilon}_{k+1} \leftarrow \text{DFT}^{-1}(\hat{\boldsymbol{\varepsilon}}_{k+1})$
    \If{$\|\boldsymbol{\Gamma} \colon \boldsymbol{\sigma}_k\|_{L^2} / \|\langle \boldsymbol{\sigma}_k \rangle\| < \text{tol}$}
        \State \textbf{break}
    \EndIf
\EndFor
\end{algorithmic}
$$

**Taichi Mapping:**
Inner product and norm computations for alpha_k map to a Taichi parallel reduction kernel. Stress evaluation, polarization, and Green's operator application are the same pointwise kernels as the basic scheme. The previous stress field sigma_{k-1} must be stored alongside the current strain, giving the 2-field memory footprint.


## 4. Known Pitfalls
**Non-monotone residual:** The residual in the BB scheme fluctuates and can temporarily increase between iterations. This non-monotonicity is inherent to spectral gradient methods and should not be interpreted as divergence. Convergence monitoring must use a running minimum or averaged residual rather than checking strict monotonic decrease.


**First iteration bootstrap:** The spectral step size $\alpha_k$ requires both the current and previous strain-stress pairs. The first iteration (k=0 to k=1) must use the standard basic scheme with a manually chosen reference medium, or a default initial step. Poor initialization of $\alpha_0$ can lead to a large first residual spike.


**Degenerate step size for nearly homogeneous fields:** When $\boldsymbol{\varepsilon}_k \approx \boldsymbol{\varepsilon}_{k-1}$ (near convergence or for nearly homogeneous microstructures), the denominator $\|\boldsymbol{\varepsilon}_k - \boldsymbol{\varepsilon}_{k-1}\|^2$ approaches zero, making $\alpha_k$ numerically unstable. A safeguard (e.g., clamping $\alpha_k$ to a bounded range) is needed in practice.


**No convergence guarantee for general nonlinearity:** Unlike the basic scheme which has a rigorous convergence proof for sufficiently stiff reference media, the BB method lacks a general convergence guarantee for non-convex or non-smooth problems. In practice it is robust, but theoretical convergence is established only for strongly convex objectives with Lipschitz gradients.


**Not suitable for non-smooth constitutive laws:** The secant approximation underlying the BB step size assumes smooth stress-strain relationships. For materials with yield surfaces or damage thresholds that introduce discontinuities in the tangent, the BB step size can become erratic. In such cases, Newton-Krylov methods may be more appropriate.


## 5. References
- Schneider (2021) -- review of nonlinear FFT-based computational homogenization, Barzilai-Borwein method and L-BFGS interpretation
- Lucarini et al. (2022) -- non-linear quasi-Newton approaches for FFT homogenization

