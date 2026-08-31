---
id: kinematics-motion-deformation-gradient
title: Motion & Deformation Gradient
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- continuum-mechanics
- deformation-gradient
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: tensor-index-notation
  type: requires
  weight: 0.8
  note: $F_{iJ}=\partial x_i/\partial X_J$ uses one spatial (lower-case) and one material (upper-case) index
- to: kinematics-strain-tensors
  type: feeds-into
  weight: 1.0
  note: All Seth-Hill strains derive from $\mathbf{C}=\mathbf{F}^T\mathbf{F}$ or $\mathbf{b}=\mathbf{F}\mathbf{F}^T$
- to: kinematics-polar-decomposition
  type: feeds-into
  weight: 1.0
  note: $\mathbf{F}=\mathbf{R}\mathbf{U}=\mathbf{V}\mathbf{R}$ separates rigid rotation from stretch
- to: kinematics-velocity-gradient
  type: feeds-into
  weight: 1.0
  note: Spatial velocity gradient $\mathbf{L}=\dot{\mathbf{F}}\mathbf{F}^{-1}$
- to: fem-tl-b-matrix
  type: feeds-into
  weight: 0.9
  note: B-matrix builds $\mathbf{F}$ from nodal displacements via shape function gradients
context_size: medium
reading_priority: full
load_with:
- kinematics-strain-tensors
- kinematics-velocity-gradient
content_ref: null
akms_schema: v2
---

# Motion & Deformation Gradient

## Summary
The motion of a body is the smooth one-parameter family of mappings $\mathbf{x}=\boldsymbol{\phi}(\mathbf{X},t)$ that takes each material point $\mathbf{X}$ in the reference configuration to its current position $\mathbf{x}$. Its material gradient is the deformation gradient $\mathbf{F}=\partial\mathbf{x}/\partial\mathbf{X}$ — an Eulerian-Lagrangian two-point tensor with components $F_{iJ}=\partial x_i/\partial X_J$ (lower-case spatial, upper-case material). $\mathbf{F}$ maps line elements ($d\mathbf{x}=\mathbf{F}\,d\mathbf{X}$), and via Nanson's formula $\mathbf{n}\,da = J\,\mathbf{F}^{-T}\mathbf{n}_0\,dA_0$ it maps oriented areas. The Jacobian $J=\det\mathbf{F}=dv/dV_0=\rho_0/\rho$ is the local volume ratio and must remain strictly positive ($J>0$) to keep the mapping invertible. Rate $\dot{\mathbf{F}}=\mathbf{L}\mathbf{F}$ links to the velocity gradient; in FEM $\mathbf{F}$ is built per element from nodal displacements via the B-matrix.


## 1. Core Concept
$\mathbf{F}$ is the central kinematic object in nonlinear solid mechanics. Geometrically it is the linearisation of the motion at a material point: line elements transform linearly via $d\mathbf{x}=\mathbf{F}\,d\mathbf{X}$, areas by Nanson's formula, and volumes by the scalar $J=\det\mathbf{F}$. Because $\mathbf{F}$ has one leg in the reference configuration and one in the current configuration, it is a TWO-POINT tensor — its row index is spatial (lower-case $i$), its column index is material (upper-case $J$) — and operations like push-forward / pull-back, polar decomposition, and the multiplicative split $\mathbf{F}=\mathbf{F}^e\mathbf{F}^p$ all hinge on respecting that asymmetry. In a finite element, $\mathbf{F}$ is reconstructed at each Gauss point from the displacement field $\mathbf{u}=\mathbf{x}-\mathbf{X}$ via shape function gradients ($\mathbf{H}=\partial\mathbf{u}/\partial\mathbf{X}$, $\mathbf{F}=\mathbf{I}+\mathbf{H}$); this construction underlies every TL-FEM weak-form derivation and every B-matrix formulation.


## 2. Mathematical Formulation
Reference coordinates $\mathbf{X}$ live in the undeformed body $\Omega_0$, current coordinates $\mathbf{x}$ in $\Omega_t$. The motion is $\mathbf{x}=\boldsymbol{\phi}(\mathbf{X},t)$, smooth in both arguments. Lower-case Latin indices ($i,j,k$) are spatial; upper-case ($I,J,K$) are material; both run over $\{1,2,3\}$. Velocity is $\mathbf{v}(\mathbf{X},t)=\partial\boldsymbol{\phi}/\partial t$.


