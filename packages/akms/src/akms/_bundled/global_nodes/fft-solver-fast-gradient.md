---
id: fft-solver-fast-gradient
title: Fast Gradient Methods (Nesterov-Type)
domain: fft-galerkin
subdomain: solver-algorithms
tags:
- solvers
- fft-galerkin
- spectral
- convergence
- accelerated-schemes
- iterative
- nesterov
- momentum
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-solver-basic-scheme
  type: requires
  weight: 1.0
  note: Fast gradient methods augment the basic scheme's gradient descent with momentum
- to: fft-lippmann-schwinger
  type: requires
  weight: 0.9
  note: Operates on the Lippmann-Schwinger equation with momentum acceleration
- to: fft-green-operator
  type: requires
  weight: 0.9
  note: Uses the Green's operator for strain update in Fourier space
- to: fft-reference-medium
  type: requires
  weight: 0.8
  note: Step size and momentum parameters depend on material bounds alpha_+/alpha_-
- to: fft-solver-barzilai-borwein
  type: refines
  weight: 0.6
  note: Both accelerate gradient descent; BB is adaptive, Nesterov uses fixed parameters
- to: fft-solver-nonlinear-cg
  type: refines
  weight: 0.7
  note: Nonlinear CG typically outperforms Nesterov in FFT benchmarks
- to: fft-convergence-schemes
  type: feeds-into
  weight: 0.7
  note: Achieves optimal sqrt(kappa) convergence rate for strongly convex problems
context_size: medium
reading_priority: full
load_with:
- fft-solver-basic-scheme
- fft-reference-medium
content_ref: null
akms_schema: v2
---

# Fast Gradient Methods (Nesterov-Type)

## Summary
Fast gradient methods augment the basic scheme's plain gradient descent with a momentum term, accelerating convergence from linear $O(\kappa)$ to optimal $O(\sqrt{\kappa})$ scaling. Two variants exist: the heavy ball method evaluates the gradient at the current iterate and adds momentum to the update, while Nesterov's method evaluates the gradient at an extrapolated point that incorporates momentum. Both can be interpreted as time discretizations of a damped Newtonian dynamical system. For FFT-based homogenization, the Nesterov variant with parameters $s_k = 1/\alpha_+$ and $\beta_k = (\sqrt{\alpha_+} - \sqrt{\alpha_-})/(\sqrt{\alpha_+} + \sqrt{\alpha_-})$ provides guaranteed convergence for strongly convex problems with Lipschitz gradients. Memory footprint is 2 strain fields with two FFT evaluations per iteration. In practice, the methods suffer from sensitive parameter selection and lag behind BB and nonlinear CG by a factor of 2-3 in iteration count even with adaptive restart strategies.


## 1. Core Concept
Fast gradient methods improve upon the basic scheme by incorporating inertia from previous iterates, analogous to a physical system with momentum. In Nesterov's formulation, the gradient is evaluated not at the current strain $\boldsymbol{\varepsilon}_k$ but at an extrapolated point $\mathbf{e}_k = \boldsymbol{\varepsilon}_k + \beta_k(\boldsymbol{\varepsilon}_k - \boldsymbol{\varepsilon}_{k-1})$ that "looks ahead" along the trajectory. This extrapolation allows the method to accelerate through flat regions of the energy landscape while maintaining stability. The heavy ball variant instead evaluates the gradient at $\boldsymbol{\varepsilon}_k$ and adds the momentum term directly to the strain update. Both methods arise as discretizations of the ODE $\ddot{\mathbf{u}}(t) + b \dot{\mathbf{u}}(t) = -\nabla W(\mathbf{u}(t))$ with damping coefficient $b$. The optimal parameters require knowledge of the Lipschitz constant $\alpha_+$ and strong convexity constant $\alpha_-$, which are often difficult to estimate for nonlinear materials, motivating the use of adaptive restart strategies.


