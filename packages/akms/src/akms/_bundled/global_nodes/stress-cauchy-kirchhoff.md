---
id: stress-cauchy-kirchhoff
title: Cauchy & Kirchhoff Stress
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- continuum-mechanics
- stress
- cauchy-stress
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: kinematics-motion-deformation-gradient
  type: requires
  weight: 0.9
  note: Kirchhoff $\boldsymbol{\tau}=J\boldsymbol{\sigma}$ uses the Jacobian from $\mathbf{F}$
- to: kinematics-velocity-gradient
  type: feeds-into
  weight: 1.0
  note: Stress-power conjugacy $\boldsymbol{\sigma}\colon\mathbf{D}=\boldsymbol{\tau}\colon\mathbf{D}/J$
- to: stress-piola-kirchhoff
  type: feeds-into
  weight: 1.0
  note: PK1 / PK2 stresses are pull-backs of Cauchy / Kirchhoff to the reference configuration
- to: stress-push-forward-pull-back
  type: feeds-into
  weight: 1.0
  note: $\boldsymbol{\tau}$ is the natural push-forward target of $\mathbf{S}$
context_size: small
reading_priority: full
load_with:
- stress-piola-kirchhoff
- stress-push-forward-pull-back
content_ref: null
akms_schema: v2
---

# Cauchy & Kirchhoff Stress

## Summary
The Cauchy (true) stress $\boldsymbol{\sigma}$ measures force per unit current area: $\mathbf{t}=\boldsymbol{\sigma}\cdot\mathbf{n}$ on a deformed surface. Symmetry $\boldsymbol{\sigma}=\boldsymbol{\sigma}^T$ follows from balance of angular momentum, and the spatial form of equilibrium reads $\nabla\cdot\boldsymbol{\sigma}+\rho\mathbf{b}=\rho\dot{\mathbf{v}}$. The Kirchhoff stress $\boldsymbol{\tau}=J\boldsymbol{\sigma}$ rescales by the Jacobian $J=\det\mathbf{F}$ and is also symmetric. Internal-power densities are equivalent: $\boldsymbol{\sigma}\colon\mathbf{D}\,dv = \boldsymbol{\tau}\colon\mathbf{D}\,(dv/J) = \boldsymbol{\sigma}\colon\mathbf{D}\,J\,dV_0$. Kirchhoff is preferred in finite-strain hyperelasticity because the convected / Truesdell rate $\mathcal{L}_v\boldsymbol{\tau}=\mathbf{F}\dot{\mathbf{S}}\mathbf{F}^T$ is the natural objective stress rate; Cauchy is the form the user reports because it has direct physical-stress units. Conversion is $\boldsymbol{\sigma}=\boldsymbol{\tau}/J$ with care taken that $J>0$.


## 1. Core Concept
Cauchy stress is the operational stress in computational mechanics: every traction boundary condition, every "stress" plotted on a deformed mesh, every yield criterion is written in terms of $\boldsymbol{\sigma}$. It is symmetric (angular momentum), it appears in the spatial equation of motion $\nabla\cdot\boldsymbol{\sigma}+\rho\mathbf{b}=\rho\dot{\mathbf{v}}$, and it is the stress users report. Kirchhoff stress $\boldsymbol{\tau}=J\boldsymbol{\sigma}$ is the same physical stress measured per unit reference volume rather than per unit current volume; the rescaling makes it the natural Eulerian companion to PK2 ($\boldsymbol{\tau}=\mathbf{F}\mathbf{S}\mathbf{F}^T$) and gives it a clean pairing with the rate-of-deformation under the Lie derivative ($\mathcal{L}_v\boldsymbol{\tau}=\mathbf{F}\dot{\mathbf{S}}\mathbf{F}^T$ is the convected/Truesdell rate). Because $\boldsymbol{\tau}$ uses reference volumes, mass / momentum balance integrated over $\Omega_0$ in TL-FEM uses $\boldsymbol{\tau}$ implicitly via $\mathbf{S}=\mathbf{F}^{-1}\boldsymbol{\tau}\mathbf{F}^{-T}$. The two stresses are interchangeable through $J$ but are NOT the same tensor; conflating them by a factor $J$ is one of the most common bugs in finite-strain code.


