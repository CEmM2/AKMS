---
id: fem-tl-weak-form
title: TL Weak Form & Internal Virtual Work
domain: computational-mechanics
subdomain: finite-elements
tags:
- fem
- finite-strain
- total-lagrangian
- variational
- weak-form
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: stress-piola-kirchhoff
  type: requires
  weight: 1.0
  note: TL weak form integrates $\mathbf{S}\colon\delta\mathbf{E}$ over $\Omega_0$
- to: kinematics-strain-tensors
  type: requires
  weight: 1.0
  note: $\delta\mathbf{E}$ is the variation of Green-Lagrange strain
- to: kinematics-motion-deformation-gradient
  type: requires
  weight: 1.0
  note: Discrete $\mathbf{F}_h$ built from nodal displacements via shape function gradients
- to: fem-tl-b-matrix
  type: feeds-into
  weight: 1.0
  note: $\delta\mathbf{E}=\sum_a \mathbf{B}_a\,\delta\mathbf{u}_a$ is the canonical use of the TL B-matrix
- to: fem-tl-linearization
  type: feeds-into
  weight: 1.0
  note: Linearisation of the residual produces $\mathbf{K}=\mathbf{K}_m+\mathbf{K}_\sigma$
context_size: medium
reading_priority: full
load_with:
- stress-piola-kirchhoff
- fem-tl-b-matrix
content_ref: null
akms_schema: v2
---

# TL Weak Form & Internal Virtual Work

## Summary
Total-Lagrangian (TL) FEM formulates equilibrium on the reference (undeformed) configuration. The principle of virtual work in PK2 form reads $\int_{\Omega_0}\mathbf{S}\colon\delta\mathbf{E}\,dV_0=\int_{\Omega_0}\rho_0(\mathbf{b}_0-\dot{\mathbf{v}})\cdot\delta\mathbf{u}\,dV_0+\int_{\partial\Omega_0^t}\bar{\mathbf{t}}_0\cdot\delta\mathbf{u}\,dA_0$, where $\delta\mathbf{E}=\mathrm{sym}(\mathbf{F}^T\nabla_0\delta\mathbf{u})=\tfrac12(\mathbf{F}^T\nabla_0\delta\mathbf{u}+\nabla_0\delta\mathbf{u}^T\mathbf{F})$. The Piola-equivalent form $\int_{\Omega_0}\mathbf{P}\colon\delta\mathbf{F}\,dV_0$ uses the nominal stress and the variation of $\mathbf{F}$. Discretization $\mathbf{u}_h=\sum_a N_a(\mathbf{X})\mathbf{u}_a$ with reference shape function gradients $\partial N_a/\partial\mathbf{X}$ produces the discrete deformation gradient $\mathbf{F}_h=\mathbf{I}+\sum_a (\partial N_a/\partial\mathbf{X})\otimes\mathbf{u}_a$ and the internal force vector $\mathbf{f}^{\mathrm{int}}_a=\sum_{\mathrm{GP}}\mathbf{B}_a^T\mathbf{S}\,W_{\mathrm{GP}}\det J_{\mathrm{ref}}$ — assembled element-by-element on the fixed reference mesh, then advanced via Newton-Raphson.


## 1. Core Concept
Total-Lagrangian FEM treats the reference configuration $\Omega_0$ as the integration domain throughout the simulation: shape functions, Gauss points, and quadrature weights are fixed in time, and only the displacement / stress / strain fields evolve. The weak form derives from the reference-configuration equilibrium $\nabla_0\cdot\mathbf{P}+\rho_0\mathbf{b}_0=\rho_0\dot{\mathbf{v}}$ via test-function multiplication and integration-by-parts; the natural pairing is $\mathbf{P}\colon\delta\mathbf{F}=\mathbf{S}\colon\delta\mathbf{E}$ (Piola transformation), so the same residual can be expressed in either nominal or PK2 form. PK2 is preferred for hyperelasticity because $\mathbf{S}=\partial\psi/\partial\mathbf{E}$ derives directly from the strain-energy potential, and for elastoplasticity in the multiplicative split because the constitutive update is performed in PK2 form on the intermediate configuration. The variation $\delta\mathbf{E}$ couples to the displacement variation through the TL B-matrix $\mathbf{B}_a=\mathbf{B}_0+\mathbf{B}_1(\mathbf{u})$, which has a constant linear part (small-strain B-matrix) and a displacement-dependent nonlinear part — the latter is what makes finite-strain TL nonlinear in displacement.


