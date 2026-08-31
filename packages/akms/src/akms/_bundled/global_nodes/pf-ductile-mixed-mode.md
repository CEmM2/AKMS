---
id: pf-ductile-mixed-mode
title: Mixed-Mode & Shear-Driven Ductile Phase-Field
domain: computational-mechanics
subdomain: phase-field-fracture
tags:
- phase-field
- mixed-mode
- shear
- cup-cone
- slant-fracture
- talamini
status: established
confidence: 0.9
source: hybrid
edges:
- to: pf-ductile-plasticity-coupling
  type: refines
  weight: 0.7
- to: pf-spectral-split
  type: requires
  weight: 1.0
- to: pf-porous-ductile
  type: feeds-into
  weight: 0.5
- to: damage-bai-wierzbicki
  type: refines
  weight: 0.7
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Mixed-Mode & Shear-Driven Ductile Phase-Field

## Summary

Formulation and implementation of mixed-mode and shear-driven ductile phase-field fracture models across multiaxial loading conditions. To accurately capture fracture initiation and localization under low, negative, or mixed stress triaxialities—where standard tensile energy degradation fails—the framework incorporates stress-state dependency characterized by stress triaxiality \eta = -p/q and the normalized Lode angle parameter \theta. Key formulation strategies include: (1) integrating phenomenological fracture loci (e.g., Modified Mohr-Coulomb / Bai-Wierzbicki criteria) into the damage driving threshold to construct a loading-history indicator D(\epsilon^p) for threshold-gated damage initiation, (2) double phase-field formulations with distinct phase variables d_I (tensile/spall) and d_{II} (shear/localization) driven by volumetric tensile energy \psi_{vol}^+ and plastic/elastic deviatoric work \psi_{dev}, and (3) hybrid coupled degradation functions combining scalar phase-field damage with void volume fraction f and shear damage D_s (e.g., shear-modified GTN phase-field models).

## 1. Core Concept

Modeling shear-dominated and mixed-mode ductile fracture within a regularized phase-field continuum requires extending classical brittle energy-split concepts (such as spectral or volumetric-deviatoric splits) to account for plastic strain accumulation, hydrostatic pressure, and Lode-angle sensitivity. In purely tensile or high-triaxiality regimes, microvoid growth dominates and crack initiation can be captured using degraded plastic strain energy. However, under shear or compression-shear loading (low or negative triaxiality), void growth is suppressed, and failure proceeds via intense shear band localization. Standard phase-field models falsely predict zero damage or numerical locking in compression unless deviatoric plastic work \int \boldsymbol{s} : d\boldsymbol{\epsilon}^p and stress-state dependent threshold functions \epsilon_f(\eta, \theta, \dot{\epsilon}^p) drive phase-field evolution. Modern frameworks resolve this using either: (i) stress-state-dependent damage indicators D(\epsilon^p) based on the Modified Mohr-Coulomb (MMC) criterion, where phase-field evolution is triggered only when D=1, or (ii) double phase-field formulations that maintain separate phase fields d_I and d_{II} with distinct fracture energies G_f^I, G_f^{II} and driving forces \mathcal{H}_I, \mathcal{H}_{II}, coupled through a unified combined damage scalar d = 1 - (1-d_I)(1-d_{II}).

## 2. Mathematical Formulation

**mmc_fracture_strain_triaxiality_lode**
$$
\epsilon_f(\eta, \theta, \dot{\epsilon}^p) = b \left[ A c_2 \left( c_3 + \frac{\sqrt{3}}{2-\sqrt{3}}(1-c_3)\left[\sec\left(\frac{\theta \pi}{6}\right)-1\right] \right) \left( 1 + c_2 \frac{\sqrt{3}}{3} \cos\left(\frac{\theta \pi}{6}\right) + c_1 \left[\eta + \frac{1}{3}\sin\left(\frac{\theta \pi}{6}\right)\right] \right) \right]^{-1/n}
$$
_Source: Li et al. (2025), Phase field fracture in elastoplastic solids: a stress-state, strain-rate, and orientation dependent model_

**loading_history_damage_indicator**
$$
D(\epsilon^p) = \int_0^{\epsilon^p} \frac{d\epsilon^p}{\epsilon_f(\eta, \theta, \dot{\epsilon}^p)}, \quad \text{with crack initiation triggered at } D=1
$$
_Source: Li et al. (2025), Phase field fracture in elastoplastic solids; Bai and Wierzbicki (2008), A new model of metal plasticity and fracture_