## 2. Mathematical Formulation
Throughout, $\Omega_t$ is the current configuration and $\Omega_0$ the reference. $\rho$ is current mass density, $\rho_0$ reference; $\mathbf{b}$ body force per unit mass; $\dot{\mathbf{v}}$ material acceleration; $\mathbf{n}$ unit outward normal on a current surface. Latin lower-case indices are spatial.


**Cauchy stress and the traction:**

$$
\mathbf{t} = \boldsymbol{\sigma}\cdot\mathbf{n},\qquad
\sigma_{ij} = \sigma_{ji} \quad(\text{angular momentum})
$$

where $\mathbf{t}$ is force per unit current area on a surface with outward normal $\mathbf{n}$

**Kirchhoff stress:**

$$
\boldsymbol{\tau} = J\,\boldsymbol{\sigma},\qquad
\tau_{ij} = J\,\sigma_{ij},\qquad
J = \det\mathbf{F} > 0
$$

where $\boldsymbol{\tau}$ is symmetric for the same reason as $\boldsymbol{\sigma}$

**Spatial equilibrium / equation of motion:**

$$
\nabla\cdot\boldsymbol{\sigma} + \rho\,\mathbf{b} = \rho\,\dot{\mathbf{v}},
\qquad
\frac{\partial \sigma_{ij}}{\partial x_j} + \rho\,b_i = \rho\,\dot v_i
$$

where Statics recovers $\nabla\cdot\boldsymbol{\sigma}+\rho\mathbf{b}=0$

**Traction transformation (Cauchy <-> reference area):**

$$
\mathbf{t}\,da = \boldsymbol{\sigma}\cdot\mathbf{n}\,da
      = J\,\boldsymbol{\sigma}\cdot\mathbf{F}^{-T}\cdot\mathbf{n}_0\,dA_0
      = \mathbf{P}\cdot\mathbf{n}_0\,dA_0
$$

where $\mathbf{P}=J\boldsymbol{\sigma}\mathbf{F}^{-T}$ is the nominal stress (PK1)

**Mass conservation:**

$$
\rho_0 = J\,\rho,\qquad
\int_{\Omega_0}\rho_0\,dV_0 = \int_{\Omega_t}\rho\,dv
$$

where Trivial consequence of $dv=J\,dV_0$

**Stress-power equivalence:**

$$
\boldsymbol{\sigma}\colon\mathbf{D}\,dv = \boldsymbol{\tau}\colon\mathbf{D}\,\frac{dv}{J} = \boldsymbol{\tau}\colon\mathbf{D}\,dV_0
$$

where $\boldsymbol{\sigma}\colon\mathbf{D}$ is power per current volume; $\boldsymbol{\tau}\colon\mathbf{D}$ is power per reference volume

**Material time derivative of $\boldsymbol{\tau}$:**

$$
\dot{\boldsymbol{\tau}} = J\,\dot{\boldsymbol{\sigma}} + \boldsymbol{\sigma}\,\mathrm{tr}\,\mathbf{D}\,J
                    = J\,(\dot{\boldsymbol{\sigma}} + \boldsymbol{\sigma}\,\mathrm{tr}\,\mathbf{L}),
\qquad \dot J = J\,\mathrm{tr}\,\mathbf{L} = J\,\mathrm{tr}\,\mathbf{D}
$$

where Used when relating spatial constitutive rates expressed in $\boldsymbol{\sigma}$ vs $\boldsymbol{\tau}$

**Lie / convected rate of $\boldsymbol{\tau}$:**

$$
\mathcal{L}_v\,\boldsymbol{\tau}
= \dot{\boldsymbol{\tau}} - \mathbf{L}\,\boldsymbol{\tau} - \boldsymbol{\tau}\,\mathbf{L}^T
= \mathbf{F}\,\dot{\mathbf{S}}\,\mathbf{F}^T
$$

where Naturally objective; the canonical stress rate in finite-strain hyperelasticity (`tensor-operations`)

**Decompositions: hydrostatic vs deviatoric:**

$$
p = -\tfrac{1}{3}\,\mathrm{tr}\,\boldsymbol{\sigma},\qquad
\mathbf{s} = \boldsymbol{\sigma} + p\,\mathbf{I},\qquad
\boldsymbol{\sigma} = -p\,\mathbf{I} + \mathbf{s}
$$

where Pressure / deviator split used in nearly-incompressible and J2 plasticity

**Notation:**

