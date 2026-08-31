---
id: kinematics-lie-derivative
title: Lie Derivative & Connection to Objective Rates
domain: computational-mechanics
subdomain: kinematics
tags:
- kinematics
- finite-strain
- continuum-mechanics
- lie-derivative
- objectivity
status: tentative
confidence: 0.9
source: hybrid
confidence_floor: 0.7
edges:
- to: stress-push-forward-pull-back
  type: requires
  weight: 1.0
  note: Lie derivative is the chain pull-back -> d/dt -> push-forward
- to: kinematics-objective-rates
  type: refines
  weight: 1.0
  note: Lie derivative is the unifying framework — Truesdell, Oldroyd, Cotter-Rivlin are Lie derivatives of kinetic / kinematic
    tensors
- to: stress-cauchy-kirchhoff
  type: feeds-into
  weight: 1.0
  note: $\mathcal{L}_v\boldsymbol{\tau}=\mathbf{F}\dot{\mathbf{S}}\mathbf{F}^T$ links Lagrangian PK2 rate to spatial Kirchhoff
    rate
- to: kinematics-velocity-gradient
  type: feeds-into
  weight: 0.8
  note: $\mathcal{L}_v\,\mathbf{g}=2\mathbf{D}$ recovers rate-of-deformation as Lie of metric
context_size: medium
reading_priority: full
load_with:
- kinematics-objective-rates
- stress-push-forward-pull-back
content_ref: null
akms_schema: v2
---

# Lie Derivative & Connection to Objective Rates

## Summary
The Lie derivative of a tensor field $\mathbf{T}$ along the spatial velocity field $\mathbf{v}$ is $\mathcal{L}_v\mathbf{T}=\phi_*\!\left(\frac{D}{Dt}\,\phi^*(\mathbf{T})\right)$ — pull $\mathbf{T}$ back to the reference, take its material time derivative there, then push forward to the current configuration. The construction is intrinsically objective: $\mathcal{L}_v$ commutes with arbitrary push-forward by an outer rigid rotation. For kinetic (contravariant-contravariant) tensors $\mathcal{L}_v\boldsymbol{\tau}=\mathbf{F}\dot{\mathbf{S}}\mathbf{F}^T=\dot{\boldsymbol{\tau}}-\mathbf{L}\boldsymbol{\tau}-\boldsymbol{\tau}\mathbf{L}^T$ (Oldroyd / convected of Kirchhoff stress; equivalently the Truesdell rate of $\boldsymbol{\sigma}$ scaled by $J$). For kinematic (covariant-covariant) tensors the rule flips: $\mathcal{L}_v\mathbf{g}=\mathbf{F}^{-T}\dot{\mathbf{C}}\mathbf{F}^{-1}=2\mathbf{D}$ recovers the rate-of-deformation as the Lie derivative of the spatial metric. The Jaumann rate is NOT a Lie derivative — it differs by a symmetric correction $\mathbf{D}\boldsymbol{\sigma}+\boldsymbol{\sigma}\mathbf{D}$ that produces the simple-shear oscillation pathology (`kinematics-objective-rates`).


## 1. Core Concept
The Lie derivative is the geometric notion of "rate" on a manifold without privileged coordinates: take the field, transport it back via the inverse flow, differentiate in the fixed reference, transport forward. For a continuum body the inverse flow is the inverse motion $\boldsymbol{\phi}^{-1}$, the differentiation is the material time derivative, and the resulting Lie derivative is automatically frame-indifferent. The catch is that "transport" depends on the variance of the tensor — kinetic tensors transport with $\mathbf{F}\bullet\mathbf{F}^T$, kinematic tensors with $\mathbf{F}^{-T}\bullet\mathbf{F}^{-1}$ — so the same word "Lie derivative" gives different formulas for different tensor types. The Lie derivative of stress is the Truesdell / Oldroyd rate; the Lie derivative of strain is the Cotter-Rivlin rate; the Lie derivative of the metric is twice the rate-of-deformation. This unifies the zoo of objective rates: each is the Lie derivative of a specific tensor variant. The Jaumann rate stands apart because it uses spin $\mathbf{W}$ rather than the full velocity gradient $\mathbf{L}$ for transport, making it a "partial" Lie derivative whose stress-update behaviour is famously pathological under finite shear.


## 2. Mathematical Formulation
Throughout, $\boldsymbol{\phi}$ is the motion, $\phi_*,\phi^*$ are push-forward / pull-back along $\boldsymbol{\phi}$. $\mathbf{F}=\nabla_0\boldsymbol{\phi}$. Time derivatives are material: $D/Dt\,(\bullet)|_{\mathbf{X}}$. Symbols below distinguish kinetic / kinematic rules.


**Definition:**