**Motion and deformation gradient:**

$$
\mathbf{x} = \boldsymbol{\phi}(\mathbf{X},t),\qquad
\mathbf{F} = \frac{\partial \mathbf{x}}{\partial \mathbf{X}} = \nabla_0\boldsymbol{\phi},\qquad
F_{iJ} = \frac{\partial x_i}{\partial X_J}
$$

where Two-point tensor with mixed Eulerian-Lagrangian indices

**Line, area, and volume transforms:**

$$
d\mathbf{x} = \mathbf{F}\cdot d\mathbf{X},\qquad
\mathbf{n}\,da = J\,\mathbf{F}^{-T}\cdot\mathbf{n}_0\,dA_0,\qquad
dv = J\,dV_0
$$

where Nanson's formula for oriented area; $J=\det\mathbf{F}$ for volume

**Jacobian and admissibility:**

$$
J = \det\mathbf{F} = \frac{dv}{dV_0} = \frac{\rho_0}{\rho},\qquad
J > 0
$$

where $J>0$ keeps the mapping one-to-one and orientation-preserving

**From displacement:**

$$
\mathbf{u}(\mathbf{X},t) = \mathbf{x} - \mathbf{X},\qquad
\mathbf{H} = \nabla_0 \mathbf{u} = \frac{\partial \mathbf{u}}{\partial \mathbf{X}},\qquad
\mathbf{F} = \mathbf{I} + \mathbf{H}
$$

where $\mathbf{H}$ is the displacement gradient; $\mathbf{F}\to\mathbf{I}$ in the small-strain limit

**Time rate and velocity gradient:**

$$
\dot{\mathbf{F}} = \frac{\partial \mathbf{F}}{\partial t}\bigg|_{\mathbf{X}} = \mathbf{L}\,\mathbf{F},\qquad
\mathbf{L} = \dot{\mathbf{F}}\,\mathbf{F}^{-1} = \nabla \mathbf{v}
$$

where $\mathbf{L}$ is the spatial velocity gradient (`kinematics-velocity-gradient`)

**Inverse and identity:**

$$
\mathbf{F}\cdot\mathbf{F}^{-1} = \mathbf{I},\qquad
\mathbf{F}^{-T} = (\mathbf{F}^T)^{-1} = (\mathbf{F}^{-1})^T,\qquad
F^{-1}_{Ji} = \frac{\partial X_J}{\partial x_i}
$$

where $\mathbf{F}^{-1}$ is the material gradient of the INVERSE motion $\mathbf{X}=\boldsymbol{\phi}^{-1}(\mathbf{x},t)$

**Polar decomposition (referenced):**

$$
\mathbf{F} = \mathbf{R}\,\mathbf{U} = \mathbf{V}\,\mathbf{R},\qquad
\mathbf{R}\in SO(3),\;
\mathbf{U}=\mathbf{U}^T\succ 0
$$

where Detail in `kinematics-polar-decomposition`

**Mass conservation:**

$$
\rho_0 = J\,\rho,\qquad
\int_{\Omega_0}\rho_0\,dV_0 = \int_{\Omega_t}\rho\,dv
$$

where Trivial consequence of the volume transform

**Notation:**

- $\mathbf{X}$ — Reference (Lagrangian) position vector
- $\mathbf{x}$ — Current (Eulerian) position vector
- $\boldsymbol{\phi}$ — Motion mapping, $\mathbf{x}=\boldsymbol{\phi}(\mathbf{X},t)$
- $\mathbf{F}$ — Deformation gradient, $\mathbf{F}=\partial\mathbf{x}/\partial\mathbf{X}$
- $F_{iJ}$ — Component, lower-case spatial $i$ and upper-case material $J$
- $J$ — Jacobian, $J=\det\mathbf{F}>0$
- $\mathbf{H}$ — Displacement gradient $\mathbf{H}=\nabla_0\mathbf{u}$
- $\mathbf{u}$ — Displacement field, $\mathbf{u}=\mathbf{x}-\mathbf{X}$
- $\mathbf{L}$ — Spatial velocity gradient, $\mathbf{L}=\dot{\mathbf{F}}\mathbf{F}^{-1}$
- $\rho_0,\rho$ — Reference and current mass densities


