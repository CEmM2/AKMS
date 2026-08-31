---
id: fem-tl-linearization
title: Consistent Linearization in TL Framework
domain: computational-mechanics
subdomain: finite-elements
tags:
- fem
- finite-strain
- total-lagrangian
- tangent-stiffness
- newton
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: fem-tl-weak-form
  type: requires
  weight: 1.0
  note: Linearisation acts on the residual derived from the TL weak form
- to: fem-tl-b-matrix
  type: requires
  weight: 1.0
  note: Material tangent uses $\mathbf{B}^T\mathbb{C}^{SE}\mathbf{B}$ kernels
- to: stress-piola-kirchhoff
  type: requires
  weight: 1.0
  note: Geometric stiffness uses the current PK2 stress
- to: tensor-derivatives-tensors
  type: requires
  weight: 0.7
  note: $\mathbb{C}^{SE}=\partial \mathbf{S}/\partial \mathbf{E}$ is a tensor-of-tensor derivative
- to: fem-tl-matrix-free-action
  type: feeds-into
  weight: 1.0
  note: Matrix-free action evaluates $(\mathbf{K}_m+\mathbf{K}_\sigma)\mathbf{v}$ without storing $\mathbf{K}$
- to: fem-newton-raphson
  type: feeds-into
  weight: 1.0
  note: Tangent stiffness drives Newton iteration
context_size: large
reading_priority: full
load_with:
- fem-tl-weak-form
- fem-tl-b-matrix
content_ref: null
akms_schema: v2
---

# Consistent Linearization in TL Framework

## Summary
Consistent linearisation of the TL residual $\mathbf{r}(\mathbf{u})=\mathbf{f}^{\mathrm{int}}(\mathbf{u})-\mathbf{f}^{\mathrm{ext}}=\mathbf{0}$ produces the tangent stiffness $\mathbf{K}=\partial\mathbf{f}^{\mathrm{int}}/\partial\mathbf{u}=\mathbf{K}_m+\mathbf{K}_\sigma$. The MATERIAL stiffness $\mathbf{K}_m=\int_{\Omega_0}\mathbf{B}^T\,\mathbb{C}^{SE}\,\mathbf{B}\,dV_0$ uses the constitutive tangent $\mathbb{C}^{SE}=\partial\mathbf{S}/\partial\mathbf{E}$ and the linearised B-matrix; symmetric whenever $\mathbb{C}^{SE}$ has major symmetry (true for hyperelasticity / associative plasticity). The GEOMETRIC (initial-stress) stiffness $\mathbf{K}_\sigma$ comes from the second variation of $\mathbf{E}$ and has the explicit form $K^{\sigma}_{ab,ij}=\delta_{ij}\int_{\Omega_0}(\partial N_a/\partial X_K)(\partial N_b/\partial X_L)\,S_{KL}\,dV_0$ — a scalar contracting with $\delta_{ij}$, hence rotation-invariant. Newton iteration uses $\mathbf{K}\,\Delta\mathbf{u}=-\mathbf{r}$. Dropping $\mathbf{K}_\sigma$ degrades convergence from quadratic to linear at finite strain.


## 1. Core Concept
In TL-FEM the residual $\mathbf{r}(\mathbf{u})$ is nonlinear in $\mathbf{u}$ for two structural reasons: (1) the constitutive law $\mathbf{S}(\mathbf{C})$ is nonlinear; (2) the strain-displacement operator $\mathbf{B}(\mathbf{F})$ depends on displacement through $\mathbf{F}$. Differentiating the residual produces two contributions, mirroring exactly these two sources of nonlinearity. The MATERIAL tangent $\mathbf{K}_m$ comes from differentiating $\mathbf{S}$ at fixed $\mathbf{B}$: it is structurally identical to the linear-elasticity stiffness with $\mathbb{C}^{SE}=\partial\mathbf{S}/\partial\mathbf{E}$ replacing $\mathbb{C}^{\mathrm{linear}}$, and it is the only piece needed in geometrically linear analyses. The GEOMETRIC tangent $\mathbf{K}_\sigma$ comes from differentiating $\mathbf{B}$ at fixed $\mathbf{S}$: it represents the "initial stress" effect that resists infinitesimal deformations from a stressed state and is essential at finite strain. Without $\mathbf{K}_\sigma$, Newton iteration cannot achieve quadratic convergence at finite strain; with it, geometric instabilities (Euler buckling, snap-through) emerge naturally as eigenvalue problems on $\mathbf{K}_m+\mathbf{K}_\sigma$.


