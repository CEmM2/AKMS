---
id: kinematics-velocity-gradient
title: Velocity Gradient, Stretching & Spin
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- continuum-mechanics
- velocity-gradient
- rate-of-deformation
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: kinematics-motion-deformation-gradient
  type: requires
  weight: 1.0
  note: $\mathbf{L}=\dot{\mathbf{F}}\mathbf{F}^{-1}$ uses $\mathbf{F}$ from the deformation gradient
- to: tensor-products-contractions
  type: requires
  weight: 0.7
  note: Decomposition $\mathbf{L}=\mathbf{D}+\mathbf{W}$ uses sym/skew operators
- to: kinematics-strain-tensors
  type: feeds-into
  weight: 1.0
  note: Pull-back $\dot{\mathbf{E}}=\mathbf{F}^T\mathbf{D}\mathbf{F}$ ties rate-of-deformation to Green strain rate
- to: kinematics-objective-rates
  type: feeds-into
  weight: 1.0
  note: Spin $\mathbf{W}$ and rate-of-deformation $\mathbf{D}$ enter Jaumann / Truesdell / Green-Naghdi rates
context_size: medium
reading_priority: full
load_with:
- kinematics-motion-deformation-gradient
content_ref: null
akms_schema: v2
---

# Velocity Gradient, Stretching & Spin

## Summary
The spatial velocity gradient $\mathbf{L}=\nabla\mathbf{v}=\dot{\mathbf{F}}\mathbf{F}^{-1}$ (mixed-variance, generally asymmetric) decomposes additively into the symmetric rate-of-deformation $\mathbf{D}=\tfrac12(\mathbf{L}+\mathbf{L}^T)$ and the skew spin $\mathbf{W}=\tfrac12(\mathbf{L}-\mathbf{L}^T)$. $\mathbf{D}$ measures the rate of stretching and shearing (the kinematic strain rate), $\mathbf{W}$ measures the local rate of rigid rotation. Pull-back / push-forward links $\mathbf{D}$ to the Green strain rate via $\dot{\mathbf{E}}=\mathbf{F}^T\mathbf{D}\mathbf{F}$. Power-conjugacy gives a hierarchy of equivalent internal-power expressions: $\boldsymbol{\sigma}\colon\mathbf{D}\,dv = \boldsymbol{\tau}\colon\mathbf{D}\,(dv/J) = \mathbf{S}\colon\dot{\mathbf{E}}\,dV_0 = \mathbf{P}\colon\dot{\mathbf{F}}\,dV_0$. In FEM $\mathbf{L}$ is built per Gauss point from nodal velocities and shape function spatial gradients; the asymmetry of $\mathbf{L}$ matters and must not be discarded by Voigt storage.


## 1. Core Concept
The velocity gradient $\mathbf{L}$ is the rate analogue of the deformation gradient: $\dot{\mathbf{F}}=\mathbf{L}\mathbf{F}$ shows that $\mathbf{L}$ generates the time evolution of $\mathbf{F}$. Its symmetric part $\mathbf{D}$ is the local rate of stretching of material line elements (the "strain rate" as measured in the current configuration), while its skew part $\mathbf{W}$ is the angular velocity of the principal axes — the rate at which the material rotates about itself. The decomposition $\mathbf{L}=\mathbf{D}+\mathbf{W}$ is the kinematic backbone of every rate-form constitutive law. Power conjugacy ties $\mathbf{D}$ to the Cauchy / Kirchhoff stress: $\boldsymbol{\sigma}\colon\mathbf{D}$ is the Eulerian internal-power density per current volume, and pull-back to the reference configuration recovers the Lagrangian $\mathbf{S}\colon\dot{\mathbf{E}}$. Hyperelastic, plastic, and viscous constitutive laws are written in terms of $\mathbf{D}$ (or its non-coaxial corrections via objective rates), so getting $\mathbf{D}$ and $\mathbf{W}$ right at every Gauss point is essential.


## 2. Mathematical Formulation
Throughout, $\mathbf{v}=\partial\boldsymbol{\phi}/\partial t|_{\mathbf{X}}$ is the material velocity (function of $\mathbf{X}$), $\dot{\mathbf{F}}$ is the material time derivative of the deformation gradient. Spatial gradient $\nabla=\partial/\partial\mathbf{x}$, material gradient $\nabla_0=\partial/\partial\mathbf{X}$.


**Spatial velocity gradient:**

