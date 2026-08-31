---
id: kinematics-multiplicative-decomp
title: Multiplicative Decomposition $\mathbf{F}=\mathbf{F}^e\mathbf{F}^p$
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- plasticity
- multiplicative-split
- mandel-stress
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: kinematics-motion-deformation-gradient
  type: requires
  weight: 1.0
  note: Multiplicative split decomposes the total $\mathbf{F}$
- to: kinematics-velocity-gradient
  type: requires
  weight: 1.0
  note: Spatial $\mathbf{L}=\mathbf{L}^e + \mathbf{F}^e\mathbf{L}^p(\mathbf{F}^e)^{-1}$ ties the kinematic split to rates
- to: tensor-isotropic-functions
  type: requires
  weight: 0.9
  note: Exponential map for the plastic update $\mathbf{F}^p_{n+1}=\exp(\Delta\gamma\,\mathbf{N})\mathbf{F}^p_n$
- to: plasticity-general-return-mapping
  type: feeds-into
  weight: 0.9
  note: Implicit return mapping in the multiplicative split uses Mandel-conjugate flow rules
- to: kinematics-objective-rates
  type: refines
  weight: 0.7
  note: Objective rates in additive-split frameworks become structurally consistent in the multiplicative split
context_size: large
reading_priority: full
load_with:
- kinematics-motion-deformation-gradient
- kinematics-velocity-gradient
- plasticity-general-return-mapping
content_ref: null
akms_schema: v2
---

# Multiplicative Decomposition $\mathbf{F}=\mathbf{F}^e\mathbf{F}^p$

## Summary
The Lee-Kroner multiplicative split $\mathbf{F}=\mathbf{F}^e\,\mathbf{F}^p$ introduces a local intermediate (relaxed) configuration: $\mathbf{F}^p$ maps reference $\to$ intermediate (purely plastic), $\mathbf{F}^e$ maps intermediate $\to$ current (purely thermoelastic). The split is non-unique up to any invertible $\mathbf{H}$ in $\mathbf{F}=(\mathbf{F}^e\mathbf{H})(\mathbf{H}^{-1}\mathbf{F}^p)$; the isoclinic assumption fixes $\mathbf{F}^p$ by requiring material directors (e.g., crystal lattice vectors) to keep their reference orientation. The plastic velocity gradient $\mathbf{L}^p=\dot{\mathbf{F}}^p(\mathbf{F}^p)^{-1}=\mathbf{D}^p+\mathbf{W}^p$ lives in the intermediate configuration; its work-conjugate stress is the (generally non-symmetric) Mandel stress $\mathbf{M}=\mathbf{C}^e\,\mathbf{S}^e$. The spatial velocity gradient satisfies $\mathbf{L}=\mathbf{L}^e+\mathbf{F}^e\mathbf{L}^p(\mathbf{F}^e)^{-1}$ — NOT the additive $\mathbf{L}=\mathbf{L}^e+\mathbf{L}^p$. Plastic incompressibility $\det\mathbf{F}^p=1$ holds for J2 metals but drifts under naive integration; exponential-map updates $\mathbf{F}^p_{n+1}=\exp(\Delta\gamma\mathbf{N})\mathbf{F}^p_n$ preserve it exactly.


## 1. Core Concept
The multiplicative split is the structural foundation of finite-strain elastoplasticity. By inserting a hypothetical intermediate configuration — obtained by virtually unloading the elastic stretch from the current state — the plastic deformation $\mathbf{F}^p$ becomes a stand-alone kinematic variable that flow rules can act on directly, mirroring the additive small-strain decomposition $\boldsymbol{\varepsilon}=\boldsymbol{\varepsilon}^e+\boldsymbol{\varepsilon}^p$ in geometry rather than algebra. The catch is that the intermediate configuration is not unique: any orthogonal rotation between $\mathbf{F}^e$ and $\mathbf{F}^p$ leaves $\mathbf{F}$ unchanged. The isoclinic convention pins this rotation by fixing the orientation of material directors (lattice vectors, fiber bundles, anisotropy axes); without it, plastic spin $\mathbf{W}^p$ has no operational meaning. The natural conjugate stress in the intermediate configuration is the Mandel stress $\mathbf{M}=\mathbf{C}^e\mathbf{S}^e$, generally non-symmetric, which couples to $\mathbf{L}^p$ through internal-power conjugacy. Spatial-rate identities, plastic incompressibility, and the structure of return-mapping algorithms all hinge on respecting the multiplicative — not additive — kinematics.