## 2. Mathematical Formulation
Throughout, $\mathbf{u}$ is the global nodal-displacement vector; $\mathbf{r}(\mathbf{u})$ residual; $\mathbf{B}_a$ TL B-matrix block for node $a$ (`fem-tl-b-matrix`); $\mathbf{S}$ PK2 stress; $\mathbb{C}^{SE}=\partial\mathbf{S}/\partial\mathbf{E}=2\partial\mathbf{S}/\partial\mathbf{C}$; $\nabla_0 N_a=\partial N_a/\partial\mathbf{X}$.


**Tangent stiffness from residual:**

$$
\mathbf{K}_{ab} = \frac{\partial \mathbf{f}^{\mathrm{int}}_a}{\partial \mathbf{u}_b}
             = \mathbf{K}^m_{ab} + \mathbf{K}^\sigma_{ab}
$$

where Material + geometric decomposition; subscripts $a,b$ index nodes, components $i,j$ implied

**Material tangent (Voigt form):**

$$
\mathbf{K}^m_{ab} = \int_{\Omega_0}\,[\mathbf{B}_a]^T\,[\mathbb{C}^{SE}]\,[\mathbf{B}_b]\,dV_0
$$

where $[\mathbb{C}^{SE}]$ is the $6\times 6$ Voigt material tangent; $[\mathbf{B}_a]$ is the $6\times 3$ TL B-matrix block

**Material tangent (indicial form):**

$$
K^m_{ab,ij} = \int_{\Omega_0}\,F_{iI}\,\frac{\partial N_a}{\partial X_J}\,
                               C^{SE}_{IJKL}\,
                               F_{jK}\,\frac{\partial N_b}{\partial X_L}\,dV_0
$$

where Sum over $I,J,K,L$; $F_{iI}$'s come from $\mathbf{B}_a$'s $\mathbf{F}$ dependence

**Geometric (initial-stress) stiffness:**

$$
K^\sigma_{ab,ij} = \delta_{ij}\,\int_{\Omega_0}\,\frac{\partial N_a}{\partial X_K}\,
                                               \frac{\partial N_b}{\partial X_L}\,
                                               S_{KL}\,dV_0
$$

where Scalar weight per node-pair, multiplied by $\delta_{ij}\mathbf{I}_{3\times 3}$ — rotation-invariant

**Symmetry properties:**

$$
\mathbf{K}_m = \mathbf{K}_m^T \;\Leftrightarrow\; C^{SE}_{IJKL} = C^{SE}_{KLIJ},\qquad
\mathbf{K}_\sigma = \mathbf{K}_\sigma^T\;\;\text{always (since $\\mathbf{S}=\\mathbf{S}^T$)}
$$

where Total $\mathbf{K}$ symmetric for hyperelasticity / associative plasticity; non-associative plasticity breaks $\mathbf{K}_m$ symmetry

**Newton iteration:**

$$
\mathbf{K}(\mathbf{u}^\nu)\,\Delta\mathbf{u}^\nu = -\mathbf{r}(\mathbf{u}^\nu),\qquad
\mathbf{u}^{\nu+1} = \mathbf{u}^\nu + \Delta\mathbf{u}^\nu
$$

where Quadratic convergence near the solution; $\nu$ iteration index

**Algorithmically consistent vs continuum tangent:**

