---
id: fft-solver-krylov-cg
title: Conjugate Gradient for FFT Homogenization
domain: fft-galerkin
subdomain: solver-algorithms
tags:
- solvers
- krylov-solver
- conjugate-gradient
- fft-galerkin
- convergence
- iterative
- preconditioning
status: established
confidence: 0.9
source: hybrid
edges:
- to: fft-lippmann-schwinger
  type: requires
  weight: 1.0
  note: CG solves the Lippmann-Schwinger equation as a linear system
- to: fft-green-operator
  type: requires
  weight: 0.9
  note: Green's operator application is the dominant cost per CG iteration
- to: fft-reference-medium
  type: requires
  weight: 0.8
  note: L-S formulation acts as preconditioning by the reference medium
- to: fft-solver-basic-scheme
  type: refines
  weight: 0.9
  note: CG achieves sqrt(kappa) convergence vs linear kappa for basic scheme
- to: fft-solver-nonlinear-cg
  type: feeds-into
  weight: 0.8
  note: Linear CG is a special case of nonlinear CG with exact line search
- to: fft-solver-newton-krylov
  type: feeds-into
  weight: 1.0
  note: CG is used as the inner linear solver in Newton-CG
- to: fft-solver-krylov-minres
  type: refines
  weight: 0.7
  note: MINRES is the alternative Krylov solver for indefinite symmetric systems
context_size: medium
reading_priority: full
load_with:
- fft-lippmann-schwinger
- fft-green-operator
- fft-reference-medium
content_ref: null
akms_schema: v2
---

# Conjugate Gradient for FFT Homogenization

## Summary
The Conjugate Gradient (CG) method is a Krylov subspace solver applied to the Lippmann-Schwinger equation of FFT-based homogenization. CG iteratively selects a solution from expanding Krylov subspaces by minimizing a quadratic energy functional $\phi_{A,b}(\mathbf{x}) = \frac{1}{2}\mathbf{x}^T A \mathbf{x} - \mathbf{b}^T \mathbf{x}$. Although the strain-based L-S operator $\mathbf{Id} + \boldsymbol{\Gamma}^0 \colon (\mathbf{C} - \mathbf{C}^0)$ appears non-symmetric on $L^2$, it is symmetric and positive definite on the subspace of compatible strain fields, justifying CG. The key advantage over fixed-point schemes is convergence scaling with $\sqrt{\kappa}$ instead of $\kappa$ (where $\kappa$ is the phase contrast), with iteration count independent of mesh size. The L-S formulation itself serves as preconditioning by the reference medium operator $P = -\mathrm{div}\,\mathbf{C}^0 \nabla^s$, removing mesh-size dependence from the condition number. CG requires storing 4 strain fields and extends to nonlinear problems via the Fletcher-Reeves nonlinear CG formulation.


## 1. Core Concept
The CG method solves the strain-based Lippmann-Schwinger equation $(\mathbf{Id} + \boldsymbol{\Gamma}^0 \colon (\mathbf{C}(\mathbf{x}) - \mathbf{C}^0)) \colon \boldsymbol{\varepsilon}(\mathbf{x}) = \bar{\boldsymbol{\varepsilon}}$ as a symmetric positive definite linear system. Each CG iteration requires one application of the Green's operator (via FFT) and one constitutive law evaluation, making it computationally equivalent in cost-per-iteration to the basic scheme. The L-S equation can be interpreted as a preconditioned balance of linear momentum: the preconditioner $P = -\mathrm{div}\,\mathbf{C}^0 \nabla^s$ with inverse $P^{-1} = -\mathbf{G}^0$ removes mesh-size dependence from the condition number but retains dependence on the material contrast. The symmetry and positive definiteness hold on the restricted subspace of compatible strain fields, as shown by $\int_Y \boldsymbol{\varepsilon}_1 \colon \mathbf{C}^0 \colon ((\mathbf{Id} + \boldsymbol{\Gamma}^0 \colon (\mathbf{C} - \mathbf{C}^0)) \colon \boldsymbol{\varepsilon}_2)\,dx = \int_Y \boldsymbol{\varepsilon}_1 \colon \mathbf{C} \colon \boldsymbol{\varepsilon}_2\,dx$ for all compatible $\boldsymbol{\varepsilon}_i = \nabla^s \mathbf{u}_i$. Alternatively, the displacement-based FFT (DBFFT) method solves directly for $\hat{\tilde{\mathbf{u}}}$ in Fourier space with an explicit preconditioner $\mathbf{M}(\boldsymbol{\xi}) = [\boldsymbol{\xi} \cdot \mathbf{C} \cdot \boldsymbol{\xi}]^{-1}$.


## 2. Mathematical Formulation
The CG method operates on two equivalent formulations of the linear homogenization problem. In the strain-based form, the unknown is the strain field and the operator is the L-S operator preconditioned by the reference medium. In the displacement-based form (DBFFT), the unknown is the fluctuating displacement in Fourier space and the system is Hermitian. The Krylov subspace framework selects iterates that optimally minimize the energy functional over expanding subspaces.


