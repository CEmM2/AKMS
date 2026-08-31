---
id: stress-push-forward-pull-back
title: Push-Forward & Pull-Back of Stress
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- continuum-mechanics
- push-forward
- pull-back
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: stress-piola-kirchhoff
  type: requires
  weight: 1.0
  note: Push-forward of PK2 to Kirchhoff and pull-back of Cauchy to PK2
- to: stress-cauchy-kirchhoff
  type: requires
  weight: 1.0
  note: $\boldsymbol{\tau}=\mathbf{F}\mathbf{S}\mathbf{F}^T$, $\boldsymbol{\sigma}=\boldsymbol{\tau}/J$
- to: tensor-operations
  type: refines
  weight: 0.7
  note: Specialises generic push-forward / pull-back to stress (kinetic, contravariant-contravariant) tensors
- to: kinematics-objective-rates
  type: feeds-into
  weight: 0.9
  note: Lie / Truesdell rate $\mathcal{L}_v\boldsymbol{\tau}=\mathbf{F}\dot{\mathbf{S}}\mathbf{F}^T$
- to: stress-tangent-push-forward
  type: feeds-into
  weight: 1.0
  note: Constitutive tangent push-forward extends the same idea to the 4th-order moduli
context_size: medium
reading_priority: full
load_with:
- stress-piola-kirchhoff
- stress-cauchy-kirchhoff
content_ref: null
akms_schema: v2
---

# Push-Forward & Pull-Back of Stress

## Summary
Stress is a kinetic (contravariant-contravariant) 2nd-order tensor, so its push-forward / pull-back uses the kinetic rule $\phi_*(\bullet)=\mathbf{F}(\bullet)\mathbf{F}^T$ and $\phi^*(\bullet)=\mathbf{F}^{-1}(\bullet)\mathbf{F}^{-T}$. Concretely: $\boldsymbol{\tau}=\phi_*(\mathbf{S})=\mathbf{F}\mathbf{S}\mathbf{F}^T$ pushes PK2 forward to Kirchhoff stress; $\mathbf{S}=\phi^*(\boldsymbol{\tau})=\mathbf{F}^{-1}\boldsymbol{\tau}\mathbf{F}^{-T}$ pulls Kirchhoff back to PK2. Cauchy stress satisfies $\boldsymbol{\sigma}=J^{-1}\boldsymbol{\tau}$. The Piola transformation $\mathbf{P}=\mathbf{F}\mathbf{S}=J\boldsymbol{\sigma}\mathbf{F}^{-T}$ produces the nominal stress (PK1) — a two-point tensor — by leaving one material leg of $\mathbf{S}$ untouched. The Lie / convected rate $\mathcal{L}_v\boldsymbol{\tau}=\mathbf{F}\dot{\mathbf{S}}\mathbf{F}^T$ is precisely the push-forward of $\dot{\mathbf{S}}$ and is the canonical objective stress rate. Applying the kinematic rule $\mathbf{F}^{-T}(\bullet)\mathbf{F}^{-1}$ to a stress silently destroys symmetry / power conjugacy — the variance of the tensor MUST drive the choice of rule.


## 1. Core Concept
Stress is a "contravariant-contravariant" tensor: both legs are upper indices that transform with $\mathbf{F}$ rather than with $\mathbf{F}^{-T}$. The kinetic push-forward rule $\phi_*(\bullet)=\mathbf{F}(\bullet)\mathbf{F}^T$ therefore takes PK2 (fully Lagrangian) to Kirchhoff (fully Eulerian); the pull-back $\phi^*(\bullet)=\mathbf{F}^{-1}(\bullet)\mathbf{F}^{-T}$ goes the other way. The pair is forced by power conjugacy: $\boldsymbol{\tau}\colon\mathbf{D}=\mathbf{S}\colon\dot{\mathbf{E}}$ holds because the $\mathbf{F}\bullet\mathbf{F}^T$ on the stress side cancels the $\mathbf{F}^{-T}\bullet\mathbf{F}^{-1}$ on the strain rate side. The first Piola-Kirchhoff (nominal) stress $\mathbf{P}=\mathbf{F}\mathbf{S}$ is a "half push-forward" — it leaves one material leg of $\mathbf{S}$ untouched, producing a two-point tensor that lives between the configurations. Lie / convected derivatives are constructed by chaining pull-back, time derivative, push-forward, which makes them inherit objectivity from the structure of the chain itself rather than from any extra correction term.