- $\boldsymbol{\sigma}$ — Cauchy (true) stress, force per unit current area
- $\boldsymbol{\tau}$ — Kirchhoff stress, $\boldsymbol{\tau}=J\boldsymbol{\sigma}$
- $J$ — Jacobian, $J=\det\mathbf{F}>0$
- $\mathbf{t}$ — Traction vector on a current surface
- $\mathbf{n},\mathbf{n}_0$ — Current / reference outward unit normals
- $p$ — Hydrostatic pressure, $p=-\tfrac13\mathrm{tr}\,\boldsymbol{\sigma}$
- $\mathbf{s}$ — Deviatoric stress, $\mathbf{s}=\boldsymbol{\sigma}+p\mathbf{I}$
- $\mathcal{L}_v\boldsymbol{\tau}$ — Lie / convected derivative of $\boldsymbol{\tau}$


## 3. Algorithmic Implementation
**Algorithm: Convert Between Cauchy and Kirchhoff Stress**

$$
\begin{algorithmic}
\State $\text{input} \colon \boldsymbol{\sigma}\,\text{or}\,\boldsymbol{\tau},\,\mathbf{F}$
\State $J \gets \det\mathbf{F}$
\If{$J \le J_{\min}$}
\State $\text{abort: element inverted, conversion undefined}$
\EndIf
\State $\boldsymbol{\tau} \gets J\,\boldsymbol{\sigma}\;\text{or}\;\boldsymbol{\sigma} \gets \boldsymbol{\tau}/J$
\Return $\boldsymbol{\tau}\,\text{or}\,\boldsymbol{\sigma}$
\end{algorithmic}
$$

**Taichi Mapping:**
`@ti.func` per Gauss point. Pre-compute $J$ once with the deformation gradient (cofactor / determinant) and cache it so the conversion is a single multiply per stress component. Tag every stress array with `_cauchy` or `_kirchhoff` to make the convention explicit at every interface.


**Algorithm: Hydrostatic / Deviatoric Split**

$$
\begin{algorithmic}
\State $\text{input} \colon \boldsymbol{\sigma}\in\mathbb{R}^{3\times 3}_{\mathrm{sym}}$
\State $p \gets -\tfrac{1}{3}(\sigma_{11}+\sigma_{22}+\sigma_{33})$
\For{$i,j = 1,2,3$}
\State $s_{ij} \gets \sigma_{ij} + p\,\delta_{ij}$
\EndFor
\Return $p,\,\mathbf{s}$
\end{algorithmic}
$$

**Taichi Mapping:**
Inline `@ti.func`; six FMAs. Reuse for J2-plasticity yield evaluations $f=\sqrt{3J_2}-\sigma_Y$ where $J_2=\tfrac12 s_{ij}s_{ij}$ (cf. `tensor-invariants`). The split is structurally identical for $\boldsymbol{\tau}$ and $\boldsymbol{\sigma}$; pick whichever is already in registers.


**Algorithm: Equilibrium Residual on a Current-Configuration Mesh (UL-FEM)**

$$
\begin{algorithmic}
\State $\text{input} \colon \boldsymbol{\sigma}\,\text{at GPs},\,\rho,\mathbf{b},\,\text{nodal}\,\dot{\mathbf{v}}$
\State $\mathbf{f}^{\mathrm{int}}_a \gets \int_{\Omega_t} \mathbf{B}_a^T\colon\boldsymbol{\sigma}\,dv$
\State $\mathbf{f}^{\mathrm{ext}}_a \gets \int_{\Omega_t} N_a\,\rho\,\mathbf{b}\,dv + \int_{\partial\Omega_t} N_a\,\bar{\mathbf{t}}\,da$
\State $\mathbf{r}_a \gets \mathbf{f}^{\mathrm{int}}_a - \mathbf{f}^{\mathrm{ext}}_a + \mathbf{M}_{ab}\,\dot{\mathbf{v}}_b$
\Return $\mathbf{r}_a$
\end{algorithmic}
$$

**Taichi Mapping:**
Updated-Lagrangian assembly uses $\boldsymbol{\sigma}$ directly. For TL-FEM convert to PK2 first (`stress-piola-kirchhoff`). The B-matrix is the spatial gradient of shape functions. Use `ti.atomic_add` for the global force scatter; pre-compute $dv=J\,dV_0$ at each Gauss point.



