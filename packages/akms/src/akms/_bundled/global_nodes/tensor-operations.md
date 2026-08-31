---
id: tensor-operations
title: Push-Forward, Pull-Back & Tensor Transformations
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- tensors
- continuum-mechanics
- push-forward
- pull-back
status: established
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: kinematics-strain-tensors
  type: feeds-into
  weight: 1.0
  note: Provides transformation rules used to relate Lagrangian and Eulerian deformation measures (E vs e, C vs b)
- to: kinematics-objective-rates
  type: feeds-into
  weight: 0.9
  note: Lie derivative (= push-forward of d/dt of pull-back) is the mathematical basis for objective stress rates
- to: fem-tl-weak-form
  type: feeds-into
  weight: 0.8
  note: Total-Lagrangian FEM requires PK2<->Kirchhoff push-forward and tangent moduli transformation
context_size: medium
reading_priority: full
load_with:
- kinematics-strain-tensors
- kinematics-objective-rates
content_ref: null
akms_schema: v2
---

# Push-Forward, Pull-Back & Tensor Transformations

## Summary
Push-forward ($\phi_*$) and pull-back ($\phi^*$) are the fundamental operations that map tensor fields between the reference (Lagrangian) and current (Eulerian) configurations of a deforming body. They are driven by the deformation gradient $F$ and depend on the variance of the tensor: kinematic (covariant–covariant) tensors transform with $F^{-T}(\bullet)F^{-1}$ pushed forward and $F^T(\bullet)F$ pulled back, while kinetic (contravariant–contravariant) tensors transform with $F(\bullet)F^T$ pushed forward and $F^{-1}(\bullet)F^{-T}$ pulled back. The variance pairing is dictated by the requirement that the mechanical power $\boldsymbol{\sigma}\colon\mathbf{D}=\mathbf{S}\colon\dot{\mathbf{E}}$ remain invariant under the transformation. Push-forward of fourth-order tangent moduli applies $F$ index-by-index ($C^\tau_{ijkl}=F_{iM}F_{jN}F_{kP}F_{lQ}\,C^{SE}_{MNPQ}$), and the Lie derivative $\mathcal{L}_v = \phi_*(\partial_t \phi^*(\bullet))$ provides the mathematically consistent objective rate that underlies the convected/Truesdell stress rates.


## 1. Core Concept
In nonlinear continuum mechanics every field defined on the deformed body has a counterpart on the reference body and vice versa. Push-forward and pull-back give the precise algebraic prescription for transporting tensors of any order and variance between these two configurations using the two-point tensor $F = \partial\mathbf{x}/\partial\mathbf{X}$.

The crucial subtlety is that the form of the transformation is not a free choice: it is dictated by the variance of the tensor (covariant indices "live downstairs", contravariant indices "live upstairs") and by the requirement that work-conjugate pairings be preserved. Stress-like (kinetic) objects such as the second Piola-Kirchhoff stress $\mathbf{S}$ and the Kirchhoff stress $\boldsymbol{\tau}$ are contravariant–contravariant; strain-like (kinematic) objects such as the Green strain rate $\dot{\mathbf{E}}$ and the rate-of-deformation $\mathbf{D}$ are covariant–covariant. Mixed objects such as the spatial velocity gradient $\mathbf{L}$ require mixed legs ($F^{-1}$ on the left, $F$ on the right).

Because material time differentiation does not commute with push-forward, the Lie derivative is introduced as the mathematically consistent objective time derivative: pull a spatial tensor back, take its material rate, then push the result forward. This operation produces the Truesdell rate of Cauchy stress and the convected rate of Kirchhoff stress, which are the "natural" stress rates appearing in finite-strain hyperelasticity.


## 2. Mathematical Formulation
Let $\mathbf{X}$ denote a material point in the reference configuration $\Omega_0$ and $\mathbf{x}=\boldsymbol{\phi}(\mathbf{X},t)$ its position in the current configuration $\Omega_t$. The deformation gradient $\mathbf{F} = \partial\mathbf{x}/\partial\mathbf{X}$ is the two-point tensor that drives all transformations. Its determinant $J = \det\mathbf{F}$ is the local volume ratio, and the metric tensor in Euclidean space satisfies $\mathbf{g}=\mathbf{I}$. Push-forward and pull-back are denoted $\phi_*$ and $\phi^*$ respectively, and the rules below are the canonical Belytschko/Borst–Crisfield "Box 5.16" set.


