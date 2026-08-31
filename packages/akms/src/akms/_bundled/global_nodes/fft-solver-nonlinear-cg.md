---
id: fft-solver-nonlinear-cg
title: Nonlinear Conjugate Gradient for FFT
domain: fft-galerkin
subdomain: solver-algorithms
tags:
- solvers
- fft-galerkin
- spectral
- convergence
- accelerated-schemes
- iterative
- conjugate-gradient
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fft-solver-basic-scheme
  type: requires
  weight: 1.0
  note: Uses the basic scheme's gradient computation and step size formula
- to: fft-lippmann-schwinger
  type: requires
  weight: 0.9
  note: Gradient is the Green's operator applied to the stress (L-S residual)
- to: fft-green-operator
  type: requires
  weight: 0.9
  note: Energy gradient computed via Green's operator in Fourier space
- to: fft-reference-medium
  type: requires
  weight: 0.7
  note: Step size alpha_0 = (alpha_+ + alpha_-)/2 from reference medium theory
- to: fft-solver-barzilai-borwein
  type: refines
  weight: 0.7
  note: Comparable iteration count in benchmarks; CG uses conjugate directions, BB uses adaptive step
- to: fft-solver-fast-gradient
  type: refines
  weight: 0.6
  note: CG outperforms Nesterov methods in FFT benchmarks
- to: fft-solver-krylov-cg
  type: refines
  weight: 0.8
  note: For linear problems with exact line search, nonlinear CG produces identical iterates to linear CG
- to: fft-convergence-schemes
  type: feeds-into
  weight: 0.7
  note: Among the fastest gradient-based methods for FFT homogenization
context_size: medium
reading_priority: full
load_with:
- fft-solver-basic-scheme
- fft-solver-barzilai-borwein
content_ref: null
akms_schema: v2
---

# Nonlinear Conjugate Gradient for FFT

## Summary
The nonlinear conjugate gradient (CG) method extends gradient descent for FFT homogenization by building conjugate search directions that accelerate convergence beyond what plain or momentum-augmented gradient methods achieve. The search direction $\mathbf{d}_k$ combines the negative energy gradient with the previous direction scaled by the Fletcher-Reeves coefficient $\gamma_{k-1} = \|\nabla W(\mathbf{u}_k)\|^2 / \|\nabla W(\mathbf{u}_{k-1})\|^2$. To avoid expensive line searches, a fixed step size $\alpha_0 = (\alpha_+ + \alpha_-)/2$ is used. The method can be interpreted as a discrete dynamical system with feedback control. Memory footprint is 3 strain fields with two FFT evaluations per iteration. For linear problems with exact line search, Fletcher-Reeves CG produces identical iterates to the standard linear CG method. It is among the fastest gradient-based FFT solvers, competitive with BB and L-BFGS of depth four.


## 1. Core Concept
The nonlinear CG method improves upon gradient descent by maintaining a search direction that incorporates information from previous iterates via the conjugate parameter $\gamma_{k-1}$. At each iteration, the energy gradient $\nabla W(\mathbf{u}_k) = G \, \partial w / \partial \boldsymbol{\varepsilon}(\cdot, \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}_k)$ is computed by applying the non-dimensional Green's operator $G$ to the stress field in Fourier space. The search direction $\mathbf{d}_k = -\nabla W(\mathbf{u}_k) + \gamma_{k-1} \mathbf{d}_{k-1}$ combines the steepest descent direction with momentum from the previous search direction. The Fletcher-Reeves formula for $\gamma_{k-1}$ is preferred because it automatically degrades to steepest descent when the gradient changes direction sharply, providing implicit restart behavior. The displacement is updated as $\mathbf{u}_{k+1} = \mathbf{u}_k + s_k \mathbf{d}_k$ with the fixed step size from the optimal gradient scheme. The corresponding strain is recovered via $\boldsymbol{\varepsilon}_k = \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}_k$. The method avoids line search entirely, trading the exact conjugacy property for generality and computational efficiency.


## 2. Mathematical Formulation
The nonlinear CG method operates on the displacement fluctuation field and minimizes the total condensed elastic energy. The gradient is computed via the Green's operator, the search direction is updated via the Fletcher-Reeves formula, and the displacement is advanced with a fixed step size. The strain-based formulation can be recovered through the kinematic relation.


**Energy gradient via Green's operator:**

$$
\nabla W(\mathbf{u}_k) = G \frac{\partial w}{\partial \boldsymbol{\varepsilon}}(\cdot, \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}_k)
$$

where G is the non-dimensional Green's operator, w is the condensed free energy density

**Fletcher-Reeves conjugate parameter:**

$$
\gamma_{k-1} = \frac{\|\nabla W(\mathbf{u}_k)\|^2}{\|\nabla W(\mathbf{u}_{k-1})\|^2}
$$

where Ratio of squared gradient norms at consecutive iterations

**Search direction update:**

$$
\mathbf{d}_k = -\nabla W(\mathbf{u}_k) + \gamma_{k-1} \mathbf{d}_{k-1}
$$

where d_k combines negative gradient with previous direction; d_0 = -nabla W(u_0)

**Displacement update:**

$$
\mathbf{u}_{k+1} = \mathbf{u}_k + s_k \mathbf{d}_k
$$

where s_k is the fixed step size parameter

**Fixed step size (no line search):**

$$
\alpha_0 = \frac{\alpha_+ + \alpha_-}{2}
$$

