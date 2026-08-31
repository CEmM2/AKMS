---
id: fft-reference-medium
title: Reference Medium Selection
domain: fft-galerkin
subdomain: solver-algorithms
tags:
- fft-galerkin
- homogenization
- convergence
- accelerated-schemes
- spectral
status: established
confidence: 0.9
source: hybrid
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: Reference medium is introduced in the L-S reformulation
- to: fft-solver-basic-scheme
  type: feeds-into
  weight: 1.0
  note: Basic scheme convergence depends critically on C0 choice
- to: fft-solver-eyre-milton
  type: feeds-into
  weight: 0.9
  note: Polarization schemes have different optimal C0
- to: fft-solver-polarization-admm
  type: feeds-into
  weight: 0.9
  note: ADMM methods converge for any C0 but speed depends on choice
- to: fft-convergence-schemes
  type: feeds-into
  weight: 0.7
  note: Convergence rates depend on reference medium
context_size: medium
reading_priority: full
load_with:
- fft-lippmann-schwinger
- fft-solver-basic-scheme
content_ref: null
akms_schema: v2
---

# Reference Medium Selection

## Summary
Reference medium selection determines the convergence behavior of all Lippmann-Schwinger-based FFT solvers. The reference stiffness tensor $\mathbf{C}^0$ is an auxiliary numerical parameter with no physical meaning in the final solution, but it controls the step size of iterative algorithms. For the basic scheme, the optimal choice is the arithmetic mean of extreme phase stiffnesses, with convergence conditional on $\alpha_0 > \alpha_+^2/(2\alpha_-)$. For polarization schemes, convergence is guaranteed for any $\mathbf{C}^0$, with optimal rate at the geometric mean. The iteration count scales linearly with phase contrast for the basic scheme and as $\sqrt{\kappa}$ for Krylov/polarization methods.


## 1. Core Concept
The reference medium with stiffness $\mathbf{C}^0$ is introduced to reformulate the heterogeneous equilibrium problem into the Lippmann-Schwinger integral equation. The polarization field $\boldsymbol{\tau} = (\mathbf{C} - \mathbf{C}^0) \colon \boldsymbol{\varepsilon}$ captures the deviation from the reference. While $\mathbf{C}^0$ does not affect the converged solution, it controls the spectral radius of the iteration operator. The basic scheme can be interpreted as a gradient descent with step size proportional to $1/\alpha_0$, making the choice of $\alpha_0$ analogous to learning rate selection. Different solver families (fixed-point, polarization, Krylov) have fundamentally different sensitivities to this choice.


## 2. Mathematical Formulation
For nonlinear materials, the convergence bounds are expressed in terms of the Lipschitz constant $\alpha_+$ and monotonicity constant $\alpha_-$ of the stress operator. The reference parameter $\alpha_0$ (for $\mathbf{C}^0 = \alpha_0 \mathbf{Id}$) must satisfy specific bounds depending on the solver family. For linear elasticity, these reduce to conditions on the Lame constants of the constituent phases.


**Lipschitz continuity bound:**

$$
\|\boldsymbol{\sigma}(\mathbf{x}, \boldsymbol{\varepsilon}_1) - \boldsymbol{\sigma}(\mathbf{x}, \boldsymbol{\varepsilon}_2)\| \le \alpha_+ \|\boldsymbol{\varepsilon}_1 - \boldsymbol{\varepsilon}_2\|
$$

where alpha_+ is the upper Lipschitz bound on the stress operator

**Monotonicity bound:**

$$
(\boldsymbol{\sigma}(\mathbf{x}, \boldsymbol{\varepsilon}_1) - \boldsymbol{\sigma}(\mathbf{x}, \boldsymbol{\varepsilon}_2)) : (\boldsymbol{\varepsilon}_1 - \boldsymbol{\varepsilon}_2) \ge \alpha_- \|\boldsymbol{\varepsilon}_1 - \boldsymbol{\varepsilon}_2\|^2
$$

where alpha_- is the lower monotonicity bound (strong monotonicity constant)

**Basic scheme convergence condition:**

$$
\alpha_0 > \frac{\alpha_+^2}{2\alpha_-}
$$

where alpha_0 is the scalar reference parameter for C0 = alpha_0 Id