**Vectors — push-forward / pull-back of line elements:**

$$
d\mathbf{x} = \phi_*(d\mathbf{X}) = \mathbf{F} \cdot d\mathbf{X}, \qquad
d\mathbf{X} = \phi^*(d\mathbf{x}) = \mathbf{F}^{-1} \cdot d\mathbf{x}
$$

where $d\mathbf{X}$ is a Lagrangian line element, $d\mathbf{x}$ its image in the current configuration

**Volume transformation:**

$$
dV = J\,dV_0, \qquad J = \det \mathbf{F} = \frac{\rho_0}{\rho}
$$

where $dV_0$ and $dV$ are reference and current infinitesimal volumes; $\rho_0,\rho$ are reference and current densities

**Nanson's formula — area / normals (covector transformation):**

$$
\mathbf{n}\,d\Gamma = J\,\mathbf{F}^{-T} \cdot \mathbf{n}_0\,d\Gamma_0
$$

where $\mathbf{n}_0,d\Gamma_0$ are reference normal and area; $\mathbf{n},d\Gamma$ are their current counterparts

**Kinematic (covariant–covariant) second-order tensors:**

$$
\phi_*(\bullet) = \mathbf{F}^{-T} \cdot (\bullet) \cdot \mathbf{F}^{-1}, \qquad
\phi^*(\bullet) = \mathbf{F}^T \cdot (\bullet) \cdot \mathbf{F}
$$

where Examples — $\mathbf{D} = \phi_*(\dot{\mathbf{E}}) = \mathbf{F}^{-T}\dot{\mathbf{E}}\mathbf{F}^{-1}$, $\dot{\mathbf{E}} = \phi^*(\mathbf{D}) = \mathbf{F}^T \mathbf{D}\, \mathbf{F}$, $\mathbf{C} = \phi^*(\mathbf{g})$

**Kinetic (contravariant–contravariant) second-order tensors:**

$$
\phi_*(\bullet) = \mathbf{F} \cdot (\bullet) \cdot \mathbf{F}^T, \qquad
\phi^*(\bullet) = \mathbf{F}^{-1} \cdot (\bullet) \cdot \mathbf{F}^{-T}
$$

where Examples — $\boldsymbol{\tau} = \phi_*(\mathbf{S}) = \mathbf{F}\mathbf{S}\mathbf{F}^T$, $\mathbf{S} = \phi^*(\boldsymbol{\tau}) = \mathbf{F}^{-1}\boldsymbol{\tau}\,\mathbf{F}^{-T}$

**Mixed (contravariant–covariant) tensors:**

$$
\phi^*(\mathbf{L}) = \mathbf{F}^{-1} \cdot \mathbf{L} \cdot \mathbf{F}, \qquad
\phi_*(\widetilde{\mathbf{L}}) = \mathbf{F} \cdot \widetilde{\mathbf{L}} \cdot \mathbf{F}^{-1}
$$

where $\mathbf{L} = \dot{\mathbf{F}}\mathbf{F}^{-1}$ is the spatial velocity gradient; $\mathbf{F}^{-1}$ acts on the contravariant (left) leg, $\mathbf{F}$ on the covariant (right) leg

**Push-forward of fourth-order elasticity tensor (index-by-index):**

$$
C^{\tau}_{ijkl} = F_{iM}\,F_{jN}\,F_{kP}\,F_{lQ}\,C^{SE}_{MNPQ}
$$

where $C^{SE}_{MNPQ}$ are material tangent moduli (a.k.a. $A^{(2)}$); $C^{\tau}_{ijkl}$ are spatial tangent moduli (a.k.a. $A^{(4)}$). Lower-case indices are spatial, upper-case material; summation convention applies

**Lie derivative — mathematically consistent objective rate:**

$$
\mathcal{L}_v(\bullet) = \phi_*\!\left(\frac{D}{Dt}\,\phi^*(\bullet)\right)
$$

where $D/Dt$ is the material time derivative (holding $\mathbf{X}$ fixed); $\mathcal{L}_v$ commutes with push-forward by construction

