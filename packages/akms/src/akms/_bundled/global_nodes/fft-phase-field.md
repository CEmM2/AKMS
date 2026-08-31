---
id: fft-phase-field
title: Phase-Field Fracture with FFT
domain: fft-galerkin
subdomain: coupled-problems
tags:
- fft-galerkin
- phase-field
- fracture
- damage
- homogenization
- spectral
status: established
confidence: 0.9
source: hybrid
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: Mechanical sub-problem solved via Lippmann-Schwinger with degraded stiffness
- to: fft-green-operator
  type: requires
  weight: 0.9
  note: Green's operator applied in the mechanical sub-step of the staggered scheme
- to: fft-solver-basic-scheme
  type: requires
  weight: 0.7
  note: Basic scheme or fast gradient method used as inner solver for mechanical sub-problem
- to: pf-at2-regularization
  type: requires
  weight: 0.9
  note: Phase-field fracture model provides the degradation function and evolution equation
- to: fft-galerkin-basics
  type: requires
  weight: 0.8
  note: FFT framework provides the spectral solver infrastructure
- to: fft-convergence-schemes
  type: feeds-into
  weight: 0.5
  note: Accelerated schemes can be used within the mechanical sub-step
context_size: large
reading_priority: full
load_with:
- fft-lippmann-schwinger
- pf-at2-regularization
content_ref: null
akms_schema: v2
---

# Phase-Field Fracture with FFT

## Summary
Phase-field fracture with FFT solves brittle fracture by smoothing the discrete crack into a continuous damage field $\phi$ concentrated in a thin volume of width $\ell$, where the sharp crack topology is recovered as $\ell \to 0$. The coupled system consists of mechanical equilibrium $\nabla \cdot \boldsymbol{\sigma}(\mathbf{u}, \phi) = 0$ with degraded stiffness $g(\phi) = (1-\phi)^2 + k$, and a phase-field evolution equation $g'(\phi) U_0(\boldsymbol{\varepsilon}) + R(\frac{1}{\ell}\phi - \ell \nabla^2 \phi) = 0$. FFT methods are ideal because the crack path is tracked by $\phi$ on a regular voxel grid without remeshing. A staggered algorithm alternately solves the mechanical sub-problem (via Lippmann-Schwinger with degraded stiffness) and the phase-field sub-problem (a linear Helmholtz-type equation). Discrete Green's operators must replace continuous ones to suppress Gibbs oscillations near the crack interface.


## 1. Core Concept
Phase-field fracture models represent cracks as a continuous damage field $\phi$ that transitions smoothly from intact ($\phi = 0$) to fully broken ($\phi = 1$) over a regularization length $\ell$. The degradation function $g(\phi) = (1-\phi)^2 + k$ couples the damage to the mechanical stiffness, and the phase-field evolution is driven by the elastic strain energy density $U_0$. FFT-based solvers operating on regular voxel grids provide an ideal framework because they avoid the remeshing required by FEM to track evolving crack paths. The coupled system is universally solved by staggered integration that alternately solves the mechanical and phase-field sub-problems, providing robust control over crack propagation. Discrete derivatives and discrete Green's operators are essential to suppress Gibbs oscillations at the sharp damage interfaces.


## 2. Mathematical Formulation
The variational phase-field model balances elastic energy storage (degraded by the damage field) against crack surface energy. The strong form yields two coupled PDEs: mechanical equilibrium with degraded stress, and a reaction-diffusion equation for the phase field. The degradation function $g(\phi)$ couples the two fields. By substituting $g'(\phi) = -2(1-\phi)$, the phase-field equation becomes a linear Helmholtz-type equation that is straightforward to solve in Fourier space.


**Mechanical equilibrium with degraded stiffness:**

$$
\nabla \cdot \boldsymbol{\sigma}(\mathbf{u}, \phi) = 0, \quad \boldsymbol{\sigma} = g(\phi)\,\mathbf{C} : \boldsymbol{\varepsilon}(\mathbf{u})
$$

where sigma is the degraded Cauchy stress, C is the intact elastic stiffness, epsilon is the strain, g(phi) is the degradation function

**Phase-field evolution equation:**

$$
g'(\phi)\,U_0(\boldsymbol{\varepsilon}(\mathbf{u})) + R\left(\frac{1}{\ell}\phi - \ell\,\nabla^2 \phi\right) = 0
$$

where U_0 is the elastic strain energy density of intact material, R is the fracture toughness, ell is the regularization length scale

**Degradation function:**

$$
g(\phi) = (1 - \phi)^2 + k
$$

where k is a small positive residual stiffness parameter to prevent ill-conditioning when phi = 1

**Linearized phase-field equation (Helmholtz form):**

$$
\left(2U_0 + \frac{R}{\ell}\right)\phi - R\ell\,\nabla^2\phi = 2U_0
$$

where Obtained by substituting g'(phi) = -2(1 - phi) and rearranging; linear in phi for fixed epsilon

**Weak form of the coupled energy functional:**

