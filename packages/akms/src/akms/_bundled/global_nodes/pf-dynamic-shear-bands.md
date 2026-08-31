---
id: pf-dynamic-shear-bands
title: Phase-Field for Adiabatic Shear Bands (ASB)
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- ASB
- viscoplasticity
- mcauliffe
- zhang-2023
- high-rate
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-thermomechanical
  type: refines
  weight: 0.7
- to: pf-dynamic-brittle
  type: refines
  weight: 0.7
- to: thermal-coupled-mechanics
  type: requires
  weight: 1.0
- to: plasticity-johnson-cook
  type: requires
  weight: 1.0
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Phase-Field for Adiabatic Shear Bands (ASB)

## Summary

Phase-field formulations for adiabatic shear banding (ASB) and high-strain-rate thermo-plastic localization in dynamic ductile failure. Under impact loading, dynamic collapse, or high-rate penetration, intense plastic working generates thermal softening that localizes into narrow shear bands preceding macroscopic fracture. The continuum framework couples elastodynamics, non-linear viscoplasticity (e.g., Johnson-Cook flow rule), thermal heat diffusion with Taylor-Quinney plastic work conversion, and diffusive phase-field damage evolution. Key modeling features include: (1) inelastic work driving forces P^+ = \int \chi \bar{\tau} \dot{\gamma}^p dt that channel plastic dissipation into phase-field degradation, (2) rational energetic degradation functions \omega(d) capturing three-stage plastic flow stress evolution, and (3) double phase-field formulations (d_I for tensile spall, d_{II} for shear banding) driven by deviatoric and volumetric strain energy splits.

## 1. Core Concept

Adiabatic shear banding (ASB) is a catastrophic thermomechanical instability occurring in metals subjected to dynamic impact and high strain rates (> 10^3 s^-1). The instability arises from a competition between strain/strain-rate hardening and thermal softening caused by converted plastic work. Standard local continuum models suffer from severe mesh sensitivity and ill-posedness upon the onset of softening. The phase-field approach regularizes ASBs by introducing an internal length scale b_s or l_0 that defines the physical band width and maintains well-posed governing equations. To model the transition from shear localization to fracture, phase-field formulations incorporate inelastic plastic work P^+ or deviatoric strain energy \psi_{dev} into the damage driving force. In complex dynamic environments (such as collapsing thick-walled cylinders or explosive expanding shells), coupled double phase-field models manage distinct damage variables d_I (tensile spalling) and d_{II} (shear localization), capturing multi-crack interactions, band intersections, counterchecks, and deflection angles without ad hoc nucleation criteria.

## 2. Mathematical Formulation

**mcauliffe_thermo_viscoplastic_asb_system**
$$
\rho_0 \ddot{u}_i = \tau_{ij,j}, \quad \rho_0 \bar{c} \dot{T} = \kappa J T_{,jj} + \chi \bar{\tau} g(\bar{\sigma}, T, \bar{\gamma}^p), \quad \frac{G_c}{4 l_0} c - l_0 G_c \Delta c = (1-c) \left[ W^+ + P^+ \right]
$$
_Source: McAuliffe and Waisman (2015), A unified model for metal failure capturing shear banding and fracture; McAuliffe and Waisman (2016), A coupled phase field shear band model_

**zhang_rational_degradation_three_stage_softening**
$$
\omega(d) = \frac{(1-d)^2}{(1-d)^2 + a_1 d \left(1 - \frac{1}{2}d\right)}, \quad \sigma_y(d) = \omega(d) \left( A + B (\epsilon^p)^k \right) \left( 1 + C \ln \frac{\dot{\epsilon}^p}{\dot{\epsilon}_0} \right)
$$
_Source: Zhang et al. (2021a), Phase-field modeling of spontaneous shear bands in collapsing thick-walled cylinders_

**double_phase_field_spall_asb_coupled_system**
$$
\eta_I \dot{d}_I = 2 b_I^2 \Delta d_I - (1-d_{II}) \omega_I'(d) \mathcal{H}_I - \alpha_I'(d_I), \quad \eta_{II} \dot{d}_{II} = 2 b_{II}^2 \Delta d_{II} - (1-d_I) \omega_{II}'(d) \mathcal{H}_{II} - \alpha_{II}'(d_{II})
$$
_Source: Zhang et al. (2023), Phase-field modeling of coupled spall and adiabatic shear banding and simulation of complex cracks in ductile metals_

**asb_stress_tensor_volumetric_deviatoric_split**
$$
\boldsymbol{\sigma} = -H(-p) p \mathbf{I} - H(p) \omega_t(d) p \mathbf{I} + \omega_s(d) \mathbf{s}
$$
_Source: Zhang et al. (2021a), Phase-field modeling of spontaneous shear bands; Zhang et al. (2023), Phase-field modeling of coupled spall and adiabatic shear banding_

**Notation:**
c, d, d_I, d_{II}: scalar phase-field damage variables; \mathbf{u}: displacement vector; \boldsymbol{\tau}: Kirchhoff stress tensor; \boldsymbol{\sigma}: Cauchy stress tensor; \mathbf{s}: deviatoric stress tensor; p: hydrostatic pressure; T: absolute temperature; \chi: Taylor-Quinney inelastic heat conversion factor; \bar{\gamma}^p, \epsilon^p: equivalent plastic strain; W^+: positive elastic strain energy density; P^+: accumulated plastic work driving energy; \psi_{dev}: deviatoric strain energy density; \omega(d), \omega_s(d), \omega_t(d): energetic degradation functions; b_s, b_I, b_{II}, l_0: phase-field length scale parameters.