**Relaxed condition (potential-based stress):**

$$
\alpha_0 > \frac{\alpha_+}{2}
$$

where Applies when the stress operator derives from a potential (gradient descent interpretation)

**Optimal C0 for basic scheme (nonlinear):**

$$
\alpha_0^{\text{opt}} = \frac{\alpha_- + \alpha_+}{2}
$$

where Arithmetic mean of the bounds gives fastest convergence for the basic scheme

**Optimal C0 for basic scheme (linear, isotropic):**

$$
\lambda_0 = \frac{1}{2}\left(\inf_{\mathbf{x}} \lambda(\mathbf{x}) + \sup_{\mathbf{x}} \lambda(\mathbf{x})\right), \quad \mu_0 = \frac{1}{2}\left(\inf_{\mathbf{x}} \mu(\mathbf{x}) + \sup_{\mathbf{x}} \mu(\mathbf{x})\right)
$$

where lambda, mu are Lame constants of the phases; inf/sup taken over domain Omega

**Optimal C0 for polarization schemes (nonlinear):**

$$
\alpha_0^{\text{opt}} = \sqrt{\alpha_- \alpha_+}
$$

where Geometric mean of the bounds for Eyre-Milton, ADMM, and augmented Lagrangian

**Optimal C0 for polarization schemes (linear, isotropic):**

$$
\lambda_0 = \sqrt{\inf_{\mathbf{x}} \lambda(\mathbf{x}) \cdot \sup_{\mathbf{x}} \lambda(\mathbf{x})}, \quad \mu_0 = \sqrt{\inf_{\mathbf{x}} \mu(\mathbf{x}) \cdot \sup_{\mathbf{x}} \mu(\mathbf{x})}
$$

where Geometric mean of extreme Lame constants for polarization schemes

**Notation:**

- $\alpha_0$ — Scalar reference medium parameter (C0 = alpha_0 Id)
- $\alpha_+$ — Lipschitz constant of the stress operator (upper bound)
- $\alpha_-$ — Strong monotonicity constant (lower bound)
- $\lambda_0, \mu_0$ — Lame constants of the reference medium
- $\lambda, \mu$ — Local Lame constants of the constituent phases
- $\kappa$ — Phase contrast ratio alpha_+/alpha_-


## 3. Algorithmic Implementation
Not applicable — reference medium selection is a parameter choice, not an algorithm. The selection formulas are in the mathematical formulation section.

## 4. Known Pitfalls
**Divergence from too-soft reference:** Choosing $\mathbf{C}^0$ too soft (below the convergence bound) corresponds to an overly large gradient descent step size and causes the basic scheme to globally diverge. There is no automatic recovery — the simulation simply fails with growing residuals.


**Linear contrast scaling for basic scheme:** The basic scheme requires iterations proportional to the phase contrast ratio $\kappa$. For high-contrast composites (e.g., $\kappa > 100$), the basic scheme becomes impractically slow even with optimal $\mathbf{C}^0$. Krylov and polarization methods reduce this to $\sqrt{\kappa}$.


**Different optima for different solvers:** The arithmetic mean (basic scheme) and geometric mean (polarization schemes) give different optimal $\mathbf{C}^0$. Using the basic-scheme optimum in a polarization method (or vice versa) will work but converge suboptimally. Always match the formula to the solver.


**Nonlinear material parameter estimation:** For nonlinear materials, the Lipschitz and monotonicity constants $\alpha_+$ and $\alpha_-$ may be strain-dependent and difficult to estimate a priori. Overestimating $\alpha_+$ or underestimating $\alpha_-$ leads to a conservative (slow) reference medium choice.


**Porous/void phases have alpha_- = 0:** For porous materials, the monotonicity constant $\alpha_- = 0$ (void has zero stiffness), making the convergence bound $\alpha_0 > \alpha_+^2/(2\alpha_-)$ impossible to satisfy. The basic scheme fundamentally cannot converge for infinite contrast. Polarization schemes or displacement-based methods are required.


## 5. References
- Schneider (2021) — §3.1: basic scheme convergence bounds, §3.5: polarization scheme reference medium
- Lucarini et al. (2022) — §3.2: reference medium role