$$
\mathbf{L} = \nabla\mathbf{v} = \frac{\partial \mathbf{v}}{\partial \mathbf{x}} = \dot{\mathbf{F}}\,\mathbf{F}^{-1},\qquad
L_{ij} = \frac{\partial v_i}{\partial x_j}
$$

where Mixed-variance two-leg tensor (one contravariant, one covariant); generally asymmetric

**Sym / skew decomposition:**

$$
\mathbf{L} = \mathbf{D} + \mathbf{W},\qquad
\mathbf{D} = \tfrac{1}{2}(\mathbf{L}+\mathbf{L}^T),\qquad
\mathbf{W} = \tfrac{1}{2}(\mathbf{L}-\mathbf{L}^T)
$$

where $\mathbf{D}=\mathbf{D}^T$ rate-of-deformation; $\mathbf{W}=-\mathbf{W}^T$ spin

**Time rate of $\mathbf{F}$:**

$$
\dot{\mathbf{F}} = \mathbf{L}\,\mathbf{F},\qquad
\dot{F}_{iJ} = L_{ik}\,F_{kJ}
$$

where $\mathbf{L}$ is the spatial generator of $\dot{\mathbf{F}}$

**Pull-back of $\mathbf{D}$ to Green strain rate:**

$$
\dot{\mathbf{E}} = \mathbf{F}^T\,\mathbf{D}\,\mathbf{F},\qquad
\mathbf{D} = \mathbf{F}^{-T}\,\dot{\mathbf{E}}\,\mathbf{F}^{-1}
$$

where Kinematic (covariant-covariant) push-forward / pull-back; verifies $\mathbf{S}\colon\dot{\mathbf{E}}=\boldsymbol{\tau}\colon\mathbf{D}$

**Internal power conjugacy:**

$$
\int_{\Omega_t}\boldsymbol{\sigma}\colon\mathbf{D}\,dv
= \int_{\Omega_t}\boldsymbol{\tau}\colon\mathbf{D}\,\frac{dv}{J}
= \int_{\Omega_0}\mathbf{S}\colon\dot{\mathbf{E}}\,dV_0
= \int_{\Omega_0}\mathbf{P}\colon\dot{\mathbf{F}}\,dV_0
$$

where Same internal power expressed in four equivalent stress / strain-rate pairings

**Spin axis vector:**

$$
\mathbf{W} = \begin{pmatrix} 0 & -\omega_3 & \omega_2 \\ \omega_3 & 0 & -\omega_1 \\ -\omega_2 & \omega_1 & 0 \end{pmatrix},
\qquad
\boldsymbol{\omega} = -\tfrac{1}{2}\,e_{ijk}\,W_{jk}\,\mathbf{e}_i
$$

where $\boldsymbol{\omega}$ is the local angular velocity vector of the material

**Vorticity:**

$$
\boldsymbol{\zeta} = \nabla\times\mathbf{v} = 2\,\boldsymbol{\omega}
$$

where Curl of velocity is twice the spin axis

**Plastic velocity gradient (multiplicative split):**

$$
\mathbf{L}^p = \dot{\mathbf{F}}^p\,(\mathbf{F}^p)^{-1},\qquad
\mathbf{L} = \mathbf{L}^e + \mathbf{F}^e\,\mathbf{L}^p\,(\mathbf{F}^e)^{-1}
$$

where Used in finite-strain plasticity; mixed variance carries through to $\mathbf{L}^p$ (`kinematics-multiplicative-decomp`)

**Notation:**

- $\mathbf{v}$ — Spatial velocity field
- $\mathbf{L}$ — Spatial velocity gradient, $\mathbf{L}=\nabla\mathbf{v}=\dot{\mathbf{F}}\mathbf{F}^{-1}$
- $\mathbf{D}$ — Rate-of-deformation, $\mathbf{D}=\tfrac12(\mathbf{L}+\mathbf{L}^T)$ (symmetric)
- $\mathbf{W}$ — Spin tensor, $\mathbf{W}=\tfrac12(\mathbf{L}-\mathbf{L}^T)$ (skew)
- $\boldsymbol{\omega}$ — Angular velocity vector dual to $\mathbf{W}$
- $\boldsymbol{\zeta}$ — Vorticity, $\boldsymbol{\zeta}=\nabla\times\mathbf{v}=2\boldsymbol{\omega}$
- $\dot{\mathbf{E}}$ — Material time derivative of Green-Lagrange strain
- $\mathbf{F}^e,\mathbf{F}^p$ — Elastic / plastic parts of the multiplicative split