## 2. Mathematical Formulation
The two fast gradient variants differ in where the gradient is evaluated and in the optimal parameter selection. The heavy ball method has a slightly faster theoretical rate but requires the stress operator to derive from a potential. Nesterov's method applies to general strongly convex functions with Lipschitz gradients. Both achieve the optimal $\sqrt{\kappa}$ iteration scaling.


**Nesterov extrapolated point:**

$$
\mathbf{e}_k = \boldsymbol{\varepsilon}_k + \beta_k (\boldsymbol{\varepsilon}_k - \boldsymbol{\varepsilon}_{k-1})
$$

where beta_k is the momentum parameter, epsilon_{k-1} is the previous strain iterate

**Nesterov strain update:**

$$
\boldsymbol{\varepsilon}_{k+1} = \bar{\boldsymbol{\varepsilon}} - s_k \boldsymbol{\Gamma} \colon \left( \boldsymbol{\sigma}(\mathbf{e}_k) - \frac{1}{s_k} \mathbf{e}_k \right)
$$

where s_k is the step size, Gamma is the Green's operator, sigma is evaluated at the extrapolated point

**Nesterov optimal parameters:**

$$
s_k = \frac{1}{\alpha_+}, \quad \beta_k = \frac{\sqrt{\alpha_+} - \sqrt{\alpha_-}}{\sqrt{\alpha_+} + \sqrt{\alpha_-}}
$$

where alpha_+ is the Lipschitz constant, alpha_- is the strong convexity constant

**Nesterov convergence estimate:**

$$
\|\boldsymbol{\varepsilon}_k - \boldsymbol{\varepsilon}^*\|_{L^2} \le C \left(1 - \sqrt{\frac{\alpha_-}{\alpha_+}}\right)^k \|\boldsymbol{\varepsilon}_0 - \boldsymbol{\varepsilon}^*\|_{L^2}
$$

where C is a fixed constant, the rate depends on sqrt(alpha_-/alpha_+) giving sqrt(kappa) scaling

**Heavy ball strain update:**

$$
\boldsymbol{\varepsilon}_{k+1} = \bar{\boldsymbol{\varepsilon}} - s_k \boldsymbol{\Gamma} \colon \left( \boldsymbol{\sigma}(\boldsymbol{\varepsilon}_k) - \frac{1}{s_k} \boldsymbol{\varepsilon}_k \right) + \beta_k (\boldsymbol{\varepsilon}_k - \boldsymbol{\varepsilon}_{k-1})
$$

where Gradient evaluated at current iterate epsilon_k, momentum added to update

**Heavy ball optimal parameters:**

$$
\frac{1}{s_k} = \left(\frac{\sqrt{\alpha_-} + \sqrt{\alpha_+}}{2}\right)^2, \quad \beta_k = \left(\frac{\sqrt{\alpha_+} - \sqrt{\alpha_-}}{\sqrt{\alpha_+} + \sqrt{\alpha_-}}\right)^2
$$

where Optimal for linear elasticity and potential-based stress operators

**Notation:**

- $\mathbf{e}_k$ — Extrapolated point (Nesterov variant)
- $\boldsymbol{\varepsilon}_k$ — Strain field at iteration k
- $\beta_k$ — Momentum parameter
- $s_k$ — Algorithmic step size
- $\alpha_+$ — Lipschitz constant of the stress operator
- $\alpha_-$ — Strong convexity (monotonicity) constant
- $\boldsymbol{\Gamma}$ — Non-dimensional Green's operator
- $\kappa$ — Condition number alpha_+/alpha_-


## 3. Algorithmic Implementation
**Algorithm: Nesterov Fast Gradient Method**