## 2. Mathematical Formulation
Throughout, $\mathbf{F}^e$ acts on the intermediate configuration $\bar\Omega$, $\mathbf{F}^p$ on the reference configuration $\Omega_0$. Quantities decorated with bars (e.g., $\bar{\mathbf{N}}$, $\bar{\mathbf{C}}^e$) live on $\bar\Omega$. Internal variables: hardening $q$, plastic strain magnitude $\bar\varepsilon^p=\int\sqrt{2/3\,\mathbf{D}^p\colon\mathbf{D}^p}\,dt$.


**Multiplicative split:**

$$
\mathbf{F} = \mathbf{F}^e\,\mathbf{F}^p,\qquad
\mathbf{F}^e \colon \bar\Omega \to \Omega_t,\qquad
\mathbf{F}^p \colon \Omega_0 \to \bar\Omega
$$

where Two-step factorisation through the intermediate (relaxed) configuration

**Non-uniqueness and isoclinic resolution:**

$$
\mathbf{F} = (\mathbf{F}^e\,\mathbf{H})(\mathbf{H}^{-1}\,\mathbf{F}^p),\qquad
\forall\,\mathbf{H}\in GL^+(3)
$$

where Resolved by isoclinic assumption: directors $\mathbf{a}_0$ keep reference orientation in $\bar\Omega$, fixing $\mathbf{H}$

**Plastic velocity gradient:**

$$
\mathbf{L}^p = \dot{\mathbf{F}}^p\,(\mathbf{F}^p)^{-1} = \mathbf{D}^p + \mathbf{W}^p,\qquad
\mathbf{D}^p = \tfrac{1}{2}(\mathbf{L}^p+\mathbf{L}^{p\,T}),\;
\mathbf{W}^p = \tfrac{1}{2}(\mathbf{L}^p-\mathbf{L}^{p\,T})
$$

where Lives on the intermediate configuration

**Spatial velocity gradient (correct decomposition):**

$$
\mathbf{L} = \mathbf{L}^e + \mathbf{F}^e\,\mathbf{L}^p\,(\mathbf{F}^e)^{-1},\qquad
\mathbf{L} \ne \mathbf{L}^e + \mathbf{L}^p
$$

where $\mathbf{L}^p$ is pushed forward by $\mathbf{F}^e$ from $\bar\Omega$ to $\Omega_t$ before adding

**Elastic right Cauchy-Green and Mandel stress:**

$$
\mathbf{C}^e = (\mathbf{F}^e)^T\,\mathbf{F}^e,\qquad
\mathbf{S}^e = 2\frac{\partial \psi^e(\mathbf{C}^e)}{\partial \mathbf{C}^e},\qquad
\mathbf{M} = \mathbf{C}^e\,\mathbf{S}^e
$$

where Mandel stress $\mathbf{M}$ is generally NON-symmetric; conjugate to $\mathbf{L}^p$

**Internal-power conjugacy in $\bar\Omega$:**

$$
P^p_{\mathrm{int}} = \mathbf{M}\colon\mathbf{L}^p
                   = \mathbf{S}^e\colon (\mathbf{C}^e\mathbf{L}^p)^{\mathrm{sym}}
$$

where Plastic dissipation written in terms of Mandel stress acting on the plastic velocity gradient

**Lagrangian flow rule (associative J2):**

$$
\mathbf{L}^p = \dot\gamma\,\mathbf{N},\qquad
\mathbf{N} = \frac{\partial f(\mathbf{M},q)}{\partial \mathbf{M}},\qquad
\dot\gamma \ge 0,\;f \le 0,\;\dot\gamma\,f = 0
$$

where Karush-Kuhn-Tucker conditions; $\mathbf{N}$ is the (deviatoric) flow direction in the intermediate configuration

**Plastic incompressibility (J2 metals):**

$$
\det\mathbf{F}^p = 1,\qquad
\mathrm{tr}\,\mathbf{L}^p = \mathrm{tr}\,\mathbf{D}^p = 0
$$