## 3. Algorithmic Implementation

**coupled-thermomechanical-asb-phase-field-solver**
$$
\begin{algorithmic}
\State $Initialize displacement \mathbf{u}_0, velocity \dot{\mathbf{u}}_0, temperature T_0, equivalent plastic strain \bar{\gamma}_0^p, accumulated inelastic work P_0^+ = 0, and phase field c_0 = 0.$
\For{$Loop over time steps n = 0, 1, 2, \dots, N_{steps} with increment \Delta t.$}
\State $Solve elastodynamic momentum equation for displacement \mathbf{u}_{n+1} and trial Kirchhoff stress \boldsymbol{\tau}_{n+1}^{trial}.$
\State $Perform plastic return-mapping using temperature-dependent Johnson-Cook flow stress \phi(T_n, \bar{\gamma}_n^p, \dot{\bar{\gamma}}^p) to find updated stress \boldsymbol{\tau}_{n+1} and plastic strain rate \dot{\bar{\gamma}}_{n+1}^p.$
\State $Evaluate Taylor-Quinney thermal source \dot{Q}_{thermal} = \chi \bar{\tau}_{n+1} \dot{\bar{\gamma}}_{n+1}^p and solve heat conduction equation for updated temperature T_{n+1}.$
\State $Update accumulated inelastic work driving force: P_{n+1}^+ = P_n^+ + \Delta t \cdot \chi \bar{\tau}_{n+1} \dot{\bar{\gamma}}_{n+1}^p.$
\State $Evaluate elastic strain energy W_{n+1}^+ and assemble phase-field residual vector and stiffness matrix incorporating total driving force (W_{n+1}^+ + P_{n+1}^+).$
\State $Solve phase-field microforce balance equation for c_{n+1}: \left( \frac{G_c}{4 l_0} + W_{n+1}^+ + P_{n+1}^+ \right) c_{n+1} - l_0 G_c \Delta c_{n+1} = W_{n+1}^+ + P_{n+1}^+.$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: McAuliffe and Waisman (2015), A unified model for metal failure capturing shear banding and fracture; McAuliffe and Waisman (2016), A coupled phase field shear band model_


## 4. Known Pitfalls

- **mesh-resolution-insufficiency-for-shear-bandwidth**: The phase-field length scale parameter b_s or l_0 determines the physical width of the localized adiabatic shear band (typically 10 \mu\text{m} to 100 \mu\text{m}). If the finite element size h exceeds b_s / 2, numerical wave dispersion distorts shear localization, producing artificially wide bands (> 200 \mu\text{m}) or inaccurate predictions of spontaneous band spacing. _(Source: Zhang et al. (2021a), Phase-field modeling of spontaneous shear bands in collapsing thick-walled cylinders; McAuliffe and Waisman (2016), A coupled phase field shear band model)_
- **neglecting-inelastic-work-or-thermal-softening-driving-forces**: Using pure elastic strain energy release rate W^+ to drive the phase field in high-strain-rate impact failure causes complete failure of the model to predict shear banding. Because elastic strain energy remains small relative to plastic work during high-rate plastic deformation, omitting accumulated plastic work P^+ or deviatoric work \psi_{dev} prevents damage localization. _(Source: McAuliffe and Waisman (2015), A unified model for metal failure capturing shear banding and fracture; McAuliffe and Waisman (2016), A coupled phase field shear band model)_
- **unphysical-hydrostatic-pressure-degradation-in-compression**: In dynamic compression problems (e.g. collapsing thick-walled cylinders), degrading total stress isotropic components causes non-physical volumetric collapse under high hydrostatic pressure. To maintain physical validity, compressive pressure must remain strictly undegraded while deviatoric and tensile stresses are degraded by \omega_s(d). _(Source: Zhang et al. (2021a), Phase-field modeling of spontaneous shear bands; Zhang et al. (2023), Phase-field modeling of coupled spall and adiabatic shear banding)_

## References

- McAuliffe, C., and Waisman, H. (2015). A unified model for metal failure capturing shear banding and fracture. International Journal of Plasticity, 65, 131-151.
- McAuliffe, C., and Waisman, H. (2016). A coupled phase field shear band model for ductile–brittle transition in notched plate impacts. Computer Methods in Applied Mechanics and Engineering, 305, 173-195.
- Zhang, H., Pei, X.-Y., Peng, H., and Wu, J.-Y. (2021a). Phase-field modeling of spontaneous shear bands in collapsing thick-walled cylinders. Engineering Fracture Mechanics, 249, 107706.
- Zhang, H., Peng, H., Pei, X.-Y., Wu, J.-Y., Li, P., Tang, T.-G., Cai, L.-C., Li, Y., and Liu, H. (2023). Phase-field modeling of coupled spall and adiabatic shear banding and simulation of complex cracks in ductile metals. Journal of the Mechanics and Physics of Solids, 172, 105186.
- Miehe, C., Hofacker, M., Schänzel, L.-M., and Aldakheel, F. (2015). Phase field modeling of fracture in multi-physics problems. Part II. Coupled brittle-to-ductile failure criteria and crack propagation in thermo-elastic-plastic solids. Computer Methods in Applied Mechanics and Engineering, 294, 486-522.