## 2. Mathematical Formulation
Throughout, $\Omega_0$ is the reference body, $\partial\Omega_0=\partial\Omega_0^u\cup\partial\Omega_0^t$ split into Dirichlet / Neumann boundaries. $\rho_0$ reference density, $\mathbf{b}_0$ body force per unit reference mass, $\bar{\mathbf{t}}_0$ prescribed nominal traction on $\partial\Omega_0^t$. Indices: lower-case Latin spatial, upper-case Latin material; both $1$-$3$.


**Reference-configuration equation of motion:**

$$
\nabla_0\cdot\mathbf{P} + \rho_0\,\mathbf{b}_0 = \rho_0\,\dot{\mathbf{v}}
\;\;\text{in}\;\Omega_0,\qquad
\mathbf{P}\cdot\mathbf{n}_0 = \bar{\mathbf{t}}_0
\;\;\text{on}\;\partial\Omega_0^t,\qquad
\mathbf{u} = \bar{\mathbf{u}} \;\;\text{on}\;\partial\Omega_0^u
$$

where Lagrangian strong form; $\mathbf{P}=J\boldsymbol{\sigma}\mathbf{F}^{-T}$ is nominal stress

**Weak form in PK1 (nominal) form:**

$$
\int_{\Omega_0}\mathbf{P}\colon\delta\mathbf{F}\,dV_0
= \int_{\Omega_0}\rho_0\,(\mathbf{b}_0 - \dot{\mathbf{v}})\cdot\delta\mathbf{u}\,dV_0
+ \int_{\partial\Omega_0^t}\bar{\mathbf{t}}_0\cdot\delta\mathbf{u}\,dA_0
$$

where $\delta\mathbf{F}=\nabla_0\delta\mathbf{u}$

**Weak form in PK2 form (Piola-transformed):**

$$
\int_{\Omega_0}\mathbf{S}\colon\delta\mathbf{E}\,dV_0
= \int_{\Omega_0}\rho_0\,(\mathbf{b}_0 - \dot{\mathbf{v}})\cdot\delta\mathbf{u}\,dV_0
+ \int_{\partial\Omega_0^t}\bar{\mathbf{t}}_0\cdot\delta\mathbf{u}\,dA_0
$$

where Equivalent via $\mathbf{P}\colon\delta\mathbf{F}=\mathbf{S}\colon\delta\mathbf{E}$

**Variation of Green-Lagrange strain:**

$$
\delta\mathbf{E} = \mathrm{sym}(\mathbf{F}^T\,\nabla_0\delta\mathbf{u})
               = \tfrac{1}{2}\!\left(\mathbf{F}^T\,\nabla_0\delta\mathbf{u}
                                    + (\nabla_0\delta\mathbf{u})^T\,\mathbf{F}\right)
$$

where Symmetric (kinematic) — $\delta\mathbf{E}=\delta\mathbf{E}^T$

**Discrete displacement field:**

$$
\mathbf{u}_h(\mathbf{X}) = \sum_{a=1}^{n_n} N_a(\mathbf{X})\,\mathbf{u}_a,\qquad
\mathbf{F}_h(\mathbf{X}) = \mathbf{I} + \sum_{a=1}^{n_n}\,\mathbf{u}_a\otimes\nabla_0 N_a
$$

where Standard isoparametric discretisation; $\mathbf{F}_h$ is element-piecewise polynomial

