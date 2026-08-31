---
id: pf-benchmarks
title: Phase-Field Fracture Benchmarks
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- benchmarks
- SENT
- kalthoff-winkler
- sneddon
- validation
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-fem-implementation
  type: refines
  weight: 0.7
- to: pf-at2-regularization
  type: feeds-into
  weight: 0.5
- to: pf-dynamic-brittle
  type: feeds-into
  weight: 0.5
- to: pf-staggered-scheme
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Phase-Field Fracture Benchmarks

## Summary

Standardized computational benchmarks for validating phase-field fracture and damage formulations across quasi-static, dynamic, brittle, and ductile failure regimes. Key benchmark suites include: (1) Single-Edge Notched Tension (SENT) and Shear (SENS) tests verifying Mode I straight crack propagation and mixed-mode curved cracking under strain energy decompositions, (2) Kalthoff-Winkler plate impact tests capturing the dynamic transition from brittle tensile fracture at ~70° propagation angle under low impact velocity (v_0 ≈ 20 m/s) to ductile adiabatic shear banding (~-8° angle) at high impact velocity (v_0 ≥ 30 m/s), (3) Symmetric and Asymmetric Three-Point Bending (TPB) tests validating crack trajectory curvature around geometric obstacles, and (4) L-shaped panel tests evaluating mixed-mode crack initiation at re-entrant corners.

## 1. Core Concept

Validation and verification of phase-field fracture models rely on canonical benchmark problems that test fundamental physical and numerical capabilities: crack nucleation, strain-energy decomposition robustness, mixed-mode path selection, and dynamic failure mode transitions. Quasi-static benchmarks such as SENT and SENS establish basic accuracy in predicting crack initiation loads and path deflection under tensile versus shear loading. Dynamic impact benchmarks, exemplified by the Kalthoff-Winkler test, evaluate the model's ability to capture wave-reflection-driven fracture and the rate-dependent transition between brittle tensile cracking (driven by tensile elastic strain energy) and thermo-plastic shear localization (driven by plastic work and thermal softening). Numerical accuracy across these benchmarks requires resolving the regularized crack localization band (h ≤ b/5) and avoiding spurious stress singularities at point-load or support boundaries.

## 2. Mathematical Formulation

**sent_sens_governing_energy**
$$
E(\mathbf{u}, d) = \int_{\Omega} \left[ g(d) \psi_0^+(\boldsymbol{\epsilon}) + \psi_0^-(\boldsymbol{\epsilon}) \right] d\Omega + \int_{B} G_f \gamma(d, \nabla d) d\Omega
$$
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture_

**kalthoff_winkler_dynamic_energy_balance**
$$
\rho \ddot{\mathbf{u}} = \nabla \cdot \boldsymbol{\sigma}, \quad \boldsymbol{\sigma} = g(d) \frac{\partial \psi_0^+}{\partial \boldsymbol{\epsilon}} + \frac{\partial \psi_0^-}{\partial \boldsymbol{\epsilon}}, \quad 2 w_c \left[ d - l^2 \Delta d \right] = 2(1-d) \mathcal{H}
$$
_Source: Miehe et al. (2015), Phase field modeling of fracture in multi-physics problems. Part II; Wang et al. (2020), A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration_

**kalthoff_winkler_transition_velocity**
$$
v_{impact} < v_{crit} \implies \theta_{crack} \approx 70^\circ \quad (\text{brittle Mode I}), \quad v_{impact} \ge v_{crit} \implies \theta_{shear} \approx -8^\circ \quad (\text{ductile shear band})
$$
_Source: Miehe et al. (2015), Phase field modeling of fracture in multi-physics problems. Part II; McAuliffe and Waisman (2016), A coupled phase field shear band model for ductile-brittle transition_

**l_shaped_panel_mixed_mode_crack**
$$
\mathcal{H}(\mathbf{x}, t) = \max_{\tau \in [0,t]} \bar{Y}(\boldsymbol{\epsilon}(\mathbf{x}, \tau)), \quad \mathbf{K}_{dd} \mathbf{d} = \mathbf{r}_d
$$
_Source: Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory; Zhang et al. (2022), Assessment of four strain energy decomposition methods_

**Notation:**
\mathbf{u}: displacement vector; d: scalar phase-field damage variable (d \in [1]); \boldsymbol{\sigma}: degraded stress tensor; \psi_0^+, \psi_0^-: tensile and compressive strain energy densities; G_f: fracture toughness; b, l: regularization length scale parameter; \rho: material density; v_0, v_{impact}: projectile velocity; \theta_{crack}: crack deflection angle; \mathcal{H}: history variable field preserving energy maximum.


## 3. Algorithmic Implementation

