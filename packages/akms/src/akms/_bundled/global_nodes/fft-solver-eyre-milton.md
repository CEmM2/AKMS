---
id: fft-solver-eyre-milton
title: Eyre-Milton Accelerated Scheme
domain: fft-galerkin
subdomain: solver-algorithms
tags:
- solvers
- polarization
- fft-galerkin
- convergence
- accelerated-schemes
- iterative
- operator-splitting
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: Rewrites the Lippmann-Schwinger equation for the polarization field
- to: fft-green-operator
  type: requires
  weight: 1.0
  note: Helmholtz reflection operator Y^0 = Id - 2C^0 Gamma^0 built from the Green's operator
- to: fft-reference-medium
  type: requires
  weight: 0.9
  note: Optimal reference stiffness is geometric mean alpha_0 = sqrt(alpha_- alpha_+)
- to: fft-solver-basic-scheme
  type: requires
  weight: 0.8
  note: Generalizes the basic scheme via Cayley transform and Peaceman-Rachford splitting
- to: fft-solver-polarization-admm
  type: refines
  weight: 0.9
  note: Eyre-Milton is Peaceman-Rachford splitting (gamma=0); ADMM is Douglas-Rachford (gamma=1/2)
- to: fft-convergence-schemes
  type: feeds-into
  weight: 0.7
  note: Achieves sqrt(kappa) convergence, matching the optimal Krylov rate
- to: fft-solver-krylov-cg
  type: feeds-into
  weight: 0.6
  note: Matches CG worst-case convergence rate with lower memory footprint
context_size: medium
reading_priority: full
load_with:
- fft-solver-polarization-admm
- fft-reference-medium
- fft-green-operator
content_ref: null
akms_schema: v2
---

# Eyre-Milton Accelerated Scheme

## Summary
The Eyre-Milton accelerated scheme reformulates the Lippmann-Schwinger equation as a fixed-point iteration on the polarization field using the Cayley transform and the Helmholtz reflection operator. It corresponds to the Peaceman-Rachford operator splitting with zero damping ($\gamma = 0$). The method converges linearly for any reference material $\mathbf{C}^0$ and any initial polarization, with the iteration count scaling as $\sqrt{\kappa}$ (square root of the contrast ratio) under the optimal geometric mean reference stiffness $\alpha_0 = \sqrt{\alpha_- \alpha_+}$. This matches the fastest Krylov solvers while requiring only 2 fields in memory.


## 1. Core Concept
The key insight is to rewrite the Lippmann-Schwinger equation in terms of the polarization field $P = \frac{\partial w}{\partial \varepsilon} + \mathbf{C}^0 \colon \varepsilon$ and construct a fixed-point iteration using two non-expansive operators. The Cayley transform $\mathcal{Z}_0(P) = (\frac{\partial w}{\partial \varepsilon} - \mathbf{C}^0)(\frac{\partial w}{\partial \varepsilon} + \mathbf{C}^0)^{-1}(P)$ maps the nonlinear constitutive law into an $L^2$-contraction for every choice of reference medium, while the Helmholtz reflection operator $\mathcal{Y}^0 = \mathbf{Id} - 2\mathbf{C}^0 \colon \Gamma^0$ provides the non-expansive projection onto compatible fields. The composition $\mathcal{Y}^0 \colon \mathcal{Z}_0$ is contractive, guaranteeing convergence. Unlike the basic scheme where the reference medium must be sufficiently stiff for stability, the Eyre-Milton method converges for any $\mathbf{C}^0$, with the geometric mean reference giving the fastest rate proportional to $\sqrt{\kappa}$ rather than the linear $\kappa$ scaling of the basic scheme.


## 2. Mathematical Formulation
The Eyre-Milton iteration updates the polarization field using the Helmholtz reflection operator applied to the Cayley transform. The Cayley transform acts as a pointwise nonlinear solve at each grid point, while the Helmholtz reflection involves a global FFT-based convolution. The convergence rate depends on the spectral radius of the composition of these two operators.


**Eyre-Milton polarization iteration:**

$$
P_{k+1} = 2\mathbf{C}^0 \colon \bar{\varepsilon} + \mathcal{Y}^0 \colon \mathcal{Z}_0(P_k)
$$

where P_k is the polarization at iteration k, Y^0 is the Helmholtz reflection operator, Z_0 is the Cayley transform

**Helmholtz reflection operator:**

$$
\mathcal{Y}^0 = \mathbf{Id} - 2\mathbf{C}^0 \colon \Gamma^0
$$

where Gamma^0 is the Green's operator; Y^0 is non-expansive in the C^0-weighted L^2 norm

**Cayley transform of the nonlinear stress operator:**

$$
\mathcal{Z}_0(P) = \left(\frac{\partial w}{\partial \varepsilon} - \mathbf{C}^0\right)\left(\frac{\partial w}{\partial \varepsilon} + \mathbf{C}^0\right)^{-1}(P)
$$

where w is the condensed free energy; Z_0 is an L^2-contraction for any reference C^0

**Cayley transform explicit form:**

$$
\mathcal{Z}_0(P) = P - 2\mathbf{C}^0 \colon \left(\frac{\partial w}{\partial \varepsilon} + \mathbf{C}^0\right)^{-1}(P)
$$