**Internal force at nodal level:**

$$
\mathbf{f}^{\mathrm{int}}_a
= \int_{\Omega_0}\mathbf{B}_a^T\,\mathbf{S}\,dV_0
= \int_{\Omega_0}\nabla_0 N_a\cdot(\mathbf{F}\,\mathbf{S})\,dV_0
$$

where Equivalent forms; the second uses $\mathbf{P}=\mathbf{F}\mathbf{S}$

**External force:**

$$
\mathbf{f}^{\mathrm{ext}}_a = \int_{\Omega_0}N_a\,\rho_0\,\mathbf{b}_0\,dV_0
                         + \int_{\partial\Omega_0^t}N_a\,\bar{\mathbf{t}}_0\,dA_0
$$

where Both integrals on reference geometry; no Jacobian rescaling needed

**Residual / equation of motion in matrix form:**

$$
\mathbf{r}_a(\mathbf{u}) = \mathbf{f}^{\mathrm{int}}_a(\mathbf{u}) - \mathbf{f}^{\mathrm{ext}}_a + \mathbf{M}_{ab}\,\dot{\mathbf{v}}_b = \mathbf{0}
$$

where Algebraic system to solve at each time step; $\mathbf{M}_{ab}=\int_{\Omega_0}\rho_0\,N_a\,N_b\,dV_0\,\mathbf{I}$ is the reference-mass matrix

**Statics (drop inertial term):**

$$
\mathbf{r}_a(\mathbf{u}) = \mathbf{f}^{\mathrm{int}}_a(\mathbf{u}) - \mathbf{f}^{\mathrm{ext}}_a = \mathbf{0}
$$

where Solved by Newton-Raphson with tangent $\mathbf{K}=\mathbf{K}_m+\mathbf{K}_\sigma$ (`fem-tl-linearization`)

**Notation:**

- $\Omega_0$ — Reference (undeformed) body
- $\mathbf{u},\delta\mathbf{u}$ — Displacement field and its variation (test function)
- $\mathbf{F}$ — Deformation gradient, $\mathbf{F}=\mathbf{I}+\nabla_0\mathbf{u}$
- $\mathbf{S},\mathbf{P}$ — PK2 and PK1 (nominal) stresses
- $\mathbf{E}$ — Green-Lagrange strain, $\mathbf{E}=\tfrac12(\mathbf{C}-\mathbf{I})$
- $\rho_0,\mathbf{b}_0,\bar{\mathbf{t}}_0$ — Reference density / body force / prescribed nominal traction
- $N_a$ — Shape function for node $a$
- $\nabla_0 N_a$ — Reference gradient of shape function, $\partial N_a/\partial\mathbf{X}$
- $\mathbf{B}_a$ — TL B-matrix block for node $a$ (`fem-tl-b-matrix`)
- $\mathbf{f}^{\mathrm{int}},\mathbf{f}^{\mathrm{ext}}$ — Internal / external nodal force vectors


## 3. Algorithmic Implementation
**Algorithm: Element-Level Internal Force Assembly (TL, PK2 Form)**

$$
\begin{algorithmic}
\State $\text{input} \colon \{\mathbf{u}_a\}_{a=1}^{n_n},\;\text{element nodes; reference Gauss data}$
\State $\mathbf{f}^{\mathrm{int}}_e \gets \mathbf{0}$
\For{$\text{each Gauss point } g \;\text{with weight } w_g,\,\det J_g$}
\State $\mathbf{F}_g \gets \mathbf{I} + \sum_a \mathbf{u}_a\otimes\nabla_0 N_a(\boldsymbol{\xi}_g)$
\State $\mathbf{C}_g \gets \mathbf{F}_g^T\,\mathbf{F}_g$
\State $\mathbf{S}_g,\,(\text{state}) \gets \mathrm{ConstitutiveUpdate}(\mathbf{C}_g,\,\text{state}_n)$
\State $\mathbf{P}_g \gets \mathbf{F}_g\,\mathbf{S}_g$
\For{$a = 1,\ldots,n_n$}
\State $f^{\mathrm{int}}_{e,a,i} \mathrel{+}= P_{g,iJ}\,(\partial N_a/\partial X_J)\,w_g\,\det J_g$
\EndFor
\EndFor
\State $\text{scatter } \mathbf{f}^{\mathrm{int}}_e \text{ into the global force vector}$
\Return $\mathbf{f}^{\mathrm{int}}_e$
\end{algorithmic}
$$

