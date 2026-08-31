---
id: stress-piola-kirchhoff
title: First & Second Piola-Kirchhoff Stress
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- continuum-mechanics
- stress
- piola-kirchhoff
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: stress-cauchy-kirchhoff
  type: requires
  weight: 1.0
  note: PK1 / PK2 are Lagrangian pull-backs of Cauchy / Kirchhoff stress
- to: kinematics-motion-deformation-gradient
  type: requires
  weight: 1.0
  note: Piola transformation $\mathbf{P}=J\boldsymbol{\sigma}\mathbf{F}^{-T}$ uses $\mathbf{F}$ and $J$
- to: kinematics-strain-tensors
  type: feeds-into
  weight: 1.0
  note: Conjugacy $\mathbf{S}\colon\dot{\mathbf{E}}$ for hyperelasticity / TL-FEM
- to: stress-push-forward-pull-back
  type: feeds-into
  weight: 1.0
  note: $\boldsymbol{\tau}=\mathbf{F}\mathbf{S}\mathbf{F}^T$ push-forward
- to: fem-tl-weak-form
  type: feeds-into
  weight: 1.0
  note: TL weak form integrates $\mathbf{S}\colon\delta\mathbf{E}$ over the reference configuration
context_size: medium
reading_priority: full
load_with:
- stress-cauchy-kirchhoff
- kinematics-strain-tensors
content_ref: null
akms_schema: v2
---

# First & Second Piola-Kirchhoff Stress