where Holds for $J_2$ flow theory and metals; not for porous / damage models (GTN, Gurson)

**Exponential-map plastic update (structure-preserving):**

$$
\mathbf{F}^p_{n+1} = \exp(\Delta\gamma\,\mathbf{N})\,\mathbf{F}^p_n,\qquad
\det\exp(\Delta\gamma\,\mathbf{N}) = \exp(\Delta\gamma\,\mathrm{tr}\,\mathbf{N}) = 1\;(\text{deviatoric }\mathbf{N})
$$

where Preserves $\det\mathbf{F}^p=1$ exactly when $\mathrm{tr}\,\mathbf{N}=0$

**Trial elastic split:**

$$
\mathbf{F}^{e,\mathrm{trial}}_{n+1} = \mathbf{F}_{n+1}\,(\mathbf{F}^p_n)^{-1},\qquad
\mathbf{F}^p_{n+1} = \exp(\Delta\gamma\,\mathbf{N})\,\mathbf{F}^p_n,\qquad
\mathbf{F}^e_{n+1} = \mathbf{F}_{n+1}\,(\mathbf{F}^p_{n+1})^{-1}
$$

where Predictor / corrector structure of the implicit return mapping

**Notation:**

- $\mathbf{F}^e,\mathbf{F}^p$ — Elastic and plastic parts of $\mathbf{F}=\mathbf{F}^e\mathbf{F}^p$
- $\bar\Omega$ — Intermediate (relaxed / isoclinic) configuration
- $\mathbf{L}^p,\mathbf{D}^p,\mathbf{W}^p$ — Plastic velocity gradient and its symmetric / skew parts
- $\mathbf{C}^e$ — Elastic right Cauchy-Green, $\mathbf{C}^e=(\mathbf{F}^e)^T\mathbf{F}^e$
- $\mathbf{S}^e$ — Elastic 2nd Piola-Kirchhoff stress on $\bar\Omega$
- $\mathbf{M}$ — Mandel stress, $\mathbf{M}=\mathbf{C}^e\mathbf{S}^e$, generally non-symmetric
- $\mathbf{N}$ — Flow direction $\partial f/\partial\mathbf{M}$
- $\dot\gamma,\Delta\gamma$ — Plastic multiplier rate / increment
- $f(\mathbf{M},q)$ — Yield function on Mandel-stress space
- $q$ — Internal hardening variables


## 3. Algorithmic Implementation
**Algorithm: Multiplicative-Split Implicit Return Mapping (Step n -> n+1)**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{F}_{n+1},\,\mathbf{F}^p_n,\,q_n,\,\text{material law}$
\State $\mathbf{F}^{e,\mathrm{trial}} \gets \mathbf{F}_{n+1}\,(\mathbf{F}^p_n)^{-1}$
\State $\mathbf{C}^{e,\mathrm{trial}} \gets (\mathbf{F}^{e,\mathrm{trial}})^T\,\mathbf{F}^{e,\mathrm{trial}}$
\State $\mathbf{S}^{e,\mathrm{trial}} \gets 2\,\partial \psi^e(\mathbf{C}^{e,\mathrm{trial}})/\partial \mathbf{C}^{e,\mathrm{trial}}$
\State $\mathbf{M}^{\mathrm{trial}} \gets \mathbf{C}^{e,\mathrm{trial}}\,\mathbf{S}^{e,\mathrm{trial}}$
\If{$f(\mathbf{M}^{\mathrm{trial}},q_n) \le 0$}
\State $\Delta\gamma \gets 0,\,\mathbf{F}^p_{n+1}\gets\mathbf{F}^p_n,\,q_{n+1}\gets q_n$
\Else
\State $\text{solve for } \Delta\gamma \;\text{such that}\; f(\mathbf{M}_{n+1}(\Delta\gamma),\,q_{n+1}(\Delta\gamma)) = 0 \;\text{(local Newton)}$
\State $\mathbf{N} \gets \partial f/\partial \mathbf{M}\,\big|_{\mathbf{M}_{n+1}}$
\State $\mathbf{F}^p_{n+1} \gets \exp(\Delta\gamma\,\mathbf{N})\,\mathbf{F}^p_n$
\State $\mathbf{F}^e_{n+1} \gets \mathbf{F}_{n+1}\,(\mathbf{F}^p_{n+1})^{-1}$
\State $q_{n+1} \gets q_n + \Delta\gamma\,\hat q(\mathbf{M},q)$
\EndIf
\State $\mathbf{S}^e_{n+1} \gets 2\partial \psi^e/\partial \mathbf{C}^e\,\big|_{\mathbf{C}^e_{n+1}},\,\mathbf{S}_{n+1} \gets (\mathbf{F}^p_{n+1})^{-1}\mathbf{S}^e_{n+1}(\mathbf{F}^p_{n+1})^{-T}$
\Return $\mathbf{S}_{n+1},\,\mathbf{F}^p_{n+1},\,q_{n+1},\,\mathbb{C}_{ep}$
\end{algorithmic}
$$