## 2. Mathematical Formulation
All operations are with respect to the deformation gradient $\mathbf{F}$ at a single material point. Symmetric stress tensors are stored in 6-component form; the asymmetric $\mathbf{P}$ stays in 9-component form. $J=\det\mathbf{F}>0$.


**Kinetic push-forward / pull-back rule:**

$$
\phi_*(\bullet) = \mathbf{F}\,(\bullet)\,\mathbf{F}^T,\qquad
\phi^*(\bullet) = \mathbf{F}^{-1}\,(\bullet)\,\mathbf{F}^{-T}
$$

where Applies to all kinetic (contravariant-contravariant) tensors

**PK2 -> Kirchhoff (push-forward):**

$$
\boldsymbol{\tau} = \phi_*(\mathbf{S}) = \mathbf{F}\,\mathbf{S}\,\mathbf{F}^T,\qquad
\tau_{ij} = F_{iI}\,F_{jJ}\,S_{IJ}
$$

where Indicial form is unambiguous; Voigt $6\times 6$ flattening cannot reproduce this directly

**Kirchhoff -> PK2 (pull-back):**

$$
\mathbf{S} = \phi^*(\boldsymbol{\tau}) = \mathbf{F}^{-1}\,\boldsymbol{\tau}\,\mathbf{F}^{-T},\qquad
S_{IJ} = F^{-1}_{Ii}\,F^{-1}_{Jj}\,\tau_{ij}
$$

where Inverse pair: $\phi^*\circ\phi_*=\mathrm{id}$

**Cauchy via Kirchhoff:**

$$
\boldsymbol{\sigma} = J^{-1}\,\boldsymbol{\tau} = J^{-1}\,\mathbf{F}\,\mathbf{S}\,\mathbf{F}^T,\qquad
\mathbf{S} = J\,\mathbf{F}^{-1}\,\boldsymbol{\sigma}\,\mathbf{F}^{-T}
$$

where Same kinetic rule with the Jacobian rescaling

**Piola transformation (PK2 -> PK1):**

$$
\mathbf{P} = \mathbf{F}\,\mathbf{S} = J\,\boldsymbol{\sigma}\,\mathbf{F}^{-T},\qquad
P_{iJ} = F_{iI}\,S_{IJ}
$$

where Half push-forward: only the spatial leg is taken forward; PK1 is a two-point tensor

**Lie / convected rate of Kirchhoff:**

$$
\mathcal{L}_v\,\boldsymbol{\tau} = \phi_*\!\left(\frac{D}{Dt}\,\phi^*(\boldsymbol{\tau})\right)
                            = \phi_*(\dot{\mathbf{S}})
                            = \mathbf{F}\,\dot{\mathbf{S}}\,\mathbf{F}^T
$$

where Construction: pull back, take material derivative on the reference frame, push forward

**Spatial expansion of $\mathcal{L}_v\boldsymbol{\tau}$:**

$$
\mathcal{L}_v\,\boldsymbol{\tau}
= \dot{\boldsymbol{\tau}} - \mathbf{L}\,\boldsymbol{\tau} - \boldsymbol{\tau}\,\mathbf{L}^T
$$

where Equivalent to the convected / Truesdell rate of $J\boldsymbol{\sigma}$ (`tensor-operations`)

**Kinetic vs kinematic — DO NOT confuse:**

$$
\text{Kinetic (stress)} \colon\;\;
  \phi_*(\boldsymbol{\sigma}\text{-like}) = \mathbf{F}(\bullet)\mathbf{F}^T,\quad
\text{Kinematic (strain rate)} \colon\;\;
  \phi_*(\mathbf{D}\text{-like}) = \mathbf{F}^{-T}(\bullet)\mathbf{F}^{-1}
$$

where Variance forces the rule; mixing them breaks $\boldsymbol{\tau}\colon\mathbf{D}=\mathbf{S}\colon\dot{\mathbf{E}}$

**Notation:**

- $\phi_*,\phi^*$ — Push-forward / pull-back operators
- $\mathbf{F}$ — Deformation gradient
- $J$ — $J=\det\mathbf{F}$
- $\mathbf{S}$ — Second Piola-Kirchhoff (Lagrangian, kinetic)
- $\boldsymbol{\tau}$ — Kirchhoff (Eulerian, kinetic), $\boldsymbol{\tau}=\mathbf{F}\mathbf{S}\mathbf{F}^T$
- $\boldsymbol{\sigma}$ — Cauchy stress, $\boldsymbol{\sigma}=\boldsymbol{\tau}/J$
- $\mathbf{P}$ — First Piola-Kirchhoff / nominal stress, two-point
- $\dot{\mathbf{S}}$ — Material time derivative of $\mathbf{S}$
- $\mathcal{L}_v$ — Lie / convected derivative
- $\mathbf{L}$ — Spatial velocity gradient