$$
\mathcal{L}_v\,\mathbf{T} = \phi_*\!\left(\frac{D}{Dt}\,\phi^*(\mathbf{T})\right)
$$

where Pull-back, time derivative, push-forward

**Lie of kinetic tensors (push-forward = $\mathbf{F}\bullet\mathbf{F}^T$):**

$$
\mathcal{L}_v\,\boldsymbol{\tau}
= \mathbf{F}\,\frac{D}{Dt}(\mathbf{F}^{-1}\boldsymbol{\tau}\mathbf{F}^{-T})\,\mathbf{F}^T
= \mathbf{F}\,\dot{\mathbf{S}}\,\mathbf{F}^T
$$

where Equivalent to Oldroyd rate of Kirchhoff stress

**Spatial expansion of kinetic Lie derivative:**

$$
\mathcal{L}_v\,\boldsymbol{\tau}
= \dot{\boldsymbol{\tau}} - \mathbf{L}\,\boldsymbol{\tau} - \boldsymbol{\tau}\,\mathbf{L}^T
$$

where Convective rate; relates to Truesdell rate of Cauchy stress via $\mathcal{L}_v\boldsymbol{\tau}=J\boldsymbol{\sigma}^{\nabla T}$

**Lie of kinematic tensors (push-forward = $\mathbf{F}^{-T}\bullet\mathbf{F}^{-1}$):**

$$
\mathcal{L}_v\,\mathbf{g}
= \mathbf{F}^{-T}\,\frac{D}{Dt}(\mathbf{F}^T\mathbf{g}\mathbf{F})\,\mathbf{F}^{-1}
= \mathbf{F}^{-T}\,\dot{\mathbf{C}}\,\mathbf{F}^{-1}
= 2\mathbf{D}
$$

where Lie derivative of spatial metric = $2\mathbf{D}$

**Cotter-Rivlin rate (Lie derivative of covariant tensor):**

$$
\mathcal{L}_v^{cov}\,\boldsymbol{\sigma}^{cov}
= \dot{\boldsymbol{\sigma}}^{cov} + \mathbf{L}^T\,\boldsymbol{\sigma}^{cov} + \boldsymbol{\sigma}^{cov}\,\mathbf{L}
$$

where Lie of covariant stress component, used when stress is treated as covariant rather than contravariant

**Decomposition $\mathcal{L}_v = \partial_t + \mathcal{L}_{\mathbf{v},\mathrm{spatial}}$:**

$$
\mathcal{L}_v\,\boldsymbol{\tau}
= \frac{\partial \boldsymbol{\tau}}{\partial t}\bigg|_{\mathbf{x}} + \mathbf{v}\cdot\nabla\boldsymbol{\tau}
                                                               - \mathbf{L}\,\boldsymbol{\tau} - \boldsymbol{\tau}\,\mathbf{L}^T
$$

where Eulerian form: local time derivative + advective + tensorial transport

**Relation to Jaumann (NOT a pure Lie derivative):**

$$
\boldsymbol{\sigma}^{\nabla J}
= \mathcal{L}_v\,\boldsymbol{\sigma} + \mathbf{D}\,\boldsymbol{\sigma} + \boldsymbol{\sigma}\,\mathbf{D}
                               - \boldsymbol{\sigma}\,\mathrm{tr}\,\mathbf{D}
$$

where Jaumann = Truesdell + symmetric corrections; NOT a Lie derivative — explains shear-oscillation pathology

**Lie derivative chain identity:**

$$
\frac{D}{Dt}\,\phi^*(\mathbf{T}) = \phi^*(\mathcal{L}_v\,\mathbf{T})
$$

where Pulled-back time derivative of $\mathcal{L}_v\mathbf{T}$ equals time derivative of pulled-back $\mathbf{T}$

**Time integration in Lagrangian frame:**

$$
\int_0^t \mathcal{L}_v\,\boldsymbol{\tau}\,d\tau = \mathbf{F}(t)\,(\mathbf{S}(t)-\mathbf{S}(0))\,\mathbf{F}(t)^T
$$

where Path-independent integration: integrating Lie rate gives the difference of pulled-back stresses pushed forward

**Notation:**

- $\mathcal{L}_v$ — Lie derivative along the spatial velocity field $\mathbf{v}$
- $\phi_*,\phi^*$ — Push-forward / pull-back operators of the motion $\boldsymbol{\phi}$
- $\boldsymbol{\tau},\mathbf{S}$ — Kirchhoff and PK2 stress (`stress-piola-kirchhoff`, `stress-cauchy-kirchhoff`)
- $\mathbf{g}$ — Spatial metric tensor (= $\mathbf{I}$ in Euclidean space)
- $\mathbf{C}$ — Right Cauchy-Green tensor
- $\mathbf{D},\mathbf{L}$ — Rate-of-deformation, spatial velocity gradient
- $\boldsymbol{\sigma}^{\nabla J},\boldsymbol{\sigma}^{\nabla T}$ — Jaumann / Truesdell rates of Cauchy stress
- $D/Dt|_{\mathbf{X}}$ — Material time derivative (holding $\mathbf{X}$ fixed)