**Taichi Mapping:**
Wrap the inner Newton iteration as a `@ti.func` that accepts the trial state and returns $\Delta\gamma$ and the converged $\mathbf{M}$. Use the closed-form 3x3 matrix exponential via spectral decomposition (`tensor-isotropic-functions`). Cache $(\mathbf{F}^p_n)^{-1}$ once at trial step, recompute $(\mathbf{F}^p_{n+1})^{-1}$ via cofactor only after convergence. The Lagrangian PK2 stress $\mathbf{S}_{n+1}$ is obtained from $\mathbf{S}^e_{n+1}$ via the inverse plastic pull-back; it is what enters the global FEM residual.


**Algorithm: Verify Plastic Incompressibility After Update**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{F}^p_{n+1},\,\text{tol}\;\tau$
\State $d \gets \det\mathbf{F}^p_{n+1}$
\If{$|d - 1| > \tau$}
\State $\mathbf{F}^p_{n+1} \gets d^{-1/3}\,\mathbf{F}^p_{n+1} \;\text{(volumetric correction)}$
\EndIf
\Return $\mathbf{F}^p_{n+1}$
\end{algorithmic}
$$

**Taichi Mapping:**
Run as a sanity check after every plastic update for J2 / metal plasticity. Use $\tau=10^{-10}$ in double precision. The exponential-map update keeps $\det\mathbf{F}^p=1$ exactly in IEEE arithmetic IF $\mathrm{tr}\,\mathbf{N}=0$; the rare correction handles cases where the flow direction is not perfectly deviatoric (e.g., GTN with porosity $f\ne 0$). For pressure-sensitive plasticity (Drucker-Prager) skip this check entirely.



## 4. Known Pitfalls
**Non-unique intermediate configuration:** $\mathbf{F}=\mathbf{F}^e\mathbf{F}^p$ is invariant under $(\mathbf{F}^e,\mathbf{F}^p)\to(\mathbf{F}^e\mathbf{H},\mathbf{H}^{-1}\mathbf{F}^p)$ for any $\mathbf{H}\in GL^+(3)$. Without an isoclinic / director-orientation convention the rotation between $\mathbf{F}^e$ and $\mathbf{F}^p$ is undetermined, and plastic spin $\mathbf{W}^p$ has no operational meaning. Either fix the intermediate configuration via material directors (lattice vectors in crystal plasticity, fiber tangents in composites) or specify a plastic-spin constitutive equation explicitly.


**Mixing additive and multiplicative splits:** $\mathbf{L}=\mathbf{L}^e+\mathbf{L}^p$ is WRONG in the multiplicative framework. The correct identity is $\mathbf{L}=\mathbf{L}^e+\mathbf{F}^e\mathbf{L}^p(\mathbf{F}^e)^{-1}$ — the plastic velocity gradient is pushed forward to the spatial frame by $\mathbf{F}^e$ before adding. The naive additive form is the most common bug in finite-strain plasticity codes; it surfaces under any non-trivial elastic stretch.