## Summary
The first Piola-Kirchhoff (PK1, nominal) stress $\mathbf{P}=J\boldsymbol{\sigma}\mathbf{F}^{-T}$ is the two-point tensor that gives the current force per unit reference area: $\mathbf{P}\cdot\mathbf{n}_0\,dA_0=\boldsymbol{\sigma}\cdot\mathbf{n}\,da$. It is generally NOT symmetric. The second Piola-Kirchhoff (PK2) stress $\mathbf{S}=\mathbf{F}^{-1}\mathbf{P}=J\mathbf{F}^{-1}\boldsymbol{\sigma}\mathbf{F}^{-T}$ is symmetric (it inherits Cauchy's symmetry through the kinetic pull-back), lives entirely on the reference configuration, and is the canonical stress measure for total-Lagrangian FEM. Conjugacy: $\mathbf{S}\leftrightarrow\dot{\mathbf{E}}$ (with $\dot{\mathbf{E}}=\tfrac12\dot{\mathbf{C}}=\mathbf{F}^T\mathbf{D}\mathbf{F}$), $\mathbf{P}\leftrightarrow\dot{\mathbf{F}}$. The reference-configuration equilibrium reads $\nabla_0\cdot\mathbf{P}+\rho_0\mathbf{b}_0=\rho_0\dot{\mathbf{v}}$. PK2 is the natural stress for hyperelasticity ($\mathbf{S}=2\partial\psi/\partial\mathbf{C}=\partial\psi/\partial\mathbf{E}$) and for the multiplicative split's elastic block.


## 1. Core Concept
PK1 and PK2 are the two Lagrangian alternatives to Cauchy stress, each with a specific role. PK1 is a two-point tensor (one spatial leg, one material leg) that lets boundary integrals stay on the reference configuration: $\int_{\partial\Omega_0}\mathbf{P}\cdot\mathbf{n}_0\,dA_0=\int_{\partial\Omega_t}\boldsymbol{\sigma}\cdot\mathbf{n}\,da$. It appears naturally in the rate-form weak power $\mathbf{P}\colon\dot{\mathbf{F}}$ and in the reference equilibrium $\nabla_0\cdot\mathbf{P}=\rho_0(\dot{\mathbf{v}}-\mathbf{b}_0)$. PK2 strips the spatial leg via $\mathbf{S}=\mathbf{F}^{-1}\mathbf{P}$, leaving a fully Lagrangian symmetric tensor: ideal for hyperelasticity, where it derives from the strain-energy potential as $\mathbf{S}=2\partial\psi/\partial\mathbf{C}$, and for return-mapping algorithms in the multiplicative split, where the elastic stress is computed in PK2 form on the intermediate configuration. The price of working in $\mathbf{S}$ is a push-forward $\boldsymbol{\sigma}=J^{-1}\mathbf{F}\mathbf{S}\mathbf{F}^T$ at the end to recover Cauchy stress for output / contact / yield checks.


## 2. Mathematical Formulation
Throughout, $\mathbf{F}$ is the deformation gradient, $J=\det\mathbf{F}>0$. Lower-case Latin = spatial; upper-case Latin = material. Density: $\rho_0=J\rho$.


**PK1 (nominal) stress:**

$$
\mathbf{P} = J\,\boldsymbol{\sigma}\,\mathbf{F}^{-T},\qquad
P_{iJ} = J\,\sigma_{ij}\,F^{-1}_{Jj}
$$

where Two-point tensor; lower-case spatial $i$, upper-case material $J$

**Traction transformation:**

$$
\mathbf{t}\,da = \mathbf{P}\cdot\mathbf{n}_0\,dA_0,\qquad
\int_{\partial\Omega_t}\mathbf{t}\,da = \int_{\partial\Omega_0}\mathbf{P}\cdot\mathbf{n}_0\,dA_0
$$

where Same physical force, integrated over reference vs current surface

**PK2 stress:**

$$
\mathbf{S} = \mathbf{F}^{-1}\mathbf{P} = J\,\mathbf{F}^{-1}\boldsymbol{\sigma}\,\mathbf{F}^{-T},\qquad
S_{IJ} = J\,F^{-1}_{Ii}\,\sigma_{ij}\,F^{-1}_{Jj}
$$

where Fully Lagrangian (both indices material); symmetric $\mathbf{S}=\mathbf{S}^T$ since $\boldsymbol{\sigma}$ symmetric

**Inverse transformations:**

$$
\boldsymbol{\sigma} = J^{-1}\,\mathbf{P}\,\mathbf{F}^T = J^{-1}\,\mathbf{F}\,\mathbf{S}\,\mathbf{F}^T,\qquad
\boldsymbol{\tau} = \mathbf{F}\,\mathbf{S}\,\mathbf{F}^T = \mathbf{P}\,\mathbf{F}^T
$$

where Recover spatial stresses from Lagrangian; $\boldsymbol{\tau}=J\boldsymbol{\sigma}$

**Symmetry contrast:**

$$
\mathbf{S} = \mathbf{S}^T \;(\text{symmetric}),\qquad
\mathbf{P} \ne \mathbf{P}^T \;\text{in general}
$$

where $\mathbf{P}$ asymmetric because the two legs live in different configurations

**Reference-configuration equation of motion:**

$$
\nabla_0\cdot\mathbf{P} + \rho_0\,\mathbf{b}_0 = \rho_0\,\dot{\mathbf{v}},\qquad
\frac{\partial P_{iJ}}{\partial X_J} + \rho_0\,b_{0,i} = \rho_0\,\dot v_i
$$

where Lagrangian counterpart of the spatial $\nabla\cdot\boldsymbol{\sigma}+\rho\mathbf{b}=\rho\dot{\mathbf{v}}$

**Conjugacy table:**

$$
\mathbf{P}\colon\dot{\mathbf{F}} = \mathbf{S}\colon\dot{\mathbf{E}}
                               = \boldsymbol{\tau}\colon\mathbf{D}
                               = J\,\boldsymbol{\sigma}\colon\mathbf{D},
\qquad \dot{\mathbf{E}} = \tfrac{1}{2}\dot{\mathbf{C}} = \mathbf{F}^T\,\mathbf{D}\,\mathbf{F}
$$

where Internal-power density per reference volume; all four expressions are equal

**Hyperelastic PK2:**

$$
\mathbf{S} = 2\,\frac{\partial \psi(\mathbf{C})}{\partial \mathbf{C}}
          = \frac{\partial \psi(\mathbf{E})}{\partial \mathbf{E}}
$$

where Same stress through $\mathbf{C}$- or $\mathbf{E}$-parameterised energy; factor 2 absorbs $\mathbf{E}=\tfrac12(\mathbf{C}-\mathbf{I})$

**Convected (Lie) rate of $\boldsymbol{\tau}$ from $\dot{\mathbf{S}}$:**

$$
\mathcal{L}_v\,\boldsymbol{\tau} = \mathbf{F}\,\dot{\mathbf{S}}\,\mathbf{F}^T
$$

where Truesdell rate of Cauchy stress equals $J^{-1}\,\mathcal{L}_v\boldsymbol{\tau}$

**Notation:**

- $\mathbf{P}$ — First Piola-Kirchhoff (nominal) stress, $\mathbf{P}=J\boldsymbol{\sigma}\mathbf{F}^{-T}$
- $\mathbf{S}$ — Second Piola-Kirchhoff stress, $\mathbf{S}=J\mathbf{F}^{-1}\boldsymbol{\sigma}\mathbf{F}^{-T}$
- $\boldsymbol{\sigma}$ — Cauchy stress (`stress-cauchy-kirchhoff`)
- $\boldsymbol{\tau}$ — Kirchhoff stress, $\boldsymbol{\tau}=J\boldsymbol{\sigma}=\mathbf{F}\mathbf{S}\mathbf{F}^T$
- $\mathbf{F},J$ — Deformation gradient and Jacobian
- $\mathbf{E}$ — Green-Lagrange strain, $\mathbf{E}=\tfrac12(\mathbf{C}-\mathbf{I})$
- $\dot{\mathbf{F}},\dot{\mathbf{E}}$ — Material time derivatives, work-conjugate to $\mathbf{P},\mathbf{S}$
- $\rho_0,\mathbf{b}_0$ — Reference density and reference-frame body force
- $\nabla_0$ — Material (reference) gradient, $\partial/\partial\mathbf{X}$


## 3. Algorithmic Implementation
**Algorithm: Compute $\mathbf{P}$ and $\mathbf{S}$ from $\boldsymbol{\sigma}$ and $\mathbf{F}$**

$$
\begin{algorithmic}
\State $\text{input} \colon \boldsymbol{\sigma}\in\mathbb{R}^{3\times 3}_{\mathrm{sym}},\,\mathbf{F}\in\mathbb{R}^{3\times 3}$
\State $J \gets \det\mathbf{F}$
\State $\mathbf{F}^{-1} \gets \mathrm{cofactor\;inverse}(\mathbf{F})$
\State $\mathbf{P} \gets J\,\boldsymbol{\sigma}\,\mathbf{F}^{-T}$
\State $\mathbf{S} \gets \mathbf{F}^{-1}\,\mathbf{P} = J\,\mathbf{F}^{-1}\,\boldsymbol{\sigma}\,\mathbf{F}^{-T}$
\State $\mathbf{S} \gets \tfrac{1}{2}(\mathbf{S}+\mathbf{S}^T) \;\text{(symmetrise to suppress round-off skew)}$
\Return $\mathbf{P},\,\mathbf{S}$
\end{algorithmic}
$$

**Taichi Mapping:**
`@ti.func` per Gauss point. Cache $\mathbf{F}^{-1}$ once at the start of the constitutive update — reuse for $\mathbf{P}$, $\mathbf{S}$, and any push-forward / pull-back routine. Symmetrise $\mathbf{S}$ at construction even though it is mathematically symmetric — round-off in $\boldsymbol{\sigma}$ and $\mathbf{F}^{-1}$ produces $\mathcal{O}(10^{-14})$ skew that integrates to wrong moments over many time steps. Store $\mathbf{S}$ as 6 components, $\mathbf{P}$ as full 9.


**Algorithm: Hyperelastic PK2 from Strain-Energy Potential**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{F},\;\psi(\mathbf{C})\;\text{or}\;\psi(\mathbf{E})$
\State $\mathbf{C} \gets \mathbf{F}^T\,\mathbf{F}$
\State $\mathbf{S} \gets 2\,\frac{\partial \psi(\mathbf{C})}{\partial \mathbf{C}} \;\text{or}\; \mathbf{S} \gets \frac{\partial \psi(\mathbf{E})}{\partial \mathbf{E}}$
\State $\boldsymbol{\sigma} \gets J^{-1}\,\mathbf{F}\,\mathbf{S}\,\mathbf{F}^T$
\Return $\mathbf{S},\,\boldsymbol{\sigma}$
\end{algorithmic}
$$

**Taichi Mapping:**
For invariant-based $\psi(I_1,I_2,I_3)$ use the chain rule $\mathbf{S}=2\sum_k(\partial\psi/\partial I_k)(\partial I_k/\partial\mathbf{C})$ from `tensor-derivatives-scalars`. For incompressible Mooney-Rivlin add a Lagrange multiplier $-p\,J\mathbf{C}^{-1}$ to enforce $J=1$. The push-forward $\boldsymbol{\sigma}=J^{-1}\mathbf{F}\mathbf{S}\mathbf{F}^T$ is the canonical use of `stress-push-forward-pull-back`.


**Algorithm: TL-FEM Internal Force from PK2**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{S}\,\text{at GPs},\,\mathbf{F},\,\partial N_a/\partial \mathbf{X}$
\For{$\text{each Gauss point}$}
\State $\mathbf{P} \gets \mathbf{F}\,\mathbf{S}$
\For{$a = 1,\ldots,n_n;\,i,J = 1,2,3$}
\State $f^{\mathrm{int}}_{a,i} \mathrel{+}= P_{iJ}\,(\partial N_a/\partial X_J)\,W\,\det(\partial \mathbf{X}/\partial \boldsymbol{\xi})$
\EndFor
\EndFor
\Return $\mathbf{f}^{\mathrm{int}}_a$
\end{algorithmic}
$$

**Taichi Mapping:**
The reference-configuration B-matrix $B_{aiJ}=\partial N_a/\partial X_J$ is constant in time — pre-compute once per element. The kernel is $\mathbf{f}^{\mathrm{int}}_a=\sum_{\mathrm{GP}}(\mathbf{F}\mathbf{S})\cdot(\partial N_a/\partial\mathbf{X})\,W_{\mathrm{GP}}\,\det J_{\mathrm{ref}}$; scatter to the global force vector with `ti.atomic_add`. Avoid converting to $\boldsymbol{\sigma}$ inside the assembly loop — it costs an extra inverse-transpose per Gauss point.



## 4. Known Pitfalls
**$\mathbf{P}$ is not symmetric:** $P_{iJ}$ is a two-point tensor: $\mathbf{P}\ne\mathbf{P}^T$ except in trivial cases (pure dilation). Storing it in 6-component symmetric form drops the skew part and corrupts the reference equilibrium $\nabla_0\cdot\mathbf{P}$. Store $\mathbf{P}$ as full 9 components; reserve symmetric storage for $\mathbf{S}$ and $\boldsymbol{\sigma}$.


**Mixing material and spatial divergences:** Reference equilibrium uses the material divergence $\partial P_{iJ}/\partial X_J$, NOT the spatial $\partial P_{ij}/\partial x_j$. The two give different residuals because they integrate against different reference / current geometries. TL-FEM kernels must use $\partial N_a/\partial \mathbf{X}$; UL-FEM must use $\partial N_a/\partial \mathbf{x}$. Mixing them silently halves or doubles the assembled residual.


**Sign / order convention on $\mathbf{F}^{-1}$:** $\mathbf{S}=\mathbf{F}^{-1}\mathbf{P}$, NOT $\mathbf{P}\mathbf{F}^{-1}$ — the inverse acts on the LEFT to remove the spatial leg of $\mathbf{P}$. Swapping the order produces a tensor with mixed legs that is neither $\mathbf{S}$ nor $\boldsymbol{\sigma}$ and corrupts every downstream stress operation. Always derive the formula in indicial form: $S_{IJ}=F^{-1}_{Ii}\,P_{iJ}$.


**Conjugacy bookkeeping:** $\mathbf{S}\colon\dot{\mathbf{E}}\,dV_0$ is the correct internal-power density per reference volume. Pairing $\mathbf{S}\colon\mathbf{D}$ (Cauchy strain rate) is dimensionally consistent but conceptually wrong and breaks energy balance under finite rotation. Tag every stress / strain pairing with its conjugate partner and validate with a closed-loop deformation cycle.


**Index ordering in $\mathbf{S}=\mathbf{F}^{-1}\boldsymbol{\sigma}\mathbf{F}^{-T}$:** The full pull-back is $S_{IJ}=J\,F^{-1}_{Ii}\,\sigma_{ij}\,F^{-1}_{Jj}$ — both inverses act on the LEFT of their respective indices, transposing the second one to give the right-leg multiplication. A common bug is using $\mathbf{F}^{-T}$ on the left instead of $\mathbf{F}^{-1}$, producing a transposed-and-mirrored tensor. Always derive component-wise first; only then write in compact form.


**Forgetting the $J$ factor:** $\mathbf{S}=J\mathbf{F}^{-1}\boldsymbol{\sigma}\mathbf{F}^{-T}$ — the $J$ is essential. Dropping it gives $\mathbf{F}^{-1}\boldsymbol{\sigma}\mathbf{F}^{-T}=J^{-1}\mathbf{S}$ which is wrong by a factor $J$ (significant at large strain). Equivalent statement: $\boldsymbol{\tau}=\mathbf{F}\mathbf{S}\mathbf{F}^T$ (no $J$) but $\boldsymbol{\sigma}=J^{-1}\mathbf{F}\mathbf{S}\mathbf{F}^T$.


**Numerical asymmetry in $\mathbf{S}$:** $\mathbf{S}$ is mathematically symmetric (inherits from $\boldsymbol{\sigma}$) but round-off in $\mathbf{F}^{-1}$ can produce skew-symmetric noise of $\mathcal{O}(10^{-14})$. Over thousands of steps this drifts into $\mathcal{O}(10^{-8})$ asymmetry, breaks angular-momentum balance, and corrupts the consistent-tangent symmetry. Symmetrise $\mathbf{S}\to\tfrac12(\mathbf{S}+\mathbf{S}^T)$ at the end of every constitutive update.


## 5. References
- Belytschko, Liu, Moran & Elkhodary (2014) — Nonlinear Finite Elements for Continua and Structures, 2nd ed. (PK1, PK2 definitions, Piola transformation, conjugacy table, reference equilibrium)
- Holzapfel (2000) — Nonlinear Solid Mechanics (Piola-Kirchhoff stresses, hyperelastic $\mathbf{S}=2\partial\psi/\partial\mathbf{C}$)
- de Borst, Crisfield, Remmers & Verhoosel (2012) — Nonlinear Finite Element Analysis of Solids and Structures, 2nd ed. (TL-FEM internal force assembly using PK2)

