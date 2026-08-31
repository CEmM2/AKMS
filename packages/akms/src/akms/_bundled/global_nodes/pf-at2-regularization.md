---
id: pf-at2-regularization
title: AT2 Regularization (Ambrosio-Tortorelli, Quadratic)
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- AT2
- regularization
- miehe
- gamma-convergence
status: tentative
confidence: 0.92
source: hybrid
confidence_floor: 0.7
edges:
- to: pf-variational-griffith
  type: refines
  weight: 0.7
- to: pf-staggered-scheme
  type: feeds-into
  weight: 0.5
- to: pf-fem-implementation
  type: feeds-into
  weight: 0.5
- to: pf-at1-regularization
  type: contradicts
  weight: 0.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# AT2 Regularization (Ambrosio-Tortorelli, Quadratic)

## Summary
AT2 is the standard quadratic regularization of variational fracture due
to Ambrosio-Tortorelli (1990) and popularized for FE by Miehe et al.
(2010). The crack surface density is gamma_l = (1/2*ell)*d^2 + (ell/2)*|grad d|^2,
the elastic energy is degraded by g(d)=(1-d)^2, and the resulting governing
PDE is linear in d when the source psi+ is fixed. Mesh refinement requires
h <= ell/2. AT2 has no elastic limit — any non-zero stress nucleates damage —
which limits its quantitative use but makes it numerically robust.


## 1. Core Concept
AT2 takes the form discovered by Ambrosio-Tortorelli (1990) as a
Gamma-convergent approximation to the Mumford-Shah image-segmentation
functional and adapted by Bourdin-Francfort-Marigo (2000) and Miehe-
Welschinger-Hofacker (2010) for fracture mechanics.

The regularized energy reads
    E_l(u, d) = integral_Omega [(1-d)^2 + k] psi(eps(u)) dV
               + Gc * integral_Omega [(1/(2*ell)) * d^2 + (ell/2)|grad d|^2] dV
where k is a small residual stiffness (~1e-6) preventing system
ill-conditioning at d=1, and ell is the regularization length.

Stationarity in d (assuming d unconstrained) yields a linear screening
equation:
    Gc * (d/ell - ell * laplace(d)) = 2*(1-d) * psi+(eps)
often written using the history variable kappa = max(psi+) for
irreversibility. The constitutive update for u uses degraded stress
sigma = (1-d)^2 * dpsi/deps.

AT2 has the closed-form 1D solution under uniaxial homogeneous load
predicting d -> 1 at sigma -> 0+, i.e., infinitesimal stress nucleates
damage. Hence "no elastic limit" — sigma_c -> 0 as ell -> 0. AT2 is
best for brittle fracture with crack propagation, less so for nucleation
thresholds.


## 2. Mathematical Formulation
The AT2 regularization uses quadratic crack surface density and quadratic
degradation, leading to a linear elliptic PDE for the phase field with
elasticity-driven source.


**at2-energy:**

$$
\mathcal{E}_\ell(\mathbf{u}, d) \;=\; \int_\Omega [(1-d)^2 + k]\,\psi^+(\boldsymbol{\varepsilon}) \,dV \;+\; G_c \int_\Omega \!\left[\frac{d^2}{2\ell} + \frac{\ell}{2}|\nabla d|^2\right] dV
$$

where k approx 1e-6: residual stiffness; psi+ = active (tensile) part of strain energy

**phase-field-pde:**

$$
\frac{G_c}{\ell}\, d \;-\; G_c \ell \, \nabla^2 d \;=\; 2(1-d)\,\mathcal{H}
$$

where H = max_{tau<=t} psi+ (history variable enforcing irreversibility per Miehe 2010)

**stress-update:**

$$
\boldsymbol{\sigma} \;=\; [(1-d)^2 + k] \, \frac{\partial \psi^+}{\partial \boldsymbol{\varepsilon}} \;+\; \frac{\partial \psi^-}{\partial \boldsymbol{\varepsilon}}
$$

where psi+/psi- split (spectral or vol-dev) prevents damage in compression

**irreversibility-history:**

$$
\mathcal{H}(\mathbf{x}, t) \;=\; \max_{\tau \in [0, t]} \psi^+(\boldsymbol{\varepsilon}(\mathbf{x}, \tau))
$$

where history-variable formulation per Miehe 2010 — replaces unilateral constraint

**elastic-limit:**

$$
\sigma_c \;=\; \frac{9}{16}\sqrt{\frac{2 E G_c}{3\ell}} \cdot 0  \;\equiv\; 0 \quad \text{(AT2 has no elastic limit)}
$$

where closed-form 1D analysis: damage initiates at any sigma > 0 — AT2 cannot capture finite strength

**mesh-requirement:**

$$
h \;\le\; \ell/2 \quad \text{(typical guideline for resolving diffuse crack)}
$$

where h = element size; coarser meshes overestimate Gc by approximately (1 + h/(2*c_w*ell)) where c_w = 1/2 for AT2

**Notation:**

- $d$ — phase field in [0,1] (Miehe notation)
- $phi$ — synonym for d (Bourdin notation)
- $k$ — residual stiffness ~ 1e-6
- $psi+, psi-$ — tensile/compressive split of strain energy
- $H$ — history field enforcing irreversibility
- $ell$ — regularization length
- $c_w$ — 1/2 for AT2 (normalization in Gamma-limit)


## 3. Algorithmic Implementation
**Algorithm: at2-staggered-step**

$$
\begin{algorithmic}
\State $$
\State $$
\State $$
\State $$
\State $$
\State $$
\State $$
\State $$
\end{algorithmic}
$$

**Taichi Mapping:**
Two passes per outer iteration: first a sparse-Helmholtz solve for d
(coefficient depends on H stored at GP), then standard elasticity
assembly with (1-d)^2 modulating the GP-level tangent. Use
ti.linalg.SparseSolver for both.



## 4. Known Pitfalls
**no-elastic-limit:** AT2 cannot represent a finite tensile strength sigma_c. As soon as
psi+ > 0 the phase field starts evolving. For problems requiring a
strength criterion (e.g., quasi-brittle materials with peak load),
use AT1 or PF-CZM instead.


**damage-in-compression:** Without an energy split, AT2 produces unphysical damage under
hydrostatic compression. Always use spectral, vol-dev, or no-tension
decomposition of psi.


**mesh-bias:** Cracks aligned with mesh edges propagate slightly cheaper than
diagonal cracks. Use isotropic h-AMR or anisotropic remeshing where
d > 0.1 to mitigate.


**small-k-conditioning:** The residual stiffness k must be small enough not to overestimate
cracked stiffness but large enough not to ill-condition the linear
system. Typical k = 1e-6 to 1e-9 of E.


**history-vs-bound-enforcement:** Miehe history variable H is mathematically equivalent to enforcing
the bound d_dot >= 0 only when no compressive unloading occurs. For
cyclic loading, use active-set bound enforcement (more expensive
but more accurate).


## 5. References
- Miehe, C., Welschinger, F., Hofacker, M. (2010). Thermodynamically consistent phase-field models of fracture: variational principles and multi-field FE implementations. IJNME 83:1273-1311.
- Ambrosio, L., Tortorelli, V. M. (1990). Approximation of functionals depending on jumps by elliptic functionals via Gamma-convergence. CPAM 43:999-1036.
- Bourdin, B., Francfort, G. A., Marigo, J.-J. (2000). Numerical experiments in revisited brittle fracture. JMPS 48:797-826.
- Bourdin, B., Francfort, G. A., Marigo, J.-J. (2008). The variational approach to fracture. Springer.