## 3. Algorithmic Implementation
**Algorithm: Push-Forward $\mathbf{S}\to\boldsymbol{\tau}$ (Symmetric Output)**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{S}\in\mathbb{R}^{3\times 3}_{\mathrm{sym}},\,\mathbf{F}$
\State $\mathbf{T} \gets \mathbf{S}\,\mathbf{F}^T \;(\,T_{Ij} = S_{IK}\,F_{jK}\,)$
\State $\boldsymbol{\tau} \gets \mathbf{F}\,\mathbf{T} \;(\,\tau_{ij} = F_{iI}\,T_{Ij}\,)$
\State $\boldsymbol{\tau} \gets \tfrac{1}{2}(\boldsymbol{\tau} + \boldsymbol{\tau}^T) \;\text{(symmetrise — round-off guard)}$
\Return $\boldsymbol{\tau}$
\end{algorithmic}
$$

**Taichi Mapping:**
`@ti.func` per Gauss point. Two $3\times 3$ matrix multiplies = 54 FMAs. Symmetrise even though it is mathematically symmetric: round-off in $\mathbf{F}$ can produce $\mathcal{O}(10^{-14})$ skew that integrates over many time steps. Reuse the cached $\mathbf{F}$ from the deformation-gradient computation — do not recompute it.


**Algorithm: Pull-Back $\boldsymbol{\sigma}\to\mathbf{S}$**

$$
\begin{algorithmic}
\State $\text{input} \colon \boldsymbol{\sigma}\in\mathbb{R}^{3\times 3}_{\mathrm{sym}},\,\mathbf{F},\,J$
\State $\mathbf{F}^{-1} \gets \mathrm{cofactor\;inverse}(\mathbf{F})$
\State $\mathbf{T} \gets \boldsymbol{\sigma}\,\mathbf{F}^{-T}$
\State $\mathbf{S} \gets J\,\mathbf{F}^{-1}\,\mathbf{T}$
\State $\mathbf{S} \gets \tfrac{1}{2}(\mathbf{S} + \mathbf{S}^T)$
\Return $\mathbf{S}$
\end{algorithmic}
$$

**Taichi Mapping:**
Use after a UL-FEM constitutive update where $\boldsymbol{\sigma}$ is the natural output but the FEM residual lives on the reference configuration. Cache $\mathbf{F}^{-1}$; reuse for the corresponding tangent push-forward. For total-Lagrangian codes the pull-back is rarely needed inside the loop because $\mathbf{S}$ is computed directly.


**Algorithm: Lie Rate via Pull-Back / Push-Forward**

$$
\begin{algorithmic}
\State $\text{input} \colon \boldsymbol{\tau}_n,\boldsymbol{\tau}_{n+1},\mathbf{F}_n,\mathbf{F}_{n+1},\Delta t$
\State $\mathbf{S}_n \gets \mathbf{F}_n^{-1}\,\boldsymbol{\tau}_n\,\mathbf{F}_n^{-T}$
\State $\mathbf{S}_{n+1} \gets \mathbf{F}_{n+1}^{-1}\,\boldsymbol{\tau}_{n+1}\,\mathbf{F}_{n+1}^{-T}$
\State $\dot{\mathbf{S}} \gets (\mathbf{S}_{n+1} - \mathbf{S}_n)/\Delta t$
\State $\mathcal{L}_v\,\boldsymbol{\tau} \gets \mathbf{F}_{n+1}\,\dot{\mathbf{S}}\,\mathbf{F}_{n+1}^T$
\Return $\mathcal{L}_v\,\boldsymbol{\tau}$
\end{algorithmic}
$$

**Taichi Mapping:**
Use this construction to verify that the spatial rate $\dot{\boldsymbol{\tau}}-\mathbf{L}\boldsymbol{\tau}-\boldsymbol{\tau}\mathbf{L}^T$ matches the constructed Lie rate to round-off — a strong diagnostic for objective-rate kernels. In production prefer the spatial form (one matrix algebra rather than four pull-backs / push-forwards), but keep this routine as a unit test.



## 4. Known Pitfalls
**Applying kinematic rule $\mathbf{F}^{-T}(\bullet)\mathbf{F}^{-1}$ to stress:** Stress is kinetic; using the kinematic rule on it (swapping $\mathbf{F}^{-T},\mathbf{F}^{-1}$ for $\mathbf{F},\mathbf{F}^T$) silently destroys $\boldsymbol{\tau}\colon\mathbf{D}=\mathbf{S}\colon\dot{\mathbf{E}}$ conjugacy and gives a numerically symmetric tensor that is the wrong stress. Symptom: integrated mechanical power in the global energy balance does not match the work of external loads.