## 3. Algorithmic Implementation
**Algorithm: Compute $\mathcal{L}_v\boldsymbol{\tau}$ via Pull-Back/Push-Forward Chain**

$$
\begin{algorithmic}
\State $\text{input} \colon \boldsymbol{\tau}_n,\boldsymbol{\tau}_{n+1},\,\mathbf{F}_n,\,\mathbf{F}_{n+1},\,\Delta t$
\State $\mathbf{S}_n \gets \mathbf{F}_n^{-1}\,\boldsymbol{\tau}_n\,\mathbf{F}_n^{-T}$
\State $\mathbf{S}_{n+1} \gets \mathbf{F}_{n+1}^{-1}\,\boldsymbol{\tau}_{n+1}\,\mathbf{F}_{n+1}^{-T}$
\State $\dot{\mathbf{S}} \gets (\mathbf{S}_{n+1}-\mathbf{S}_n)/\Delta t$
\State $\mathcal{L}_v\,\boldsymbol{\tau} \gets \mathbf{F}_{n+1}\,\dot{\mathbf{S}}\,\mathbf{F}_{n+1}^T$
\Return $\mathcal{L}_v\,\boldsymbol{\tau}$
\end{algorithmic}
$$

**Taichi Mapping:**
Use as a unit test for spatial-form Lie / Truesdell implementations: this chain construction must match $\dot{\boldsymbol{\tau}}-\mathbf{L}\boldsymbol{\tau}-\boldsymbol{\tau}\mathbf{L}^T$ to round-off. In production prefer the spatial form (one matrix algebra rather than four pull-backs / push-forwards), but keep the chain routine for diagnostics. Cache $\mathbf{F}_n^{-1}$ between steps to avoid recomputing the previous step's inverse.


**Algorithm: Verify $\mathcal{L}_v\,\mathbf{g}=2\mathbf{D}$**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathbf{F},\dot{\mathbf{F}},\Delta t$
\State $\mathbf{C} \gets \mathbf{F}^T\mathbf{F},\;\dot{\mathbf{C}} \gets \dot{\mathbf{F}}^T\mathbf{F} + \mathbf{F}^T\dot{\mathbf{F}}$
\State $\mathcal{L}_v\,\mathbf{g} \gets \mathbf{F}^{-T}\,\dot{\mathbf{C}}\,\mathbf{F}^{-1}$
\State $2\mathbf{D} \gets \mathbf{L} + \mathbf{L}^T \;\text{with } \mathbf{L} = \dot{\mathbf{F}}\mathbf{F}^{-1}$
\State $\text{assert} \;\|\mathcal{L}_v\,\mathbf{g} - 2\mathbf{D}\|/\|\mathbf{D}\| < 10^{-12}$
\Return $\mathcal{L}_v\,\mathbf{g}$
\end{algorithmic}
$$

**Taichi Mapping:**
Diagnostic / regression test, not a production routine. Run on at least one Gauss point to confirm the kinematic Lie derivative is implemented correctly — failures usually reveal sign errors or wrong index ordering in the kinematic push-forward / pull-back rule.


**Algorithm: Convert Between Spatial Lie Form and Truesdell-Cauchy Form**

$$
\begin{algorithmic}
\State $\text{input} \colon \mathcal{L}_v\,\boldsymbol{\tau},\,J,\,\mathrm{tr}\,\mathbf{D}$
\State $\boldsymbol{\sigma}^{\nabla T} \gets J^{-1}\,\mathcal{L}_v\,\boldsymbol{\tau} - \boldsymbol{\sigma}\,\mathrm{tr}\,\mathbf{D} \;\;(\text{equivalently}\;= \dot{\boldsymbol{\sigma}} - \mathbf{L}\boldsymbol{\sigma} - \boldsymbol{\sigma}\mathbf{L}^T + \boldsymbol{\sigma}\,\mathrm{tr}\,\mathbf{L})$
\Return $\boldsymbol{\sigma}^{\nabla T}$
\end{algorithmic}
$$

**Taichi Mapping:**
Keep both forms available so the user code can choose either Kirchhoff Lie or Cauchy Truesdell at the API. Truesdell of $\boldsymbol{\sigma}$ has the volumetric correction baked in; Lie of $\boldsymbol{\tau}$ does not. The conversion is one division by $J$ and one trace contraction.