$$
\int_{\partial\Omega_F} \mathbf{t} \cdot \dot{\mathbf{u}}\,dA = \int_\Omega \left[g'(\phi)\,U_0\,\dot{\phi} + R\left(\frac{1}{\ell}\phi\dot{\phi} + \ell\,\nabla\phi \cdot \nabla\dot{\phi}\right)\right]d\Omega - \int_\Omega \nabla \cdot \boldsymbol{\sigma} \cdot \dot{\mathbf{u}}\,d\Omega
$$

where t is the boundary traction on the loaded boundary partial Omega_F

**Lippmann-Schwinger equation for the mechanical sub-problem:**

$$
\hat{\boldsymbol{\varepsilon}}(\boldsymbol{\xi}) = \bar{\boldsymbol{\varepsilon}} - \hat{\boldsymbol{\Gamma}}^0(\boldsymbol{\xi}) : \hat{\boldsymbol{\tau}}(\boldsymbol{\xi}), \quad \boldsymbol{\tau}(\mathbf{x}) = g(\phi)\,\mathbf{C} : \boldsymbol{\varepsilon} - \mathbf{C}^0 : \boldsymbol{\varepsilon}
$$

where Gamma^0 is the Green's operator, tau is the stress polarization with degraded stiffness, C^0 is the reference medium

**Notation:**

- $\phi$ — Phase-field damage variable (0 = intact, 1 = fully broken)
- $g(\phi)$ — Degradation function coupling damage to stiffness
- $U_0$ — Elastic strain energy density of intact material
- $R$ — Fracture toughness (critical energy for unit crack surface)
- $\ell$ — Regularization length scale controlling diffuse crack width
- $k$ — Small residual stiffness parameter for numerical stability
- $\hat{\boldsymbol{\Gamma}}^0$ — Green's operator of the reference medium


## 3. Algorithmic Implementation
**Algorithm: Staggered Algorithm for Phase-Field Fracture with FFT**

$$
\begin{algorithmic}
\State $Initialize \colon \phi_0(\mathbf{x}) = 0, \; \boldsymbol{\varepsilon}_0(\mathbf{x}) = \bar{\boldsymbol{\varepsilon}}$
\For{$\text{each load step } n = 1, 2, \ldots$}
    \While{$\text{staggered iteration not converged}$}
        \State $\text{Step 1 (Mechanical)} \colon \boldsymbol{\sigma}(\mathbf{x}) = g(\phi)\,\mathbf{C} \colon \boldsymbol{\varepsilon}(\mathbf{x})$
        \State $\hat{\boldsymbol{\tau}}(\boldsymbol{\xi}) = \mathcal{F}\{g(\phi)\,\mathbf{C} \colon \boldsymbol{\varepsilon} - \mathbf{C}^0 \colon \boldsymbol{\varepsilon}\}$
        \State $\hat{\boldsymbol{\varepsilon}}_{k+1}(\boldsymbol{\xi}) = \bar{\boldsymbol{\varepsilon}} - \hat{\boldsymbol{\Gamma}}^0_{\mathrm{discrete}}(\boldsymbol{\xi}) \colon \hat{\boldsymbol{\tau}}_k(\boldsymbol{\xi})$
        \State $\text{Iterate mechanical solver until } \|\nabla \cdot \boldsymbol{\sigma}\| < \mathrm{tol}_{\mathrm{mech}}$
        \State $\text{Step 2 (Phase-field)} \colon \left(2U_0(\boldsymbol{\varepsilon}) + \frac{R}{\ell}\right)\phi - R\ell\,\nabla^2\phi = 2U_0(\boldsymbol{\varepsilon})$
        \State $\hat{\phi}(\boldsymbol{\xi}) = \frac{2\hat{U}_0(\boldsymbol{\xi})}{2U_0 + R/\ell + R\ell\,|\boldsymbol{\xi}|^2}$
    \EndWhile
\EndFor
\end{algorithmic}
$$

**Taichi Mapping:**
Both sub-problems are embarrassingly parallel at the voxel level. The mechanical solver uses standard FFT infrastructure. The phase-field Helmholtz solve is a single-pass pointwise division in Fourier space after FFT of U_0. Discrete derivative operators implemented as modified Fourier multipliers (e.g., Willot rotated staggered grid). The damage field phi stored as a scalar ti.field.


## 4. Known Pitfalls
**Gibbs oscillations near crack interfaces:** Phase-field fracture involves sharp transitions in the damage field at the crack boundary. Standard continuous Fourier derivatives produce severe ringing artifacts (Gibbs phenomenon) near these interfaces. Discrete derivatives and discrete Green's operators (e.g., Willot rotated staggered grid or high-order finite differences) must replace continuous ones to maintain stability and accuracy.


**Artificial residual stiffness parameter k:** The degradation function $g(\phi) = (1-\phi)^2 + k$ includes a small positive parameter $k$ to prevent the stiffness matrix from becoming singular when $\phi = 1$. This artificially maintains residual load-bearing capacity in fully damaged regions. The value of $k$ must be small enough not to affect the physics but large enough for numerical stability.


**Length scale ell sensitivity:** The regularization length $\ell$ controls the width of the diffuse crack zone. The sharp crack limit is only recovered as $\ell \to 0$, so results are inherently sensitive to $\ell$. The voxel grid must be fine enough to resolve the damage band (typically several voxels across $\ell$), creating a coupling between mesh resolution and physical accuracy.


**No irreversibility in basic formulation:** The standard variational equations as presented do not include a history variable to enforce damage irreversibility (preventing crack healing upon unloading). Without this constraint, the formulation is strictly valid only for monotonic loading. A strain-energy history field $\mathcal{H}(\mathbf{x}, t) = \max_{\tau \leq t} U_0(\boldsymbol{\varepsilon}(\mathbf{x}, \tau))$ must be added for cyclic or non-monotonic loading.


**Operator splitting errors in staggered scheme:** The staggered algorithm decouples the mechanical and phase-field sub-problems, solving them sequentially. This operator splitting introduces temporal integration errors that can reduce accuracy in strongly coupled regimes. Sufficient staggered iterations per load step are needed to ensure convergence of the coupled system.


## 5. References
- Schneider (2021) -- Phase-field fracture with FFT, staggered algorithms, discrete operators
- Chen et al. -- Variational phase-field fracture model, degradation function, energy functional
- Willot (2015) -- Discrete Green's operators for suppressing Gibbs oscillations