**Wrong index order in $\mathbf{F}\mathbf{S}\mathbf{F}^T$:** $\tau_{ij}=F_{iI}F_{jJ}S_{IJ}$. Swapping to $F_{Ii}$ etc. (using $\mathbf{F}^T$ instead of $\mathbf{F}$) silently produces a transposed tangent that still has the right symmetries and passes minor consistency checks but is not $\boldsymbol{\tau}$. Always derive in indicial form and verify $\mathrm{tr}\,\boldsymbol{\tau}=J\,\mathrm{tr}\,\boldsymbol{\sigma}$ on a uniaxial benchmark.


**Dropping the $J$ factor between $\boldsymbol{\sigma}$ and $\boldsymbol{\tau}$:** $\boldsymbol{\tau}=J\boldsymbol{\sigma}$, NOT $\boldsymbol{\tau}=\boldsymbol{\sigma}$. The push-forward of $\mathbf{S}$ goes to $\boldsymbol{\tau}$, not to $\boldsymbol{\sigma}$ — recovering Cauchy requires an extra division by $J$. Forgetting the $J$ rescaling reports a stress wrong by $J$ on the deformed mesh (significant once $J\ne 1$).


**Push-forward of $\mathbf{S}$ is $\boldsymbol{\tau}$ not $\boldsymbol{\sigma}$:** A common slip: writing "push-forward of PK2 = Cauchy" instead of "= Kirchhoff". The composition $\boldsymbol{\sigma}=J^{-1}\mathbf{F}\mathbf{S}\mathbf{F}^T$ is the push-forward followed by Kirchhoff-to-Cauchy rescaling — TWO operations. Treating it as a single push-forward formula causes the $J^{-1}$ factor to be absorbed elsewhere by mistake.


**Round-off skew in $\boldsymbol{\tau}$ from non-symmetric $\mathbf{F}\mathbf{S}\mathbf{F}^T$:** Even with $\mathbf{S}$ exactly symmetric, $\mathbf{F}\mathbf{S}\mathbf{F}^T$ in floating-point introduces $\mathcal{O}(10^{-14})$ skew. Symmetrise $\boldsymbol{\tau}\to\tfrac12(\boldsymbol{\tau}+\boldsymbol{\tau}^T)$ before storing; otherwise the skew accumulates over many Newton iterations and breaks angular-momentum balance.


**Naive Voigt $6\times 6$ push-forward:** $\boldsymbol{\tau}=\mathbf{F}\mathbf{S}\mathbf{F}^T$ in Voigt form is NOT $\{F\}_{6\times 6}\{S\}_{6\times 1}$ — the two-point structure of $\mathbf{F}$ does not survive the symmetric flatten. Either revert to indicial form for the push-forward or build a specialised $6\times 6$ kinetic-Voigt operator $\mathbf{T}_\sigma(\mathbf{F})$ that respects the kinetic rule. See `tensor-voigt-notation` pitfalls for details.


**Using $\dot{\boldsymbol{\tau}}$ in a constitutive law:** $\dot{\boldsymbol{\tau}}$ is NOT objective: under a rigid-body rotation it picks up $\mathbf{L}\boldsymbol{\tau}+\boldsymbol{\tau}\mathbf{L}^T$ contributions. Constitutive laws must use $\mathcal{L}_v\boldsymbol{\tau}=\dot{\boldsymbol{\tau}}-\mathbf{L}\boldsymbol{\tau}-\boldsymbol{\tau}\mathbf{L}^T$ (the convected / Truesdell rate). Substituting $\dot{\boldsymbol{\tau}}$ produces oscillating shear stress under simple shear (`kinematics-objective-rates`).


## 5. References
- Belytschko, Liu, Moran & Elkhodary (2014) — Nonlinear Finite Elements for Continua and Structures, 2nd ed. (push-forward / pull-back of stress, Piola transformation, conjugacy of $\boldsymbol{\tau}\colon\mathbf{D}=\mathbf{S}\colon\dot{\mathbf{E}}$)
- Holzapfel (2000) — Nonlinear Solid Mechanics (kinetic vs kinematic push-forward, Lie derivative, convected rate)
- de Borst, Crisfield, Remmers & Verhoosel (2012) — Nonlinear Finite Element Analysis of Solids and Structures, 2nd ed. (Piola transformation in TL / UL FEM)