**Strain-based Lippmann-Schwinger system:**

$$
(\mathbf{Id} + \boldsymbol{\Gamma}^0 \colon (\mathbf{C}(\mathbf{x}) - \mathbf{C}^0)) \colon \boldsymbol{\varepsilon}(\mathbf{x}) = \bar{\boldsymbol{\varepsilon}}
$$

where Gamma0 is the Green's operator, C is the local stiffness, C0 is the reference stiffness

**CG energy functional (objective):**

$$
\phi_{A,b}(\mathbf{x}) = \frac{1}{2}\mathbf{x}^T A \mathbf{x} - \mathbf{b}^T \mathbf{x}
$$

where A is the symmetric positive definite L-S operator restricted to compatible fields, b = eps_bar

**Krylov subspace:**

$$
\mathcal{K}_k(A;\mathbf{b}) = \left\{ \sum_{j=0}^{k-1} \alpha_j A^j \mathbf{b} \right\}
$$

where k is the iteration number, the CG iterate x_k minimizes phi over K_{k+1}

**Symmetry on compatible fields:**

$$
\int_Y \boldsymbol{\varepsilon}_1 \colon \mathbf{C}^0 \colon ((\mathbf{Id} + \boldsymbol{\Gamma}^0 \colon (\mathbf{C} - \mathbf{C}^0)) \colon \boldsymbol{\varepsilon}_2)\,dx = \int_Y \boldsymbol{\varepsilon}_1(\mathbf{x}) \colon \mathbf{C}(\mathbf{x}) \colon \boldsymbol{\varepsilon}_2(\mathbf{x})\,dx
$$

where Holds for all compatible eps_i = grad^s u_i with u_i in H1_per(Y)

**Search direction update (nonlinear CG / Fletcher-Reeves):**

$$
\mathbf{d}_k = -\nabla W(\mathbf{u}_k) + \gamma_{k-1} \mathbf{d}_{k-1}
$$

where d_k is the search direction, nabla W is the energy gradient

**Displacement update:**

$$
\mathbf{u}_{k+1} = \mathbf{u}_k + s_k \mathbf{d}_k
$$

where s_k is the step size, for linear problems s_k is computed via exact line search

**Fletcher-Reeves conjugate parameter:**

$$
\gamma_{k-1} = \frac{\|\nabla W(\mathbf{u}_k)\|^2}{\|\nabla W(\mathbf{u}_{k-1})\|^2}
$$

where Ratio of squared gradient norms; reduces to linear CG for linear elastic problems with exact line search

**DBFFT preconditioner:**

$$
\mathbf{M}(\boldsymbol{\xi}) = [\boldsymbol{\xi} \cdot \mathbf{C} \cdot \boldsymbol{\xi}]^{-1} \quad \text{for } \boldsymbol{\xi} \neq \mathbf{0}
$$

where Left preconditioner for the displacement-based FFT system evaluated at each frequency

**Convergence rate bound:**

$$
N_{\text{iter}} \sim \sqrt{\kappa}, \quad \kappa = \alpha_+ / \alpha_-
$$

where kappa is the material contrast; basic scheme scales as kappa (linear)

**Notation:**

- $\boldsymbol{\Gamma}^0$ — Green's operator for the reference medium
- $\mathbf{C}^0$ — Reference medium stiffness tensor
- $\mathbf{C}(\mathbf{x})$ — Local material stiffness at position x
- $\bar{\boldsymbol{\varepsilon}}$ — Prescribed macroscopic strain
- $\kappa$ — Phase contrast ratio alpha_+/alpha_-
- $\nabla W$ — Gradient of the stored energy functional
- $\gamma_{k-1}$ — Conjugate parameter (Fletcher-Reeves formula)
- $s_k$ — Step size parameter


## 3. Algorithmic Implementation
**Algorithm: Conjugate Gradient for Strain-Based L-S Equation**

$$
\begin{algorithmic}
\State $Initialize \colon \boldsymbol{\varepsilon}_0 = \bar{\boldsymbol{\varepsilon}}, \; \mathbf{r}_0 = \bar{\boldsymbol{\varepsilon}} - (\mathbf{Id} + \boldsymbol{\Gamma}^0 \colon (\mathbf{C} - \mathbf{C}^0)) \colon \boldsymbol{\varepsilon}_0, \; \mathbf{d}_0 = \mathbf{r}_0$
\While{$\|\mathbf{r}_k\| / \|\bar{\boldsymbol{\varepsilon}}\| > \text{tol}$}
    \State $\mathbf{q}_k = (\mathbf{Id} + \boldsymbol{\Gamma}^0 \colon (\mathbf{C} - \mathbf{C}^0)) \colon \mathbf{d}_k$
    \State $\alpha_k = \langle \mathbf{r}_k, \mathbf{r}_k \rangle / \langle \mathbf{d}_k, \mathbf{q}_k \rangle$
    \State $\boldsymbol{\varepsilon}_{k+1} = \boldsymbol{\varepsilon}_k + \alpha_k \mathbf{d}_k$
    \State $\mathbf{r}_{k+1} = \mathbf{r}_k - \alpha_k \mathbf{q}_k$
    \State $\beta_k = \langle \mathbf{r}_{k+1}, \mathbf{r}_{k+1} \rangle / \langle \mathbf{r}_k, \mathbf{r}_k \rangle$
    \State $\mathbf{d}_{k+1} = \mathbf{r}_{k+1} + \beta_k \mathbf{d}_k$