**Lie derivative of Kirchhoff stress = convected / Truesdell rate:**

$$
\mathcal{L}_v\boldsymbol{\tau} = \mathbf{F} \cdot \dot{\mathbf{S}} \cdot \mathbf{F}^T
= \dot{\boldsymbol{\tau}} - \mathbf{L}\cdot\boldsymbol{\tau} - \boldsymbol{\tau}\cdot\mathbf{L}^T
\equiv \boldsymbol{\tau}^{\nabla c}
$$

where $\dot{\boldsymbol{\tau}}$ is non-objective; subtraction of $\mathbf{L}\boldsymbol{\tau}+\boldsymbol{\tau}\mathbf{L}^T$ removes spurious rotation/stretch contributions

**Lie derivative of spatial metric:**

$$
\mathcal{L}_v\,\mathbf{g} = \mathbf{F}^{-T}\cdot\dot{\mathbf{C}}\cdot\mathbf{F}^{-1} = 2\mathbf{D}
$$

where Recovers the rate-of-deformation as the kinematic Lie derivative of the metric

**Power conjugacy invariance (motivates the variance rules):**

$$
\boldsymbol{\tau} \colon \mathbf{D}
= \big(\mathbf{F}\mathbf{S}\mathbf{F}^T\big) \colon \big(\mathbf{F}^{-T}\dot{\mathbf{E}}\mathbf{F}^{-1}\big)
= \mathbf{S} \colon \dot{\mathbf{E}}
$$

where Confirms that the kinetic / kinematic pairing is the unique choice preserving stress-power

**Notation:**

- $\mathbf{F}$ — Deformation gradient, two-point tensor with $F_{iI} = \partial x_i/\partial X_I$
- $\mathbf{F}^T$ — Transpose of $\mathbf{F}$
- $\mathbf{F}^{-1}$ — Inverse of $\mathbf{F}$
- $\mathbf{F}^{-T}$ — Inverse transpose, $(\mathbf{F}^{-1})^T$
- $J$ — Jacobian determinant, $J=\det\mathbf{F}$, equals the volume ratio $dV/dV_0$
- $\phi_*$ — Push-forward operator (reference $\to$ current configuration)
- $\phi^*$ — Pull-back operator (current $\to$ reference configuration)
- $\mathbf{S}$ — Second Piola-Kirchhoff stress (Lagrangian, kinetic)
- $\boldsymbol{\tau}$ — Kirchhoff stress, $\boldsymbol{\tau}=J\boldsymbol{\sigma}$ (Eulerian, kinetic)
- $\boldsymbol{\sigma}$ — Cauchy stress (Eulerian)
- $\mathbf{P}$ — Nominal (first Piola-Kirchhoff) stress, two-point tensor
- $\dot{\mathbf{E}}$ — Material time derivative of Green-Lagrange strain (Lagrangian, kinematic)
- $\mathbf{D}$ — Rate-of-deformation tensor, $\mathbf{D}=\tfrac12(\mathbf{L}+\mathbf{L}^T)$ (Eulerian, kinematic)
- $\mathbf{L}$ — Spatial velocity gradient, $\mathbf{L}=\dot{\mathbf{F}}\mathbf{F}^{-1}$ (mixed variance)
- $\mathbf{C}$ — Right Cauchy-Green tensor, $\mathbf{C}=\mathbf{F}^T\mathbf{F}$
- $\mathbf{g}$ — Spatial metric tensor (= $\mathbf{I}$ in Euclidean space)
- $\mathbf{n}_0,\mathbf{n}$ — Outward unit normals on reference / current surfaces
- $d\Gamma_0,d\Gamma$ — Reference / current infinitesimal area elements
- $C^{SE}_{MNPQ}$ — Material tangent stiffness tensor ($\partial \mathbf{S}/\partial \mathbf{E}$)
- $C^{\tau}_{ijkl}$ — Spatial tangent stiffness tensor (push-forward of $C^{SE}$)
- $\mathcal{L}_v$ — Lie derivative along the spatial velocity field $\mathbf{v}$
- $D/Dt$ — Material time derivative (partial with $\mathbf{X}$ held fixed)