## 4. Known Pitfalls
**Confusing $\boldsymbol{\sigma}$ with $\boldsymbol{\tau}$:** $\boldsymbol{\tau}=J\boldsymbol{\sigma}$ — they differ by the Jacobian. Plotting $\boldsymbol{\tau}$ where the user expects $\boldsymbol{\sigma}$ overestimates "stress" by $J$ (e.g., 50% at $J=1.5$). Tag every output stress with its convention; provide a single-point-of-conversion utility rather than ad-hoc inline rescaling.


**Forgetting $\boldsymbol{\sigma}=\boldsymbol{\sigma}^T$:** Angular momentum balance enforces $\boldsymbol{\sigma}=\boldsymbol{\sigma}^T$. Numerical algorithms (especially incremental rotation updates, Hughes-Winget) can drift off symmetry by round-off; over many steps the asymmetry builds and corrupts the equilibrium residual. Symmetrise $\boldsymbol{\sigma}\to\tfrac12(\boldsymbol{\sigma}+\boldsymbol{\sigma}^T)$ at the end of every constitutive update.


**Mixing reference and current divergence operators:** Spatial equilibrium is $\nabla\cdot\boldsymbol{\sigma}+\rho\mathbf{b}=\rho\dot{\mathbf{v}}$ on $\Omega_t$; reference equilibrium is $\nabla_0\cdot\mathbf{P}+\rho_0\mathbf{b}_0=\rho_0\dot{\mathbf{v}}$ on $\Omega_0$. Using a material gradient on $\boldsymbol{\sigma}$ or a spatial gradient on $\mathbf{P}$ produces residuals off by an integration over the wrong configuration. Decide UL or TL once, document, validate.


**Sign convention on traction / normal:** $\mathbf{t}=\boldsymbol{\sigma}\cdot\mathbf{n}$ assumes $\mathbf{n}$ is the OUTWARD unit normal. A common bug in contact / surface-load assembly is using the inward normal, flipping the sign of every applied traction. Document the convention at the boundary-condition API and validate with a uniaxial-tension benchmark.


**Element inversion makes $\boldsymbol{\tau}/J$ singular:** As $J\to 0$ the conversion $\boldsymbol{\sigma}=\boldsymbol{\tau}/J$ blows up. Detect $J<J_{\min}$ before any conversion that divides by $J$; trigger remeshing / step bisection. The Kirchhoff stress remains finite even for $J\to 0$, so storing $\boldsymbol{\tau}$ in degenerate regions is safer than storing $\boldsymbol{\sigma}$.


**Updating $\boldsymbol{\sigma}$ via material rate without objectivity correction:** $\dot{\boldsymbol{\sigma}}$ is NOT objective: under rigid-body rotation it picks up spurious $\boldsymbol{\Omega}\boldsymbol{\sigma}-\boldsymbol{\sigma}\boldsymbol{\Omega}$ terms. Constitutive rate laws must use objective rates ($\mathcal{L}_v\boldsymbol{\tau}$, Jaumann, Truesdell, Green-Naghdi — see `kinematics-objective-rates`). Using $\dot{\boldsymbol{\sigma}}=\mathbb{C}\colon\mathbf{D}$ directly produces stress oscillations under simple shear.


**Volumetric locking on nearly-incompressible Cauchy stress:** For nearly-incompressible materials ($J\to 1$) the pressure $p=-\tfrac13\mathrm{tr}\,\boldsymbol{\sigma}$ becomes the dominant stress and a poor approximation of $J$ in the constitutive law produces wild pressure oscillations (volumetric locking). Use $\bar F$ / F-bar / mixed u/p formulations and store $p$ as a separate field rather than recovering it from $\mathrm{tr}\,\boldsymbol{\sigma}$.


## 5. References
- Belytschko, Liu, Moran & Elkhodary (2014) — Nonlinear Finite Elements for Continua and Structures, 2nd ed. (Cauchy stress, Kirchhoff stress, traction transformation, equilibrium)
- Holzapfel (2000) — Nonlinear Solid Mechanics (Cauchy / Kirchhoff stress, stress power, hydrostatic / deviatoric decomposition)
- de Borst, Crisfield, Remmers & Verhoosel (2012) — Nonlinear Finite Element Analysis of Solids and Structures, 2nd ed. (current-configuration equilibrium, traction-area transformations)