## 3. Algorithmic Implementation
**Algorithm: Compute $\mathbf{L},\mathbf{D},\mathbf{W}$ at a Gauss Point**

$$
\begin{algorithmic}
\State $\text{input} \colon \{\mathbf{v}_a\}_{a=1}^{n_n},\,\{\partial N_a/\partial \mathbf{x}\}_{a=1}^{n_n} \;\text{at the GP},\,\mathbf{F}$
\State $\mathbf{L} \gets \mathbf{0} \in \mathbb{R}^{3\times 3}$
\For{$a = 1,\ldots,n_n$}
\For{$i,j = 1,2,3$}
\State $L_{ij} \mathrel{+}= v_{a,i}\,(\partial N_a/\partial x_j)$
\EndFor
\EndFor
\For{$i,j = 1,2,3$}
\State $D_{ij} \gets \tfrac{1}{2}(L_{ij} + L_{ji})$
\State $W_{ij} \gets \tfrac{1}{2}(L_{ij} - L_{ji})$
\EndFor
\Return $\mathbf{L},\mathbf{D},\mathbf{W}$
\end{algorithmic}
$$

**Taichi Mapping:**
`@ti.func` per Gauss point. The spatial shape function gradients $\partial N_a/\partial\mathbf{x}=\partial N_a/\partial\mathbf{X}\cdot\mathbf{F}^{-1}$ change every step in TL-FEM; in UL-FEM they are computed from current geometry directly. Store $\mathbf{D}$ as a full $3\times 3$ symmetric matrix or a 6-component Mandel vector — never as a Voigt vector that would lose factor-of-2 bookkeeping in shear blocks.


**Algorithm: Pull-Back $\mathbf{D}\to\dot{\mathbf{E}}$ and Verify Conjugacy**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{D},\,\mathbf{F},\,\mathbf{S},\,\boldsymbol{\sigma}$
\State $\dot{\mathbf{E}} \gets \mathbf{F}^T\,\mathbf{D}\,\mathbf{F}$
\State $P^{\mathrm{mat}}_{\mathrm{int}} \gets \mathbf{S}\colon\dot{\mathbf{E}} \;\text{(Lagrangian)}$
\State $P^{\mathrm{spt}}_{\mathrm{int}} \gets \boldsymbol{\sigma}\colon\mathbf{D} \;\text{(Eulerian)}$
\State $P^{\mathrm{spt}}_{\mathrm{int}} \cdot J = \mathbf{S}\colon\dot{\mathbf{E}} \;\text{(must hold to round-off)}$
\Return $\dot{\mathbf{E}}$
\end{algorithmic}
$$

**Taichi Mapping:**
Use as a unit test in development; the equality $\boldsymbol{\sigma}\colon\mathbf{D}\,J = \mathbf{S}\colon\dot{\mathbf{E}}$ is a rigorous check on internal-power consistency. Failures usually indicate Voigt factor-of-2 errors in shear or wrong stress / strain-rate pairing in the constitutive update.


**Algorithm: Update $\mathbf{F}$ via Exponential Map (Structure-Preserving)**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{F}_n,\,\mathbf{L}_{n+1/2},\,\Delta t$
\State $\mathbf{F}_{n+1} \gets \exp(\Delta t\,\mathbf{L}_{n+1/2})\,\mathbf{F}_n$
\Return $\mathbf{F}_{n+1}$
\end{algorithmic}
$$

**Taichi Mapping:**
Closed-form $3\times 3$ matrix exponential via spectral decomposition (`tensor-isotropic-functions`). Preserves $\det\mathbf{F}$ exactly when $\mathrm{tr}(\Delta t\,\mathbf{L})=0$ (incompressible flow) and preserves $\mathbf{F}\in GL^+(3)$ unconditionally. Substantially more stable than the direct update $\mathbf{F}_{n+1}=\mathbf{F}_n+\Delta t\,\mathbf{L}\mathbf{F}_n$ for large $\Delta t$ at a moderate cost penalty.



## 4. Known Pitfalls
**$\mathbf{L}$ is asymmetric — separate $\mathbf{D}$ and $\mathbf{W}$ consistently:** Storing $\mathbf{L}$ in a 6-component symmetric form loses the spin part and corrupts every objective stress integration that depends on $\mathbf{W}$. Always store $\mathbf{L}$ as a full $3\times 3$ matrix (9 components) or store $\mathbf{D}$ (6) and $\mathbf{W}$ (3) separately. The vector form of $\mathbf{W}$ is $\boldsymbol{\omega}=-\tfrac12 e_{ijk}W_{jk}\mathbf{e}_i$, which compresses to 3 numbers without loss.