**Drift of plastic incompressibility under explicit integration:** Direct Euler updates $\mathbf{F}^p_{n+1}=\mathbf{F}^p_n+\Delta t\,\mathbf{L}^p\mathbf{F}^p_n$ do NOT preserve $\det\mathbf{F}^p=1$ even when $\mathrm{tr}\,\mathbf{D}^p=0$; the determinant drifts as $\mathcal{O}(\Delta t^2)$ per step and accumulates over thousands of steps into visible volumetric inflation / deflation. Use the exponential map $\mathbf{F}^p_{n+1}=\exp(\Delta\gamma\mathbf{N})\mathbf{F}^p_n$ which preserves the determinant exactly when $\mathrm{tr}\,\mathbf{N}=0$.


**Confusing Mandel stress with PK2 / Cauchy:** The flow rule in the multiplicative split is $\mathbf{L}^p=\dot\gamma\,\partial f/\partial\mathbf{M}$, NOT $\partial f/\partial\mathbf{S}$ or $\partial f/\partial\boldsymbol{\sigma}$. The Mandel stress $\mathbf{M}=\mathbf{C}^e\mathbf{S}^e$ is generally non-symmetric (unlike $\mathbf{S}$ and $\boldsymbol{\sigma}$), and substituting one for another breaks thermodynamic consistency of the plastic dissipation $\mathbf{M}\colon\mathbf{L}^p\ge 0$. For isotropic elasticity $\mathbf{M}$ becomes symmetric and the distinction collapses; for anisotropic elasticity it does NOT.


**Treating $\mathbf{F}^p$ as symmetric:** $\mathbf{F}^p$ is generally NOT symmetric — under simple shear with rotation $\mathbf{F}^p$ has both stretch and rotation components. Storing only the symmetric part (a common shortcut for "stretch only") drops the plastic spin and corrupts the intermediate configuration. Store $\mathbf{F}^p$ as a full $3\times 3$ matrix at every Gauss point.


**Polar decomposition applied to $\mathbf{F}$ instead of $\mathbf{F}^e$:** Corotational stress integration in finite-strain plasticity uses the polar decomposition of $\mathbf{F}^e$ (the elastic part), NOT of $\mathbf{F}$. Decomposing $\mathbf{F}=\mathbf{R}\mathbf{U}$ directly mixes elastic stretch with plastic flow direction and corrupts the algorithmic tangent. Always extract $\mathbf{F}^e=\mathbf{F}(\mathbf{F}^p)^{-1}$ first, then decompose.


**Sign / order errors in $\mathbf{S}=(\mathbf{F}^p)^{-1}\mathbf{S}^e(\mathbf{F}^p)^{-T}$:** The pull-back of $\mathbf{S}^e$ from $\bar\Omega$ to $\Omega_0$ is $\mathbf{S}=(\mathbf{F}^p)^{-1}\mathbf{S}^e(\mathbf{F}^p)^{-T}$ (kinetic, contravariant-contravariant tensor). Swapping $\mathbf{F}^p$ for $(\mathbf{F}^p)^{-1}$ or transposing the wrong leg silently corrupts the global PK2 stress that enters the FEM residual; the bug shows up as wrong reaction forces under finite plastic deformation.


**Forgetting the geometric correction in the consistent tangent:** The algorithmic tangent for the multiplicative split has multiple contributions: $\partial\mathbf{S}/\partial\mathbf{C}$ in the elastic block, $\partial\mathbf{F}^p/\partial\mathbf{F}$ from the plastic update, and the geometric correction from $\partial\mathbf{F}^e/\partial\mathbf{F}=\mathbf{I}\bar\otimes(\mathbf{F}^p)^{-T}-\mathbf{F}^e\partial\mathbf{F}^p/\partial\mathbf{F}\cdot(\mathbf{F}^p)^{-1}$. Dropping any term degrades Newton convergence from quadratic to linear and stalls solvers near limit points.


## 5. References
- Lee, E. H. (1969) — Elastic-plastic deformation at finite strains (origin of $\mathbf{F}=\mathbf{F}^e\mathbf{F}^p$ split)
- Mandel, J. (1972) — Plasticite classique et viscoplasticite (intermediate configuration, isoclinic axes, Mandel stress)
- Miehe, Apel, Lambrecht (2002) — Anisotropic additive plasticity in the logarithmic strain space (modular wrapper that bypasses explicit multiplicative split via log-strain)
- Holzapfel (2000) — Nonlinear Solid Mechanics (multiplicative split, plastic velocity gradient, exponential-map integration)