## 3. Algorithmic Implementation
**Algorithm: Push-Forward of Second Piola-Kirchhoff Stress to Kirchhoff Stress**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{S} \in \mathbb{R}^{3\times 3},\; \mathbf{F} \in \mathbb{R}^{3\times 3}$
\State $\mathbf{T} \gets \mathbf{S} \cdot \mathbf{F}^{T} \quad (T_{Ij} = S_{IK}\,F_{jK})$
\State $\boldsymbol{\tau} \gets \mathbf{F} \cdot \mathbf{T} \quad (\tau_{ij} = F_{iI}\,T_{Ij})$
\Return $\boldsymbol{\tau}$
\end{algorithmic}
$$

**Algorithm: Pull-Back of Rate-of-Deformation to Rate of Green Strain**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{D} \in \mathbb{R}^{3\times 3},\; \mathbf{F} \in \mathbb{R}^{3\times 3}$
\State $\mathbf{T} \gets \mathbf{D} \cdot \mathbf{F} \quad (T_{iJ} = D_{ik}\,F_{kJ})$
\State $\dot{\mathbf{E}} \gets \mathbf{F}^{T} \cdot \mathbf{T} \quad (\dot{E}_{IJ} = F_{iI}\,T_{iJ})$
\Return $\dot{\mathbf{E}}$
\end{algorithmic}
$$

**Algorithm: Index-by-Index Push-Forward of Fourth-Order Tangent (C^SE -> C^tau)**

$$
\begin{algorithmic}
\State $\text{input} \colon C^{SE} \in \mathbb{R}^{3\times3\times3\times3},\; \mathbf{F} \in \mathbb{R}^{3\times3}$
\For{$i,N,P,Q = 1,\ldots,3$}
\State $H^{(1)}_{iNPQ} \gets \sum_{M=1}^{3} F_{iM}\,C^{SE}_{MNPQ}$
\EndFor
\For{$i,j,P,Q = 1,\ldots,3$}
\State $H^{(2)}_{ijPQ} \gets \sum_{N=1}^{3} F_{jN}\,H^{(1)}_{iNPQ}$
\EndFor
\For{$i,j,k,Q = 1,\ldots,3$}
\State $H^{(3)}_{ijkQ} \gets \sum_{P=1}^{3} F_{kP}\,H^{(2)}_{ijPQ}$
\EndFor
\For{$i,j,k,l = 1,\ldots,3$}
\State $C^{\tau}_{ijkl} \gets \sum_{Q=1}^{3} F_{lQ}\,H^{(3)}_{ijkQ}$
\EndFor
\Return $C^{\tau}$
\end{algorithmic}
$$

**Algorithm: Lie Derivative of Kirchhoff Stress (= convected/Truesdell rate)**

$$
\begin{algorithmic}
\State $\text{input} \colon \boldsymbol{\tau}_n,\boldsymbol{\tau}_{n+1} \in \mathbb{R}^{3\times 3},\; \mathbf{L} \in \mathbb{R}^{3\times 3},\; \Delta t > 0$
\State $\dot{\boldsymbol{\tau}} \gets (\boldsymbol{\tau}_{n+1} - \boldsymbol{\tau}_n)/\Delta t$
\State $\mathcal{L}_v\boldsymbol{\tau} \gets \dot{\boldsymbol{\tau}} - \mathbf{L}\cdot\boldsymbol{\tau}_{n+1} - \boldsymbol{\tau}_{n+1}\cdot\mathbf{L}^{T}$
\Return $\mathcal{L}_v\boldsymbol{\tau}$
\end{algorithmic}
$$

## 4. Known Pitfalls
**Confusing kinetic and kinematic transformations:** Applying the kinetic rule $\mathbf{F}(\bullet)\mathbf{F}^T$ to a strain-like quantity (or the kinematic rule $\mathbf{F}^{-T}(\bullet)\mathbf{F}^{-1}$ to a stress) silently destroys work conjugacy. The integrated mechanical power $\int\boldsymbol{\sigma}\colon\mathbf{D}\,dV$ then no longer matches $\int\mathbf{S}\colon\dot{\mathbf{E}}\,dV_0$, energy is created or lost, and convergence in finite-strain Newton iterations degrades or stalls. Rule of thumb: stresses (PK2, $\boldsymbol{\tau}$) push forward with $\mathbf{F}$ on the outside; strains (Green strain, $\mathbf{C}$) pull back with $\mathbf{F}^T$ on the outside.