**sent-sens-benchmark-procedure**
$$
\begin{algorithmic}
\State $Set up 1 mm \times 1 mm square domain with a 0.5 mm horizontal notch at y=0.5 mm and refined mesh h \le b/5 along the expected crack path.$
\For{$Loop over load increments n = 1, 2, \dots, N_{steps}.$}
\State $For SENT (Mode I): apply incremental vertical displacement \Delta u_y > 0 on top boundary with bottom fixed (u_x = u_y = 0).$
\State $For SENS (Mode II/Mixed-Mode): apply incremental horizontal shear displacement \Delta u_x > 0, u_y = 0 on top boundary with bottom fixed.$
\State $Solve coupled mechanical equilibrium and phase-field evolution equations using staggered or BFGS quasi-Newton solver.$
\State $Update integration point strain energy \psi_0^+ and history field \mathcal{H}_{n+1} = \max(\mathcal{H}_n, \psi_0^+).$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Wu and Huang (2020), Comprehensive implementations of phase-field damage models in Abaqus; Zhang et al. (2022), Assessment of four strain energy decomposition methods_

**kalthoff-winkler-impact-benchmark**
$$
\begin{algorithmic}
\State $Define double pre-notched plate specimen (100 mm \times 200 mm, notch length 50 mm, notch spacing 50 mm) with density \rho and elastic/plastic properties.$
\State $Apply symmetric velocity profile v_0 across the edge segment between the two notch tips over rise time t_0 = 0.1 \ \mu\text{s}.$
\If{$Impact velocity v_0 = 20 \text{ m/s} (Low loading rate).$}
\State $Observe tensile stress wave reflection at notch tip generating Mode I stress field; brittle crack initiates and propagates at \approx 70^\circ angle.$
\ElsIf{$Impact velocity v_0 \ge 30 \text{ m/s} (High loading rate).$}
\State $Observe intense plastic strain accumulation and thermal/softening localization at notch tip; adiabatic shear band initiates and propagates horizontally at \approx -8^\circ.$
\EndIf
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Miehe et al. (2015), Phase field modeling of fracture in multi-physics problems. Part II; McAuliffe and Waisman (2016), A coupled phase field shear band model for ductile-brittle transition_


## 4. Known Pitfalls

- **sens-crack-path-dependency-on-energy-split**: In Single-Edge Notched Shear (SENS) tests, the predicted crack propagation trajectory is highly sensitive to the strain energy decomposition method (e.g., spectral vs. deviatoric split). Unsplit energy functions cause non-physical crack propagation under compressive stress zones. _(Source: Zhang et al. (2022), Assessment of four strain energy decomposition methods for phase field fracture; Miehe et al. (2010), Thermodynamically consistent phase-field models of fracture)_
- **kalthoff-winkler-mesh-bias-and-velocity-toughening**: In dynamic impact benchmarks such as Kalthoff-Winkler, coarse meshes (h > b/2) around the notch tip introduce numerical wave dispersion and artificially elevate the critical transition velocity for shear banding. Furthermore, neglecting dynamic inertia terms in J-integral evaluations distorts the calculation of the instantaneous stress intensity factor K_{ID}. _(Source: Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Miehe et al. (2015), Phase field modeling of fracture in multi-physics problems. Part II)_
- **tpb-lshaped-spurious-damage-at-point-load-supports**: In Three-Point Bending (TPB) and L-shaped panel benchmarks, applying point loads or rigid displacement constraints directly to single nodes creates non-physical stress singularities. This causes artificial localized damage nucleation at support points rather than at the notch or re-entrant corner unless distributed contact/traction boundary conditions are applied. _(Source: Zhang et al. (2022), Assessment of four strain energy decomposition methods for phase field fracture; Wu et al. (2020), On the BFGS monolithic algorithm for the unified phase field damage theory)_

## References

- Wu, J.-Y., and Huang, Y. (2020). Comprehensive implementations of phase-field damage models in Abaqus. Theoretical and Applied Fracture Mechanics, 106, 102440.
- Miehe, C., Hofacker, M., and Welschinger, F. (2010). Thermodynamically consistent phase-field models of fracture: Variational principles and multi-field FE implementations. International Journal for Numerical Methods in Engineering, 83(10), 1273-1311.
- Miehe, C., Hofacker, M., Schänzel, L.-M., and Aldakheel, F. (2015). Phase field modeling of fracture in multi-physics problems. Part II. Coupled brittle-to-ductile failure criteria and crack propagation in thermo-elastic-plastic solids. Computer Methods in Applied Mechanics and Engineering, 294, 486-522.
- McAuliffe, C., and Waisman, H. (2016). A coupled phase field shear band model for ductile–brittle transition in notched plate impacts. Computer Methods in Applied Mechanics and Engineering, 305, 173-195.
- Zhang, Z., et al. (2022). Assessment of four strain energy decomposition methods for phase field fracture models. Materials Theory, 6, 6.
- Wu, J.-Y., Huang, Y., and Nguyen, V. P. (2020). On the BFGS monolithic algorithm for the unified phase field damage theory. Computer Methods in Applied Mechanics and Engineering, 360, 112704.
- Molnar, G., Gravouil, A., Seghir, R., and Réthoré, J. (2020). An open-source Abaqus implementation of the phase-field method to study the effect of plasticity on the instantaneous fracture toughness in dynamic crack propagation. Computer Methods in Applied Mechanics and Engineering, 365, 113004.
- Wang, T., Ye, X., Liu, Z., Liu, X., Chu, D., and Zhuang, Z. (2020). A phase-field model of thermo-elastic coupled brittle fracture with explicit time integration. Computational Mechanics, 65(5), 1305-1321.