$$
\mathbb{C}^{SE,\mathrm{alg}} = \frac{\partial \mathbf{S}_{n+1}^{\mathrm{algorithm}}}{\partial \mathbf{E}_{n+1}}
\;\ne\;
\mathbb{C}^{SE,\mathrm{cont}} = \frac{\partial \mathbf{S}}{\partial \mathbf{E}}\,\bigg|_{\mathbf{E}_{n+1}}
\;\;\text{for finite-step return mapping}
$$

where Use $\mathbb{C}^{SE,\mathrm{alg}}$ for quadratic Newton convergence in elastoplasticity

**Updated-Lagrangian limit:**

$$
\mathbf{F} \to \mathbf{I},\,\mathbf{S}\to\boldsymbol{\sigma},\,\mathbb{C}^{SE}\to\mathbb{C}^\tau,
\;\Rightarrow\; \mathbf{K}^m \to \int_{\Omega_t}\,[\mathbf{B}^{UL}]^T[\mathbb{C}^\tau][\mathbf{B}^{UL}]\,dv,\;
             \mathbf{K}^\sigma \to \int_{\Omega_t}\,\nabla N_a\nabla N_b\,\boldsymbol{\sigma}\,dv
$$

where Recovers the UL form when current configuration is taken as the reference

**Notation:**

- $\mathbf{r}(\mathbf{u})$ — Residual, $\mathbf{r}=\mathbf{f}^{\mathrm{int}}-\mathbf{f}^{\mathrm{ext}}$
- $\mathbf{K}$ — Tangent stiffness matrix, $\mathbf{K}=\mathbf{K}_m+\mathbf{K}_\sigma$
- $\mathbf{K}_m,\mathbf{K}_\sigma$ — Material / geometric (initial-stress) stiffness
- $\mathbb{C}^{SE}$ — PK2-Green-Lagrange material tangent, $\mathbb{C}^{SE}=\partial \mathbf{S}/\partial \mathbf{E}$
- $\mathbf{B}_a$ — TL B-matrix block for node $a$
- $\nabla_0 N_a$ — Reference shape function gradient $\partial N_a/\partial \mathbf{X}$
- $\mathbf{S}$ — Second Piola-Kirchhoff stress
- $\Delta\mathbf{u}^\nu$ — Newton increment at iteration $\nu$


## 3. Algorithmic Implementation
**Algorithm: Element Tangent Stiffness Assembly (TL)**

$$
\begin{algorithmic}
\State $\text{input} \colon \{\mathbf{u}_a\}_{a=1}^{n_n},\,\text{constitutive law providing } \mathbb{C}^{SE,\mathrm{alg}}$
\State $\mathbf{K}_e \gets \mathbf{0} \in \mathbb{R}^{3 n_n \times 3 n_n}$
\For{$\text{each Gauss point } g$}
\State $\mathbf{F}_g \gets \mathbf{I}+\sum_a \mathbf{u}_a\otimes\nabla_0 N_a(\boldsymbol{\xi}_g)$
\State $\mathbf{S}_g,\,\mathbb{C}^{SE,\mathrm{alg}}_g \gets \mathrm{ConstitutiveUpdate}(\mathbf{F}_g,\,\text{state}_n)$
\State $\text{build } [\mathbf{B}_a^g]_{6\times 3}\,\text{for each node from}\,\mathbf{F}_g,\,\nabla_0 N_a$
\For{$a,b = 1,\ldots,n_n$}
\State $\mathbf{K}^m_{e,ab} \mathrel{+}= [\mathbf{B}_a^g]^T\,[\mathbb{C}^{SE,\mathrm{alg}}_g]\,[\mathbf{B}_b^g]\,w_g\,\det J_g$
\State $K^\sigma_{e,ab,ij} \mathrel{+}= \delta_{ij}\,(\nabla_0 N_a^T\,\mathbf{S}_g\,\nabla_0 N_b)\,w_g\,\det J_g$
\EndFor
\EndFor
\State $\mathbf{K}_e \gets \mathbf{K}^m_e + \mathbf{K}^\sigma_e$
\State $\text{scatter } \mathbf{K}_e \text{ into the global stiffness}$
\Return $\mathbf{K}_e$
\end{algorithmic}
$$