**Taichi Mapping:**
Single fused element kernel `@ti.kernel` parameterised by element type. Pre-compute reference shape function gradients $\partial N_a/\partial\mathbf{X}$ once per element at startup (constant in time for TL). Use `ti.atomic_add` to scatter into the global force; or pre-color elements to allow safe parallel assembly without atomics. For high-order elements ($n_n>20$) split the element into per-Gauss-point parallel blocks to manage register pressure.


**Algorithm: Verify Discrete Conservation by Closed-Loop Cycle**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{u}(t)\,\text{prescribed closed loop in displacement space}$
\State $\text{compute } P_{\mathrm{int}}(t) = \int_{\Omega_0}\mathbf{S}\colon\dot{\mathbf{E}}\,dV_0$
\State $\text{integrate over the loop:}\,\,\oint P_{\mathrm{int}}\,dt$
\State $\text{For elastic material the integral must be zero to round-off}$
\Return $\oint P_{\mathrm{int}}\,dt$
\end{algorithmic}
$$

**Taichi Mapping:**
Diagnostic: drives the body around a path-independent loop (e.g., shear up / shear down) and integrates the internal power. For elastic constitutive laws the integrated power must vanish; failure indicates wrong stress / strain conjugacy, missing Voigt factor 2 on shear, or wrong $J$ scaling.


**Algorithm: External Force from Prescribed Surface Traction**

$$
\begin{algorithmic}
\State $\text{input} \colon \bar{\mathbf{t}}_0(\mathbf{X},t)\,\text{on}\,\partial\Omega_0^t$
\For{$\text{each surface element on}\,\partial\Omega_0^t$}
\For{$\text{each surface Gauss point}\,g$}
\For{$a = 1,\ldots,n_{n,\mathrm{surf}}$}
\State $f^{\mathrm{ext}}_{a,i} \mathrel{+}= N_a(\boldsymbol{\xi}_g)\,\bar{t}_{0,i}(\mathbf{X}_g,t)\,w_g\,\det J^{\mathrm{surf}}_g$
\EndFor
\EndFor
\EndFor
\Return $\mathbf{f}^{\mathrm{ext}}_a$
\end{algorithmic}
$$

**Taichi Mapping:**
Surface integrals stay on the REFERENCE surface in TL — no Nanson-formula push-forward needed because the prescribed traction is already nominal. If the user supplies Cauchy traction $\bar{\mathbf{t}}$ on the deformed surface, convert via Nanson: $\bar{\mathbf{t}}_0=J\boldsymbol{\sigma}\mathbf{F}^{-T}\mathbf{n}_0/\|\cdot\|$ (cf. `kinematics-motion-deformation-gradient`). Tag the input as `_nominal` or `_cauchy` at the API boundary.



## 4. Known Pitfalls
**Confusing reference vs current divergence:** Reference equilibrium uses $\nabla_0\cdot\mathbf{P}$; current equilibrium uses $\nabla\cdot\boldsymbol{\sigma}$. Mixing the two — e.g., applying material gradients to $\boldsymbol{\sigma}$ — produces residuals integrated against the wrong configuration. Pick TL or UL once, document, validate. The variation $\delta\mathbf{u}$ is associated with the chosen configuration.