**Loss of work conjugacy under sloppy mixed transformations:** Velocity-gradient-like (mixed-variance) tensors require $\mathbf{F}^{-1}$ on the contravariant leg and $\mathbf{F}$ on the covariant leg, NOT a sandwich of identical operators. A common mistake is treating $\mathbf{L}$ as either purely kinematic or purely kinetic; both choices break the multiplicative split $\mathbf{L}=\mathbf{L}^e+\mathbf{L}^p$ that elastoplastic codes rely on.


**Element inversion / vanishing det(F):** Push-forward and pull-back rely on $\mathbf{F}^{-1}$ and $1/J$. Near element inversion ($J\to 0^+$) or full inversion ($J<0$) these become numerically singular and produce NaN tangent moduli that propagate through Newton iterations. Check that $J$ remains admissible before transforming, and never blindly invert $\mathbf{F}$.


**Index ordering errors in fourth-order push-forward:** The contraction $C^{\tau}_{ijkl} = F_{iM}F_{jN}F_{kP}F_{lQ}\,C^{SE}_{MNPQ}$ requires that the spatial index appears on the left of each $F$ and the material index on the right. Swapping to $F_{Mi}$ etc. (using $\mathbf{F}^T$ instead of $\mathbf{F}$) silently produces a transposed tangent that still has the right symmetries and passes minor consistency checks but yields a wrong stiffness matrix — typically detectable only via a finite-difference verification of the global tangent.


**Lie derivative confused with the material time derivative:** The bare material time derivative $\dot{\boldsymbol{\tau}} = \partial\boldsymbol{\tau}/\partial t |_{\mathbf{X}}$ is NOT objective — under a rigid-body rotation it picks up spurious $\boldsymbol{\Omega}\boldsymbol{\tau}-\boldsymbol{\tau}\boldsymbol{\Omega}$ terms. Constitutive laws must be written in terms of $\mathcal{L}_v\boldsymbol{\tau}$ (or the equivalent Truesdell/Jaumann/Green-Naghdi rates, see `kinematics-objectivity`). Using $\dot{\boldsymbol{\tau}}$ directly in a hyperelastic update produces stress oscillations under simple shear and rotates the principal axes incorrectly under rigid spin.


**Voigt notation gotchas for kinetic vs kinematic tensors:** Belytschko's Appendix 1 defines two Voigt rules: the kinematic rule multiplies shear strains by 2 (so $\dot{E}_4 = 2\dot{E}_{23}$, etc.), the kinetic rule does not. When pushing forward a fourth-order tangent stored as a $6\times 6$ Voigt matrix, the strain-like factors and stress-like factors must use opposite Voigt conventions or the resulting tangent is wrong by factors of 2 / 4 in shear blocks. Either convert back to indicial form before transforming, or carry an explicit $\mathbf{T}_{\text{kin}}$ / $\mathbf{T}_{\text{kit}}$ Voigt-mapping matrix and apply $C^{\tau}_{6\times 6} = \mathbf{T}_{\text{kit}}\,C^{SE}_{6\times 6}\,\mathbf{T}_{\text{kit}}^T$ (kinetic Voigt) consistently.


**Symmetry on Nyquist / boundary indices not preserved:** $C^{\tau}$ inherits the major and minor symmetries of $C^{SE}$ only if the index-by-index contraction is carried out exactly. Truncation/Voigt tricks can break the minor symmetry $C^{\tau}_{ijkl}=C^{\tau}_{jikl}$, which then violates angular momentum balance at the element level. Always verify $\|C^{\tau}_{ijkl}-C^{\tau}_{jikl}\|/\|C^{\tau}\| < 10^{-12}$ on a unit-cell test.


## 5. References
- Belytschko, Liu, Moran & Elkhodary (2014) — Nonlinear Finite Elements for Continua and Structures, 2nd ed. (transformations between stresses; rate-of-deformation pull-back; elasticity tensors and Voigt form; push-forward / pull-back / Lie derivative)
- de Borst, Crisfield, Remmers & Verhoosel (2012) — Nonlinear Finite Element Analysis of Solids and Structures, 2nd ed. (deformation gradient, Jacobian, volume transformation)