## 4. Known Pitfalls
**Confusing kinetic and kinematic Lie derivatives:** $\mathcal{L}_v\,\boldsymbol{\tau}=\mathbf{F}\dot{\mathbf{S}}\mathbf{F}^T$ uses the kinetic push-forward; $\mathcal{L}_v\,\mathbf{g}=\mathbf{F}^{-T}\dot{\mathbf{C}}\mathbf{F}^{-1}$ uses the kinematic. Applying the kinematic rule to a kinetic tensor (a common slip when adapting metric formulas) silently destroys symmetry / power conjugacy and produces wrong stress rates.


**Forgetting that Lie derivative depends on tensor variance:** "Lie derivative" is shorthand for a family of operators indexed by tensor variance. Stating "$\mathcal{L}_v\mathbf{T}$" without specifying whether $\mathbf{T}$ is kinetic or kinematic leaves the formula ambiguous. Document the variance at every API boundary; a tensor stored as $T_{ij}$ may be either contravariant or covariant component-wise, and the choice determines the push-forward rule.


**Mistaking Lie of metric for $\mathbf{L}$:** $\mathcal{L}_v\mathbf{g}=2\mathbf{D}$, NOT $\mathbf{L}$. The Lie derivative of the spatial metric is the SYMMETRIC rate-of-deformation; the velocity gradient $\mathbf{L}$ is generally asymmetric. Using $\mathbf{L}$ in place of $2\mathbf{D}$ in a Lie-derivative-based formulation introduces spurious skew contributions.


**Assuming all objective rates are Lie derivatives:** Truesdell, Oldroyd, Cotter-Rivlin, Lie of $\boldsymbol{\tau}$: all are pure Lie derivatives. Jaumann is NOT — it differs from Lie by symmetric $\mathbf{D}\boldsymbol{\sigma}+\boldsymbol{\sigma}\mathbf{D}$ corrections. Green-Naghdi is also NOT a Lie derivative (it uses the polar rotation rate, not full $\mathbf{L}$). Treating all four as members of the same family produces tangents off by symmetric corrections.


**Implementing $\dot{\boldsymbol{\sigma}}+\boldsymbol{\sigma}\,\mathrm{tr}\,\mathbf{L}$ as if Lie:** $\dot{\boldsymbol{\sigma}}-\mathbf{L}\boldsymbol{\sigma}-\boldsymbol{\sigma}\mathbf{L}^T+\boldsymbol{\sigma}\,\mathrm{tr}\,\mathbf{L}$ is the Truesdell rate of CAUCHY stress, NOT a pure Lie derivative. The Lie of Kirchhoff is $\dot{\boldsymbol{\tau}}-\mathbf{L}\boldsymbol{\tau}-\boldsymbol{\tau}\mathbf{L}^T$ (no trace term). The two are equivalent up to a $J$ rescaling and the trace correction; mixing them produces a residual off by $\boldsymbol{\sigma}\,\mathrm{tr}\,\mathbf{D}$.


**Path-dependence under finite-difference $\mathbf{S}$:** Computing $\dot{\mathbf{S}}\approx(\mathbf{S}_{n+1}-\mathbf{S}_n)/\Delta t$ and pushing forward to $\mathcal{L}_v\boldsymbol{\tau}=\mathbf{F}_{n+1}\dot{\mathbf{S}}\mathbf{F}_{n+1}^T$ produces a result that depends on the choice of $\mathbf{F}_{n+1}$ vs $\mathbf{F}_{n+1/2}$ for the push-forward. Use the mid-point $\mathbf{F}_{n+1/2}$ for second-order accuracy; using $\mathbf{F}_{n+1}$ degrades to first order.


**Missing the convective term in spatial expansion:** $\mathcal{L}_v\boldsymbol{\tau}=\dot{\boldsymbol{\tau}}-\mathbf{L}\boldsymbol{\tau}-\boldsymbol{\tau}\mathbf{L}^T$. The two transport terms are essential — dropping either one (a common slip) makes the rate non-objective and reproduces the Jaumann pathology in disguise. Always include both $\mathbf{L}\boldsymbol{\tau}$ and $\boldsymbol{\tau}\mathbf{L}^T$.


## 5. References
- Belytschko, Liu, Moran & Elkhodary (2014) — Nonlinear Finite Elements for Continua and Structures, 2nd ed. (Lie derivative, Box 5.17, relations to Jaumann / Truesdell rates)
- Holzapfel (2000) — Nonlinear Solid Mechanics (Lie derivative of contravariant / covariant tensors, convected rates, Cotter-Rivlin)
- Marsden & Hughes (1983) — Mathematical Foundations of Elasticity (geometric formulation of Lie derivatives in continuum mechanics)