where Equivalent form requiring a single local nonlinear solve per grid point

**Optimal reference stiffness:**

$$
\alpha_0^{\text{opt}} = \sqrt{\alpha_- \alpha_+}
$$

where Geometric mean of monotonicity and Lipschitz bounds; convergence rate proportional to sqrt(alpha_+/alpha_-)

**Convergence rate scaling:**

$$
\text{iterations} \sim \sqrt{\kappa}, \quad \kappa = \frac{\alpha_+}{\alpha_-}
$$

where kappa is the material contrast ratio; compared to linear kappa scaling for the basic scheme

**Notation:**

- $P_k$ — Polarization field at iteration k
- $\mathcal{Y}^0$ — Helmholtz reflection operator
- $\mathcal{Z}_0$ — Cayley transform of the nonlinear stress operator
- $\mathbf{C}^0$ — Reference medium stiffness tensor
- $\Gamma^0$ — Green's operator of the reference medium
- $\alpha_0$ — Scalar reference medium parameter
- $\alpha_+$ — Lipschitz constant of the stress operator
- $\alpha_-$ — Strong monotonicity (convexity) constant
- $\kappa$ — Material contrast ratio alpha_+/alpha_-


## 3. Algorithmic Implementation
**Algorithm: Eyre-Milton Accelerated Scheme**

$$
\begin{algorithmic}
\State $P_0(\mathbf{x}) \leftarrow 2\mathbf{C}^0 \colon \bar{\varepsilon}$
\State $\alpha_0 \leftarrow \sqrt{\alpha_- \alpha_+}$
\While{$\|P_{k+1} - P_k\|_{L^2} / \|P_{k+1}\|_{L^2} > \text{tol}$}
    \State $e_k \leftarrow \left(\frac{\partial w}{\partial \varepsilon} + \mathbf{C}^0\right)^{-1}(P_k) \quad \text{(local nonlinear solve per voxel)}$
    \State $\mathcal{Z}_0(P_k) \leftarrow P_k - 2\mathbf{C}^0 \colon e_k$
    \State $\hat{Q}_k \leftarrow \text{DFT}(\mathcal{Z}_0(P_k))$
    \State $\hat{R}_k(\boldsymbol{\xi}) \leftarrow \hat{Q}_k(\boldsymbol{\xi}) - 2\mathbf{C}^0 \colon \hat{\Gamma}^0(\boldsymbol{\xi}) \colon \hat{Q}_k(\boldsymbol{\xi}) \quad \forall \boldsymbol{\xi} \neq \mathbf{0}$
    \State $\hat{R}_k(\mathbf{0}) \leftarrow \hat{Q}_k(\mathbf{0})$
    \State $P_{k+1} \leftarrow 2\mathbf{C}^0 \colon \bar{\varepsilon} + \text{DFT}^{-1}(\hat{R}_k)$
\EndWhile
\end{algorithmic}
$$

**Taichi Mapping:**
The local nonlinear solve for the Cayley transform maps to a Taichi parallel kernel over all voxels. The Helmholtz reflection decomposes into a forward FFT, pointwise Fourier-space kernel applying Id - 2C^0 Gamma^0, and inverse FFT. Convergence check requires a parallel reduction for the L^2 norm. Total memory is 2 polarization fields (P_k and P_{k+1}).


## 4. Known Pitfalls
**Local nonlinear solve for the Cayley transform:** Each iteration requires inverting $(\frac{\partial w}{\partial \varepsilon} + \mathbf{C}^0)$ at every grid point. For complex nonlinear constitutive laws (e.g., crystal plasticity), this local Newton iteration can be expensive. The cost per iteration is comparable to ADMM but higher than the basic scheme, which only evaluates the forward stress operator.


**No direct access to stress and strain fields:** The Eyre-Milton scheme iterates on the polarization field $P$, not on strain or stress directly. Extracting the physical strain and stress fields for post-processing requires an additional recovery step after convergence. The compatible strain is $\varepsilon = \bar{\varepsilon} - \Gamma^0 \colon P$ and the stress is $\sigma = P - \mathbf{C}^0 \colon \varepsilon$.


**Convergence criterion differs from gradient-based solvers:** The natural convergence measure is the relative change in the polarization $\|P_{k+1} - P_k\|/\|P_{k+1}\|$, not the equilibrium residual used by gradient-based schemes. This makes direct comparison of stopping tolerances across solver families non-trivial.


**Geometric mean reference medium differs from basic scheme:** The optimal reference for Eyre-Milton is the geometric mean $\sqrt{\alpha_- \alpha_+}$, whereas the basic scheme uses the arithmetic mean $(\alpha_+ + \alpha_-)/2$. Reusing the basic scheme reference medium in the Eyre-Milton method will yield suboptimal convergence. This difference is especially significant for high-contrast materials.


## 5. References
- Schneider (2021) -- review of nonlinear FFT-based computational homogenization, Eyre-Milton scheme and Peaceman-Rachford interpretation
- Eyre and Milton (1999) -- original polarization-based accelerated scheme for composites
- Lucarini et al. (2022) -- operator splitting framework unifying Douglas-Rachford and Peaceman-Rachford for FFT homogenization