$$
\begin{algorithmic}
\State $\boldsymbol{\varepsilon}_0(\mathbf{x}) \leftarrow \bar{\boldsymbol{\varepsilon}}, \quad \boldsymbol{\varepsilon}_{-1} \leftarrow \boldsymbol{\varepsilon}_0$
\State $s \leftarrow 1/\alpha_+, \quad \beta \leftarrow (\sqrt{\alpha_+} - \sqrt{\alpha_-})/(\sqrt{\alpha_+} + \sqrt{\alpha_-})$
\For{$k = 0, 1, 2, \ldots$}
    \State $\mathbf{e}_k \leftarrow \boldsymbol{\varepsilon}_k + \beta (\boldsymbol{\varepsilon}_k - \boldsymbol{\varepsilon}_{k-1})$
    \State $\boldsymbol{\sigma}_k \leftarrow \boldsymbol{\sigma}(\mathbf{e}_k)$
    \State $\boldsymbol{\tau}_k \leftarrow \boldsymbol{\sigma}_k - \frac{1}{s} \mathbf{e}_k$
    \State $\hat{\boldsymbol{\varepsilon}}_{k+1}(\boldsymbol{\xi}) \leftarrow -s \, \hat{\boldsymbol{\Gamma}}(\boldsymbol{\xi}) \colon \widehat{\boldsymbol{\tau}}_k(\boldsymbol{\xi}) \quad \forall \boldsymbol{\xi} \neq \mathbf{0}$
    \State $\hat{\boldsymbol{\varepsilon}}_{k+1}(\mathbf{0}) \leftarrow \bar{\boldsymbol{\varepsilon}}$
    \State $\boldsymbol{\varepsilon}_{k+1} \leftarrow \text{DFT}^{-1}(\hat{\boldsymbol{\varepsilon}}_{k+1})$
    \If{$\|\boldsymbol{\Gamma} \colon \boldsymbol{\sigma}(\boldsymbol{\varepsilon}_{k+1})\|_{L^2} / \|\langle \boldsymbol{\sigma}_{k+1} \rangle\| < \text{tol}$}
        \State \textbf{break}
    \EndIf
\EndFor
\end{algorithmic}
$$

**Taichi Mapping:**
Extrapolation e_k = epsilon_k + beta*(epsilon_k - epsilon_{k-1}) is a pointwise Taichi kernel requiring both current and previous strain fields (2-field footprint). Stress evaluation at the extrapolated point and FFT operations are identical to the basic scheme. Restart logic (speed restart or Fercoq-Qu) adds a conditional branch resetting beta to zero when the residual increases.


## 4. Known Pitfalls
**Sensitive parameter selection:** The optimal parameters $s_k$ and $\beta_k$ require knowledge of the Lipschitz constant $\alpha_+$ and strong convexity constant $\alpha_-$. For nonlinear materials, these bounds may be strain-dependent and difficult to estimate a priori. For porous materials, the effective strong convexity constant is unknown and determining it can be more difficult than solving the problem itself.


**Restart strategies add overhead:** Adaptive restart strategies (speed restart by Su et al., Fercoq-Qu restart) are needed to handle unknown material parameters, but they increase the iteration count by a factor of 2-3 compared to the optimal fixed-parameter choice in the linear case. This makes Nesterov's method lag behind BB and nonlinear CG in practice.


**Heavy ball method requires potential-based stress:** The heavy ball variant with optimal parameters is only valid when the stress operator derives from a potential (symmetric positive definite tangent). For general monotone but non-symmetric operators, only Nesterov's method provides convergence guarantees. Using heavy ball parameters on non-potential operators can cause divergence.


**Instability near sharp contrasts:** The momentum term amplifies oscillations near material interfaces with sharp stiffness jumps. In the presence of high contrast or geometric singularities, the extrapolated point $\mathbf{e}_k$ can overshoot into physically unreasonable strain states, particularly for finite strain formulations.


**Inferior to CG and BB in FFT benchmarks:** Despite achieving the theoretically optimal $\sqrt{\kappa}$ rate, Nesterov's method with restart consistently requires 2-3 times more iterations than linear CG, Fletcher-Reeves nonlinear CG, BB, and L-BFGS of depth four in published FFT benchmarks. The constant factor in the convergence estimate is larger than for these competing methods.


## 5. References
- Schneider (2021) -- review of nonlinear FFT-based computational homogenization, fast gradient methods (Nesterov and heavy ball)
- Lucarini et al. (2022) -- Nesterov's method and momentum-based acceleration for FFT homogenization

