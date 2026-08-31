---
id: pf-dynamic-brittle
title: 'Dynamic Phase-Field: Brittle Crack Propagation & Branching'
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- dynamic
- brittle
- branching
- borden-2012
- yoffe
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-at2-regularization
  type: refines
  weight: 0.7
- to: pf-explicit-time-integration
  type: feeds-into
  weight: 0.5
- to: pf-spectral-split
  type: requires
  weight: 1.0
- to: pf-dynamic-shear-bands
  type: refines
  weight: 0.7
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Dynamic Phase-Field: Brittle Crack Propagation & Branching

## Summary

Formulation, governing equations, and numerical implementation of dynamic phase-field models for brittle crack propagation, velocity acceleration, and spontaneous crack branching. The continuum framework couples elastodynamics with a diffusive crack interface field d, governed by macro-momentum balance \rho \ddot{\mathbf{u}} = \nabla \cdot \boldsymbol{\sigma} + \mathbf{b} and microforce balance for the phase field. Crack initiation, propagation, and branching emerge naturally as thermodynamic energy dissipation processes driven by the historical maximum strain energy release rate \mathcal{H}, without requiring extrinsic tracking or ad hoc branching criteria. Physical resolution of dynamic branching instabilities requires resolving the length scale l_c with fine spatial discretization (h \le l_c/2) and explicit or implicit time integration algorithms.

## 1. Core Concept

Dynamic fracture in brittle materials involves complex wave-structure interactions, crack tip acceleration toward Rayleigh wave speed c_R, and spontaneous crack branching under dynamic loading rates. Linear elastic fracture mechanics (LEFM) requires ad hoc criteria to predict when and where a crack will branch or arrest. The dynamic phase-field approach replaces sharp crack interfaces with a regularized crack functional governed by internal length scale l_c, incorporating kinetic energy density \frac{1}{2}\rho |\dot{\mathbf{u}}|^2 into the continuum balance principles. As a crack accelerates under dynamic impact or tensile traction, kinetic and strain energy accumulate around the crack tip; when the local thermodynamic driving force significantly exceeds critical fracture toughness g_c, single-crack propagation becomes unstable, triggering spontaneous crack tip splitting and branching. The phase-field formulation naturally captures stress wave reflections off boundaries, surface roughening, and velocity-toughening effects without explicit interface tracking.

## 2. Mathematical Formulation

**dynamic_brittle_momentum_balance**
$$
\rho \ddot{\mathbf{u}} = \nabla \cdot \boldsymbol{\sigma} + \mathbf{b}, \quad \boldsymbol{\sigma} = g(d) \frac{\partial \psi_0^+}{\partial \boldsymbol{\epsilon}} + \frac{\partial \psi_0^-}{\partial \boldsymbol{\epsilon}}
$$
_Source: Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method_

**dynamic_phase_field_governing_equation**
$$
g_c l_c \Delta d - \frac{g_c}{l_c} d + 2(1-d) \mathcal{H} = \eta \dot{d}
$$
_Source: Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration; Zhang et al. (2022), Assessment of four strain energy decomposition methods_

**dynamic_history_variable_field**
$$
\mathcal{H}(\mathbf{x}, t) = \max_{\tau \in [0, t]} \psi_0^+(\mathbf{x}, \tau)
$$
_Source: Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture_