**double_phase_field_coupled_governing_equations**
$$
\eta_I \dot{d}_I = 2 b_I^2 \Delta d_I - (1-d_{II}) \omega_I'(d) \mathcal{H}_I - \alpha_I'(d_I), \quad \eta_{II} \dot{d}_{II} = 2 b_{II}^2 \Delta d_{II} - (1-d_I) \omega_{II}'(d) \mathcal{H}_{II} - \alpha_{II}'(d_{II})
$$
_Source: Zhang et al. (2023), Phase-field modeling of coupled spall and adiabatic shear banding and simulation of complex cracks in ductile metals_

**shear_modified_gtn_degradation_coupling**
$$
g(d, D_s, f) = (1-d)^{(a_1 + a_2 D_s + a_3 f)}, \quad \dot{D}_s = \psi(\theta, T^*) \frac{n D_s^{(n-1)/n}}{\epsilon_f^s} \dot{\epsilon}_q^m
$$
_Source: Tao et al. (2022), Phase-field modeling of 3D fracture in elasto-plastic solids based on the shear-modified GTN model_

**Notation:**
d, d_I, d_{II}: scalar phase-field damage variables; \eta, T^*: stress triaxiality (\eta = -p/q); \theta: normalized Lode angle parameter; \epsilon^p, \epsilon_q^m: equivalent plastic strain; \epsilon_f: fracture strain; D: damage indicator; D_s: shear damage; f: void volume fraction; \psi_{vol}^+, \psi_{vol}^-: positive and negative volumetric strain energy densities; \psi_{dev}: deviatoric strain energy density (including plastic work); \mathcal{H}_I, \mathcal{H}_{II}: historical damage driving energy fields; G_f^I, G_f^{II}: critical fracture energies for tensile and shear modes; b_I, b_{II}, l_c: regularization length scale parameters.


## 3. Algorithmic Implementation

**explicit-dynamics-stress-state-ductile-pf**
$$
\begin{algorithmic}
\State $Initialize displacement \mathbf{u}_0, velocity \dot{\mathbf{u}}_0, plastic strain \epsilon_0^p, damage indicator D_0 = 0, and phase field d_0 = 0.$
\For{$Loop over explicit time steps n = 0, 1, 2, \dots, N_{steps}.$}
\State $Compute trial stress state \tilde{\boldsymbol{\sigma}}_{n+1}^{trial} using corotational hypoelastic-plastic predictor.$
\State $Evaluate current stress triaxiality \eta_{n+1} = -p/q and Lode angle parameter \theta_{n+1}.$
\State $Calculate failure strain \epsilon_f(\eta_{n+1}, \theta_{n+1}, \dot{\epsilon}^p) from MMC criterion and update damage indicator: D_{n+1} = D_n + \Delta \epsilon^p / \epsilon_f.$
\If{$D_{n+1} \ge 1 (Damage initiation threshold reached).$}
\State $Compute history driving field \mathcal{H}_{n+1} = \max(\mathcal{H}_n, \bar{Y}_{n+1}) incorporating deviatoric plastic work and elastic strain energy.$
\State $Update phase field d_{n+1} explicitly by solving: \varpi \dot{d} = (1-d)\mathcal{H}_{n+1} - (d - l_c^2 \Delta d).$
\EndIf
\State $Degrade Cauchy stress tensor: \boldsymbol{\sigma}_{n+1} = (1 - d_{n+1})^2 \tilde{\boldsymbol{\sigma}}_{n+1} and update nodal accelerations \ddot{\mathbf{u}}_{n+1} = \mathbf{M}^{-1} (\mathbf{F}_{ext} - \mathbf{F}_{int}).$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Li et al. (2025), Phase field fracture in elastoplastic solids: a stress-state, strain-rate, and orientation dependent model_

**coupled-double-phase-field-solver**
$$
\begin{algorithmic}
\State $Initialize nodal displacements \mathbf{u}_0, tensile phase field d_{I,0} = 0, shear phase field d_{II,0} = 0, and combined damage d_0 = 0.$
\For{$Loop over time increments n = 0, 1, \dots, N_{steps}.$}
\State $Decompose undamaged strain energy into tensile volumetric \psi_{vol}^+, compressive volumetric \psi_{vol}^-, and plastic/elastic deviatoric \psi_{dev}.$
\State $Update tensile driving force \mathcal{H}_I = \frac{2 b_I}{G_f^I} \max_{\tau \le t} \psi_{vol}^+ and shear driving force \mathcal{H}_{II} = \frac{2 b_{II}}{G_f^{II}} \max_{\tau \le t} \psi_{dev}.$
\State $Solve coupled phase-field sub-problem for d_{I,n+1}: \eta_I \dot{d}_I - 2 b_I^2 \Delta d_I = -(1-d_{II,n}) \omega_I'(d_n) \mathcal{H}_I - \alpha_I'(d_{I,n}).$
\State $Solve coupled phase-field sub-problem for d_{II,n+1}: \eta_{II} \dot{d}_{II} - 2 b_{II}^2 \Delta d_{II} = -(1-d_{I,n+1}) \omega_{II}'(d_n) \mathcal{H}_{II} - \alpha_{II}'(d_{II,n}).$
\State $Compute updated combined damage: d_{n+1} = 1 - (1-d_{I,n+1})(1-d_{II,n+1}).$
\State $Evaluate degraded Cauchy stress: \boldsymbol{\sigma}_{n+1} = -\omega_I(d) H(-p) p \mathbf{I} - H(p) p \mathbf{I} + \omega_{II}(d) \mathbf{s}.$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Zhang et al. (2023), Phase-field modeling of coupled spall and adiabatic shear banding and simulation of complex cracks in ductile metals_