\EndWhile
\end{algorithmic}
$$

**Taichi Mapping:**
Each CG iteration maps to two Taichi kernels: (1) a real-space kernel for constitutive evaluation (C - C0) : eps at each voxel, (2) a spectral kernel applying Gamma0 via batched FFT. Inner products are parallel reductions. All 4 strain fields (eps, r, d, q) stored as Taichi fields on GPU.

**Algorithm: Nonlinear CG (Fletcher-Reeves) for FFT Homogenization**

$$
\begin{algorithmic}
\State $Initialize \colon \mathbf{u}_0 = \mathbf{0}, \; \nabla W_0 = \boldsymbol{\Gamma} \colon \boldsymbol{\sigma}(\bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}_0), \; \mathbf{d}_0 = -\nabla W_0$
\While{$\|\nabla W(\mathbf{u}_k)\| > \text{tol}$}
    \State $\mathbf{u}_{k+1} = \mathbf{u}_k + s_k \mathbf{d}_k, \quad s_k = (\alpha_+ + \alpha_-)/2$
    \State $\nabla W_{k+1} = \boldsymbol{\Gamma} \colon \boldsymbol{\sigma}(\bar{\boldsymbol{\varepsilon}} + \nabla^s \mathbf{u}_{k+1})$
    \State $\gamma_k = \|\nabla W_{k+1}\|^2 / \|\nabla W_k\|^2$
    \State $\mathbf{d}_{k+1} = -\nabla W_{k+1} + \gamma_k \mathbf{d}_k$
\EndWhile
\end{algorithmic}
$$

**Taichi Mapping:**
Same kernel structure as linear CG but with nonlinear constitutive evaluation. Requires only 3 displacement/strain fields. The fixed step size s_k eliminates inner loops. Parallel norm reductions for conjugate parameter computation.


## 4. Known Pitfalls
**Failure for infinite contrast (voids/rigid inclusions):** The L-S linear system becomes ill-posed for infinite phase contrast ($\kappa \to \infty$), causing CG to fail to converge. For porous materials, the condition number diverges because the basic scheme attempts a $\mathbf{C}^0$-elastic extension into void space, which is incompatible with trigonometric polynomial discretizations. Discrete (finite difference) discretizations like Willot's scheme are required to handle voids stably.


**Hidden symmetry requires compatible strain subspace:** The strain-based L-S operator is NOT symmetric on the full $L^2(Y;\mathrm{Sym}(d))$ space. It is only symmetric and positive definite when restricted to compatible strain fields $\boldsymbol{\varepsilon} = \nabla^s \mathbf{u}$. Despite this, CG converges identically to BiCGStab (a non-symmetric solver) because the CG iterates automatically remain in the compatible subspace. This was a surprising empirical finding by Zeman et al. explained theoretically by Vondrejc et al.


**Memory cost in Newton-CG context:** Standalone linear CG requires only 4 strain fields. However, when used as the inner solver in Newton-CG, total memory explodes to 8.5 strain fields plus the tangent stiffness (21 GB for symmetric tangent at $512^3$ voxels). For a $512^3$ grid, Newton-CG requires approximately 51 GB total vs. 6 GB for the basic scheme.


**Nonlinear CG step size is fixed, not optimal:** The nonlinear CG extension uses a fixed step size $s_k = (\alpha_+ + \alpha_-)/2$ to avoid expensive line searches (each line search step requires a full constitutive law evaluation). This is only optimal for linear problems; for nonlinear materials with strain-dependent moduli, the fixed step size may lead to slower convergence compared to methods with adaptive step sizes.


**Discretization affects convergence behavior:** CG convergence is sensitive to the choice of spatial discretization. The Moulinec-Suquet (trigonometric polynomial) discretization causes CG residual stagnation for porous materials. Willot's finite-difference discretization, staggered grids, and higher-order central differences all yield different convergence profiles for the same microstructure.


## 5. References
- Schneider (2021) -- Krylov subspace methods, CG for L-S equation, nonlinear CG with Fletcher-Reeves
- Lucarini et al. (2022) -- Krylov solver algorithm, DBFFT preconditioner, finite strain extensions
- Zeman et al. (2010) -- First application of CG to strain-based L-S equation
- Vondrejc et al. (2012) -- Proof of symmetry on compatible strain subspace
- Brisard and Dormieux (2010) -- CG for polarization-based L-S, preconditioning interpretation