**Time-step instability from finite-difference $\dot{\mathbf{F}}$:** Computing $\mathbf{L}=\dot{\mathbf{F}}\mathbf{F}^{-1}$ via $\dot{\mathbf{F}}\approx(\mathbf{F}_{n+1}-\mathbf{F}_n)/\Delta t$ amplifies time-step noise and produces oscillatory $\mathbf{D}$ that drives spurious plastic flow. Build $\mathbf{L}$ from the spatial velocity gradient $\nabla\mathbf{v}$ directly (using nodal velocities and shape function gradients), not from finite differences on $\mathbf{F}$.


**Treating $\dot{\mathbf{E}}$ as identical to $\mathbf{D}$:** $\mathbf{D}=\mathbf{F}^{-T}\dot{\mathbf{E}}\mathbf{F}^{-1}$ — they coincide only when $\mathbf{F}=\mathbf{I}$ (small strain) or for purely coaxial flow. Using $\mathbf{D}$ in place of $\dot{\mathbf{E}}$ in a Lagrangian constitutive update introduces a spurious push-forward that breaks the $\mathbf{S}\leftrightarrow\dot{\mathbf{E}}$ conjugacy and corrupts the consistent tangent.


**Voigt factor-of-2 confusion on shear strain rate:** In the kinematic Voigt form $\{\mathbf{D}\}=(D_{11},D_{22},D_{33},2D_{23},2D_{13},2D_{12})^T$ — shear components carry the factor 2. Forgetting it produces shear stress that is half of correct, breaks $\boldsymbol{\sigma}\colon\mathbf{D}=\{\boldsymbol{\sigma}\}^T\{\mathbf{D}\}$, and shows up only on shear-dominated benchmarks (uniaxial tests are insensitive).


**$\mathbf{W}$ not trace-free in 2D / plane-strain:** $\mathbf{W}$ is mathematically skew-symmetric and exactly trace-free, but careless plane-strain projections that zero-pad the out-of-plane components can produce $W_{33}\ne 0$ from round-off in the symmetric-skew split. Validate $|\mathrm{tr}\,\mathbf{W}|<10^{-12}\|\mathbf{L}\|$ at every Gauss point; fix the projection at construction rather than masking by truncation later.


**Mixing material and spatial gradients in $\mathbf{L}$:** $\mathbf{L}$ is a SPATIAL gradient: $\partial\mathbf{v}/\partial\mathbf{x}$. Computing it as the material gradient $\partial\mathbf{v}/\partial\mathbf{X}$ (a common slip in TL-FEM where shape function gradients are stored in reference form) gives $\dot{\mathbf{F}}$ instead, which has different mixed-variance structure and yields wrong $\mathbf{D}$ and $\mathbf{W}$. Convert via $\partial\mathbf{v}/\partial\mathbf{x}=(\partial\mathbf{v}/\partial\mathbf{X})\cdot\mathbf{F}^{-1}$.


**Multiplicative split: $\mathbf{L}\ne\mathbf{L}^e+\mathbf{L}^p$ without push-forward:** The multiplicative split $\mathbf{F}=\mathbf{F}^e\mathbf{F}^p$ does NOT translate to $\mathbf{L}=\mathbf{L}^e+\mathbf{L}^p$. The correct identity is $\mathbf{L}=\mathbf{L}^e+\mathbf{F}^e\mathbf{L}^p(\mathbf{F}^e)^{-1}$ (the plastic part is pushed forward to the current configuration). Treating it as additive in $\mathbf{L}$ — a common error in elastoplastic codes — corrupts the plastic flow direction and breaks objectivity.


## 5. References
- Belytschko, Liu, Moran & Elkhodary (2014) — Nonlinear Finite Elements for Continua and Structures, 2nd ed. (velocity gradient, sym/skew decomposition, conjugacy table, pull-back of $\mathbf{D}$)
- Holzapfel (2000) — Nonlinear Solid Mechanics (rate-of-deformation, spin, vorticity, exponential map for $\mathbf{F}$)
- de Borst, Crisfield, Remmers & Verhoosel (2012) — Nonlinear Finite Element Analysis of Solids and Structures, 2nd ed. (velocity gradient in updated Lagrangian formulations)