**rayleigh_wave_speed_limit**
$$
c_R \approx 0.926 \sqrt{\frac{\mu}{\rho}} \quad \text{for Poisson's ratio } \nu = 0.25
$$
_Source: Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Zhang et al. (2023), Phase-field modeling of coupled spall and adiabatic shear banding_

**Notation:**
\mathbf{u}: displacement vector; \ddot{\mathbf{u}}: acceleration vector; d: scalar phase-field damage variable (d \in [1]); \boldsymbol{\sigma}: degraded Cauchy stress tensor; \psi_0^+, \psi_0^-: tensile and compressive strain energy densities; g_c: critical fracture energy density; l_c: regularization length scale parameter; \rho: material mass density; c_R: Rayleigh wave velocity; \mathcal{H}: history variable field; \eta: viscous damping parameter.


## 3. Algorithmic Implementation

**explicit-dynamic-phase-field-staggered-step**
$$
\begin{algorithmic}
\State $Initialize nodal displacement \mathbf{u}_0, velocity \dot{\mathbf{u}}_0, acceleration \ddot{\mathbf{u}}_0, damage d_0 = 0, and history field \mathcal{H}_0 = 0.$
\For{$Loop over time increments n = 0, 1, 2, \dots, N_{steps} with time step size \Delta t.$}
\State $Update nodal displacements using explicit time integration: \mathbf{u}_{n+1} = \mathbf{u}_n + \Delta t \dot{\mathbf{u}}_n + \frac{\Delta t^2}{2} \ddot{\mathbf{u}}_n.$
\State $At element integration points, compute updated strain \boldsymbol{\epsilon}_{n+1} = \nabla^{sym} \mathbf{u}_{n+1} and positive strain energy density \psi_{0, n+1}^+.$
\State $Update history driving field: \mathcal{H}_{n+1} = \max\left(\mathcal{H}_n, \psi_{0, n+1}^+\right).$
\State $Solve uncoupled phase-field equation for d_{n+1}: \left( \frac{g_c}{l_c} + 2 \mathcal{H}_{n+1} + \frac{\eta}{\Delta t} \right) d_{n+1} - g_c l_c \Delta d_{n+1} = 2 \mathcal{H}_{n+1} + \frac{\eta}{\Delta t} d_n.$
\State $Compute degraded Cauchy stress \boldsymbol{\sigma}_{n+1} = [(1-d_{n+1})^2 + k] \frac{\partial \psi_0^+}{\partial \boldsymbol{\epsilon}} + \frac{\partial \psi_0^-}{\partial \boldsymbol{\epsilon}} and assemble internal force vector \mathbf{F}_{int, n+1}.$
\State $Compute updated accelerations \ddot{\mathbf{u}}_{n+1} = \mathbf{M}^{-1} (\mathbf{F}_{ext, n+1} - \mathbf{F}_{int, n+1}) and velocities \dot{\mathbf{u}}_{n+1} = \dot{\mathbf{u}}_n + \frac{\Delta t}{2} (\ddot{\mathbf{u}}_n + \ddot{\mathbf{u}}_{n+1}).$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method_


## 4. Known Pitfalls

- **spurious-branching-from-coarse-mesh-dispersion**: In dynamic fracture simulations, using element size h > l_c/2 causes high-frequency numerical wave dispersion and spurious stress reflections. This distorts the local energy release rate at accelerating crack tips, causing non-physical premature crack branching or mesh-aligned branching trajectories. _(Source: Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture)_
- **critical-time-step-instability-in-explicit-dynamics**: Explicit time integration for dynamic phase-field fracture requires satisfying the Courant-Friedrichs-Lewy (CFL) stability condition \Delta t \le h / c_p, where c_p is the dilatational wave speed. Extremely fine meshes required to resolve l_c severely reduce \Delta t (often \Delta t \sim 10^{-8} \text{ s} - 10^{-9} \text{ s}), leading to high computational costs. _(Source: Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture; Zhang et al. (2023), Phase-field modeling of coupled spall and adiabatic shear banding)_

## References

- Wang, T., Ye, X., Liu, Z., Liu, X., Chu, D., and Zhuang, Z. (2020). A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration. Computational Mechanics, 65(5), 1305-1321.
- Molnar, G., Gravouil, A., Seghir, R., and Réthoré, J. (2020). An open-source Abaqus implementation of the phase-field method to study the effect of plasticity on the instantaneous fracture toughness in dynamic crack propagation. Computer Methods in Applied Mechanics and Engineering, 365, 113004.
- Miehe, C., Hofacker, M., and Welschinger, F. (2010). Thermodynamically consistent phase-field models of fracture: Variational principles and multi-field FE implementations. International Journal for Numerical Methods in Engineering, 83(10), 1273-1311.
- Miehe, C., Hofacker, M., Schänzel, L.-M., and Aldakheel, F. (2015). Phase field modeling of fracture in multi-physics problems. Part II. Coupled brittle-to-ductile failure criteria and crack propagation in thermo-elastic-plastic solids. Computer Methods in Applied Mechanics and Engineering, 294, 486-522.
- Zhang, Z., et al. (2022). Assessment of four strain energy decomposition methods for phase field fracture models. Materials Theory, 6, 6.
- Zhang, H., et al. (2023). Phase-field modeling of coupled spall and adiabatic shear banding and simulation of complex cracks in ductile metals. Journal of the Mechanics and Physics of Solids, 172, 105186.