## 3. Algorithmic Implementation
**Algorithm: Compute $\mathbf{F}$ at a Gauss Point from Nodal Displacements**

$$
\begin{algorithmic}
\State $\text{input} \colon \{\mathbf{u}_a\}_{a=1}^{n_n},\,\{\partial N_a/\partial \mathbf{X}\}_{a=1}^{n_n} \;\text{at the GP}$
\State $\mathbf{H} \gets \mathbf{0} \in \mathbb{R}^{3\times 3}$
\For{$a = 1,\ldots,n_n$}
\For{$i,J = 1,2,3$}
\State $H_{iJ} \mathrel{+}= u_{a,i}\,(\partial N_a/\partial X_J)$
\EndFor
\EndFor
\State $\mathbf{F} \gets \mathbf{I} + \mathbf{H}$
\State $J \gets \det\mathbf{F}$
\If{$J \le J_{\min}$}
\State $\text{trigger element-inversion handler (line search / step bisection / abort)}$
\EndIf
\Return $\mathbf{F},\,J,\,\mathbf{H}$
\end{algorithmic}
$$

**Taichi Mapping:**
Implement as a `@ti.func` per Gauss point. Pre-compute $\partial N_a/\partial \mathbf{X}$ once per element at the start of the step (cheap because reference geometry is fixed in TL-FEM). Use `ti.static(range(n_n))` to fully unroll the node loop for fixed-element kernels. Build $\mathbf{F}=\mathbf{I}+\mathbf{H}$ rather than directly summing into $\mathbf{F}$: this avoids massive cancellation at small strain (round-off pitfall).


**Algorithm: Closed-Form 3x3 Inverse and Determinant**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{F}\in\mathbb{R}^{3\times 3}$
\State $\mathrm{cof}_{ij}\mathbf{F} \gets \tfrac{1}{2}\,e_{ikl}\,e_{jmn}\,F_{km}\,F_{ln}$
\State $J \gets F_{1i}\,(\mathrm{cof}\,\mathbf{F})_{1i} \;\text{(co-factor expansion)}$
\State $\mathbf{F}^{-1} \gets (\mathrm{cof}\,\mathbf{F})^T / J$
\Return $J,\,\mathbf{F}^{-1}$
\end{algorithmic}
$$

**Taichi Mapping:**
Hand-coded $3\times 3$ inverse outperforms `ti.linalg.inverse` (which targets generic dimensions). Reuse the cofactor matrix for $\partial(\det\mathbf{F})/\partial\mathbf{F} = (\det\mathbf{F})\,\mathbf{F}^{-T}$. For TL-FEM the inverse is rarely needed inside the constitutive update — most quantities work with $\mathbf{F}$ directly — but it IS needed for the spatial velocity gradient $\mathbf{L}$ and for stress push-forward.


**Algorithm: Nanson's Formula for Oriented-Area Pull-Back**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{n}_0\,\text{(reference normal)},\;dA_0\,\text{(reference area)},\;\mathbf{F},\;J$
\State $\mathbf{N} \gets J\,\mathbf{F}^{-T}\cdot\mathbf{n}_0$
\State $da \gets \|\mathbf{N}\|,\;\mathbf{n} \gets \mathbf{N}/da$
\Return $\mathbf{n},\,da$
\end{algorithmic}
$$

**Taichi Mapping:**
Boundary integrals over deformed surfaces use Nanson directly: traction $\mathbf{t}\,da = \boldsymbol{\sigma}\cdot\mathbf{n}\,da = \boldsymbol{\sigma}\cdot J\mathbf{F}^{-T}\mathbf{n}_0\,dA_0 = \mathbf{P}\cdot\mathbf{n}_0\,dA_0$, recovering the nominal stress. Run on every boundary Gauss point each step; cache $J\mathbf{F}^{-T}$ between volumetric and surface kernels.



## 4. Known Pitfalls
**$J\to 0$ element inversion:** Element distortion drives $J\to 0$, which makes $\mathbf{F}^{-1}$ singular and corrupts every push-forward / pull-back / polar decomposition. Set $J_{\min}\sim 10^{-3}$, detect $J<J_{\min}$ before any operation that uses $\mathbf{F}^{-1}$, and either (a) abort the increment, (b) reduce the time step, (c) activate $\bar F$ / locking remedies, or (d) signal the global Newton solver. Never silently continue.