**Taichi Mapping:**
Single fused element kernel. The triple product $\mathbf{B}^T\mathbb{C}^{SE}\mathbf{B}$ dominates the cost: $6\times 3 \cdot 6\times 6 \cdot 6\times 3 = 6\times 3$ per pair, repeated $n_n^2$ times per Gauss point. For hex8 ($n_n=8$, 8 Gauss points) the per-element cost is $\sim 9000$ FMAs. The geometric $\mathbf{K}_\sigma$ block is much cheaper ($\sim n_n^2$ scalar contractions per Gauss point). Use `ti.atomic_add` for global scatter or pre-color elements for race-free parallel assembly.


**Algorithm: Newton-Raphson Outer Iteration**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{u}^0,\,\text{tol}\,\tau,\,\text{max iter}\,K$
\For{$\nu = 0,\ldots,K-1$}
\State $\mathbf{r}^\nu \gets \mathbf{f}^{\mathrm{int}}(\mathbf{u}^\nu) - \mathbf{f}^{\mathrm{ext}}$
\If{$\|\mathbf{r}^\nu\|/\|\mathbf{f}^{\mathrm{ext}}\| < \tau$}
\State $\textbf{break}$
\EndIf
\State $\mathbf{K}^\nu \gets \mathbf{K}(\mathbf{u}^\nu) \;\text{(modified Newton: skip update some iterations)}$
\State $\Delta \mathbf{u}^\nu \gets -(\mathbf{K}^\nu)^{-1}\,\mathbf{r}^\nu$
\State $\mathbf{u}^{\nu+1} \gets \mathbf{u}^\nu + \Delta\mathbf{u}^\nu$
\EndFor
\Return $\mathbf{u}^{\nu+1},\,\nu\,\text{(iteration count)}$
\end{algorithmic}
$$

**Taichi Mapping:**
Combine the residual / tangent assembly into a single sweep when possible — every inner Gauss-point evaluation gives both. For modified Newton (Jacobian held fixed for several iterations) skip the tangent reassembly. For load-stepping difficult problems use line search ($\mathbf{u}^{\nu+1}=\mathbf{u}^\nu+\alpha\Delta\mathbf{u}^\nu$ with $\alpha$ chosen by Armijo or bisection) before declaring divergence. Track residual norm history for adaptive load stepping.


**Algorithm: Symmetry Check on Tangent**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{K}_e\,\text{element tangent}$
\State $r \gets \|\mathbf{K}_e - \mathbf{K}_e^T\|_F/\|\mathbf{K}_e\|_F$
\If{$r > \tau_{\mathrm{sym}}\,(\sim 10^{-10})$}
\State $\text{warning: tangent is non-symmetric beyond round-off}$
\EndIf
\Return $r,\,\mathbf{K}_e$
\end{algorithmic}
$$

**Taichi Mapping:**
Diagnostic to run on at least one element during development. Genuine non-symmetry comes from non-associative plasticity, viscoplastic Perzyna laws with rate-dependent flow, or contact friction; round-off non-symmetry is $\mathcal{O}(10^{-12})$. If sources of non-symmetry are intentional, switch to a non-symmetric solver (GMRES, Bi-CGSTAB) instead of CG / LDLT.



## 4. Known Pitfalls
**Forgetting geometric stiffness:** Dropping $\mathbf{K}_\sigma$ from the tangent while keeping $\mathbf{K}_m$ produces an "initial-stiffness" approximation that is widely used in textbook problems but degrades quadratic to linear convergence at finite strain and misses geometric instabilities (Euler buckling, snap-through). Newton iteration may still converge for small steps but at a much higher iteration count and with poor robustness.