**Factor of 2 in $\delta\mathbf{E}$:** $\delta\mathbf{E}=\tfrac12(\mathbf{F}^T\nabla_0\delta\mathbf{u}+\nabla_0\delta\mathbf{u}^T\mathbf{F})$ — the factor 1/2 is essential to make $\delta\mathbf{E}=\delta\mathbf{E}^T$ symmetric. Forgetting it doubles the symmetric strain variation and the internal force becomes wrong by a factor of 2 in shear blocks. Always write the symmetrised form explicitly.


**Mixing kinetic / kinematic Voigt representations:** In Voigt form $\delta\{\mathbf{E}\}$ uses kinematic Voigt (factor 2 on shears) while $\{\mathbf{S}\}$ uses kinetic Voigt (no factor). The product $\{\mathbf{S}\}^T\{\delta\mathbf{E}\}=\mathbf{S}\colon\delta\mathbf{E}$ holds only with this convention. Substituting kinetic-Voigt $\delta\{\mathbf{E}\}$ (no factor) halves the shear contribution and silently corrupts internal energy.


**Dropping geometric stiffness in linearization:** The tangent $\mathbf{K}=\mathbf{K}_m+\mathbf{K}_\sigma$ has both a material and a geometric (initial-stress) contribution; dropping $\mathbf{K}_\sigma$ degrades Newton convergence from quadratic to linear at finite strain. The geometric term comes from the SECOND variation of $\mathbf{E}$ — see `fem-tl-linearization`. Always include it for finite-strain analyses.


**$\mathbf{S}$ paired with $\dot{\mathbf{F}}$ instead of $\dot{\mathbf{E}}$:** The conjugate strain rate of $\mathbf{S}$ is $\dot{\mathbf{E}}$, NOT $\dot{\mathbf{F}}$. The conjugate of $\dot{\mathbf{F}}$ is $\mathbf{P}$ (nominal). Pairing $\mathbf{S}\colon\dot{\mathbf{F}}$ in an internal-power expression is dimensionally ill-formed (mixed-leg vs symmetric tensors) and breaks energy balance. State the conjugacy convention at every internal-power computation.


**Forgetting the reference Jacobian in surface integrals:** Surface integrals on $\partial\Omega_0^t$ use $\det J^{\mathrm{surf}}_g$ from the parametric surface mapping (parent boundary $\to$ reference surface). Some codes accidentally reuse the volumetric Jacobian, producing tractions wrong by a factor proportional to surface curvature. Use a separate surface-Gauss data structure with its own quadrature weights and Jacobians.


**Discontinuous shape functions across element boundaries:** $\mathbf{F}_h$ has $C^0$ continuity in standard FEM (displacement is continuous, gradient is discontinuous across element edges). Computing element-level quantities and naively averaging at nodes produces visually plausible but quantitatively wrong contour plots of stress / strain. Use proper L2 / superconvergent recovery for nodal output; never average raw element-level $\mathbf{F}$ at nodes.


**Treating material time derivative as Eulerian partial in TL:** In TL the material derivative $\dot{(\bullet)}=\partial(\bullet)/\partial t|_{\mathbf{X}}$ is exactly the partial derivative at fixed reference label — the Eulerian advective term $\mathbf{v}\cdot\nabla(\bullet)$ does NOT appear. Adding it (a habit from UL / Eulerian fluid codes) introduces a spurious convective term and breaks the TL formulation. Material-frame is the simplest case; the advective term emerges only in UL / Eulerian formulations.


## 5. References
- Belytschko, Liu, Moran & Elkhodary (2014) — Nonlinear Finite Elements for Continua and Structures, 2nd ed., Ch. 4-6 (TL weak form, PK1 / PK2 equivalence, element internal force, Newton iteration)
- de Borst, Crisfield, Remmers & Verhoosel (2012) — Nonlinear Finite Element Analysis of Solids and Structures, 2nd ed. (geometrically nonlinear weak form, computational flow chart)
- Bathe (1975) — Finite element formulations for large deformation dynamic analysis (early TL formulation; conjugacy of PK2 with Green strain rate)