where Identical to the optimal basic scheme reference medium; avoids expensive constitutive evaluations for line search

**Strain recovery:**

$$
\boldsymbol{\varepsilon}_k = \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}_k
$$

where Symmetrized gradient maps displacement fluctuation to total strain

**Strain-space gradient (residual):**

$$
\boldsymbol{\Gamma} \colon \frac{\partial w}{\partial \boldsymbol{\varepsilon}}(\cdot, \boldsymbol{\varepsilon}_k)
$$

where Gamma is the Eshelby-Green operator; this is the L-S residual evaluated in Fourier space

**Notation:**

- $\nabla W$ — Gradient of the total condensed elastic energy
- $G$ — Non-dimensional Green's operator for displacement
- $\boldsymbol{\Gamma}$ — Eshelby-Green operator (strain-based)
- $\mathbf{d}_k$ — Search direction at iteration k
- $\gamma_{k-1}$ — Fletcher-Reeves conjugate parameter
- $s_k$ — Fixed step size (= 1/alpha_0)
- $\alpha_+$ — Lipschitz constant of the stress operator
- $\alpha_-$ — Strong convexity constant
- $\mathbf{u}_k$ — Displacement fluctuation field at iteration k
- $\boldsymbol{\varepsilon}_k$ — Strain field at iteration k


## 3. Algorithmic Implementation
**Algorithm: Nonlinear Conjugate Gradient (Fletcher-Reeves)**

$$
\begin{algorithmic}
\State $\mathbf{u}_0 \leftarrow \mathbf{0}, \quad \boldsymbol{\varepsilon}_0 \leftarrow \bar{\boldsymbol{\varepsilon}}$
\State $\mathbf{g}_0 \leftarrow G \, \partial w / \partial \boldsymbol{\varepsilon}(\cdot, \boldsymbol{\varepsilon}_0)$
\State $\mathbf{d}_0 \leftarrow -\mathbf{g}_0$
\For{$k = 0, 1, 2, \ldots$}
    \State $\mathbf{u}_{k+1} \leftarrow \mathbf{u}_k + s_k \mathbf{d}_k$
    \State $\boldsymbol{\varepsilon}_{k+1} \leftarrow \bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}_{k+1}$
    \State $\mathbf{g}_{k+1} \leftarrow G \, \partial w / \partial \boldsymbol{\varepsilon}(\cdot, \boldsymbol{\varepsilon}_{k+1})$
    \If{$\|\mathbf{g}_{k+1}\| / \|\langle \boldsymbol{\sigma}_{k+1} \rangle\| < \text{tol}$}
        \State \textbf{break}
    \EndIf
    \State $\gamma_k \leftarrow \|\mathbf{g}_{k+1}\|^2 / \|\mathbf{g}_k\|^2$
    \State $\mathbf{d}_{k+1} \leftarrow -\mathbf{g}_{k+1} + \gamma_k \mathbf{d}_k$
\EndFor
\end{algorithmic}
$$

**Taichi Mapping:**
The displacement update and strain recovery are pointwise Taichi kernels. Gradient computation requires one forward FFT (stress to Fourier space), Green's operator application (pointwise in Fourier space), and one inverse FFT. The Fletcher-Reeves coefficient gamma_k requires two global reduction kernels for the gradient norms. Three strain/displacement fields must be stored: current u_k, search direction d_k, and gradient g_k.


## 4. Known Pitfalls
**Fixed step size suboptimality:** The fixed step size $\alpha_0 = (\alpha_+ + \alpha_-)/2$ avoids expensive line searches but sacrifices the exact conjugacy that makes linear CG optimal. For strongly nonlinear problems, the fixed step size can lead to suboptimal search directions and slower convergence than what a line search would achieve. The trade-off is justified because each constitutive evaluation in FFT homogenization is expensive.


**Loss of conjugacy in nonlinear problems:** Theoretical CG guarantees conjugacy of search directions only for linear problems with exact line search. In the nonlinear FFT setting with fixed step size, conjugacy is progressively lost over iterations. The Fletcher-Reeves formula provides implicit restart when the gradient changes direction sharply (gamma becomes small), partially mitigating this issue.


**Higher memory than BB and Nesterov:** Nonlinear CG requires 3 strain fields (current state, search direction, gradient) compared to 2 for BB and Nesterov methods. For large 3D problems with $512^3$ voxels where a single strain field occupies 6 GB, this extra field (18 GB vs 12 GB total) can be significant, though still far less than Newton-CG (51+ GB).


**Requires smooth energy landscape:** The Fletcher-Reeves formula assumes a smooth gradient field. For materials with sharp yield surfaces, damage, or phase transformations that create discontinuities in the stress-strain response, the conjugate parameter $\gamma_{k-1}$ can become unreliable. In such cases, the method may need frequent explicit restarts or a switch to a more robust solver like BB.


**Parameter estimation still needed:** Although the method avoids line search, it still requires estimates of $\alpha_+$ and $\alpha_-$ for the fixed step size. For nonlinear materials, these bounds may be unknown or strain-dependent. Unlike BB which is fully parameter-free, nonlinear CG inherits the reference medium sensitivity of the basic scheme for the step size selection.


## 5. References
- Schneider (2021) -- review of nonlinear FFT-based computational homogenization, nonlinear conjugate gradient with Fletcher-Reeves formula
- Lucarini et al. (2022) -- non-linear conjugate gradient approaches for FFT homogenization