**Wrong index pairing in $\mathbf{K}_\sigma$:** The geometric stiffness has the EXPLICIT form $K^\sigma_{ab,ij}=\delta_{ij}\int(\partial N_a/\partial X_K)(\partial N_b/\partial X_L) S_{KL}\,dV_0$ — the $\delta_{ij}$ identity in spatial indices is what makes $\mathbf{K}_\sigma$ rotation-invariant. Constructing $\mathbf{K}_\sigma$ as a generic $3\times 3$ matrix per node-pair (as in the material part) destroys rotation invariance and yields a stiffness that depends on the global frame.


**Asymmetric stiffness from inconsistent material vs geometric contributions:** $\mathbf{K}_\sigma$ is always symmetric (thanks to $\mathbf{S}=\mathbf{S}^T$); $\mathbf{K}_m$ is symmetric iff $\mathbb{C}^{SE}$ has major symmetry. Combining a non-symmetric $\mathbf{K}_m$ from non-associative plasticity with a symmetric $\mathbf{K}_\sigma$ produces a non-symmetric total stiffness — switch to GMRES / BiCGSTAB; do NOT symmetrise by averaging which silently breaks consistency.


**Factor of 2 in $\delta\mathbf{E}$ first variation:** The B-matrix-to-strain mapping $\delta\mathbf{E}=\sum_a\mathbf{B}_a\delta\mathbf{u}_a$ uses kinematic Voigt (factor 2 on shears). The material tangent $\mathbb{C}^{SE}$ in $6\times 6$ Voigt form must use the kinetic rule (no factor 2). Applying both kinematic or both kinetic rules introduces factor-of-4 errors in the shear stiffness that survive uniaxial verification.


**Continuum vs algorithmic consistent tangent:** For path-dependent constitutive laws (return mapping in plasticity), $\mathbb{C}^{SE,\mathrm{cont}}=\partial\mathbf{S}/\partial\mathbf{E}$ is NOT the same as the algorithmically consistent tangent $\mathbb{C}^{SE,\mathrm{alg}}=\partial\mathbf{S}_{n+1}^{\mathrm{numerical}}/\partial\mathbf{E}_{n+1}$ — the difference is the implicit dependence through the Newton iteration on $\Delta\gamma$. Using the continuum tangent in finite-step elastoplasticity degrades Newton from quadratic to linear; use the algorithmic tangent (`plasticity-consistent-tangent`).


**Mass matrix in the wrong configuration:** The TL inertial term uses the REFERENCE mass matrix $\mathbf{M}_{ab}=\int_{\Omega_0}\rho_0\,N_a N_b\,dV_0\,\mathbf{I}_{3\times 3}$ — constant in time. Some codes recompute $\mathbf{M}$ each step using current $\rho$, $dv$, which is unnecessary and wrong (the reference form is exact). Wasted CPU and corrupted dynamics if $\rho_0\to\rho$ substitution is done inconsistently.


**Boundary conditions imposed on the wrong side:** Dirichlet BCs in TL are imposed on the reference configuration: $\mathbf{u}=\bar{\mathbf{u}}$ on $\partial\Omega_0^u$. Imposing them on the current configuration (a habit from UL) introduces a moving-boundary subproblem and corrupts the residual structure. Validate BC application by zero-displacement test on a moving / rotating body — internal stress should remain zero.


## 5. References
- Belytschko, Liu, Moran & Elkhodary (2014) — Nonlinear Finite Elements for Continua and Structures, 2nd ed., Ch. 6 (consistent linearisation, $\mathbf{K}_m+\mathbf{K}_\sigma$, Newton-Raphson, algorithmically consistent tangent)
- Bathe (1975) — Finite element formulations for large deformation dynamic analysis (incremental linearised tangent stiffness)
- de Borst, Crisfield, Remmers & Verhoosel (2012) — Nonlinear Finite Element Analysis of Solids and Structures, 2nd ed. (geometric stiffness, computational flow chart for nonlinear FEM)