## 4. Known Pitfalls

- **shear-driven-fracture-locking-under-compression**: In shear-dominated or mixed-mode ductile fracture under heavy hydrostatic compression, standard unsplit or purely volumetric energy degradation methods cause non-physical volumetric locking and artificial damage suppression. Properly decoupling tensile volumetric and deviatoric strain energy components—and degrading deviatoric and tensile volumetric stresses while keeping compressive pressure undegraded—is required to accurately predict shear band and mixed-mode crack trajectories. _(Source: Zhang et al. (2023), Phase-field modeling of coupled spall and adiabatic shear banding; Molnar et al. (2020), An open-source Abaqus implementation of the phase-field method; Zhang et al. (2022), Assessment of four strain energy decomposition methods)_
- **neglecting-lode-angle-in-low-triaxiality-shear-fracture**: Relying solely on stress triaxiality \eta = -p/q to drive ductile fracture fails in low or negative triaxiality regimes (e.g., simple shear or compression-shear). Omitting the Lode angle parameter \theta leads to severe underestimation of shear damage initiation and incorrect predictions of mixed-mode crack deflection angles. _(Source: Li et al. (2025), Phase field fracture in elastoplastic solids; Bai and Wierzbicki (2008), A new model of metal plasticity and fracture)_
- **unphysical-early-damage-accumulation-prior-to-plastic-yield**: Using standard quadratic degradation functions g(d) = (1-d)^2 without an explicit plastic work or strain-state threshold (such as MMC D=1 or critical plastic strain \alpha_c) causes the phase field d to evolve prematurely during early elastic deformation, artificially lowering the macroscopic yield stress. _(Source: Borden et al. (2016), A phase-field formulation for fracture in ductile materials; Miehe et al. (2015), Phase field modeling of fracture in multi-physics problems. Part II; Li et al. (2025), Phase field fracture in elastoplastic solids)_

## References

- Li, C., Liu, J., Dong, L., Wu, C., Steven, G., Li, Q., and Fang, J. (2025). Phase field fracture in elastoplastic solids: a stress-state, strain-rate, and orientation dependent model in explicit dynamics and its applications to additively manufactured metals. Journal of the Mechanics and Physics of Solids, 197, 105978.
- Zhang, H., Peng, H., Pei, X.-Y., Wu, J.-Y., Li, P., Tang, T.-G., Cai, L.-C., Li, Y., and Liu, H. (2023). Phase-field modeling of coupled spall and adiabatic shear banding and simulation of complex cracks in ductile metals. Journal of the Mechanics and Physics of Solids, 172, 105186.
- Tao, Z., Li, X., Tao, S., and Chen, Z. (2022). Phase-field modeling of 3D fracture in elasto-plastic solids based on the modified GTN theory and Abaqus subroutines UEL/UMAT. Engineering Fracture Mechanics, 260, 108196.
- Borden, M. J., Hughes, T. J. R., Landis, C. M., Anvari, A., and Lee, I. J. (2016). A phase-field formulation for fracture in ductile materials: Finite deformation balance law derivation, plastic degradation, and stress triaxiality effects. Computer Methods in Applied Mechanics and Engineering, 312, 130-166.
- Miehe, C., Hofacker, M., Schänzel, L.-M., and Aldakheel, F. (2015). Phase field modeling of fracture in multi-physics problems. Part II. Coupled brittle-to-ductile failure criteria and crack propagation in thermo-elastic-plastic solids. Computer Methods in Applied Mechanics and Engineering, 294, 486-522.
- Zhang, H., Pei, X.-Y., Peng, H., and Wu, J.-Y. (2021). Phase-field modeling of spontaneous shear bands in collapsing thick-walled cylinders. Engineering Fracture Mechanics, 249, 107706.
- Zhang, Z., et al. (2022). Assessment of four strain energy decomposition methods for phase field fracture models. Materials Theory, 6, 6.