**Mismatched material vs spatial indices in $F_{iJ}$:** Treating $\mathbf{F}$ as a square $3\times 3$ matrix and forgetting that the row index is spatial while the column index is material is the most common source of subtle bugs in finite-strain FEM. Operations like $\mathbf{F}^T\mathbf{F}=\mathbf{C}$ (material), $\mathbf{F}\mathbf{F}^T=\mathbf{b}$ (spatial), and $\mathbf{F}^{-T}\mathbf{n}_0$ (Nanson) only work because the legs match. Tag every kernel argument with `_ref` / `_curr` indicating its leg.


**Volumetric locking from mishandled $\nabla\det\mathbf{F}$:** For nearly-incompressible materials ($J\to 1$) the standard B-matrix produces overly stiff response (volumetric locking). Remedies — $\bar F$ (constant volumetric part per element), F-bar, mixed u/p formulations — modify how $\det\mathbf{F}$ enters the energy / stress. Implementing them requires careful bookkeeping of the volumetric vs deviatoric parts of $\mathbf{F}$; mistakes either reintroduce locking or break consistency of the consistent tangent.


**Round-off when computing $\mathbf{E}$ directly from $\mathbf{F}^T\mathbf{F}$:** For small strains $\mathbf{F}^T\mathbf{F}-\mathbf{I}$ involves the difference of two near-equal $\mathcal{O}(1)$ quantities, with $\mathcal{O}(\|\mathbf{H}\|)$ result and $\mathcal{O}(\epsilon_\mathrm{mach})$ noise from cancellation. Compute $\mathbf{E}=\tfrac12(\mathbf{H}+\mathbf{H}^T+\mathbf{H}^T\mathbf{H})$ from the displacement gradient instead — same $\mathbf{E}$, no catastrophic cancellation.


**Forgetting $\mathbf{F}$ is not symmetric:** $\mathbf{F}$ is generally NOT symmetric — under a pure rotation $\mathbf{F}=\mathbf{R}$ which is orthogonal but not symmetric. Storing only 6 components (the symmetric-tensor convention) loses the rotation information; operating on $\mathbf{F}$ with kinetic / kinematic Voigt rules silently drops half the information. Store $\mathbf{F}$ as a full $3\times 3$ matrix (9 components) at every quadrature point.


**Confusing material time derivative with partial derivative:** $\dot{\mathbf{F}}=(\partial\mathbf{F}/\partial t)|_{\mathbf{X}}$ — derivative at fixed material point. The Eulerian partial derivative $(\partial\mathbf{F}/\partial t)|_{\mathbf{x}}$ differs by $-\mathbf{F}\,\mathbf{L}\cdot\mathbf{x}$ contributions and is not a useful quantity for material laws. Use the material time derivative everywhere in TL-FEM and label time-derivative routines accordingly.


**Accumulation drift in explicit $\mathbf{F}$ integration:** Updating $\mathbf{F}_{n+1}=\mathbf{F}_n+\Delta t\,\dot{\mathbf{F}}_n=\mathbf{F}_n+\Delta t\,\mathbf{L}_n\mathbf{F}_n$ accumulates drift from $\det\mathbf{F}=1$ in incompressible problems and from $\mathbf{R}\in SO(3)$ in pure rotation. Either project onto admissible manifolds each step (Gram-Schmidt on $\mathbf{R}$, log-volume normalisation on $J$) or use exponential-map updates $\mathbf{F}_{n+1}=\exp(\Delta t\,\mathbf{L}_n)\mathbf{F}_n$ which preserve the structure exactly.


## 5. References
- Belytschko, Liu, Moran & Elkhodary (2014) — Nonlinear Finite Elements for Continua and Structures, 2nd ed. (motion, deformation gradient, Jacobian, Nanson's formula, displacement gradient form, $\bar F$ for locking)
- de Borst, Crisfield, Remmers & Verhoosel (2012) — Nonlinear Finite Element Analysis of Solids and Structures, 2nd ed. (deformation gradient, mass conservation, B-matrix construction)
- Holzapfel (2000) — Nonlinear Solid Mechanics (kinematic foundations, two-point tensor character of $\mathbf{F}$)

